"""Teacher-only template mapping/review; all images require normal authentication."""
import hashlib
import uuid
from pathlib import Path
from typing import Literal
import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from utils.database import get_db
from utils.deps import get_current_user
from models.user import User
from models.homework import HomeworkTask, HomeworkImage
from models.learning import AssignmentVariant
from models.known_assignment import PageTemplate, QuestionPlacement, KnownPageMatch, ChoiceRead, ChoiceReviewAudit
from app.v1.learning import _require_teacher, _assignment_for_teacher
from services.known_assignment_templates import generate, questions, fingerprint, rasterize_pdf, store, valid_box, inside
from services.known_page_vision import load_image, png, LocalStrokeReader, teacher_registration
from services.known_assignment_grading import apply_review, template_candidates, read_page, refresh_status

router=APIRouter(prefix='/known-assignments',tags=['013 known bracket'])


def variant_access(db,user,variant_id):
    _require_teacher(db,user)
    variant=db.get(AssignmentVariant,variant_id)
    if not variant:
        raise HTTPException(404,'作业版本不存在')
    assignment=_assignment_for_teacher(db,user,variant.assignment_id)
    return assignment,variant


def page_access(db,user,page_id):
    page=db.get(PageTemplate,page_id)
    if not page:
        raise HTTPException(404,'页面不存在')
    variant_access(db,user,page.variant_id)
    return page


def task_access(db,user,task_id):
    _require_teacher(db,user)
    task=db.query(HomeworkTask).filter_by(task_id=task_id).first()
    if not task or not task.assignment_id:
        raise HTTPException(404,'任务不存在')
    _assignment_for_teacher(db,user,task.assignment_id)
    return task


def page_data(db,page):
    return {'id':page.id,'page_index':page.page_index,'page_uid':page.page_uid,'width':page.width,'height':page.height,
            'source':page.source,'status':page.status,'export_version':page.export_version,'has_pdf':bool(page.pdf_locator),'image_sha256':page.image_sha256,
            'placements':[{'variant_question_id':p.variant_question_id,'question_number':p.question_number,
              'stem_bbox':p.stem_bbox,'answer_bracket_bbox':p.answer_bracket_bbox,'options_bbox':p.options_bbox,
              'question_bbox':p.question_bbox,'choice_kind':p.choice_kind,'id':p.id} for p in db.query(QuestionPlacement).filter_by(page_template_id=page.id).all()]}


