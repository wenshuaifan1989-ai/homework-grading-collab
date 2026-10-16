"""014 transparent teacher-reviewed evidence; no network/LLM execution."""
import hashlib
import json
from collections import defaultdict
from typing import Protocol
from sqlalchemy import and_,or_
from models.teacher_v2 import AssignmentPublication
from models.homework import HomeworkTask,GradingResult
from models.paper import QuestionAsset,QuestionAssetSource,MistakeRecord,PaperCorrectionAttempt
from models.known_assignment import ChoiceRead,KnownPageMatch
from models.learning import StudentSubjectTier
from models.learning_advice import EvidenceSnapshot,TierSuggestion,PracticeRecommendation

POLICY={'version':'014-pilot-v1','min_tasks':2,'min_unique_questions':6,'min_knowledge_points':2,
        'description':'保守试点门槛，非科研能力刻度；只提供教师审阅线索，不自动变档'}

class SuggestionAdapter(Protocol):
    def propose(self,evidence:dict)->dict: ...

class DisabledModelAdapter:
    def propose(self,evidence):
        return {'status':'MODEL_NOT_RUN','enabled':False,'daily_limit':0,'request_sent':False}

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()

def lock_evidence_scope(db,class_id,subject,student_ids):
    """Keep existing source revocations/regrades from racing an approval.

    MySQL row locks are held until the caller's decision/publish transaction
    commits. SQLite unit tests alone cannot demonstrate these locks.
    """
    tasks=db.query(HomeworkTask).filter(HomeworkTask.class_id==class_id,HomeworkTask.subject==subject,
        HomeworkTask.student_id.in_(student_ids)).order_by(HomeworkTask.id).with_for_update().all()
    ids=[t.task_id for t in tasks]
    grades=db.query(GradingResult).filter(GradingResult.task_id.in_(ids)).order_by(GradingResult.id).with_for_update().all()
    sources=db.query(QuestionAssetSource).filter(QuestionAssetSource.source_task_id.in_(ids)).all()
    db.query(QuestionAsset).filter(QuestionAsset.id.in_([s.question_asset_id for s in sources])).order_by(QuestionAsset.id).with_for_update().all()
    db.query(QuestionAssetSource).filter(QuestionAssetSource.id.in_([s.id for s in sources])).order_by(QuestionAssetSource.id).with_for_update().all()

