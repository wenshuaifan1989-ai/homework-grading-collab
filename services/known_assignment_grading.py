"""Local known-paper pipeline and append-only teacher decisions."""
from datetime import datetime
import hashlib
import cv2
import numpy as np
from models.known_assignment import PageTemplate, QuestionPlacement, KnownPageMatch, ChoiceRead, ChoiceReviewAudit
from models.learning import AssignmentVariantTask, AssignmentVariantQuestion
from models.homework import HomeworkTask, HomeworkImage, QuestionBlock, OCRResult, GradingResult
from models.paper import QuestionAsset, QuestionAssetSource, MistakeRecord
from services.known_assignment_templates import questions, fingerprint, store
from services.known_page_vision import LocalPageMatcher, LocalStrokeReader, AnswerKeyGrader, load_image, png, expanded_answer_roi


def template_candidates(db,task):
    link=db.query(AssignmentVariantTask).filter_by(task_id=task.task_id,assignment_id=task.assignment_id,student_id=task.student_id).first()
    if not task.assignment_id or not link:
        return []
    fp=fingerprint(questions(db,link.variant_id))
    return db.query(PageTemplate).filter_by(assignment_id=task.assignment_id,variant_id=link.variant_id,status='ACTIVE',variant_fingerprint=fp).order_by(PageTemplate.page_index).all()


def refresh_status(db,task):
    pages=template_candidates(db,task)
    matches=db.query(KnownPageMatch).filter_by(task_id=task.task_id).all()
    reads=db.query(ChoiceRead).filter_by(task_id=task.task_id).all()
    expected=db.query(QuestionPlacement).filter(QuestionPlacement.page_template_id.in_([p.id for p in pages])).count() if pages else 0
    complete=bool(pages) and len(matches)==len(pages) and {m.page_template_id for m in matches if m.status=='MATCHED'}=={p.id for p in pages}
    task.status='UNKNOWN_LAYOUT' if not complete else 'WAIT_REVIEW' if len(reads)!=expected or any(r.status!='CONFIRMED' for r in reads) else 'SUCCESS'
    # Unconfirmed candidates have no grade. Totals remain provisional until SUCCESS.
    grades=db.query(GradingResult).filter_by(task_id=task.task_id).all()
    task.total_score=sum(float(g.score) for g in grades)
    task.model_name='local-bracket-v1';task.prompt_version='no-paid-model'
    return task.status


def process_known(db,task_id):
    task=db.query(HomeworkTask).filter_by(task_id=task_id).with_for_update().one()
    if task.grading_mode!='known' or task.assignment_id is None:
        raise ValueError('Known pipeline requires assigned task')
    if db.query(KnownPageMatch).filter_by(task_id=task_id).first():
        return {'task_id':task_id,'status':task.status,'skipped_duplicate':True}
    pages=template_candidates(db,task)
    images=db.query(HomeworkImage).filter_by(task_id=task_id).order_by(HomeworkImage.image_index).all()
    matcher=LocalPageMatcher();reader=LocalStrokeReader();seen=set()
    for image in images:
        original=load_image(image.original_url)
        page,aligned,ev=matcher.match(original,pages)
        if page and page.id in seen:
            page=None;ev={'reason':'DUPLICATE_PAGE'}
        match=KnownPageMatch(task_id=task_id,homework_image_id=image.id,page_template_id=page.id if page else None,
                             status='MATCHED' if page else 'UNMATCHED',reason=ev.get('reason'),evidence_json=ev,
                             aligned_locator=store(png(aligned)) if page else None)
        db.add(match);db.flush()
        if page:
            seen.add(page.id)
            read_page(db,task,match,page,aligned,reader)
    refresh_status(db,task);db.commit()
    return {'task_id':task_id,'status':task.status,'paid_calls':0}


