"""014 teacher-reviewed rule hints and targeted practice on existing plans."""
from datetime import date
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy.orm import Session
from utils.database import get_db
from utils.deps import get_current_user
from models.user import User
from models.classroom import StudentRoster,Class
from models.identity_relations import Student
from models.learning_advice import EvidenceSnapshot,TierSuggestion,SuggestionDecision,PracticeRecommendation
from models.assignment_plan import AssignmentPlan,AssignmentPlanQuestion
from app.v1.learning import _require_teacher,_teacher_subject_class
from services.learning_advice import collect_evidence,store_snapshot,current_level,rule_proposal,invalidate,digest,DisabledModelAdapter,guard_practice_plan
from services.learning import change_student_tier
from services.question_bank_provider import question_bank_provider
from schemas.assignment_plan import AssignmentPlanCreate

router=APIRouter(prefix='/learning-advice',tags=['014 学科建议与专项训练'])

def scope(db,user,class_id,subject,ids=None):
    _require_teacher(db,user);_teacher_subject_class(db,user,class_id,subject)
    rows=db.query(StudentRoster).join(Student,Student.id==StudentRoster.student_id).filter(
        StudentRoster.class_id==class_id,StudentRoster.status=='active',Student.status=='active').all()
    students={r.student_id:r for r in rows}
    if ids is not None and (not ids or len(set(ids))!=len(ids) or not set(ids)<=set(students)):
        raise HTTPException(404,'学生不属于当前班级有效名册')
    return students

def advice_access(db,user,suggestion_id):
    row=db.query(TierSuggestion).filter_by(id=suggestion_id).with_for_update().first()
    if row is None:raise HTTPException(404,'建议不存在')
    scope(db,user,row.class_id,row.subject,[row.student_id])
    return row

def suggestion_payload(db,row,context=None):
    snap=context['snapshots'][row.snapshot_id] if context else db.get(EvidenceSnapshot,row.snapshot_id)
    history=context['decisions'].get(row.id,[]) if context else db.query(SuggestionDecision).filter_by(suggestion_id=row.id).order_by(SuggestionDecision.id).all()
    level=context['levels'].get(row.student_id) if context else current_level(db,row.student_id,row.class_id,row.subject)
    return {'id':row.id,'student_id':row.student_id,'subject':row.subject,'status':row.status,'current_level':level,
        'base_level':row.base_level or None,'revision':row.revision,'proposed_level':row.proposed_level,'snapshot_id':snap.id,'evidence_hash':snap.evidence_hash,
        'evidence':snap.evidence_json,'rationale':row.rationale_json,
        'history':[{'action':d.action,'from_level':d.from_level,'to_level':d.to_level,'reason':d.reason,'actor_id':d.actor_id,'at':str(d.created_at),'tier_audit_id':d.tier_audit_id} for d in history]}

