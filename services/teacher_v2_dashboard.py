"""Per-publication trusted denominators. No submission-rate ability inference."""
from collections import defaultdict
from datetime import datetime, timezone
from models.classroom import StudentRoster
from models.homework import HomeworkTask, GradingResult, OCRResult
from models.paper import QuestionAssetSource
from models.known_assignment import ChoiceRead, KnownPageMatch, QuestionPlacement
from models.user import User
from models.user_role import UserRole
from services.teacher_v2 import publication_for


def build_dashboard(db, assignment):
    pub = publication_for(db, assignment.id)
    if not pub:
        from services.dashboard_service import build_daily_dashboard
        from models.classroom import Class
        return {'mode':'legacy','title':assignment.title,'legacy_dashboard':build_daily_dashboard(
            db,db.get(Class,assignment.class_id),assignment.assignment_date,assignment.id),
            'notice':'历史作业未记录必做/选做快照，不回填或混排'}
    snap=pub.snapshot; cohort=set(map(int,snap['requirements']));questions=snap['questions']
    by_number={q['number']:q for q in questions}
    roster={r.student_id:r for r in db.query(StudentRoster).filter(StudentRoster.class_id==assignment.class_id)}
    tasks=db.query(HomeworkTask).filter_by(assignment_id=assignment.id,class_id=assignment.class_id).order_by(
        HomeworkTask.created_at.desc(),HomeworkTask.id.desc()).all()
    latest={}
    for t in tasks:
        if t.student_id in cohort:latest.setdefault(t.student_id,t)
    teacher_ids={u[0] for u in db.query(User.id).filter(User.role=='teacher')}
    teacher_ids.update(u[0] for u in db.query(UserRole.user_id).filter_by(role_code='teacher',status='active'))
    rows=db.query(GradingResult,HomeworkTask,QuestionAssetSource).join(
        HomeworkTask,HomeworkTask.task_id==GradingResult.task_id).join(
        QuestionAssetSource,QuestionAssetSource.grading_result_id==GradingResult.id).filter(
        HomeworkTask.assignment_id==assignment.id,HomeworkTask.class_id==assignment.class_id,
        HomeworkTask.student_id.in_(cohort),HomeworkTask.status.in_(['SUCCESS','WAIT_REVIEW']),
        GradingResult.is_reviewed.is_(True),GradingResult.reviewer_id.is_not(None),
        QuestionAssetSource.source_task_id==HomeworkTask.task_id,
        QuestionAssetSource.review_status=='CONFIRMED',QuestionAssetSource.link_status=='CONFIRMED').order_by(
        HomeworkTask.created_at.desc(),GradingResult.id.desc()).all()
    valid={}
    for grade,task,source in rows:
        if latest.get(task.student_id) is not task:
            continue
        q=by_number.get(grade.question_no)
        if not q or source.question_asset_id!=q['asset_id'] or grade.reviewer_id not in teacher_ids or source.reviewed_by not in teacher_ids or not source.reviewed_at:
            continue
        if grade.correct_answer!=q['correct_answer'] or float(grade.max_score)!=q['max_score']:continue
        score=float(grade.reviewed_score if grade.reviewed_score is not None else grade.score)
        if not 0<=score<=q['max_score']:continue
        outcome='correct' if score==q['max_score'] else 'wrong' if score==0 else 'partial'
        if grade.result!=outcome:continue
        answer=db.query(OCRResult.student_answer).filter_by(question_block_id=grade.question_block_id).scalar()
        blank=not answer or str(answer).strip().upper()=='BLANK'
        if task.grading_mode=='known':
            read=db.query(ChoiceRead).filter_by(grading_result_id=grade.id,status='CONFIRMED').first()
            if not read or read.reviewed_by!=grade.reviewer_id:continue
            match=db.get(KnownPageMatch,read.page_match_id);placement=db.get(QuestionPlacement,read.placement_id)
            if not match or match.status!='MATCHED' or not placement or placement.variant_question_id!=q['variant_question_id']:continue
            blank=read.symbol=='BLANK'
        rule=snap['requirements'][str(task.student_id)][q['number']]['requirement']
        if rule=='optional' and blank:continue
        valid.setdefault((task.student_id,q['number']),{'grade_id':grade.id,'task_id':task.task_id,
            'outcome':outcome,'answered':not blank,'source_id':source.id,'student_id':task.student_id})
    qstats=[];kp=defaultdict(lambda:{'wrong':0,'partial':0,'valid':0,'students':set(),'questions':set()})
    for q in questions:
        answers=[v for (sid,no),v in valid.items() if no==q['number']]
        wrong=[v for v in answers if v['outcome']=='wrong'];partial=[v for v in answers if v['outcome']=='partial']
        qstats.append({**q,'snapshot_question_id':q['variant_question_id'],'valid_count':len(answers),
            'wrong_count':len(wrong),'partial_count':len(partial),
            'wrong_rate':len(wrong)/len(answers) if answers else None,'answers':answers})
        for point in set(q['attributes']['knowledge_points']):
            item=kp[point];item['valid']+=len(answers);item['wrong']+=len(wrong);item['partial']+=len(partial)
            item['students'].update(v['student_id'] for v in answers);item['questions'].add(q['variant_question_id'])
    students=[];now=datetime.now(timezone.utc).replace(tzinfo=None)
    for sid in sorted(cohort):
        rules=snap['requirements'][str(sid)];required=[no for no,r in rules.items() if r['requirement']=='required']
        optional=[no for no,r in rules.items() if r['requirement']=='optional'];t=latest.get(sid)
        r=roster.get(sid)
        done=sum(bool(valid.get((sid,no),{}).get('answered')) for no in required)
        participating=sum(bool(valid.get((sid,no),{}).get('answered')) for no in optional)
        overdue=bool(assignment.due_at and ((t.created_at if t else now)>assignment.due_at))
        students.append({'student_id':sid,'name':r.student_name if r else f'历史学生{sid}',
            'bound':bool(r and r.bound_user_id),'task_id':t.task_id if t else None,'status':t.status if t else 'UNSUBMITTED',
            'overdue':overdue,'required_count':len(required),'required_done':done,
            'required_completion':done/len(required) if required else None,
            'optional_count':len(optional),'optional_done':participating,
            'optional_participation':participating/len(optional) if optional else None})
    return {'mode':'uniform_mixed','assignment_id':assignment.id,'title':assignment.title,
        'snapshot_sha256':pub.snapshot_sha256,'questions':qstats,'students':students,
        'knowledge_points':[{'id':key,'wrong_count':v['wrong'],'partial_count':v['partial'],'valid_count':v['valid'],
           'wrong_rate':v['wrong']/v['valid'] if v['valid'] else None,'student_ids':sorted(v['students']),
           'attributed_questions':len(v['questions'])} for key,v in kp.items()],
        'counts':{'expected':len(cohort),'submitted':len(latest),'unsubmitted':len(cohort)-len(latest),
            'overdue':sum(s['overdue'] for s in students),'graded':sum(s['status']=='SUCCESS' for s in students),
            'waiting_review':sum(s['status']=='WAIT_REVIEW' for s in students),
            'processing':sum(s['status'] in ('PENDING','PROCESSING','GRADING') for s in students),
            'exceptions':sum(s['status'] in ('FAILED','UNKNOWN_LAYOUT') for s in students)},
        'exceptions':[{'task_id':t.task_id,'student_id':t.student_id,'status':t.status} for t in latest.values()
                      if t.status in ('FAILED','UNKNOWN_LAYOUT','WAIT_REVIEW')],
        'notice':'错误率只按同一发布题目的可信判分计算；部分正确独立显示；无可靠样本显示空值。不同必做范围不排名。'}
