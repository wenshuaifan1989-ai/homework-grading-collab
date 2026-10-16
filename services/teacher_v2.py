"""V2 reuses original class, assets, variants, submission and review services."""
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy.orm import Session
from models.classroom import Assignment, StudentRoster
from models.learning import AssignmentVariant, AssignmentVariantSet, AssignmentVariantQuestion
from models.paper import QuestionAsset
from models.teacher_v2 import PaperBatch, PaperDocument, AssignmentPublication
from schemas.teacher_v2 import Attributes, Publish
from services.identity_relations import user_has_role


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), default=str).encode()).hexdigest()


def teacher(db, user):
    if not user_has_role(db, user, 'teacher'):
        raise HTTPException(403, '只有教师可以管理套卷')


def owned_paper(db, user, paper_id, lock=False):
    teacher(db, user)
    query = db.query(PaperDocument).filter_by(id=paper_id, teacher_id=user.id)
    paper = (query.with_for_update() if lock else query).first()
    if not paper:
        raise HTTPException(404, '套卷不存在')
    return paper


def inherited_attributes(batch, paper, item, asset):
    result = {'subject': asset.subject, 'grade': asset.grade, 'difficulty': asset.difficulty,
              'knowledge_points': asset.knowledge_points_json or [], 'question_type': asset.question_type}
    provenance = {key: 'asset' for key in result}
    for level, values in [('batch', batch), ('paper', paper), ('question', item)]:
        Attributes.model_validate(values)
        for key, value in values.items():
            result[key] = deepcopy(value)
            provenance[key] = level
    return result, provenance


def question_snapshots(db, paper):
    batch = db.get(PaperBatch, paper.batch_id)
    output = []
    for item in paper.questions:
        asset = db.get(QuestionAsset, item['asset_id'])
        if not asset or asset.review_status != 'CONFIRMED' or asset.rights_basis not in {
            'PROJECT_AUTHORED', 'OPEN_LICENSE', 'TEACHER_AUTHORIZED'
        } or not asset.rights_reference:
            raise HTTPException(409, '存在未审核或来源不明的题目，请先补齐答案与审核')
        if asset.source == 'teacher_v2' and not asset.rights_reference.startswith(f'teacher:{paper.teacher_id}:'):
            raise HTTPException(404, '题目不存在')
        attrs, provenance = inherited_attributes(batch.attributes, paper.attributes, item.get('overrides', {}), asset)
        if attrs.get('subject') != asset.subject or attrs.get('grade') != asset.grade:
            raise HTTPException(409, '继承后的学科年级与题目不符')
        if not asset.question_text or not asset.correct_answer or not asset.analysis:
            raise HTTPException(409, '题干、答案和解析须由教师确认')
        if attrs.get('difficulty') not in ('easy', 'medium', 'hard') or not attrs.get('knowledge_points'):
            raise HTTPException(409, '请补齐难度及知识点；难度与必做选做无关')
        output.append({'asset_id': asset.id, 'number': item['number'], 'max_score': item['max_score'],
                       'question_text': asset.question_text, 'options': asset.options_json,
                       'correct_answer': asset.correct_answer, 'analysis': asset.analysis,
                       'attributes': attrs, 'attribute_sources': provenance,
                       'rights_basis': asset.rights_basis, 'rights_reference': asset.rights_reference})
    if not output:
        raise HTTPException(409, '尚未关联可审核题目；仅上传原卷不代表自动识题成功')
    if len({q['number'] for q in output}) != len(output) or len({q['asset_id'] for q in output}) != len(output):
        raise HTTPException(409, '题号或题目资产重复')
    if len({(q['attributes']['subject'], q['attributes']['grade']) for q in output}) != 1:
        raise HTTPException(409, '一份套卷须属于同一学科与年级')
    return output


def publication_for(db, assignment_id):
    pub = db.query(AssignmentPublication).filter_by(assignment_id=assignment_id).first()
    if pub and digest(pub.snapshot) != pub.snapshot_sha256:
        raise HTTPException(409, '发布快照完整性校验失败，已停止使用')
    return pub


