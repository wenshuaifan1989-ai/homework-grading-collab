"""Teacher V2 endpoints; same API, database, assets and RBAC as 010-015."""
import hashlib
import json
import uuid
import zipfile
from io import BytesIO
from pathlib import Path
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict, Field
from config import settings
from models.classroom import Assignment, StudentRoster
from models.paper import QuestionAsset
from models.teacher_v2 import PaperBatch, PaperDocument, AssignmentPublication
from schemas.teacher_v2 import Attributes, PaperEdit, Publish
from services.teacher_v2 import teacher, owned_paper, question_snapshots, publish, publication_for, digest
from services.identity_relations import user_has_role
from utils.database import get_db
from utils.deps import get_current_user

router = APIRouter(prefix='/teacher-v2', tags=['教师V2'])
ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT/'数据/教材目录/三陶_九年级人教2024数理化_20261016/normalized_catalog.jsonl'


def payload(db, paper):
    errors = []
    try:
        resolved = question_snapshots(db, paper)
    except HTTPException as exc:
        resolved = []; errors = [exc.detail]
    return {'id': paper.id, 'batch_id': paper.batch_id, 'title': paper.title, 'revision': paper.revision,
        'source_name': paper.source_name, 'source_sha256': paper.source_sha256, 'format': paper.source_format,
        'attributes': paper.attributes, 'batch_attributes': db.get(PaperBatch, paper.batch_id).attributes,
        'questions': paper.questions, 'question_count': len(paper.questions), 'status': paper.status,
        'resolved_questions': resolved, 'exceptions': errors, 'ready': bool(resolved) and not errors,
        'parser_notice': '保留原卷。PDF/图片未启用自动识题、OCR与答案猜测；请关联已审核题目或补充确认。'}


def source_path(paper):
    path = Path(paper.source_locator).resolve()
    if not path.is_relative_to((Path(settings.UPLOAD_DIR)/'v2-papers').resolve()) or not path.is_file():
        raise HTTPException(404, '原卷不存在')
    if hashlib.sha256(path.read_bytes()).hexdigest() != paper.source_sha256:
        raise HTTPException(409, '原卷哈希不一致')
    return path


@router.get('/catalog')
def catalog(subject: str = 'math', query: str = '', db: Session = Depends(get_db), user=Depends(get_current_user)):
    teacher(db, user)
    chinese = {'math':'数学', 'physics':'物理', 'chemistry':'化学'}.get(subject)
    if not chinese or not CATALOG.is_file():
        return {'items': [], 'notice': '当前只收录人教2024九年级数理化的实际可访问目录，未补造缺失册次'}
    rows = [json.loads(line) for line in CATALOG.read_text(encoding='utf8').splitlines() if line]
    return {'items':[{'id':r['id'], 'name':r['raw_name'], 'path':r['path'], 'version':'santao-pep2024-20261016'}
        for r in rows if r['kind']=='knowledge_point' and r['subject']==chinese
        and query.casefold() in r['raw_name'].casefold()][:200],
        'notice':'目录不完整：数学九下等缺口保留待补；数据仅供受控内部使用'}


@router.get('/papers')
def list_papers(db: Session = Depends(get_db), user=Depends(get_current_user)):
    teacher(db, user)
    return {'items':[payload(db,p) for p in db.query(PaperDocument).filter_by(teacher_id=user.id)
                     .order_by(PaperDocument.id.desc()).all()]}


@router.post('/classes/{class_id}/prepare-roster')
def prepare_roster(class_id:int,db:Session=Depends(get_db),user=Depends(get_current_user)):
    from app.v1.school import _managed_class
    from models.identity_relations import Student
    teacher(db,user)
    _managed_class(db,class_id,user,owner_only=True)
    rows=db.query(StudentRoster).filter_by(class_id=class_id,status='active').order_by(StudentRoster.id).with_for_update().all()
    created=0
    for row in rows:
        if row.student_id is None:
            student=Student(name=row.student_name,status='active')
            db.add(student);db.flush();row.student_id=student.id;created+=1
    db.commit()
    return {'created':created,'notice':'只建立名册学生实体，没有创建登录账号或绑定关系'}


