"""Free synthetic evidence tests; not real pupil/model/GUI acceptance."""
import json
import unittest
import tempfile
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import main
from models.base import Base
from models.user import User
from models.classroom import Class,StudentRoster,Assignment
from models.identity_relations import Student,StudentUserBinding,ClassTeacher
from models.homework import HomeworkTask,HomeworkImage,QuestionBlock,GradingResult
from models.paper import QuestionAsset,QuestionAssetSource,MistakeRecord,PaperCorrectionAttempt
from models.learning import StudentSubjectTier,StudentSubjectTierAudit
from models.learning_advice import TierSuggestion,SuggestionDecision,PracticeRecommendation,EvidenceSnapshot
from services.learning_advice import collect_evidence
from utils.database import get_db
from utils.deps import get_current_user
_EVIDENCE_TMP=tempfile.TemporaryDirectory(prefix='collab-test-014-')
EVIDENCE=Path(_EVIDENCE_TMP.name)

def seed(db):
    teacher=User(id=141,username='teacher014',email='teacher014@example.com',hashed_password='test-only-hashed-password-010',role='teacher',is_active=True)
    other=User(id=142,username='other014',email='other014@example.com',hashed_password='test-only-hashed-password-010',role='teacher',is_active=True)
    parent=User(id=149,username='parent014',email='parent014@example.com',hashed_password='test-only-hashed-password-010',role='student',is_active=True)
    db.add_all([teacher,other,parent]);db.flush()
    db.add(Class(id=1401,teacher_id=141,name='014无隐私测试班',grade='grade7',status='active',invite_code='TEST014001'));db.flush()
    db.add(ClassTeacher(class_id=1401,teacher_user_id=141,role='owner',status='active',subject_codes_json=['math','physics','chemistry']));db.flush()
    for i in range(3):
        db.add_all([User(id=151+i,username=f'student014-{i}',email=f'student014-{i}@example.com',hashed_password='test-only-hashed-password-010',role='student',is_active=True),
                    Student(id=2401+i,name=f'虚拟学生{i+1}',status='active')]);db.flush()
        db.add_all([StudentRoster(class_id=1401,student_id=2401+i,bound_user_id=151+i,student_name=f'虚拟学生{i+1}',student_no=f'014-{i}',status='active'),
                    StudentUserBinding(student_id=2401+i,user_id=151+i,relationship_type='self',status='active')])
        for subject,level in [('math','L2'),('physics','L1'),('chemistry','L3')]:
            db.add(StudentSubjectTier(student_id=2401+i,class_id=1401,subject=subject,level=level,updated_by=141))
    db.add(StudentUserBinding(student_id=2401,user_id=149,relationship_type='mother',status='active'))
    for sidx,subject in enumerate(('math','physics','chemistry')):
        for q in range(6):
            db.add(QuestionAsset(id=3000+sidx*100+q,subject=subject,grade='grade7',question_text=f'原创{subject}原题{q+1}',question_type='单选题',
                options_json={'A':'1','B':'2','C':'3','D':'4'},correct_answer='B',analysis='原创解析',difficulty='hard' if subject=='physics' else 'easy',
                knowledge_points_json=[f'{subject}-知识点{q%2+1}'],review_status='CONFIRMED',source='local_test',rights_basis='PROJECT_AUTHORED',rights_reference='014-synthetic'))
        for task_num in range(2):
            assignment_id=4000+sidx*10+task_num
            db.add(Assignment(id=assignment_id,class_id=1401,teacher_id=141,title=f'原创{subject}练习{task_num}',subject=subject,grade='grade7',status='published'))
            db.flush()
            for i in range(3):
                task_id=f'014-{subject}-{task_num}-{i}'
                db.add(HomeworkTask(task_id=task_id,user_id=151+i,student_id=2401+i,class_id=1401,assignment_id=assignment_id,
                         subject=subject,grade='grade7',status='SUCCESS',grading_mode='vision'))
                db.flush();image=HomeworkImage(task_id=task_id,original_url='synthetic-not-a-real-student-image.png',image_index=0);db.add(image);db.flush()
                for j in range(3):
                    q=task_num*3+j;asset_id=3000+sidx*100+q
                    block=QuestionBlock(task_id=task_id,question_no=str(j+1),question_image_url='synthetic.png',x1=0,y1=0,x2=100,y2=100,image_index=0)
                    db.add(block);db.flush()
                    wrong=subject=='math'
                    grade=GradingResult(task_id=task_id,question_block_id=block.id,question_no=str(j+1),score=0 if wrong else 5,max_score=5,result='wrong' if wrong else 'correct',
                              correct_answer='B',is_reviewed=True,reviewed_score=0 if wrong else 5,reviewer_id=141)
                    db.add(grade);db.flush()
                    source=QuestionAssetSource(question_asset_id=asset_id,source_task_id=task_id,source_image_id=image.id,grading_result_id=grade.id,page_index=0,question_no=str(j+1),
                        x1=0,y1=0,x2=100,y2=100,bbox_fingerprint=f'{task_id}-{j}',crop_locator='synthetic.png',provider_name='synthetic',provider_version='014',
                        link_status='CONFIRMED',review_status='CONFIRMED',reviewed_by=141,reviewed_at=datetime(2026,10,15,8,0,task_num*3+j))
                    db.add(source);db.flush()
                    if wrong:db.add(MistakeRecord(student_id=2401+i,assignment_id=assignment_id,question_asset_id=asset_id,question_asset_source_id=source.id,
                        source_task_id=task_id,source_grading_result_id=grade.id,detection_basis='teacher_confirmed',status='open'))
        for q in range(12):
            db.add(QuestionAsset(id=6000+sidx*100+q,subject=subject,grade='grade7',question_text=f'原创{subject}迁移练习{q+1}',question_type='单选题',options_json={'A':'1','B':'2','C':'3','D':'4'},
                correct_answer='B',analysis='独立专项题解析',difficulty='easy',knowledge_points_json=[f'{subject}-知识点{q%2+1}'],source='local_test',
                review_status='CONFIRMED',rights_basis='PROJECT_AUTHORED',rights_reference='014-own-synthetic'))
    db.flush()
    return teacher,other,parent