def collect_evidence(db,class_id,subject,student_ids):
    """One scoped join + bounded bulk context reads; excludes untrusted states."""
    rows=db.query(GradingResult,HomeworkTask,QuestionAssetSource,QuestionAsset,ChoiceRead,KnownPageMatch).join(
        HomeworkTask,HomeworkTask.task_id==GradingResult.task_id).join(
        QuestionAssetSource,QuestionAssetSource.grading_result_id==GradingResult.id).join(
        QuestionAsset,QuestionAsset.id==QuestionAssetSource.question_asset_id).outerjoin(
        ChoiceRead,ChoiceRead.grading_result_id==GradingResult.id).outerjoin(
        KnownPageMatch,KnownPageMatch.id==ChoiceRead.page_match_id).filter(
        HomeworkTask.class_id==class_id,HomeworkTask.subject==subject,HomeworkTask.student_id.in_(student_ids),
        or_(HomeworkTask.status=='SUCCESS',and_(HomeworkTask.status=='WAIT_REVIEW',
            HomeworkTask.assignment_id.in_(db.query(AssignmentPublication.assignment_id)))),
        GradingResult.is_reviewed.is_(True),GradingResult.reviewer_id.is_not(None),
        QuestionAssetSource.source_task_id==HomeworkTask.task_id,
        QuestionAssetSource.review_status=='CONFIRMED',QuestionAssetSource.link_status=='CONFIRMED',
        QuestionAssetSource.reviewed_by.is_not(None),QuestionAssetSource.reviewed_at.is_not(None),
        QuestionAsset.review_status=='CONFIRMED',QuestionAsset.subject==subject,QuestionAsset.grade==HomeworkTask.grade).all()
    from models.user import User
    from models.user_role import UserRole
    teacher_ids={r[0] for r in db.query(User.id).filter(User.role=='teacher').all()}
    teacher_ids.update(r[0] for r in db.query(UserRole.user_id).filter_by(role_code='teacher',status='active').all())
    pubs={p.assignment_id:p for p in db.query(AssignmentPublication).filter(
        AssignmentPublication.assignment_id.in_({task.assignment_id for _,task,_,_,_,_ in rows if task.assignment_id}))}
    from fastapi import HTTPException
    for pub in pubs.values():
        if digest(pub.snapshot)!=pub.snapshot_sha256:
            raise HTTPException(409,'发布快照完整性校验失败，已停止使用')
    from models.known_assignment import QuestionPlacement
    placements={p.id:p for p in db.query(QuestionPlacement).filter(QuestionPlacement.id.in_(
        {read.placement_id for _,task,_,_,read,_ in rows if read and task.assignment_id in pubs}))} if pubs else {}
    raw=defaultdict(list)
    for grade,task,source,asset,read,match in rows:
        pub=pubs.get(task.assignment_id)
        frozen=next((q for q in pub.snapshot['questions'] if q['number']==grade.question_no
                     and q['asset_id']==asset.id),None) if pub else None
        if pub and not frozen:
            continue
        if pub and task.grading_mode=='known':
            placement=placements.get(read.placement_id) if read else None
            if not placement or placement.variant_question_id!=frozen['variant_question_id']:
                continue
        attrs=frozen['attributes'] if frozen else {'difficulty':asset.difficulty,
            'knowledge_points':asset.knowledge_points_json,'question_type':asset.question_type}
        canonical_key=frozen['correct_answer'] if frozen else asset.correct_answer
        if grade.reviewer_id not in teacher_ids or source.reviewed_by not in teacher_ids:
            continue
        if task.grading_mode=='known' and (not read or read.status!='CONFIRMED' or read.reviewed_by!=grade.reviewer_id or not match or match.status!='MATCHED'):
            continue
        score=float(grade.reviewed_score if grade.reviewed_score is not None else grade.score)
        max_score=float(grade.max_score)
        if max_score<=0 or not 0<=score<=max_score or grade.result not in {'correct','partial','wrong'}:
            continue
        expected_outcome='correct' if score==max_score else 'wrong' if score==0 else 'partial'
        if grade.result!=expected_outcome:
            continue
        if not (canonical_key or '').strip() or (canonical_key or '').strip().casefold()!=(grade.correct_answer or '').strip().casefold():
            continue
        if not attrs['knowledge_points'] or attrs['difficulty'] not in {'easy','medium','hard'}:
            continue
        raw[task.student_id].append({'grade_id':grade.id,'task_id':task.task_id,'assignment_id':task.assignment_id,
            'asset_id':asset.id,'source_id':source.id,'question_no':grade.question_no,'question_text':frozen['question_text'] if frozen else asset.question_text,
            'subject':subject,'grade':asset.grade,'score':score,'max_score':max_score,'outcome':grade.result,
            'difficulty':attrs['difficulty'],'question_type':attrs.get('question_type'),'knowledge_points':sorted(set(attrs['knowledge_points'])),
            'key':canonical_key,'options':frozen['options'] if frozen else asset.options_json,'reviewer_id':grade.reviewer_id,'source_reviewer_id':source.reviewed_by,
            'confirmed_at':str(source.reviewed_at),'grade_updated_at':str(grade.updated_at),'asset_updated_at':str(asset.updated_at),
            'known_read_id':read.id if read else None,'read_reviewed_at':str(read.reviewed_at) if read else None,
            'teacher_review_history_hash':digest((grade.raw_response or {}).get('014_evidence_reviews',[]))})
    mistakes=db.query(MistakeRecord).filter(MistakeRecord.student_id.in_(student_ids)).all()
    mistake_by_grade={m.source_grading_result_id:m for m in mistakes}
    corrections=db.query(PaperCorrectionAttempt).filter(PaperCorrectionAttempt.mistake_id.in_([m.id for m in mistakes]),
           PaperCorrectionAttempt.reviewed_by.is_not(None),PaperCorrectionAttempt.reviewed_at.is_not(None)).order_by(PaperCorrectionAttempt.id).all() if mistakes else []
    contexts=defaultdict(list)
    for c in corrections:
        if c.reviewed_by in teacher_ids:
            contexts[c.mistake_id].append({'id':c.id,'status':c.status,'reviewed_by':c.reviewed_by,'reviewed_at':str(c.reviewed_at)})
    output={}
    for student_id in student_ids:
        # A repeat submission/correction of the same canonical asset is not an
        # independent ability sample. Most recent teacher-confirmed grade wins.
        unique={}
        for item in sorted(raw[student_id],key=lambda r:(r['confirmed_at'],r['grade_updated_at'],r['grade_id'])):
            identity=digest({'text':' '.join((item['question_text'] or '').split()).casefold(),'options':item['options'],'key':item['key']})
            unique[identity]=item
        evidence=sorted(unique.values(),key=lambda r:r['asset_id'])
        kp=defaultdict(lambda:{'questions':0,'wrong':0,'by_difficulty':{}})
        for item in evidence:
            m=mistake_by_grade.get(item['grade_id'])
            item['mistake']={'id':m.id,'status':m.status,'corrections':contexts[m.id]} if m else None
            for point in item['knowledge_points']:
                part=kp[point];part['questions']+=1;part['wrong']+=int(item['outcome']=='wrong')
                diff=part['by_difficulty'].setdefault(item['difficulty'],{'questions':0,'score_fraction_sum':0})
                diff['questions']+=1;diff['score_fraction_sum']+=item['score']/item['max_score']
        payload={'version':'014-confirmed-evidence-v1','class_id':class_id,'student_id':student_id,'subject':subject,
                 'policy':POLICY,'sources':evidence,'task_count':len({r['assignment_id'] or r['task_id'] for r in evidence}),
                 'unique_question_count':len(evidence),'knowledge_points':dict(sorted(kp.items())),
                 'trust':'TEACHER_CONFIRMED_ONLY','corrections_are_independent_samples':False}
        payload['sufficient']=payload['task_count']>=POLICY['min_tasks'] and len(evidence)>=POLICY['min_unique_questions'] and len(kp)>=POLICY['min_knowledge_points']
        payload['evidence_status']='SUFFICIENT_FOR_TEACHER_REVIEW' if payload['sufficient'] else 'EVIDENCE_INSUFFICIENT'
        output[student_id]=(payload,digest(payload))
    return output

