"""Synthetic pen strokes only: these tests are NOT handwriting accuracy claims."""
import json
import time
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
import cv2
import numpy as np
from tests import test_013_assignment_plans as plan_tests
from models.classroom import Assignment
from models.learning import AssignmentVariant,AssignmentVariantQuestion,AssignmentVariantTask,AssignmentVariantSet
from models.homework import HomeworkTask,HomeworkImage,GradingResult
from models.paper import QuestionAsset,MistakeRecord
from models.known_assignment import PageTemplate,QuestionPlacement,KnownPageMatch,ChoiceRead,ChoiceReviewAudit
from services.known_assignment_templates import generate,store,render_pdf,questions
from services.known_page_vision import LocalPageMatcher,LocalStrokeReader,AnswerKeyGrader,STROKES,load_image,png
from services.known_assignment_grading import process_known,apply_review
from config import settings

_EVIDENCE_TMP=tempfile.TemporaryDirectory(prefix='collab-test-013-')
EVIDENCE=Path(_EVIDENCE_TMP.name)


class Known013Tests(unittest.TestCase):
    setUpBase=plan_tests.AssignmentPlan013Tests.setUp
    tearDownBase=plan_tests.AssignmentPlan013Tests.tearDown

    def setUp(self):
        EVIDENCE.mkdir(parents=True,exist_ok=True)
        self.setUpBase();self.folder=tempfile.TemporaryDirectory(prefix='known-test-')
        self.storage_patch=patch.object(settings,'UPLOAD_DIR',self.folder.name);self.storage_patch.start()
        with self.Session.begin() as db:
            db.add(Assignment(id=1301,class_id=3013,teacher_id=131,title='原创数学选择题（无隐私模拟）',subject='math',grade='grade7',status='published'))
            db.add(AssignmentVariantSet(assignment_id=1301,allow_uniform_fallback=False,updated_by=131))
            db.add_all([AssignmentVariant(id=1401,assignment_id=1301,level='L1',version=1,is_current=True,updated_by=131),
                        AssignmentVariant(id=1402,assignment_id=1301,level='L2',version=1,is_current=True,updated_by=131)])
            for i in range(8):
                opts={'A':str(i+1),'B':str(i+2),'C':str(i+3),'D':str(i+4)}
                text=f'第{i+1}题：计算 {i+1} + 1 的结果，选择正确选项。'
                db.add(QuestionAsset(id=1501+i,subject='math',grade='grade7',question_text=text,question_type='单选题',options_json=opts,correct_answer='B',analysis='加一得到下一个整数。',source='PROJECT_AUTHORED',review_status='CONFIRMED',clean_image_status='NOT_REQUIRED'))
                db.add(AssignmentVariantQuestion(id=1601+i,variant_id=1401,source_type='question_asset',source_asset_id=1501+i,sort_order=i+1,question_text=text,options_json=opts,correct_answer='B',analysis='加一得到下一个整数。',max_score=5))
            db.add(AssignmentVariantQuestion(id=1699,variant_id=1402,source_type='question_asset',source_asset_id=1501,sort_order=1,question_text='异版本不能匹配。',options_json={'A':'1','B':'2','C':'3','D':'4'},correct_answer='B',max_score=5))
        with self.Session() as db:
            # Stable opaque fixture markers keep independently captured evidence
            # from these tests associated with the same two synthetic pages.
            self.pages=generate(db,db.get(Assignment,1301),db.get(AssignmentVariant,1401),131,
                                page_uids=[f'{1000+i:032x}' for i in range(9)])

    def tearDown(self):
        self.storage_patch.stop();self.folder.cleanup();self.tearDownBase()

    def task(self,name='known-task',paths=None):
        paths=paths or [p.image_locator for p in self.pages]
        with self.Session.begin() as db:
            db.add(HomeworkTask(task_id=name,user_id=132,subject='math',grade='grade7',status='PROCESSING',grading_mode='known',assignment_id=1301,class_id=3013,student_id=2013,actor_user_id=132))
            db.add(AssignmentVariantTask(task_id=name,assignment_id=1301,student_id=2013,variant_id=1401))
            for i,path in enumerate(paths):db.add(HomeworkImage(task_id=name,original_url=path,image_index=i))

    def test_template_pdf_geometry_and_idempotence(self):
        self.assertEqual(len(self.pages),2)
        with self.Session() as db:
            again=generate(db,db.get(Assignment,1301),db.get(AssignmentVariant,1401),131)
            self.assertEqual([p.id for p in again],[p.id for p in self.pages])
            placements=db.query(QuestionPlacement).all();self.assertEqual(len(placements),8)
            for p in placements:self.assertLess(p.answer_bracket_bbox[3],p.options_bbox[1])
            EVIDENCE.mkdir(parents=True,exist_ok=True)
            (EVIDENCE/'原创括号试卷.pdf').write_bytes(Path(self.pages[0].pdf_locator).read_bytes())
            for p in self.pages:(EVIDENCE/f'template-{p.page_index}.png').write_bytes(Path(p.image_locator).read_bytes())
            (EVIDENCE/'placements.json').write_text(json.dumps([{'page_id':p.page_template_id,'question':p.question_number,'stem':p.stem_bbox,'bracket':p.answer_bracket_bbox,'options':p.options_bbox} for p in placements],ensure_ascii=False,indent=2),encoding='utf-8')

    def test_local_strokes_blank_printed_options_and_double_marks(self):
        ref=np.full((100,220),255,np.uint8)
        cv2.putText(ref,'A. 1 B. 2 C. 3 D. 4',(0,90),cv2.FONT_HERSHEY_SIMPLEX,.35,0,1)
        bbox=[10,5,160,55]
        reader=LocalStrokeReader()
        result,_,_=reader.read(ref,ref.copy(),bbox)
        self.assertEqual(result['symbol'],'BLANK')
        option_circle=ref.copy();cv2.circle(option_circle,(10,85),8,0,2)
        result,_,_=reader.read(ref,option_circle,bbox);self.assertEqual(result['symbol'],'BLANK')
        observed={}
        for letter,strokes in STROKES.items():
            photo=ref.copy()
            for stroke in strokes:cv2.polylines(photo,[np.array(stroke)+[45,12]],False,0,2,cv2.LINE_AA)
            result,crop,ink=reader.read(ref,photo,bbox)
            self.assertEqual(result['symbol'],letter,result)
            self.assertEqual(result['status'],'HOLD_REVIEW')
            observed[letter]=result
            EVIDENCE.mkdir(parents=True,exist_ok=True)
            (EVIDENCE/f'simulated-{letter}-crop.png').write_bytes(png(crop))
            (EVIDENCE/f'simulated-{letter}-ink.png').write_bytes(png(ink))
        photo=ref.copy()
        for offset in (30,90):
            for stroke in STROKES['A']:cv2.polylines(photo,[np.array(stroke)+[offset,12]],False,0,2)
        result,_,_=reader.read(ref,photo,bbox)
        self.assertEqual(result['symbol'],'UNCERTAIN')
        self.assertEqual(result['reason'],'MULTI_MARK_OR_ERASURE')
        (EVIDENCE/'stroke-results.json').write_text(json.dumps(observed,indent=2),encoding='utf-8')

    def test_alignment_rotation_perspective_foreign_duplicate_and_shuffle(self):
        matcher=LocalPageMatcher();records=[]
        image=load_image(self.pages[0].image_locator)
        for name,photo in [('plain',image),('rotate90',cv2.rotate(image,cv2.ROTATE_90_CLOCKWISE)),('rotate180',cv2.rotate(image,cv2.ROTATE_180)),('mirror',cv2.flip(image,1)),('blur',cv2.GaussianBlur(image,(71,71),20)),('crop',image[120:,:])]:
            start=time.perf_counter();page,aligned,evidence=matcher.match(photo,self.pages)
            if name in ('plain','rotate90','rotate180'):self.assertIsNotNone(page,(name,evidence))
            else:self.assertIsNone(page,(name,evidence))
            records.append({'case':name,'matched':page is not None,'seconds':time.perf_counter()-start,'evidence':evidence})
            if aligned is not None:
                (EVIDENCE/f'aligned-{name}.png').write_bytes(png(aligned))
        h,w=image.shape
        mat=cv2.getPerspectiveTransform(np.float32([[0,0],[w,0],[w,h],[0,h]]),np.float32([[35,20],[w-35,50],[w-20,h-20],[20,h-50]]))
        photo=cv2.warpPerspective(image,mat,(w,h),borderValue=255)
        page,aligned,ev=matcher.match(photo,self.pages)
        # Photographs must either align correctly or refuse with evidence;
        # do not loosen production thresholds to force this fixture green.
        if page is not None:
            self.assertEqual(page.id,self.pages[0].id)
            (EVIDENCE/'aligned-perspective.png').write_bytes(png(aligned))
        else:
            self.assertEqual(ev['reason'],'UNMATCHED_LAYOUT')
        records.append({'case':'perspective','matched':page is not None,'evidence':ev})
        (EVIDENCE/'simulated-perspective.png').write_bytes(png(photo))
        with self.Session() as db:
            foreign=generate(db,db.get(Assignment,1301),db.get(AssignmentVariant,1402),131)
        page,_,_=matcher.match(load_image(foreign[0].image_locator),self.pages);self.assertIsNone(page)
        self.task(paths=[p.image_locator for p in reversed(self.pages)])
        with self.Session() as db:
            result=process_known(db,'known-task');self.assertEqual(result['status'],'WAIT_REVIEW')
            self.assertEqual(db.query(ChoiceRead).count(),8)
            repeated=process_known(db,'known-task');self.assertTrue(repeated['skipped_duplicate'])
            self.assertEqual(db.query(ChoiceRead).count(),8)
        self.task('duplicate-task',[self.pages[0].image_locator]*2)
        with self.Session() as db:self.assertEqual(process_known(db,'duplicate-task')['status'],'UNKNOWN_LAYOUT')
        (EVIDENCE/'registration-results.json').write_text(json.dumps(records,indent=2),encoding='utf-8')

    def test_review_grading_mistake_correction_idempotence_and_permissions(self):
        self.task()
        with self.Session() as db:
            self.assertEqual(process_known(db,'known-task')['status'],'WAIT_REVIEW')
            self.assertEqual(db.query(GradingResult).count(),0)
            self.assertEqual(db.query(MistakeRecord).count(),0)
        self.current_user=self.student_user
        self.assertEqual(self.client.get('/api/v1/known-assignments/assignments/1301').status_code,403)
        self.current_user=self.other_teacher
        self.assertIn(self.client.get('/api/v1/known-assignments/assignments/1301').status_code,[403,404])
        self.current_user=self.teacher
        detail=self.client.get('/api/v1/known-assignments/tasks/known-task');self.assertEqual(detail.status_code,200,detail.text)
        read=detail.json()['reads'][0]
        body={'symbol':'A','note':'模拟笔迹经人工核对为A','request_key':'review-test-001'}
        url=f"/api/v1/known-assignments/tasks/known-task/reads/{read['id']}/review"
        response=self.client.post(url,json=body);self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.client.post(url,json=body).status_code,200)
        with self.Session() as db:
            self.assertEqual(db.query(GradingResult).count(),1);self.assertEqual(db.query(MistakeRecord).one().status,'open')
            self.assertEqual(db.query(ChoiceReviewAudit).count(),1)
        body.update(symbol='B',request_key='review-test-002',note='核对后改判为B')
        self.assertEqual(self.client.post(url,json=body).status_code,200)
        with self.Session() as db:
            self.assertEqual(db.query(GradingResult).count(),1);self.assertEqual(db.query(MistakeRecord).one().status,'not_wrong')
            self.assertEqual(db.query(ChoiceReviewAudit).count(),2)
        self.assertEqual(self.client.post(url,json={**body,'symbol':'C'}).status_code,409)
        for r in detail.json()['reads'][1:]:
            response=self.client.post(f"/api/v1/known-assignments/tasks/known-task/reads/{r['id']}/review",json={'symbol':'B','note':'测试人工确认','request_key':f"review-complete-{r['id']}"})
            self.assertEqual(response.status_code,200,response.text)
        with self.Session() as db:
            self.assertEqual(db.query(HomeworkTask).filter_by(task_id='known-task').one().status,'SUCCESS')
            self.assertEqual(float(db.query(HomeworkTask).filter_by(task_id='known-task').one().total_score),40)
        self.current_user=self.student_user
        self.assertEqual(self.client.get(f"/api/v1/known-assignments/pages/{self.pages[0].id}/file").status_code,403)

    def test_uploaded_pdf_mapping_and_invalid_regions(self):
        with self.Session() as db:
            pdf=Path(self.pages[0].pdf_locator).read_bytes()
            # Upload to other variant to avoid invalidating existing work.
        response=self.client.post('/api/v1/known-assignments/variants/1402/upload',files={'file':('sample.pdf',pdf,'application/pdf')})
        self.assertEqual(response.status_code,200,response.text)
        page=response.json()['pages'][0]
        item={'variant_question_id':1699,'question_number':'1','stem_bbox':[30,100,900,240],
              'answer_bracket_bbox':[400,150,550,200],'options_bbox':[30,250,900,400],'question_bbox':[20,90,950,410],'choice_kind':'single'}
        url=f"/api/v1/known-assignments/pages/{page['id']}/mapping"
        self.assertEqual(self.client.put(url,json={'placements':[item],'blank_reference_confirmed':True}).status_code,200)
        bad={**item,'answer_bracket_bbox':[50,260,200,300]}
        self.assertEqual(self.client.put(url,json={'placements':[bad],'blank_reference_confirmed':True}).status_code,422)
        self.assertEqual(self.client.put(url,json={'placements':[{**item,'variant_question_id':1601}],'blank_reference_confirmed':True}).status_code,422)
        self.assertEqual(self.client.post(f"/api/v1/known-assignments/pages/{page['id']}/activate-set").status_code,200)
        self.assertEqual(self.client.put(url,json={'placements':[item],'blank_reference_confirmed':True}).status_code,409)

    def test_answer_rules(self):
        grader=AnswerKeyGrader()
        self.assertEqual(grader.grade('B','B',5)['score'],5)
        self.assertEqual(grader.grade('A','B',5)['score'],0)
        self.assertEqual(grader.grade('AC','CA',5,True)['score'],5)
        self.assertEqual(grader.grade('A','AC',5,True)['score'],0)
        self.assertEqual(grader.grade('BLANK','B',5)['score'],0)
        for value,key in [('UNCERTAIN','B'),('BB','B'),('A','maybe')]:
            with self.assertRaises(ValueError):grader.grade(value,key,5)

    def test_real_upload_contract_celery_entry_and_no_paid_fallback(self):
        from tasks.homework_tasks import process_homework_task
        photos=[];expected={}
        with self.Session() as db:
            for page in self.pages:
                image=load_image(page.image_locator)
                placements=db.query(QuestionPlacement).filter_by(page_template_id=page.id).order_by(QuestionPlacement.id).all()
                for idx,p in enumerate(placements):
                    x1,y1,x2,y2=p.answer_bracket_bbox
                    letter='ABCD'[idx%4]
                    expected[p.id]=letter
                    for stroke in STROKES[letter]:
                        cv2.polylines(image,[np.array(stroke)+[(x1+x2)//2-16,y1+5]],False,0,2,cv2.LINE_AA)
                photos.append(png(image))
                (EVIDENCE/f'simulated-submission-{page.page_index}.png').write_bytes(png(image))
        queued=[]
        def enqueue(*args,**kwargs):
            queued.append(kwargs)
            return process_homework_task.run(*args,**kwargs)
        self.current_user=self.student_user
        with patch('tasks.homework_tasks.SessionLocal',self.Session),patch('app.v1.homework.process_homework_task.delay',side_effect=enqueue),patch('tasks.homework_tasks._vision_pipeline',side_effect=AssertionError('PAID_PATH_FORBIDDEN')),patch('tasks.homework_tasks._ocr_pipeline',side_effect=AssertionError('OCR_PATH_FORBIDDEN')):
            uploads=[('files',(f'p{i}.png',data,'image/png')) for i,data in enumerate(reversed(photos))]
            response=self.client.post('/api/v1/homework/analyze',data={'subject':'math','grade':'grade7','assignment_id':1301,'student_id':2013,'mode':'vision'},files=uploads,headers={'Idempotency-Key':'known-v01-upload-001'})
            self.assertEqual(response.status_code,200,response.text)
            task_id=response.json()['data']['task_id']
            self.assertEqual(queued[0]['grading_mode'],'known')
            status=self.client.get(f'/api/v1/homework/status/{task_id}')
            self.assertEqual(status.status_code,200,status.text)
            self.assertEqual(status.json()['data']['status'],'WAIT_REVIEW')
            self.assertFalse(status.json()['data']['can_retry'])
            repeated=self.client.post('/api/v1/homework/analyze',data={'subject':'math','grade':'grade7','assignment_id':1301,'student_id':2013},files=uploads,headers={'Idempotency-Key':'known-v01-upload-001'})
            self.assertEqual(repeated.status_code,200,repeated.text)
            self.assertEqual(repeated.json()['data']['task_id'],task_id)
            self.assertEqual(len(queued),1)
            self.assertEqual(self.client.post(f'/api/v1/homework/retry/{task_id}',json={'confirm_possible_duplicate_charge':True}).status_code,409)
        with self.Session() as db:
            self.assertEqual(db.query(HomeworkTask).count(),1)
            self.assertEqual(db.query(HomeworkImage).count(),2)
            self.assertEqual(db.query(ChoiceRead).count(),8)
            self.assertEqual(db.query(GradingResult).count(),0)
            candidates=[{'symbol':r.symbol,'expected':expected[r.placement_id],'reason':r.reason,'evidence':r.evidence_json} for r in db.query(ChoiceRead).all()]
            for candidate in candidates:self.assertEqual(candidate['symbol'],candidate['expected'])
            (EVIDENCE/'pipeline-candidates.json').write_text(json.dumps(candidates,indent=2),encoding='utf-8')
        (EVIDENCE/'api-celery-focused.json').write_text(json.dumps({'transport':'TestClient + synchronous Celery task.run; NOT real broker acceptance', 'one_task':True,'images':2,'status':'WAIT_REVIEW','queue_invocations':1,'paid_calls':0},indent=2),encoding='utf-8')

    def test_unconfirmed_asset_invalid_key_and_relocation_are_safe(self):
        self.task()
        with self.Session() as db:process_known(db,'known-task')
        detail=self.client.get('/api/v1/known-assignments/tasks/known-task').json()
        row=detail['reads'][0]
        url=f"/api/v1/known-assignments/tasks/known-task/reads/{row['id']}"
        moved=self.client.post(url+'/relocate',json={'bbox':row['bbox'],'note':'重新框选题干括号','request_key':'relocate-test-001'})
        self.assertEqual(moved.status_code,200,moved.text)
        with self.Session.begin() as db:db.get(QuestionAsset,1501).review_status='PENDING_REVIEW'
        rejected=self.client.post(url+'/review',json={'symbol':'B','note':'不应通过未审核题目','request_key':'invalid-key-test-001'})
        self.assertEqual(rejected.status_code,409,rejected.text)
        with self.Session() as db:
            self.assertEqual(db.query(GradingResult).count(),0)
            self.assertEqual(db.query(MistakeRecord).count(),0)

    def test_nine_pages_shuffled_and_per_page_number_restart(self):
        import uuid
        from services.known_assignment_templates import rasterize_pdf
        rows=[SimpleNamespace(id=i,source_asset_id=None,question_text=f'原创综合选择题 {i}: 求 {i}+{i} 的和，括号填写答案。',options_json={'A':'1','B':'2','C':'3','D':'4'},correct_answer='B',max_score=5) for i in range(1,42)]
        uids=[uuid.uuid4().hex for _ in range(9)]
        data,geometry=render_pdf('九页乱序合成工程用卷',rows,uids)
        images=rasterize_pdf(data)
        self.assertEqual(len(images),9)
        candidates=[SimpleNamespace(id=i,page_uid=uids[i],width=img.shape[1],height=img.shape[0],image_locator=store(png(img))) for i,img in enumerate(images)]
        matcher=LocalPageMatcher();durations=[]
        for idx in [8,1,5,0,7,3,6,2,4]:
            start=time.perf_counter();page,_,ev=matcher.match(images[idx],candidates)
            self.assertIsNotNone(page,ev);self.assertEqual(page.id,idx);durations.append(time.perf_counter()-start)
        (EVIDENCE/'nine-page-shuffle.json').write_text(json.dumps({'sample_type':'synthetic_printed_paper_no_real_handwriting','pages':9,'matched':9,'seconds':durations,'paid_calls':0},indent=2),encoding='utf-8')
        self.task('restart-numbers')
        with self.Session() as db:
            for p in db.query(QuestionPlacement).filter_by(page_template_id=self.pages[1].id).all():p.question_number='1'
            db.commit();process_known(db,'restart-numbers')
            self.assertEqual(db.query(ChoiceRead).count(),8)