def validate_file(name, data):
    ext = Path(name).suffix.lower()
    try:
        if ext == '.pdf':
            if not data.startswith(b'%PDF-'): raise ValueError()
            from pypdf import PdfReader
            pdf = PdfReader(BytesIO(data))
            if pdf.is_encrypted or not 1 <= len(pdf.pages) <= 9: raise ValueError()
        elif ext in {'.png','.jpg','.jpeg'}:
            from PIL import Image
            with Image.open(BytesIO(data)) as im:
                if im.width*im.height > 40000000: raise ValueError()
                im.verify()
        elif ext == '.docx':
            with zipfile.ZipFile(BytesIO(data)) as z:
                if sum(i.file_size for i in z.infolist()) > 40000000 or 'word/document.xml' not in z.namelist():
                    raise ValueError()
        else:
            raise HTTPException(415, '支持PDF、DOCX、PNG、JPG；旧DOC与自动OCR暂不支持')
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(422, '文件损坏、加密、尺寸过大或内容与格式不符')
    return ext[1:]


@router.post('/batches')
async def upload_batch(files: list[UploadFile] = File(...), attributes: str = Form('{}'),
    rights_confirmed: bool = Form(False), request_key: str = Header(..., alias='Idempotency-Key'),
    db: Session = Depends(get_db), user=Depends(get_current_user)):
    teacher(db, user)
    if not rights_confirmed: raise HTTPException(409, '请确认有权使用所上传原卷')
    if not 8 <= len(request_key) <= 64 or not 1 <= len(files) <= 9: raise HTTPException(422, '一次选择1至9份文件，需有效幂等键')
    try: attrs=Attributes.model_validate(json.loads(attributes)).model_dump(exclude_unset=True)
    except Exception: raise HTTPException(422, '批次公共属性无效')
    contents=[]; total=0
    for f in files:
        data=await f.read(20*1024*1024+1);total+=len(data)
        if not data or len(data)>20*1024*1024 or total>60*1024*1024: raise HTTPException(413, '单份20MB，批次60MB上限')
        name=(f.filename or 'paper').replace('\\','/').split('/')[-1][:240]
        fmt=validate_file(name,data)
        contents.append((name,data,fmt,hashlib.sha256(data).hexdigest()))
    fingerprint=digest({'attributes':attrs,'files':[(n,h) for n,_,_,h in contents]})
    from models.user import User
    db.query(User).filter_by(id=user.id).with_for_update().one()
    old=db.query(PaperBatch).filter_by(teacher_id=user.id,request_key=request_key).first()
    if old:
        if old.request_hash!=fingerprint: raise HTTPException(409,'导入幂等键冲突')
        return {'batch_id':old.id,'papers':[payload(db,p) for p in db.query(PaperDocument).filter_by(batch_id=old.id)]}
    batch=PaperBatch(teacher_id=user.id,request_key=request_key,request_hash=fingerprint,attributes=attrs)
    db.add(batch);db.flush();papers=[]
    destination=Path(settings.UPLOAD_DIR)/'v2-papers';destination.mkdir(parents=True,exist_ok=True)
    for name,data,fmt,sha in contents:
        path=destination/(uuid.uuid4().hex+'.'+fmt)
        path.write_bytes(data)
        p=PaperDocument(batch_id=batch.id,teacher_id=user.id,title=Path(name).stem,source_name=name,
            source_locator=str(path.resolve()),source_sha256=sha,source_format=fmt,attributes={},questions=[])
        db.add(p);db.flush();papers.append(p)
    db.commit()
    return {'batch_id':batch.id,'papers':[payload(db,p) for p in papers]}


@router.put('/batches/{batch_id}/attributes')
def batch_attributes(batch_id:int, body:Attributes,db:Session=Depends(get_db),user=Depends(get_current_user)):
    teacher(db,user)
    batch=db.query(PaperBatch).filter_by(id=batch_id,teacher_id=user.id).with_for_update().first()
    if not batch: raise HTTPException(404,'批次不存在')
    batch.attributes=body.model_dump(exclude_unset=True)
    for paper in db.query(PaperDocument).filter_by(batch_id=batch.id):
        paper.revision+=1;paper.status='DRAFT'
    db.commit();return {'batch_id':batch.id}


@router.get('/papers/{paper_id}')
def get_paper(paper_id:int,db:Session=Depends(get_db),user=Depends(get_current_user)):
    return payload(db,owned_paper(db,user,paper_id))


@router.get('/papers/{paper_id}/source')
def get_source(paper_id:int,db:Session=Depends(get_db),user=Depends(get_current_user)):
    p=owned_paper(db,user,paper_id)
    return FileResponse(source_path(p),filename=p.source_name,content_disposition_type='inline')