@router.get('/classes/{class_id}/{subject}')
def overview(class_id:int,subject:str,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    students=scope(db,user,class_id,subject)
    evidence=collect_evidence(db,class_id,subject,list(students))
    suggestions=db.query(TierSuggestion).filter_by(class_id=class_id,subject=subject).order_by(TierSuggestion.id.desc()).all()
    snapshots={s.id:s for s in db.query(EvidenceSnapshot).filter(EvidenceSnapshot.id.in_([s.snapshot_id for s in suggestions])).all()}
    for row in suggestions:
        if row.student_id in evidence and snapshots[row.snapshot_id].evidence_hash!=evidence[row.student_id][1]:row.status='STALE'
    db.flush()
    from models.learning import StudentSubjectTier
    from collections import defaultdict
    levels={t.student_id:t.level for t in db.query(StudentSubjectTier).filter_by(class_id=class_id,subject=subject).all()}
    decisions=defaultdict(list)
    for d in db.query(SuggestionDecision).filter(SuggestionDecision.suggestion_id.in_([s.id for s in suggestions])).order_by(SuggestionDecision.id).all():decisions[d.suggestion_id].append(d)
    context={'levels':levels,'snapshots':snapshots,'decisions':decisions}
    practices=db.query(PracticeRecommendation).filter_by(class_id=class_id,subject=subject,teacher_id=user.id).order_by(PracticeRecommendation.id.desc()).limit(100).all()
    plans={p.id:p for p in db.query(AssignmentPlan).filter(AssignmentPlan.id.in_([p.plan_id for p in practices if p.plan_id])).all()}
    plan_rows=defaultdict(list)
    for q in db.query(AssignmentPlanQuestion).filter(AssignmentPlanQuestion.plan_id.in_(list(plans))).order_by(AssignmentPlanQuestion.level,AssignmentPlanQuestion.sort_order).all():plan_rows[q.plan_id].append(q)
    result={'model':DisabledModelAdapter().propose({}),'students':[{'student_id':sid,'name':r.student_name,'current_level':levels.get(sid),
        'summary':evidence[sid][0],'suggestions':[suggestion_payload(db,s,context) for s in suggestions if s.student_id==sid][:10]} for sid,r in students.items()],
        'practices':[practice_payload(db,p,plans,plan_rows) for p in practices]}
    db.commit();return result

class GenerateBody(BaseModel):
    student_ids:list[int]=Field(min_length=1,max_length=100)

@router.post('/classes/{class_id}/{subject}/suggestions')
def generate_suggestions(class_id:int,subject:str,body:GenerateBody,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    scope(db,user,class_id,subject,body.student_ids)
    evidence=collect_evidence(db,class_id,subject,body.student_ids);result=[]
    for sid in sorted(body.student_ids):
        db.query(Student).filter_by(id=sid).with_for_update().one()
        payload,hash_value=evidence[sid];snap=store_snapshot(db,payload,hash_value,user.id)
        level=current_level(db,sid,class_id,subject)
        old=db.query(TierSuggestion).filter_by(student_id=sid,class_id=class_id,subject=subject).all()
        for item in old:
            if not invalidate(db,item,hash_value) and item.base_level!=(level or '') and item.status in {'REVIEW_PENDING','NEEDS_MORE_EVIDENCE'}:item.status='SUPERSEDED'
        row=db.query(TierSuggestion).filter_by(snapshot_id=snap.id,base_level=level or '').order_by(TierSuggestion.revision.desc()).first()
        if row is None or row.status in {'STALE','SUPERSEDED','REJECTED'}:
            proposal=rule_proposal(payload,level)
            revision=row.revision+1 if row else 1
            row=TierSuggestion(snapshot_id=snap.id,student_id=sid,class_id=class_id,subject=subject,base_level=level or '',revision=revision,proposed_level=proposal['proposed_level'],
                status='REVIEW_PENDING' if payload['sufficient'] else 'NEEDS_MORE_EVIDENCE',rationale_json=proposal)
            db.add(row);db.flush()
        result.append(row)
    db.commit();return {'suggestions':[suggestion_payload(db,r) for r in result]}

class DecisionBody(BaseModel):
    action:Literal['ACCEPT','REJECT','ADJUST']
    target_level:Literal['L1','L2','L3']|None=None
    expected_level:Literal['L1','L2','L3']|None=None
    reason:str=Field(min_length=1,max_length=1000)
    request_key:str=Field(min_length=8,max_length=64)

@router.post('/suggestions/{suggestion_id}/decision')
def decide(suggestion_id:int,body:DecisionBody,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    row=advice_access(db,user,suggestion_id)
    db.query(Student).filter_by(id=row.student_id).with_for_update().one()
    previous=db.query(SuggestionDecision).filter_by(suggestion_id=row.id,request_key=body.request_key).first()
    if previous:
        if previous.action!=body.action or previous.reason!=body.reason or (body.target_level is not None and previous.to_level!=body.target_level):
            raise HTTPException(409,'幂等键已用于其他决定')
        return suggestion_payload(db,row)
    from services.learning_advice import lock_evidence_scope
    lock_evidence_scope(db,row.class_id,row.subject,[row.student_id])
    live=collect_evidence(db,row.class_id,row.subject,[row.student_id])[row.student_id]
    if invalidate(db,row,live[1]):
        db.commit();raise HTTPException(409,'STALE：证据已变化，须重新生成审阅')
    old=current_level(db,row.student_id,row.class_id,row.subject)
    if old!=body.expected_level:raise HTTPException(409,'档位已被其他操作调整，请刷新')
    if row.status in {'REVIEW_PENDING','NEEDS_MORE_EVIDENCE'} and row.base_level!=(old or ''):
        row.status='SUPERSEDED';db.commit();raise HTTPException(409,'建议基于旧档位，须重新生成')
    if row.status in {'STALE','SUPERSEDED','REJECTED'}:raise HTTPException(409,'建议不可再应用，请重新生成或使用原手动分层入口')
    if body.action=='REJECT':
        if row.status=='ACCEPTED':raise HTTPException(409,'已生效建议需明确手动调整并保留审计，不可用拒绝隐式撤销')
        row.status='REJECTED';target=old;audit=None
    else:
        if not live[0]['sufficient']:raise HTTPException(409,'EVIDENCE_INSUFFICIENT；建议不能生效，仍可使用012手动分层')
        if body.action=='ACCEPT' and row.status=='ACCEPTED':raise HTTPException(409,'已接受，重复操作请使用原幂等键；再次调整请选择ADJUST')
        target=body.target_level or row.proposed_level
        if target is None:raise HTTPException(422,'请选择档位')
        audit=change_student_tier(db,student_id=row.student_id,class_id=row.class_id,subject=row.subject,level=target,actor_id=user.id)
        row.status='ACCEPTED'
    db.add(SuggestionDecision(suggestion_id=row.id,request_key=body.request_key,action=body.action,from_level=old,to_level=target,
             reason=body.reason,actor_id=user.id,tier_audit_id=audit.id if audit else None))
    db.commit();return suggestion_payload(db,row)

class PracticeBody(BaseModel):
    student_ids:list[int]=Field(min_length=1,max_length=100)
    count:int=Field(default=1,ge=1,le=20)
    difficulty:Literal['easy','medium','hard','mixed']='mixed'
    question_type:str|None=None
    selected_asset_ids:list[int]|None=Field(default=None,max_length=60)
    request_key:str=Field(min_length=8,max_length=64)

def practice_payload(db,row,plans=None,rows=None):
    plan=(plans.get(row.plan_id) if plans is not None else db.get(AssignmentPlan,row.plan_id)) if row.plan_id else None
    from app.v1.assignment_plans import _plan_payload
    return {'id':row.id,'status':row.status,'student_ids':row.target_student_ids,'snapshot_ids':row.snapshot_ids,'knowledge_points':row.knowledge_points,
            'assignment_id':row.assignment_id,'model_status':'MODEL_NOT_RUN','plan':_plan_payload(db,plan,rows=rows.get(plan.id,[]) if rows is not None else None) if plan else None}

def candidate_assets(db,subject,grade,points,originals,texts,difficulty,question_type,teacher_id=None):
    candidates=question_bank_provider.search_questions(db,subject=subject,grade=grade,limit=200,teacher_id=teacher_id)
    return [a for a in candidates if a.review_status=='CONFIRMED' and a.id not in originals and ' '.join((a.question_text or '').split()).casefold() not in texts
        and set(a.knowledge_points_json or []) & points and a.difficulty in {'easy','medium','hard'}
        and (difficulty=='mixed' or a.difficulty==difficulty) and (not question_type or a.question_type==question_type)]

@router.post('/classes/{class_id}/{subject}/practices')
def create_practice(class_id:int,subject:str,body:PracticeBody,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    scope(db,user,class_id,subject,body.student_ids)
    # Per-teacher row lock serializes duplicate draft requests.
    db.query(User).filter_by(id=user.id).with_for_update().one()
    request_hash=digest({'class_id':class_id,'subject':subject,**body.model_dump()})
    existing=db.query(PracticeRecommendation).filter_by(teacher_id=user.id,request_key=body.request_key).first()
    if existing:
        if existing.request_hash!=request_hash:raise HTTPException(409,'幂等键与训练请求冲突')
        if existing.plan_id is not None:return practice_payload(db,existing)
    evidence=collect_evidence(db,class_id,subject,body.student_ids)
    points=set();originals=set();texts=set();snaps=[]
    for sid,(payload,hash_value) in evidence.items():
        weak={p for p,v in payload['knowledge_points'].items() if v['wrong']>0}
        if not weak:raise HTTPException(409,'当前目标学生无教师确认的薄弱知识点/错题，不凭空创建专项')
        points.update(weak);originals.update(r['asset_id'] for r in payload['sources']);texts.update(' '.join((r['question_text'] or '').split()).casefold() for r in payload['sources'])
        # A partially reviewed V2 paper still owns ALL original questions.
        # Unreviewed questions cannot sneak back in as "new" practice items.
        from services.teacher_v2 import publication_for
        for assignment_id in {r['assignment_id'] for r in payload['sources'] if r['assignment_id']}:
            pub=publication_for(db,assignment_id)
            if pub:
                originals.update(q['asset_id'] for q in pub.snapshot['questions'])
                texts.update(' '.join(q['question_text'].split()).casefold() for q in pub.snapshot['questions'])
        snaps.append(store_snapshot(db,payload,hash_value,user.id))
    classroom=db.get(Class,class_id)
    assets=candidate_assets(db,subject,classroom.grade,points,originals,texts,body.difficulty,body.question_type,user.id)
    if body.selected_asset_ids is not None:
        if len(set(body.selected_asset_ids))!=len(body.selected_asset_ids) or not set(body.selected_asset_ids)<={a.id for a in assets}:
            raise HTTPException(422,'所选题含原题、未审核题、错科或不满足知识点/难度/题型范围')
        by_id={a.id:a for a in assets};assets=[by_id[i] for i in body.selected_asset_ids]
    # 013 three variants stay distinct; no fake clones of the same question.
    if len(assets)<3*body.count:
        raise HTTPException(409,detail={'code':'QUESTION_BANK_INSUFFICIENT','available':len(assets),'required':3*body.count,'message':'题库不足，需教师补充合法且已审核的非原题'})
    assets=assets[:3*body.count]
    from app.v1.assignment_plans import create_assignment_plan
    request=AssignmentPlanCreate(idempotency_key='014-'+digest({'key':body.request_key})[:60],class_id=class_id,title='专项训练',description='请完成老师确认的本次练习。',subject=subject,
        grade=classroom.grade,assignment_date=date.today(),target_knowledge_points=sorted(points),question_types=[body.question_type] if body.question_type else [],
        question_count_per_tier=body.count,difficulty=body.difficulty,tier_strategy={level:'教师审阅后指定练习内容' for level in ('L1','L2','L3')},
        variants=[{'level':level,'questions':[{'source_asset_id':a.id,'max_score':10} for a in assets[index*body.count:(index+1)*body.count]]} for index,level in enumerate(('L1','L2','L3'))])
    # Reserve target scope BEFORE the existing 013 writer commits. A crash may
    # leave a BUILDING draft, never an untargeted published assignment. A replay
    # recovers the same 013 idempotent plan and attaches it.
    recommendation=existing or PracticeRecommendation(teacher_id=user.id,class_id=class_id,subject=subject,target_student_ids=sorted(body.student_ids),snapshot_ids=[s.id for s in snaps],
        knowledge_points=sorted(points),request_key=body.request_key,request_hash=request_hash,status='BUILDING')
    if existing is None:db.add(recommendation)
    db.flush()
    db.info['014_practice_reservation_id']=recommendation.id
    try:
        plan=create_assignment_plan(request,db,user).data
    finally:
        db.info.pop('014_practice_reservation_id',None)
    recommendation.plan_id=plan['id'];recommendation.status='DRAFT'
    db.commit();return practice_payload(db,recommendation)

def practice_access(db,user,practice_id):
    row=db.query(PracticeRecommendation).filter_by(id=practice_id,teacher_id=user.id).with_for_update().first()
    if row is None:raise HTTPException(404,'专项训练不存在')
    scope(db,user,row.class_id,row.subject,row.target_student_ids)
    return row

class ReplaceQuestionsBody(BaseModel):
    asset_ids:list[int]=Field(min_length=3,max_length=60)

@router.put('/practices/{practice_id}/questions')
def replace_questions(practice_id:int,body:ReplaceQuestionsBody,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    row=practice_access(db,user,practice_id)
    plan=db.get(AssignmentPlan,row.plan_id)
    if row.status!='DRAFT' or plan.status!='DRAFT':raise HTTPException(409,'只有未确认专项草稿可以换题')
    guard_practice_plan(db,plan)
    snapshots=db.query(EvidenceSnapshot).filter(EvidenceSnapshot.id.in_(row.snapshot_ids)).all()
    originals={r['asset_id'] for s in snapshots for r in s.evidence_json['sources']}
    texts={' '.join((r['question_text'] or '').split()).casefold() for s in snapshots for r in s.evidence_json['sources']}
    available={a.id:a for a in candidate_assets(db,plan.subject,plan.grade,set(row.knowledge_points),originals,texts,plan.difficulty,None,user.id)}
    if len(body.asset_ids)!=plan.requested_question_count*3 or len(set(body.asset_ids))!=len(body.asset_ids) or not set(body.asset_ids)<=set(available) or any(plan.question_types_json and available[i].question_type not in plan.question_types_json for i in body.asset_ids if i in available):
        raise HTTPException(422,'选题数量不齐，或包含重复原题、未审核或不满足学科知识点的题')
    from app.v1.assignment_plans import _replace_questions,_asset_snapshot
    n=plan.requested_question_count
    _replace_questions(db,plan,[(level,j+1,10,_asset_snapshot(available[asset_id])) for i,level in enumerate(('L1','L2','L3')) for j,asset_id in enumerate(body.asset_ids[i*n:(i+1)*n])])
    db.commit();return practice_payload(db,row)

class ConfirmBody(BaseModel):
    confirmed:Literal[True]

@router.post('/practices/{practice_id}/confirm')
def confirm_practice(practice_id:int,body:ConfirmBody,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    row=practice_access(db,user,practice_id)
    if row.status=='PUBLISHED':return practice_payload(db,row)
    plan=db.get(AssignmentPlan,row.plan_id);guard_practice_plan(db,plan)
    from app.v1.assignment_plans import confirm_assignment_plan
    confirm_assignment_plan(plan.id,db,user)
    row.status='CONFIRMED';db.commit();return practice_payload(db,row)

@router.post('/practices/{practice_id}/publish')
def publish_practice(practice_id:int,body:ConfirmBody,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    row=practice_access(db,user,practice_id)
    from app.v1.assignment_plans import publish_assignment_plan
    publish_assignment_plan(row.plan_id,db,user)
    db.refresh(row);return practice_payload(db,row)

@router.get('/practices/{practice_id}/feedback')
def practice_feedback(practice_id:int,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    row=practice_access(db,user,practice_id)
    evidence=collect_evidence(db,row.class_id,row.subject,row.target_student_ids)
    return {'practice_id':row.id,'assignment_id':row.assignment_id,'students':[{'student_id':sid,'confirmed_practice_results':[r for r in payload['sources'] if r['assignment_id']==row.assignment_id],
         'updated_subject_evidence':payload} for sid,(payload,_) in evidence.items()]}

@router.post('/classes/{class_id}/{subject}/ai-proposal')
def ai_disabled(class_id:int,subject:str,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    scope(db,user,class_id,subject)
    raise HTTPException(409,detail=DisabledModelAdapter().propose({}))

@router.get('/classes/{class_id}/{subject}/review-candidates')
def review_candidates(class_id:int,subject:str,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    students=scope(db,user,class_id,subject)
    from models.homework import GradingResult,HomeworkTask
    from models.paper import QuestionAssetSource,QuestionAsset
    rows=db.query(GradingResult,HomeworkTask,QuestionAssetSource,QuestionAsset).join(HomeworkTask,HomeworkTask.task_id==GradingResult.task_id).join(
        QuestionAssetSource,QuestionAssetSource.grading_result_id==GradingResult.id).join(QuestionAsset,QuestionAsset.id==QuestionAssetSource.question_asset_id).filter(
        HomeworkTask.class_id==class_id,HomeworkTask.subject==subject,HomeworkTask.student_id.in_(list(students)),HomeworkTask.status=='SUCCESS',
        HomeworkTask.grading_mode!='known',QuestionAssetSource.review_status=='CONFIRMED',QuestionAsset.review_status=='CONFIRMED').order_by(GradingResult.id.desc()).limit(200).all()
    return {'items':[{'grade_id':g.id,'task_id':t.task_id,'student_id':t.student_id,'source_id':s.id,'question_text':a.question_text,'score':float(g.score),
        'max_score':float(g.max_score),'result':g.result,'answer':a.correct_answer,'reviewed':g.is_reviewed,
        'version':digest({'score':str(g.score),'result':g.result,'key':a.correct_answer,'asset_updated':str(a.updated_at),'grade_updated':str(g.updated_at)})} for g,t,s,a in rows]}

class EvidenceReviewBody(BaseModel):
    confirmed:bool
    expected_version:str=Field(min_length=64,max_length=64)
    reason:str=Field(min_length=1,max_length=1000)
    request_key:str=Field(min_length=8,max_length=64)

@router.post('/grades/{grade_id}/evidence-review')
def review_grade_evidence(grade_id:int,body:EvidenceReviewBody,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    from datetime import datetime,timezone
    from models.homework import GradingResult,HomeworkTask
    from models.paper import QuestionAssetSource,QuestionAsset
    g=db.query(GradingResult).filter_by(id=grade_id).with_for_update().first()
    if g is None:raise HTTPException(404,'成绩不存在')
    task=db.query(HomeworkTask).filter_by(task_id=g.task_id).one()
    scope(db,user,task.class_id,task.subject,[task.student_id])
    if task.grading_mode=='known':raise HTTPException(409,'括号候选只能通过013_V01原人工复核入口确认，不能绕过HOLD_REVIEW')
    source=db.query(QuestionAssetSource).filter_by(grading_result_id=g.id,source_task_id=task.task_id).first()
    asset=db.get(QuestionAsset,source.question_asset_id) if source else None
    if source is None or asset is None:raise HTTPException(409,'请先通过011完成原题来源关联与审核')
    raw=dict(g.raw_response or {});history=list(raw.get('014_evidence_reviews',[]))
    old=next((h for h in history if h['request_key']==body.request_key),None)
    if old:
        if old['confirmed']!=body.confirmed or old['reason']!=body.reason:raise HTTPException(409,'复核幂等键冲突')
        return {'grade_id':g.id,'reviewed':g.is_reviewed,'idempotent':True}
    version=digest({'score':str(g.score),'result':g.result,'key':asset.correct_answer,'asset_updated':str(asset.updated_at),'grade_updated':str(g.updated_at)})
    if version!=body.expected_version:raise HTTPException(409,'题目或评分已变化，请刷新后核对')
    if body.confirmed:
        if task.status!='SUCCESS' or source.review_status!='CONFIRMED' or source.link_status!='CONFIRMED' or asset.review_status!='CONFIRMED' or asset.subject!=task.subject or asset.grade!=task.grade:
            raise HTTPException(409,'任务/来源/题目尚未可信确认')
        score,max_score=float(g.score),float(g.max_score)
        expected='correct' if score==max_score else 'wrong' if score==0 else 'partial'
        if not 0<=score<=max_score or max_score<=0 or g.result!=expected or not asset.correct_answer or (asset.correct_answer or '').strip().casefold()!=(g.correct_answer or '').strip().casefold():
            raise HTTPException(409,'已有评分与标准答案或评分状态不一致，请先回原批改/题目入口核对')
    history.append({'request_key':body.request_key,'confirmed':body.confirmed,'reason':body.reason,'actor_id':user.id,'at':datetime.now(timezone.utc).isoformat(),'score':str(g.score)})
    raw['014_evidence_reviews']=history;g.raw_response=raw;g.is_reviewed=body.confirmed
    if body.confirmed:g.reviewed_score=g.score;g.reviewer_id=user.id
    db.commit();return {'grade_id':g.id,'reviewed':g.is_reviewed}