@router.get('/assignments/{assignment_id}')
def overview(assignment_id:int,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    _require_teacher(db,user);_assignment_for_teacher(db,user,assignment_id)
    from services.teacher_v2 import publication_for
    pub=publication_for(db,assignment_id)
    numbers={q['variant_question_id']:q['number'] for q in pub.snapshot['questions']} if pub else {}
    variants=db.query(AssignmentVariant).filter_by(assignment_id=assignment_id,is_current=True).all()
    return {'variants':[{'id':v.id,'level':v.level,'questions':[{'id':q.id,'number':numbers.get(q.id,i+1),'text':q.question_text,'answer':q.correct_answer} for i,q in enumerate(questions(db,v.id))],
                        'pages':[page_data(db,p) for p in db.query(PageTemplate).filter_by(variant_id=v.id).order_by(PageTemplate.export_version.desc(),PageTemplate.page_index).all()]} for v in variants],
            'tasks':[{'task_id':t.task_id,'status':t.status,'student_id':t.student_id} for t in db.query(HomeworkTask).filter_by(assignment_id=assignment_id,grading_mode='known').order_by(HomeworkTask.id.desc()).limit(100).all()]}


@router.post('/variants/{variant_id}/generate')
def generate_template(variant_id:int,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    assignment,variant=variant_access(db,user,variant_id)
    from services.teacher_v2 import publication_for
    if publication_for(db,assignment.id):
        raise HTTPException(409,'统一原卷模式不得重新生成并替换原卷，请上传同一份原文件标定')
    # Do not replace a mapped teacher-uploaded paper implicitly.
    if db.query(PageTemplate).filter_by(variant_id=variant.id,status='ACTIVE',source='uploaded').first():
        raise HTTPException(409,'已有上传卷模板；请保留使用，不可隐式替换')
    try:
        pages=generate(db,assignment,variant,user.id)
        return {'pages':[page_data(db,p) for p in pages]}
    except ValueError as e:
        raise HTTPException(409,str(e))


@router.get('/pages/{page_id}/file')
def template_file(page_id:int,kind:Literal['image','pdf']='image',db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    page=page_access(db,user,page_id)
    locator=page.pdf_locator if kind=='pdf' else page.image_locator
    if not locator or not Path(locator).is_file():
        raise HTTPException(404,'文件不存在')
    return FileResponse(locator,media_type='application/pdf' if kind=='pdf' else 'image/png',filename='known-paper.pdf' if kind=='pdf' else None)


@router.post('/variants/{variant_id}/upload')
async def upload_template(variant_id:int,file:UploadFile=File(...),db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    assignment,variant=variant_access(db,user,variant_id)
    data=await file.read(20*1024*1024+1)
    if len(data)>20*1024*1024:
        raise HTTPException(413,'模板文件最多20MB')
    from services.teacher_v2 import publication_for
    pub=publication_for(db,assignment.id)
    if pub and hashlib.sha256(data).hexdigest()!=pub.snapshot['source_sha256']:
        raise HTTPException(409,'模板必须是发布快照中同一份原卷，文件哈希不符')
    try:
        pdf=data.startswith(b'%PDF-')
        if pdf:
            images=rasterize_pdf(data)
        else:
            image=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_GRAYSCALE)
            if image is None or image.size>30_000_000:
                raise ValueError('图片无效或超过30MP')
            images=[image]
        previous=db.query(PageTemplate).filter_by(variant_id=variant_id).all()
        version=max([p.export_version for p in previous] or [0])+1
        pdf_path=store(data,'.pdf') if pdf else None
        pages=[]
        for idx,image in enumerate(images):
            encoded=png(image)
            printed_uid,_,_=cv2.QRCodeDetector().detectAndDecode(image)
            existing_marker=db.query(PageTemplate).filter_by(page_uid=printed_uid).first() if printed_uid else None
            if printed_uid and len(printed_uid)>40:
                raise ValueError('上传卷页标过长')
            if existing_marker:
                if not pub or existing_marker.image_sha256!=hashlib.sha256(encoded).hexdigest():
                    raise ValueError('上传卷页标已登记且非同一受控原页，禁止替换')
                # Keep the actual original pixels unchanged. The new opaque marker
                # intentionally does NOT pretend automatic QR registration passed;
                # existing FOREIGN_PAGE_MARKER refusal requires explicit teacher mapping.
                printed_uid=''
            page=PageTemplate(assignment_id=assignment.id,variant_id=variant.id,page_index=idx,page_uid=printed_uid or uuid.uuid4().hex,
              export_version=version,width=image.shape[1],height=image.shape[0],image_locator=store(encoded),
              image_sha256=hashlib.sha256(encoded).hexdigest(),pdf_locator=pdf_path,variant_fingerprint=fingerprint(questions(db,variant.id)),
              source='uploaded',status='DRAFT',created_by=user.id)
            db.add(page);pages.append(page)
        db.commit()
        return {'pages':[page_data(db,p) for p in pages]}
    except (ValueError,cv2.error) as e:
        raise HTTPException(422,str(e))


class PlacementBody(BaseModel):
    variant_question_id:int
    question_number:str=Field(min_length=1,max_length=20)
    stem_bbox:list[int]
    answer_bracket_bbox:list[int]
    options_bbox:list[int]
    question_bbox:list[int]
    choice_kind:Literal['single','multi']='single'


class MappingBody(BaseModel):
    placements:list[PlacementBody]=Field(min_length=1,max_length=100)
    blank_reference_confirmed:Literal[True]


@router.put('/pages/{page_id}/mapping')
def mapping(page_id:int,body:MappingBody,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    page=page_access(db,user,page_id)
    if page.status!='DRAFT':
        raise HTTPException(409,'已激活模板不可原地改坐标；请重新上传新版本后标定')
    allowed={q.id:q for q in questions(db,page.variant_id)}
    seen=set();items=[]
    try:
        for p in body.placements:
            if p.variant_question_id not in allowed or p.variant_question_id in seen:
                raise ValueError('题目不属于该版本或重复映射')
            seen.add(p.variant_question_id)
            item=p.model_dump()
            for name in ['stem_bbox','answer_bracket_bbox','options_bbox','question_bbox']:
                item[name]=valid_box(item[name],page.width,page.height)
            if not inside(item['answer_bracket_bbox'],item['stem_bbox']) or not inside(item['stem_bbox'],item['question_bbox']) or not inside(item['options_bbox'],item['question_bbox']):
                raise ValueError('括号须在题干内，题干和选项须在题目范围内')
            if item['answer_bracket_bbox'][3]>item['options_bbox'][1]:
                raise ValueError('题干括号须位于四个印刷选项之前，不得重叠')
            item['question_asset_id']=allowed[p.variant_question_id].source_asset_id
            items.append(item)
    except ValueError as e:
        raise HTTPException(422,str(e))
    db.query(QuestionPlacement).filter_by(page_template_id=page_id).delete()
    for item in items:
        db.add(QuestionPlacement(page_template_id=page_id,**item))
    db.commit()
    return page_data(db,page)


@router.post('/pages/{page_id}/activate-set')
def activate(page_id:int,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    page=page_access(db,user,page_id)
    if page.status!='DRAFT':
        raise HTTPException(409,'仅草稿可激活')
    # Never invalidate templates referenced by submitted tasks.
    previous=db.query(PageTemplate).filter_by(variant_id=page.variant_id,status='ACTIVE').all()
    if previous:
        from models.learning import AssignmentVariantTask
        if db.query(AssignmentVariantTask).filter_by(variant_id=page.variant_id).first():
            raise HTTPException(409,'该版本已有提交，不能替换坐标；请创建新的作业版本')
    pages=db.query(PageTemplate).filter_by(variant_id=page.variant_id,export_version=page.export_version,status='DRAFT').all()
    placements=db.query(QuestionPlacement).filter(QuestionPlacement.page_template_id.in_([p.id for p in pages])).all()
    expected={q.id for q in questions(db,page.variant_id)}
    actual=[p.variant_question_id for p in placements]
    if not expected or set(actual)!=expected or len(actual)!=len(expected):
        raise HTTPException(409,'必须完整标定全部题目，每题只能属于一页')
    if page.variant_fingerprint!=fingerprint(questions(db,page.variant_id)):
        raise HTTPException(409,'版本内容已变化，请重新上传标定')
    for p in previous:p.status='RETIRED'
    for p in pages:p.status='ACTIVE'
    db.commit();return {'status':'ACTIVE','pages':[page_data(db,p) for p in pages]}


@router.get('/tasks/{task_id}')
def review_detail(task_id:str,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    task=task_access(db,user,task_id)
    matches=db.query(KnownPageMatch).filter_by(task_id=task_id).all()
    rows=[]
    for r in db.query(ChoiceRead).filter_by(task_id=task_id).all():
        p=db.get(QuestionPlacement,r.placement_id)
        from models.learning import AssignmentVariantQuestion
        q=db.get(AssignmentVariantQuestion,p.variant_question_id)
        rows.append({'id':r.id,'match_id':r.page_match_id,'page_id':p.page_template_id,'number':p.question_number,
                     'question_text':q.question_text,'answer':q.correct_answer,'symbol':r.symbol,'status':r.status,'reason':r.reason,
                     'evidence':r.evidence_json,'bbox':p.answer_bracket_bbox,'score_metric':r.confidence})
    return {'task_id':task_id,'status':task.status,'reads':rows,'pages':[{'id':m.id,'page_id':m.page_template_id,'status':m.status,'reason':m.reason,'evidence':m.evidence_json} for m in matches],
            'allowed_pages':[page_data(db,p) for p in template_candidates(db,task)]}


@router.get('/tasks/{task_id}/images/{image_id}')
def review_image(task_id:str,image_id:int,kind:Literal['original','aligned','crop','ink']='original',db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    task_access(db,user,task_id)
    if kind in ('crop','ink'):
        row=db.query(ChoiceRead).filter_by(task_id=task_id,id=image_id).first()
        locator=(row.crop_locator if kind=='crop' else row.ink_locator) if row else None
    else:
        row=db.query(KnownPageMatch).filter_by(task_id=task_id,id=image_id).first()
        locator=(row.aligned_locator if kind=='aligned' else db.get(HomeworkImage,row.homework_image_id).original_url) if row else None
    if not locator or locator.startswith('cos://') or not Path(locator).is_file():
        raise HTTPException(404,'本地证据不存在')
    return FileResponse(locator)


class ReviewBody(BaseModel):
    symbol:str=Field(pattern=r'^(?:[ABCD]{1,4}|BLANK)$')
    note:str=Field(min_length=1,max_length=500)
    request_key:str=Field(min_length=8,max_length=64)


class TeacherQuestionRegion(BaseModel):
    placement_id:int=Field(gt=0)
    original_polygon:list[list[float]]=Field(min_length=4,max_length=4)


class TeacherRegistrationBody(BaseModel):
    page_id:int
    expected_template_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')
    original_points:list[list[float]]
    reference_points:list[list[float]]
    note:str=Field(min_length=10,max_length=500)
    request_key:str=Field(min_length=8,max_length=64)
    question_regions:list[TeacherQuestionRegion]|None=Field(default=None,min_length=1,max_length=100)


@router.post('/tasks/{task_id}/pages/{match_id}/register')
def register_unmatched(task_id:str,match_id:int,body:TeacherRegistrationBody,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    task=task_access(db,user,task_id)
    db.query(HomeworkTask).filter_by(task_id=task_id).with_for_update().one()
    match=db.query(KnownPageMatch).filter_by(task_id=task_id,id=match_id).first()
    if not match:raise HTTPException(404,'提交图片不存在')
    if match.status=='MATCHED':
        old=match.evidence_json
        if old.get('request_key')==body.request_key and old.get('registration_body')==body.model_dump():return {'status':task.status,'idempotent':True}
        raise HTTPException(409,'已匹配页不可替换，请保留原审计记录')
    allowed={p.id:p for p in template_candidates(db,task)}
    page=allowed.get(body.page_id)
    if not page or page.image_sha256!=body.expected_template_sha256:raise HTTPException(409,'模板不属于当前学生版本或hash已变化')
    if db.query(KnownPageMatch).filter_by(task_id=task_id,page_template_id=page.id,status='MATCHED').first():raise HTTPException(409,'重复页不能作为另一页提交')
    if hashlib.sha256(Path(page.image_locator).read_bytes()).hexdigest()!=page.image_sha256:raise HTTPException(409,'参考文件hash不一致')
    image=db.get(HomeworkImage,match.homework_image_id)
    original=load_image(image.original_url)
    decoded,_,_=cv2.QRCodeDetector().detectAndDecode(original)
    if decoded and decoded!=page.page_uid:raise HTTPException(409,'原图页标与所选模板不符')
    placements=db.query(QuestionPlacement).filter_by(page_template_id=page.id).all()
    try:
        if body.question_regions is not None:
            # Human cropping is NOT automatic registration. Every question keeps
            # its own real-source transform; never pretend curved paper is planar.
            regions={r.placement_id:r for r in body.question_regions}
            if len(regions)!=len(body.question_regions) or set(regions)!={p.id for p in placements}:
                raise ValueError('必须逐题核对当前参考页的全部题目，不能缺题、重题或跨页')
            aligned=np.full((page.height,page.width),255,np.uint8)
            masks=[];transforms={}
            for p in placements:
                points=np.asarray(regions[p.id].original_polygon,np.float32)
                if points.shape!=(4,2) or not np.isfinite(points).all() or (points<0).any() or (points[:,0]>=original.shape[1]).any() or (points[:,1]>=original.shape[0]).any():raise ValueError('单题原图四边形无效或越界')
                if not cv2.isContourConvex(points) or cv2.contourArea(points,oriented=True)<1000:raise ValueError('单题范围须为顺时针凸四边形')
                mask=np.zeros(original.shape,np.uint8);cv2.fillConvexPoly(mask,points.astype('int32'),1)
                if any(np.count_nonzero(mask&previous)>min(np.count_nonzero(mask),np.count_nonzero(previous))*.02 for previous in masks):raise ValueError('单题原图范围重叠，不能重复绑定同一题')
                masks.append(mask)
                x1,y1,x2,y2=p.question_bbox
                h=cv2.getPerspectiveTransform(points,np.float32([[x1,y1],[x2,y1],[x2,y2],[x1,y2]]))
                from services.known_page_vision import normalize_paper_illumination
                warped=normalize_paper_illumination(cv2.warpPerspective(original,h,(page.width,page.height),borderValue=255))
                aligned[y1:y2,x1:x2]=warped[y1:y2,x1:x2]
                transforms[str(p.id)]={'homography':h.tolist(),'original_polygon':points.tolist()}
            evidence={'method':'TEACHER_QUESTION_REGION_COMPOSITE','automatic_match':False,'composite_not_global_registration':True,'question_transforms':transforms,'homography':None}
        else:
            aligned,evidence=teacher_registration(original,load_image(page.image_locator),body.original_points,body.reference_points,placements)
    except (ValueError,cv2.error,np.linalg.LinAlgError) as e:raise HTTPException(422,str(e))
    evidence.update({'reviewer_id':user.id,'note':body.note,'request_key':body.request_key,'registration_body':body.model_dump(),
                    'template_sha256':page.image_sha256,'original_sha256':hashlib.sha256(Path(image.original_url).read_bytes()).hexdigest(),'previous_refusal':match.evidence_json})
    match.status='MATCHED';match.page_template_id=page.id;match.reason='TEACHER_REGISTERED_REQUIRES_ANSWER_REVIEW'
    match.evidence_json=evidence;match.aligned_locator=store(png(aligned))
    read_page(db,task,match,page,aligned)
    refresh_status(db,task);db.commit()
    return {'status':task.status,'automatic_match':False}


@router.post('/tasks/{task_id}/recover')
def recover_task(task_id:str,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    task_access(db,user,task_id)
    from services.known_assignment_grading import recover_known
    try:return recover_known(db,task_id)
    except ValueError as exc:raise HTTPException(409,str(exc))


@router.post('/tasks/{task_id}/reads/{read_id}/review')
def review(task_id:str,read_id:int,body:ReviewBody,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    task=task_access(db,user,task_id)
    row=db.query(ChoiceRead).filter_by(task_id=task_id,id=read_id).first()
    if not row:raise HTTPException(404,'识别项不存在')
    try:
        apply_review(db,task,row,user.id,body.symbol,body.note,body.request_key)
        return {'status':task.status,'read_status':row.status}
    except ValueError as e:
        db.rollback();raise HTTPException(409,str(e))


class RelocateBody(BaseModel):
    bbox:list[int]
    note:str=Field(min_length=1,max_length=500)
    request_key:str=Field(min_length=8,max_length=64)


@router.post('/tasks/{task_id}/reads/{read_id}/relocate')
def relocate(task_id:str,read_id:int,body:RelocateBody,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    task=task_access(db,user,task_id)
    db.query(HomeworkTask).filter_by(task_id=task_id).with_for_update().one()
    row=db.query(ChoiceRead).filter_by(task_id=task_id,id=read_id).first()
    if not row:raise HTTPException(404,'识别项不存在')
    if row.status=='CONFIRMED':raise HTTPException(409,'已确认成绩不允许重定位，请直接审计改判')
    audit=db.query(ChoiceReviewAudit).filter_by(choice_read_id=row.id,request_key=body.request_key).first()
    if audit:
        if audit.after_json.get('bbox')!=body.bbox or audit.note!=body.note:raise HTTPException(409,'幂等键冲突')
        return {'status':row.status}
    p=db.get(QuestionPlacement,row.placement_id);page=db.get(PageTemplate,p.page_template_id);match=db.get(KnownPageMatch,row.page_match_id)
    try:
        bbox=valid_box(body.bbox,page.width,page.height)
        if not inside(bbox,p.stem_bbox) or (p.options_bbox and bbox[3]>p.options_bbox[1]):raise ValueError('必须位于题干内且在选项之前')
        result,crop,ink=LocalStrokeReader().read(load_image(page.image_locator),load_image(match.aligned_locator),bbox,p.choice_kind=='multi')
    except ValueError as e:raise HTTPException(422,str(e))
    db.add(ChoiceReviewAudit(choice_read_id=row.id,request_key=body.request_key,reviewer_id=user.id,before_json={'symbol':row.symbol,'evidence':row.evidence_json},after_json={'bbox':bbox,'symbol':result['symbol']},note=body.note))
    row.symbol=result['symbol'];row.reason=result['reason'];row.evidence_json={**result,'relocated_bbox':bbox,'relocated_by':user.id};row.confidence=str(result['score'])
    row.crop_locator=store(png(crop));row.ink_locator=store(png(ink));db.commit()
    return {'status':row.status}