@router.put('/papers/{paper_id}')
def edit_paper(paper_id:int,body:PaperEdit,db:Session=Depends(get_db),user=Depends(get_current_user)):
    p=owned_paper(db,user,paper_id,True)
    if p.revision!=body.expected_revision: raise HTTPException(409,'套卷版本变化，请刷新')
    p.title=body.title;p.attributes=body.attributes.model_dump(exclude_unset=True)
    p.questions=[q.model_dump(exclude_unset=True) for q in body.questions]
    # Fill omitted defaults before persistence, not invented question content.
    for q in p.questions: q.setdefault('max_score',10);q.setdefault('overrides',{})
    p.revision+=1;p.status='DRAFT';db.commit();return payload(db,p)


@router.post('/papers/{paper_id}/confirm')
def confirm_paper(paper_id:int,db:Session=Depends(get_db),user=Depends(get_current_user)):
    p=owned_paper(db,user,paper_id,True);question_snapshots(db,p)
    p.status='CONFIRMED';db.commit();return payload(db,p)


class Transfer(BaseModel):
    model_config=ConfigDict(extra='forbid')
    target_paper_id:int=Field(gt=0)
    number:str
    mode:str=Field(pattern='^(copy|move)$')
    expected_source_revision:int
    expected_target_revision:int


@router.post('/papers/{paper_id}/transfer')
def transfer_question(paper_id:int,body:Transfer,db:Session=Depends(get_db),user=Depends(get_current_user)):
    if paper_id==body.target_paper_id:raise HTTPException(422,'请选择另一套卷')
    a=owned_paper(db,user,paper_id,True);b=owned_paper(db,user,body.target_paper_id,True)
    if (a.revision,b.revision)!=(body.expected_source_revision,body.expected_target_revision):raise HTTPException(409,'套卷版本变化')
    q=next((q for q in a.questions if q['number']==body.number),None)
    if not q:raise HTTPException(404,'题目不存在')
    if any(x['asset_id']==q['asset_id'] or x['number']==q['number'] for x in b.questions):raise HTTPException(409,'目标题号或资产冲突，请先调整编号')
    b.questions=[*b.questions,q];b.revision+=1;b.status='DRAFT'
    if body.mode=='move':a.questions=[x for x in a.questions if x['number']!=body.number];a.revision+=1;a.status='DRAFT'
    db.commit();return {'source':payload(db,a),'target':payload(db,b)}


class ManualAsset(BaseModel):
    model_config=ConfigDict(extra='forbid')
    subject:str=Field(min_length=1,max_length=40)
    grade:str=Field(min_length=1,max_length=40)
    question_text:str=Field(min_length=1,max_length=12000)
    options:dict[str,str]|list[str]|None=None
    correct_answer:str=Field(min_length=1,max_length=4000)
    analysis:str=Field(min_length=1,max_length=8000)
    difficulty:str=Field(pattern='^(easy|medium|hard)$')
    knowledge_points:list[str]=Field(min_length=1,max_length=40)
    confirmed:bool


@router.post('/assets')
def create_asset(body:ManualAsset,db:Session=Depends(get_db),user=Depends(get_current_user)):
    teacher(db,user)
    if not body.confirmed:raise HTTPException(409,'题干答案解析需教师确认，不能猜测')
    q=QuestionAsset(subject=body.subject,grade=body.grade,question_text=body.question_text,options_json=body.options,
        question_type='choice' if body.options else 'teacher_authored',correct_answer=body.correct_answer,
        analysis=body.analysis,difficulty=body.difficulty,knowledge_points_json=body.knowledge_points,
        source='teacher_v2',asset_version='V2-001-v1',rights_basis='TEACHER_AUTHORIZED',
        rights_reference=f'teacher:{user.id}:{uuid.uuid4().hex}',review_status='CONFIRMED',clean_image_status='NOT_REQUIRED')
    db.add(q);db.commit();return {'asset_id':q.id}


@router.post('/papers/{paper_id}/publish')
def publish_paper(paper_id:int,body:Publish,db:Session=Depends(get_db),user=Depends(get_current_user)):
    p=owned_paper(db,user,paper_id,True)
    existing=db.query(AssignmentPublication).filter_by(teacher_id=user.id,request_key=body.request_key).first()
    if p.status!='CONFIRMED' and not existing:raise HTTPException(409,'请先整套确认题目与答案')
    result=publish(db,user,p,body);db.commit()
    return {'assignment_id':result.assignment_id,'publication_id':result.id,'snapshot_sha256':result.snapshot_sha256}