def store_snapshot(db,payload,hash_value,actor):
    snap=db.query(EvidenceSnapshot).filter_by(student_id=payload['student_id'],class_id=payload['class_id'],subject=payload['subject'],evidence_hash=hash_value).first()
    if snap is None:
        snap=EvidenceSnapshot(student_id=payload['student_id'],class_id=payload['class_id'],subject=payload['subject'],evidence_hash=hash_value,evidence_json=payload,created_by=actor)
        db.add(snap);db.flush()
    return snap

def current_level(db,student_id,class_id,subject):
    tier=db.query(StudentSubjectTier).filter_by(student_id=student_id,class_id=class_id,subject=subject).first()
    return tier.level if tier else None

def rule_proposal(payload,level):
    weak=[k for k,v in payload['knowledge_points'].items() if v['wrong']>0]
    # No scalar "ability score": difficulty-stratified conservative hints only.
    easy=[r for r in payload['sources'] if r['difficulty']=='easy']
    hard=[r for r in payload['sources'] if r['difficulty']=='hard']
    target=level
    reason='保留当前档位；请结合逐题、难度与知识点证据审阅。'
    if not payload['sufficient']:
        target=None;reason='EVIDENCE_INSUFFICIENT：独立作业/原题数/知识点覆盖不足，不推断能力。'
    elif level and len(easy)>=4 and sum(r['outcome']=='wrong' for r in easy)>=3:
        target={'L1':'L1','L2':'L1','L3':'L2'}[level];reason='多道已确认基础难度题存在错误，建议教师检查是否调整；这不是能力诊断。'
    elif level and len(hard)>=4 and all(r['outcome']=='correct' for r in hard):
        target={'L1':'L2','L2':'L3','L3':'L3'}[level];reason='多道已确认挑战难度题作答正确，建议教师审阅是否增加挑战；不与其他版本粗正确率比较。'
    return {'proposed_level':target,'weak_knowledge_points':weak,'reason':reason,'kind':'RULE_ASSISTED','model_status':'MODEL_NOT_RUN','policy':POLICY}