def publish(db: Session, user, paper, body: Publish):
    from app.v1.assignment_plans import _teacher_subject_class
    teacher(db, user)
    from models.user import User
    db.query(User).filter_by(id=user.id).with_for_update().one()
    fingerprint = digest({'paper_id': paper.id, **body.model_dump(mode='json')})
    existing = db.query(AssignmentPublication).filter_by(teacher_id=user.id, request_key=body.request_key).first()
    if existing:
        if existing.request_hash != fingerprint:
            raise HTTPException(409, '发布幂等键已用于不同内容')
        return existing
    if paper.revision != body.expected_revision:
        raise HTTPException(409, '套卷已被修改，请刷新后确认')
    questions = question_snapshots(db, paper)
    subject, grade = questions[0]['attributes']['subject'], questions[0]['attributes']['grade']
    classroom = _teacher_subject_class(db, user, body.class_id, subject)
    if classroom.status != 'active' or classroom.grade and classroom.grade != grade:
        raise HTTPException(409, '班级状态或年级不符')
    if not Path(paper.source_locator).is_file() or hashlib.sha256(Path(paper.source_locator).read_bytes()).hexdigest() != paper.source_sha256:
        raise HTTPException(409, '原卷不存在或哈希变化，禁止发布')
    roster = db.query(StudentRoster).filter_by(class_id=body.class_id, status='active').all()
    if not roster or any(r.student_id is None for r in roster):
        raise HTTPException(409, '请先补齐班级学生名册实体（可未绑定登录账号）')
    requirements = {str(r.student_id): {q['number']: {'requirement': body.default_requirement,
                      'basis': 'teacher_default', 'reason': '教师统一默认策略'} for q in questions} for r in roster}
    for rule in body.requirements:
        if str(rule.student_id) not in requirements or rule.number not in requirements[str(rule.student_id)]:
            raise HTTPException(422, '要求超出本班学生或本套卷题号')
        requirements[str(rule.student_id)][rule.number] = {'requirement': rule.requirement,
                           'basis': 'teacher_override', 'reason': rule.reason}
    assignment = Assignment(class_id=body.class_id, teacher_id=user.id, title=body.title,
        subject=subject, grade=grade, assignment_date=body.assignment_date, due_at=body.due_at, status='published')
    db.add(assignment); db.flush()
    # Single original variant for transport compatibility, not three differentiated papers.
    variant = AssignmentVariant(assignment_id=assignment.id, level='L1', version=1,
                                is_current=True, updated_by=user.id)
    db.add(variant); db.flush()
    db.add(AssignmentVariantSet(assignment_id=assignment.id, allow_uniform_fallback=True,
                                fallback_level='L1', updated_by=user.id))
    for q in questions:
        row = AssignmentVariantQuestion(variant_id=variant.id, source_type='ASSET', source_asset_id=q['asset_id'],
              sort_order=len([x for x in questions if 'variant_question_id' in x])+1,
              question_text=q['question_text'], options_json=q['options'], correct_answer=q['correct_answer'],
              analysis=q['analysis'], max_score=q['max_score'])
        db.add(row); db.flush(); q['variant_question_id'] = row.id
    snapshot = {'mode': 'uniform_mixed', 'version': 1, 'class_id': body.class_id, 'subject': subject,
        'grade': grade, 'assignment_date': str(body.assignment_date), 'due_at': str(body.due_at) if body.due_at else None,
        'source_sha256': paper.source_sha256, 'source_name': paper.source_name, 'paper_revision': paper.revision,
        'questions': questions, 'requirements': requirements, 'teacher_confirmed_by': user.id,
        'policy': {'version': 'V2-001-v1', 'unconfirmed': 'excluded', 'optional_unanswered': 'not_wrong'}}
    pub = AssignmentPublication(assignment_id=assignment.id, paper_id=paper.id, teacher_id=user.id,
        variant_id=variant.id, request_key=body.request_key, request_hash=fingerprint,
        snapshot=snapshot, snapshot_sha256=digest(snapshot), mode='uniform_mixed')
    db.add(pub); db.flush()
    return pub


def student_fields(pub, student_id):
    rules = pub.snapshot['requirements'].get(str(student_id))
    if rules is None:
        return {'variant_mode': True, 'variant_available': False, 'variant_questions': [],
                'variant_message': '本次发布未包含当前学生，请联系老师。'}
    return {'variant_mode': True, 'variant_available': True, 'assignment_mode': 'uniform_mixed',
        'original_format':Path(pub.snapshot['source_name']).suffix.lower().lstrip('.'),
        'variant_questions': [{'id': q['variant_question_id'], 'number': q['number'],
          'question_text': q['question_text'], 'options': [f'{k}. {v}' for k,v in q['options'].items()]
              if isinstance(q['options'], dict) else q['options'], 'max_score': q['max_score'],
          'requirement': rules[q['number']]['requirement'],
          'requirement_label': '必做' if rules[q['number']]['requirement']=='required' else '选做'}
          for q in pub.snapshot['questions']], 'variant_message': None}


def optional_unanswered(db, task, number, symbol):
    pub = publication_for(db, task.assignment_id) if task.assignment_id else None
    return bool(pub and symbol == 'BLANK' and pub.snapshot['requirements'].get(str(task.student_id), {})
                .get(str(number), {}).get('requirement') == 'optional')