def read_page(db,task,match,page,aligned,reader=None):
    reader=reader or LocalStrokeReader()
    ref=load_image(page.image_locator)
    for placement in db.query(QuestionPlacement).filter_by(page_template_id=page.id).all():
        bbox=expanded_answer_roi(placement,ref.shape)
        result,crop,ink=reader.read(ref,aligned,bbox,placement.choice_kind=='multi')
        result.update({'template_bracket_bbox':placement.answer_bracket_bbox,'effective_bbox':bbox,'roi_policy':'bounded-before-options-v1'})
        db.add(ChoiceRead(task_id=task.task_id,page_match_id=match.id,placement_id=placement.id,symbol=result['symbol'],
                          confidence=str(result['score']),status='HOLD_REVIEW',reason=result['reason'],evidence_json=result,
                          crop_locator=store(png(crop)),ink_locator=store(png(ink))))
    db.flush()


def recover_known(db,task_id):
    """Retry only unmatched pages; never overwrite held/confirmed answers or grades."""
    task=db.query(HomeworkTask).filter_by(task_id=task_id).with_for_update().one()
    if task.grading_mode!='known':
        raise ValueError('Only local known-paper tasks can use safe recovery')
    candidates=template_candidates(db,task)
    matches=db.query(KnownPageMatch).filter_by(task_id=task_id).all()
    seen={m.page_template_id for m in matches if m.status=='MATCHED'}
    recovered=0
    for match in matches:
        if match.status=='MATCHED' or db.query(ChoiceRead.id).filter_by(page_match_id=match.id).first():
            continue
        image=db.get(HomeworkImage,match.homework_image_id)
        page,aligned,evidence=LocalPageMatcher().match(load_image(image.original_url),candidates)
        if not page or page.id in seen:
            continue
        match.page_template_id=page.id;match.status='MATCHED';match.reason='LOCAL_SAFE_RECOVERY'
        match.evidence_json={**evidence,'recovered_unmatched_page':True}
        match.aligned_locator=store(png(aligned));seen.add(page.id)
        read_page(db,task,match,page,aligned);recovered+=1
    refresh_status(db,task);db.commit()
    return {'task_id':task_id,'status':task.status,'recovered_pages':recovered,'paid_calls':0,
            'notice':'未通过原匹配门禁的页仍需教师明确配准；原拒判与审核不覆盖'}