def invalidate(db,suggestion,live_hash):
    snapshot=db.get(EvidenceSnapshot,suggestion.snapshot_id)
    if snapshot.evidence_hash!=live_hash:
        suggestion.status='STALE'
        return True
    return False

def practice_for_assignment(db,assignment_id):
    return db.query(PracticeRecommendation).filter_by(assignment_id=assignment_id).first()

def can_receive_practice(practice,student_id):
    return practice is None or (practice.status=='PUBLISHED' and student_id in practice.target_student_ids)

def guard_practice_plan(db,plan,*,publishing=False):
    practice=db.query(PracticeRecommendation).filter_by(plan_id=plan.id).first()
    if practice is None:return None
    from fastapi import HTTPException
    from models.assignment_plan import AssignmentPlanQuestion
    if plan.class_id!=practice.class_id or plan.subject!=practice.subject:
        raise HTTPException(409,'专项训练范围已变更，请重新生成')
    if publishing and practice.status not in {'CONFIRMED','PUBLISHED'}:
        raise HTTPException(409,'专项训练必须在建议页核验目标学生并明确确认后发布')
    if publishing and any(current_level(db,sid,plan.class_id,plan.subject) is None for sid in practice.target_student_ids):
        raise HTTPException(409,'目标学生存在未设定的学科档位，请先通过原012手动入口设置；不自动分档')
    lock_evidence_scope(db,practice.class_id,practice.subject,practice.target_student_ids)
    live=collect_evidence(db,practice.class_id,practice.subject,practice.target_student_ids)
    snapshots=db.query(EvidenceSnapshot).filter(EvidenceSnapshot.id.in_(practice.snapshot_ids)).all()
    originals={r['asset_id'] for snap in snapshots for r in snap.evidence_json['sources']}
    original_texts={' '.join((r['question_text'] or '').split()).casefold() for snap in snapshots for r in snap.evidence_json['sources']}
    for snap in snapshots:
        if live[snap.student_id][1]!=snap.evidence_hash:
            raise HTTPException(409,'学情已改判或新增，请刷新证据并重新创建专项训练')
    for row in db.query(AssignmentPlanQuestion).filter_by(plan_id=plan.id).all():
        asset=db.get(QuestionAsset,row.source_asset_id)
        if not asset or asset.review_status!='CONFIRMED' or asset.id in originals or ' '.join((asset.question_text or '').split()).casefold() in original_texts:
            raise HTTPException(409,'专项训练含未审核题或原题，请重新选题')
        from app.v1.assignment_plans import _asset_snapshot
        current=_asset_snapshot(asset)
        expected=row.question_snapshot_json
        if any(current[k]!=expected[k] for k in current if k!='review_status_at_selection'):
            raise HTTPException(409,'专项训练题目/答案/来源已变更，请重新核对')
    return practice