@router.get('/assignments')
def assignments(db:Session=Depends(get_db),user=Depends(get_current_user)):
    teacher(db,user)
    from app.v1.classroom import _teacher_assignment
    rows=db.query(Assignment).order_by(Assignment.id.desc()).all();items=[]
    for a in rows:
        try:_teacher_assignment(db,a.id,user.id)
        except HTTPException:continue
        pub=publication_for(db,a.id)
        items.append({'id':a.id,'class_id':a.class_id,'title':a.title,'subject':a.subject,'grade':a.grade,
            'assignment_date':str(a.assignment_date),'mode':'uniform_mixed' if pub else 'legacy',
            'source_format':Path(pub.snapshot['source_name']).suffix.lstrip('.') if pub else None,
            'paper_id':pub.paper_id if pub else None,'variant_id':pub.variant_id if pub else None})
    return {'items':items}


@router.get('/papers/{paper_id}/suggest-requirements')
def suggest_requirements(paper_id:int,class_id:int,db:Session=Depends(get_db),user=Depends(get_current_user)):
    from app.v1.assignment_plans import _teacher_subject_class
    from services.learning_advice import collect_evidence
    p=owned_paper(db,user,paper_id);qs=question_snapshots(db,p);subject=qs[0]['attributes']['subject']
    _teacher_subject_class(db,user,class_id,subject)
    ids=[r[0] for r in db.query(StudentRoster.student_id).filter_by(class_id=class_id,status='active') if r[0]]
    evidence=collect_evidence(db,class_id,subject,ids);rules=[]
    for sid in ids:
        data,_=evidence[sid]
        if data['evidence_status']!='SUFFICIENT_FOR_TEACHER_REVIEW':continue
        for q in qs:
            # A suggestion only; no tier/requirement is changed until teacher publishes.
            matching=[e for e in data['sources'] if set(q['attributes']['knowledge_points']) & set(e['knowledge_points'])]
            if len(matching)>=3 and all(e['outcome']=='correct' for e in matching):
                rules.append({'student_id':sid,'number':q['number'],'requirement':'optional',
                    'reason':f"教师已确认的同知识点至少3题均正确，建议选做，待教师决定；证据{digest(matching)[:16]}"})
    return {'requirements':rules,'default_requirement':'required','notice':'证据不足统一必做；建议不会自动应用或改变档位'}


@router.get('/assignments/{assignment_id}/dashboard')
def dashboard(assignment_id:int,db:Session=Depends(get_db),user=Depends(get_current_user)):
    from app.v1.classroom import _teacher_assignment
    from services.teacher_v2_dashboard import build_dashboard
    teacher(db,user);a=_teacher_assignment(db,assignment_id,user.id)
    return build_dashboard(db,a)


@router.get('/assignments/{assignment_id}/source')
def student_source(assignment_id:int,student_id:int,db:Session=Depends(get_db),user=Depends(get_current_user)):
    from services.identity_relations import user_can_access_student
    from app.v1.classroom import _teacher_assignment
    a=db.get(Assignment,assignment_id);pub=publication_for(db,assignment_id)
    if not a or not pub:raise HTTPException(404,'作业不存在')
    if user_has_role(db,user,'teacher'):
        _teacher_assignment(db,assignment_id,user.id)
    elif not user_can_access_student(db,user,student_id,class_id=a.class_id) or str(student_id) not in pub.snapshot['requirements']:
        raise HTTPException(404,'作业不存在')
    p=db.get(PaperDocument,pub.paper_id)
    if p.source_sha256!=pub.snapshot['source_sha256']:raise HTTPException(409,'原卷版本变化')
    return FileResponse(source_path(p),filename=p.source_name,content_disposition_type='inline')


@router.post('/assignments/{assignment_id}/prepare-template')
async def prepare_original_template(assignment_id:int,db:Session=Depends(get_db),user=Depends(get_current_user)):
    from app.v1.classroom import _teacher_assignment
    from app.v1.known_assignments import upload_template,page_data
    from models.known_assignment import PageTemplate
    teacher(db,user);_teacher_assignment(db,assignment_id,user.id)
    pub=publication_for(db,assignment_id)
    if not pub:raise HTTPException(409,'历史作业请沿用原模板入口')
    existing=db.query(PageTemplate).filter_by(variant_id=pub.variant_id).all()
    if existing:return {'pages':[page_data(db,p) for p in existing],'reused':True}
    paper=db.get(PaperDocument,pub.paper_id)
    if paper.source_format not in ('pdf','png','jpg','jpeg'):
        raise HTTPException(409,'原Word尚不支持本地括号模板解析，不能伪造模板；请保留人工审核')
    file=UploadFile(filename=paper.source_name,file=BytesIO(source_path(paper).read_bytes()))
    try:return await upload_template(pub.variant_id,file,db,user)
    finally:await file.close()