def apply_review(db,task,read,user_id,symbol,note,request_key):
    # Serialize all reviews of this task, including total/status recomputation.
    db.query(HomeworkTask).filter_by(task_id=task.task_id).with_for_update().one()
    read=db.query(ChoiceRead).filter_by(id=read.id).with_for_update().one()
    audit=db.query(ChoiceReviewAudit).filter_by(choice_read_id=read.id,request_key=request_key).first()
    if audit:
        if audit.after_json['symbol']!=symbol or audit.note!=note:
            raise ValueError('Idempotency key conflicts with a previous decision')
        return read
    pages=template_candidates(db,task)
    match=db.get(KnownPageMatch,read.page_match_id)
    placement=db.get(QuestionPlacement,read.placement_id)
    if match.status!='MATCHED' or placement.page_template_id not in {p.id for p in pages}:
        raise ValueError('HOLD_REVIEW: template is stale or unmatched')
    q=db.get(AssignmentVariantQuestion,placement.variant_question_id)
    asset=db.get(QuestionAsset,q.source_asset_id) if q.source_asset_id else None
    multi=placement.choice_kind=='multi'
    grader=AnswerKeyGrader()
    if not asset or asset.review_status!='CONFIRMED' or asset.question_text!=q.question_text or asset.options_json!=q.options_json or grader.normalize(asset.correct_answer,multi)!=grader.normalize(q.correct_answer,multi):
        raise ValueError('HOLD_REVIEW: canonical question/key unconfirmed or differs from snapshot')
    verdict=grader.grade(symbol,q.correct_answer,q.max_score,multi)
    from services.teacher_v2 import optional_unanswered
    skipped_optional=optional_unanswered(db,task,placement.question_number,symbol)
    if skipped_optional:
        verdict={**verdict,'result':'unanswered','score':0}
    before={'symbol':read.symbol,'status':read.status,'grade_id':read.grading_result_id}
    page=db.get(PageTemplate,placement.page_template_id)
    image=db.get(HomeworkImage,match.homework_image_id)
    x1,y1,x2,y2=placement.question_bbox
    aligned=load_image(match.aligned_locator)
    full_crop=store(png(aligned[y1:y2,x1:x2]))
    # Original-coordinate provenance comes from the inverse registration matrix.
    coords=np.float32([[[x1,y1],[x2,y1],[x2,y2],[x1,y2]]])
    transform=match.evidence_json.get('question_transforms',{}).get(str(placement.id),{}).get('homography')
    if transform is None:transform=match.evidence_json['homography']
    original=cv2.perspectiveTransform(coords,np.linalg.inv(np.array(transform)))[0]
    ox1,oy1=np.floor(original.min(axis=0)).astype(int);ox2,oy2=np.ceil(original.max(axis=0)).astype(int)
    grade=db.get(GradingResult,read.grading_result_id) if read.grading_result_id else None
    if grade is None:
        block=QuestionBlock(task_id=task.task_id,question_no=placement.question_number,question_image_url=full_crop,
                            x1=int(ox1),y1=int(oy1),x2=int(ox2),y2=int(oy2),image_index=image.image_index)
        db.add(block);db.flush()
        db.add(OCRResult(task_id=task.task_id,question_block_id=block.id,question_no=placement.question_number,
                         question_text=q.question_text,student_answer=symbol,question_type='choice',raw_response={'provider':'local-bracket','teacher_confirmed':True}))
        grade=GradingResult(task_id=task.task_id,question_block_id=block.id,question_no=placement.question_number,
                            score=verdict['score'],max_score=q.max_score,result=verdict['result'])
        db.add(grade);db.flush();read.grading_result_id=grade.id
        source=QuestionAssetSource(question_asset_id=asset.id,source_task_id=task.task_id,source_image_id=image.id,
              grading_result_id=grade.id,page_index=image.image_index,question_no=placement.question_number,
              x1=int(ox1),y1=int(oy1),x2=int(ox2),y2=int(oy2),bbox_fingerprint=hashlib.sha256(f'known-placement:{placement.id}'.encode()).hexdigest(),
              crop_locator=full_crop,provider_name='local-bracket',provider_version='013-V01',link_status='CONFIRMED',review_status='CONFIRMED',
              reviewed_by=user_id,reviewed_at=datetime.now())
        db.add(source);db.flush()
    else:
        source=db.query(QuestionAssetSource).filter_by(grading_result_id=grade.id).one()
        db.query(OCRResult).filter_by(question_block_id=grade.question_block_id).update({'student_answer':symbol})
    grade.score=verdict['score'];grade.result=verdict['result'];grade.correct_answer=verdict['correct_answer']
    grade.analysis=q.analysis;grade.is_reviewed=True;grade.reviewer_id=user_id;grade.reviewed_score=grade.score
    grade.raw_response={'provider':'local-bracket','teacher_confirmed':True,'choice_read_id':read.id}
    grade.accuracy=None if skipped_optional else 100 if grade.result=='correct' else 0
    if skipped_optional:
        grade.max_score=0  # Optional non-participation is not part of the scored denominator.
    else:
        grade.max_score=q.max_score
    mistake=db.query(MistakeRecord).filter_by(student_id=task.student_id,source_grading_result_id=grade.id).first()
    if grade.result=='wrong' and mistake is None:
        mistake=MistakeRecord(student_id=task.student_id,assignment_id=task.assignment_id,question_asset_id=asset.id,
              question_asset_source_id=source.id,source_task_id=task.task_id,source_grading_result_id=grade.id,detection_basis='teacher_confirmed_bracket',status='open')
        db.add(mistake)
    elif mistake:
        if grade.result in ('correct','unanswered'):
            mistake.status='not_wrong'
        elif mistake.status=='not_wrong':
            mistake.status='open'
    read.symbol=symbol;read.status='CONFIRMED';read.reviewed_by=user_id;read.reviewed_at=datetime.now()
    db.add(ChoiceReviewAudit(choice_read_id=read.id,request_key=request_key,reviewer_id=user_id,
                            before_json=before,after_json={'symbol':symbol,'result':grade.result,'score':float(grade.score)},note=note))
    db.flush();refresh_status(db,task);db.commit()
    return read