class Advice014Tests(unittest.TestCase):
    def setUp(self):
        EVIDENCE.mkdir(parents=True,exist_ok=True)
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.Session=sessionmaker(bind=self.engine,expire_on_commit=False)
        with self.Session.begin() as db:self.teacher,self.other,self.parent=seed(db)
        self.user=self.teacher
        def database():
            with self.Session() as db:yield db
        main.app.dependency_overrides[get_db]=database
        main.app.dependency_overrides[get_current_user]=lambda:self.user
        self.client=TestClient(main.app)
    def tearDown(self):
        main.app.dependency_overrides.clear();self.engine.dispose()
    def generate(self,subject='math',ids=None):
        response=self.client.post(f'/api/v1/learning-advice/classes/1401/{subject}/suggestions',json={'student_ids':ids or [2401]})
        self.assertEqual(response.status_code,200,response.text)
        return response.json()['suggestions'][0]

    def test_confirmed_evidence_three_students_three_subjects_and_exclusions(self):
        with self.Session() as db:
            for subject in ('math','physics','chemistry'):
                items=collect_evidence(db,1401,subject,[2401,2402,2403])
                for payload,_ in items.values():self.assertEqual(payload['unique_question_count'],6);self.assertEqual(payload['task_count'],2)
            baseline=collect_evidence(db,1401,'math',[2401])[2401]
            # Entire nonterminal/failed/known-unconfirmed tasks must not count.
            task=db.query(HomeworkTask).filter_by(task_id='014-math-0-0').one();task.status='WAIT_REVIEW';db.commit()
            self.assertEqual(collect_evidence(db,1401,'math',[2401])[2401][0]['unique_question_count'],3)
            for status in ('FAILED','UNKNOWN_LAYOUT'):
                task.status=status;db.commit();self.assertEqual(collect_evidence(db,1401,'math',[2401])[2401][0]['unique_question_count'],3)
            task.status='SUCCESS';task.grading_mode='known';db.commit()
            self.assertEqual(collect_evidence(db,1401,'math',[2401])[2401][0]['unique_question_count'],3)
            task.grading_mode='vision';grade=db.query(GradingResult).filter_by(task_id=task.task_id).first();grade.is_reviewed=False;db.commit()
            self.assertEqual(collect_evidence(db,1401,'math',[2401])[2401][0]['unique_question_count'],5)
            grade.is_reviewed=True;asset=db.get(QuestionAsset,3000);asset.review_status='PENDING_REVIEW';db.commit()
            self.assertEqual(collect_evidence(db,1401,'math',[2401])[2401][0]['unique_question_count'],5)
            empty=collect_evidence(db,1401,'math',[99999])[99999][0];self.assertEqual(empty['evidence_status'],'EVIDENCE_INSUFFICIENT')
            (EVIDENCE/'evidence-scope-sample.json').write_text(json.dumps(baseline[0],ensure_ascii=False,indent=2),encoding='utf-8')

    def test_teacher_only_accept_reject_adjust_idempotency_and_stale(self):
        math=self.generate();self.assertEqual(math['proposed_level'],'L1')
        physics=self.generate('physics');self.assertEqual(physics['proposed_level'],'L2')
        with self.Session() as db:self.assertEqual(db.query(StudentSubjectTier).filter_by(student_id=2401,subject='math').one().level,'L2')
        url=f"/api/v1/learning-advice/suggestions/{math['id']}/decision"
        body={'action':'ACCEPT','expected_level':'L2','reason':'教师核对基础题证据','request_key':'014-decision-accept'}
        response=self.client.post(url,json=body);self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.client.post(url,json=body).status_code,200)
        with self.Session() as db:
            self.assertEqual(db.query(SuggestionDecision).count(),1);self.assertEqual(db.query(StudentSubjectTierAudit).count(),1)
            self.assertEqual(db.query(StudentSubjectTier).filter_by(student_id=2401,subject='physics').one().level,'L1')
        adjusted=self.client.post(url,json={'action':'ADJUST','target_level':'L2','expected_level':'L1','reason':'教师复核撤回上次调整','request_key':'014-adjust-rollback'})
        self.assertEqual(adjusted.status_code,200,adjusted.text)
        reject=self.client.post(f"/api/v1/learning-advice/suggestions/{physics['id']}/decision",json={'action':'REJECT','expected_level':'L1','reason':'暂维持原练习','request_key':'014-reject-no-change'})
        self.assertEqual(reject.status_code,200,reject.text)
        with self.Session() as db:
            self.assertEqual(db.query(StudentSubjectTier).filter_by(student_id=2401,subject='physics').one().level,'L1')
            grade=db.query(GradingResult).filter_by(task_id='014-math-0-0').first();grade.is_reviewed=False;db.commit()
        stale=self.client.post(url,json={'action':'ADJUST','target_level':'L1','expected_level':'L2','reason':'不能复用旧证据','request_key':'014-stale-rejected'})
        self.assertEqual(stale.status_code,409,stale.text)
        with self.Session() as db:self.assertEqual(db.get(TierSuggestion,math['id']).status,'STALE')

    def test_not_based_on_submission_rate_and_duplicate_corrections(self):
        with self.Session() as db:
            baseline=collect_evidence(db,1401,'math',[2401])[2401]
            for i in range(8):db.add(Assignment(class_id=1401,teacher_id=141,title='未提交管理样本',subject='math',grade='grade7',status='published'))
            db.commit();after=collect_evidence(db,1401,'math',[2401])[2401]
            self.assertEqual(baseline,after)
            m=db.query(MistakeRecord).filter_by(student_id=2401).first()
            for i in range(3):db.add(PaperCorrectionAttempt(mistake_id=m.id,student_id=2401,attempt_type='text',submitted_answer='B',status='accepted',reviewed_by=141,reviewed_at=datetime(2026,10,15,9,i)))
            db.commit();after=collect_evidence(db,1401,'math',[2401])[2401]
            self.assertEqual(after[0]['unique_question_count'],6)
            self.assertEqual(after[0]['task_count'],2)

    def test_permissions_and_disabled_model(self):
        for user in (self.other,self.parent):
            self.user=user
            self.assertIn(self.client.get('/api/v1/learning-advice/classes/1401/math').status_code,[403,404])
        self.user=self.teacher
        with self.Session.begin() as db:db.query(ClassTeacher).filter_by(teacher_user_id=141).one().subject_codes_json=['math']
        self.assertEqual(self.client.post('/api/v1/learning-advice/classes/1401/physics/suggestions',json={'student_ids':[2401]}).status_code,403)
        self.assertEqual(self.client.post('/api/v1/learning-advice/classes/1401/math/suggestions',json={'student_ids':[99999]}).status_code,404)
        response=self.client.post('/api/v1/learning-advice/classes/1401/math/ai-proposal');self.assertEqual(response.status_code,409)
        self.assertEqual(response.json()['detail']['status'],'MODEL_NOT_RUN');self.assertFalse(response.json()['detail']['request_sent'])

    def test_practice_confirm_publish_target_scope_and_no_fake_questions(self):
        body={'student_ids':[2401],'count':1,'difficulty':'easy','request_key':'014-practice-create'}
        path='/api/v1/learning-advice/classes/1401/math/practices'
        response=self.client.post(path,json=body);self.assertEqual(response.status_code,200,response.text)
        practice=response.json();pid=practice['id'];planid=practice['plan']['id']
        self.assertEqual(self.client.post(path,json=body).json()['id'],pid)
        self.assertEqual(self.client.post(f'/api/v1/assignment-plans/{planid}/publish').status_code,409)
        self.assertEqual(self.client.put(f'/api/v1/learning-advice/practices/{pid}/questions',json={'asset_ids':[6006,6007,6008]}).status_code,200)
        self.assertEqual(self.client.post(f'/api/v1/learning-advice/practices/{pid}/publish',json={'confirmed':True}).status_code,409)
        confirm=self.client.post(f'/api/v1/learning-advice/practices/{pid}/confirm',json={'confirmed':True});self.assertEqual(confirm.status_code,200,confirm.text)
        response=self.client.post(f'/api/v1/learning-advice/practices/{pid}/publish',json={'confirmed':True});self.assertEqual(response.status_code,200,response.text)
        assignment_id=response.json()['assignment_id'];self.assertIsNotNone(assignment_id)
        self.assertEqual(self.client.post(f'/api/v1/learning-advice/practices/{pid}/publish',json={'confirmed':True}).json()['assignment_id'],assignment_id)
        with self.Session() as db:
            self.user=db.get(User,151)
        visible=self.client.get('/api/v1/assignments/mine?student_id=2401');self.assertEqual(visible.status_code,200,visible.text)
        self.assertTrue(any(a['id']==assignment_id for a in visible.json()['data']))
        for forbidden in ('L1','L2','L3','基础组','拔尖','建议降档'):
            self.assertNotIn(forbidden,visible.text)
        with self.Session() as db:self.user=db.get(User,152)
        visible=self.client.get('/api/v1/assignments/mine?student_id=2402');self.assertFalse(any(a['id']==assignment_id for a in visible.json()['data']))
        result=self.client.post('/api/v1/homework/analyze',data={'assignment_id':assignment_id,'student_id':2402,'subject':'math','grade':'grade7'},files={'files':('test.png',b'test','image/png')})
        self.assertEqual(result.status_code,403,result.text)
        self.user=self.teacher
        with self.Session.begin() as db:
            for a in db.query(QuestionAsset).filter(QuestionAsset.id>=6000).all():a.review_status='PENDING_REVIEW'
        response=self.client.post(path,json={**body,'request_key':'014-practice-insufficient'})
        self.assertEqual(response.status_code,409,response.text);self.assertEqual(response.json()['detail']['code'],'QUESTION_BANK_INSUFFICIENT')
        (EVIDENCE/'practice-published-sample.json').write_text(json.dumps(practice,ensure_ascii=False,default=str,indent=2),encoding='utf-8')

    def test_low_evidence_and_same_rate_different_difficulty_do_not_force_tiers(self):
        with self.Session.begin() as db:
            # Hard questions all wrong are not the basic-difficulty rule.
            for asset in db.query(QuestionAsset).filter(QuestionAsset.id.between(3000,3005)).all():asset.difficulty='hard'
        suggestion=self.generate()
        self.assertEqual(suggestion['proposed_level'],'L2')
        with self.Session.begin() as db:
            for grade in db.query(GradingResult).join(HomeworkTask,HomeworkTask.task_id==GradingResult.task_id).filter(HomeworkTask.student_id==2403,HomeworkTask.subject=='math').all():grade.is_reviewed=False
        insufficient=self.generate(ids=[2403]);self.assertEqual(insufficient['status'],'NEEDS_MORE_EVIDENCE');self.assertIsNone(insufficient['proposed_level'])
        response=self.client.post(f"/api/v1/learning-advice/suggestions/{insufficient['id']}/decision",json={'action':'ACCEPT','target_level':'L1','expected_level':'L2','reason':'样本不足不能生效','request_key':'014-insufficient-decision'})
        self.assertEqual(response.status_code,409)

    def test_snapshot_generation_idempotency_query_bound_and_additive_rollback(self):
        from sqlalchemy import event,text
        from scripts.migrate_014_additive import migrate,TABLES
        first=self.generate(ids=[2401,2402,2403]);again=self.generate(ids=[2401,2402,2403])
        self.assertEqual(first['id'],again['id'])
        with self.Session() as db:self.assertEqual(db.query(EvidenceSnapshot).count(),3)
        queries=[]
        def counted(conn,cursor,statement,parameters,context,executemany):
            if statement.lstrip().upper().startswith('SELECT'):queries.append(statement)
        event.listen(self.engine,'before_cursor_execute',counted)
        try:response=self.client.get('/api/v1/learning-advice/classes/1401/math')
        finally:event.remove(self.engine,'before_cursor_execute',counted)
        self.assertEqual(response.status_code,200,response.text);self.assertLessEqual(len(queries),25)
        (EVIDENCE/'overview-query-count.json').write_text(json.dumps({'students':3,'suggestions':3,'select_count':len(queries),'bound':25}),encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError,'nonempty'):migrate(self.engine,rollback=True)
        isolated=create_engine('sqlite://')
        try:
            Base.metadata.create_all(isolated)
            result=migrate(isolated);self.assertTrue(result['existing_rows_unchanged'])
            self.assertEqual(len(migrate(isolated)['tables']),4)
            self.assertEqual(migrate(isolated,rollback=True)['tables'],[])
        finally:isolated.dispose()

    def test_changed_asset_or_evidence_cannot_be_published_through_old_plan_routes(self):
        body={'student_ids':[2401],'count':1,'difficulty':'easy','request_key':'014-practice-stale-source'}
        response=self.client.post('/api/v1/learning-advice/classes/1401/math/practices',json=body)
        self.assertEqual(response.status_code,200,response.text)
        data=response.json();pid=data['id'];planid=data['plan']['id']
        # Generic 013 update cannot switch class/subject behind target binding.
        with self.Session.begin() as db:
            asset_id=data['plan']['variants'][0]['questions'][0]['source_asset_id']
            db.get(QuestionAsset,asset_id).correct_answer='D'
        self.assertEqual(self.client.post(f'/api/v1/assignment-plans/{planid}/confirm').status_code,409)
        self.assertEqual(self.client.post(f'/api/v1/learning-advice/practices/{pid}/confirm',json={'confirmed':True}).status_code,409)

    def test_existing_score_explicit_trust_confirmation_and_revocation(self):
        with self.Session.begin() as db:
            grade=db.query(GradingResult).filter_by(task_id='014-math-0-0').first();gid=grade.id;grade.is_reviewed=False
        rows=self.client.get('/api/v1/learning-advice/classes/1401/math/review-candidates').json()['items']
        item=next(r for r in rows if r['grade_id']==gid)
        url=f'/api/v1/learning-advice/grades/{gid}/evidence-review'
        body={'confirmed':True,'expected_version':item['version'],'reason':'教师逐题核对原分数可信','request_key':'014-evidence-confirm'}
        result=self.client.post(url,json=body);self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(self.client.post(url,json=body).status_code,200)
        suggestion=self.generate()
        item=next(r for r in self.client.get('/api/v1/learning-advice/classes/1401/math/review-candidates').json()['items'] if r['grade_id']==gid)
        result=self.client.post(url,json={'confirmed':False,'expected_version':item['version'],'reason':'教师撤销可信确认','request_key':'014-evidence-revoke'})
        self.assertEqual(result.status_code,200,result.text)
        overview=self.client.get('/api/v1/learning-advice/classes/1401/math').json()
        self.assertEqual(overview['students'][0]['suggestions'][0]['status'],'STALE')
        with self.Session.begin() as db:db.query(HomeworkTask).filter_by(task_id='014-math-0-0').one().grading_mode='known'
        self.assertEqual(self.client.post(url,json={**body,'request_key':'014-known-must-review'}).status_code,409)
