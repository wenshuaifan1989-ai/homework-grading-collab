import hashlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from tests.synthetic_fixtures import synthetic_reference_pdf
from unittest.mock import patch

from PIL import Image
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect, text

from tests.test_013_assignment_plans import AssignmentPlan013Tests
from config import settings
from models.teacher_v2 import PaperBatch, PaperDocument, AssignmentPublication
from models.classroom import Assignment, Class
from models.learning import AssignmentVariant
from scripts.migrate_v2_001_additive import migrate
from services.teacher_v2 import publication_for, student_fields, optional_unanswered


class V2Tests(unittest.TestCase):
    def test_daily_calendar_waiting_review_is_not_failed_or_final_score(self):
        from types import SimpleNamespace
        from services.dashboard_service import _student_rows
        roster=SimpleNamespace(id=999,student_id=888,student_name='虚构',student_no=None,bound_user_id=777)
        task=SimpleNamespace(student_id=888,user_id=777,task_id='qa-review',status='WAIT_REVIEW',total_score=20)
        row=_student_rows([roster],{('student',888):task},{888})[0]
        self.assertEqual(row['submission_status_label'],'待教师复核')
        self.assertIsNone(row['score'])
        task.status='SUCCESS'
        self.assertEqual(_student_rows([roster],{('student',888):task},{888})[0]['score'],20)

    def setUp(self):
        AssignmentPlan013Tests.setUp(self)
        self.temp = tempfile.TemporaryDirectory()
        self.upload_patch = patch.object(settings, 'UPLOAD_DIR', self.temp.name)
        self.upload_patch.start()
        image = io.BytesIO()
        Image.new('RGB', (48, 48), 'white').save(image, 'PNG')
        self.image = image.getvalue()

    def tearDown(self):
        self.upload_patch.stop()
        self.temp.cleanup()
        AssignmentPlan013Tests.tearDown(self)

    def upload(self, key='batch-test-0001', count=1):
        return self.client.post('/api/v1/teacher-v2/batches',
            headers={'Idempotency-Key':key},
            data={'rights_confirmed':'true','attributes':'{"subject":"math","grade":"grade7","difficulty":"easy"}'},
            files=[('files',(f'paper-{i}.png', self.image, 'image/png')) for i in range(count)])

    def paper(self):
        result = self.upload()
        self.assertEqual(result.status_code, 200, result.text)
        paper = result.json()['papers'][0]
        asset = self.client.post('/api/v1/teacher-v2/assets', json={
            'subject':'math','grade':'grade7','question_text':'一加一等于（ ）',
            'options':{'A':'1','B':'2','C':'3','D':'4'},'correct_answer':'B',
            'analysis':'1+1=2','difficulty':'hard','knowledge_points':['加法'], 'confirmed':True})
        self.assertEqual(asset.status_code, 200, asset.text)
        edit = self.client.put(f"/api/v1/teacher-v2/papers/{paper['id']}",json={
            'expected_revision':paper['revision'],'title':'V2原卷',
            'attributes':{'difficulty':'medium','catalog_version':'test-v1'},
            'questions':[{'asset_id':asset.json()['asset_id'],'number':'6','max_score':10,
                          'overrides':{'difficulty':'hard'}}]})
        self.assertEqual(edit.status_code, 200, edit.text)
        paper = edit.json()
        confirmed = self.client.post(f"/api/v1/teacher-v2/papers/{paper['id']}/confirm")
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        return confirmed.json()

    def publish(self, paper, **changes):
        body = {'request_key':'publication-test-0001','expected_revision':paper['revision'],
            'class_id':3013,'title':'V2混合卷','assignment_date':'2026-10-16',
            'confirmed':True,'requirements':[{'student_id':2013,'number':'6',
                'requirement':'optional','reason':'教师手动覆盖，与难度无关'}]}
        body.update(changes)
        return self.client.post(f"/api/v1/teacher-v2/papers/{paper['id']}/publish", json=body)

    def test_three_files_are_three_papers_and_retry_is_idempotent(self):
        first = self.upload(count=3)
        self.assertEqual(first.status_code,200,first.text)
        second = self.upload(count=3)
        self.assertEqual(first.json(),second.json())
        self.assertEqual(len(first.json()['papers']),3)
        self.assertEqual(self.upload(count=2).status_code,409)
        with self.Session() as db:
            self.assertEqual(db.query(PaperBatch).count(),1)
            self.assertEqual(db.query(PaperDocument).count(),3)

    def test_inheritance_snapshot_same_variant_and_optional_no_student_labels(self):
        p=self.paper(); r=self.publish(p)
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.publish(p).json(),r.json())
        with self.Session() as db:
            pub=publication_for(db,r.json()['assignment_id'])
            q=pub.snapshot['questions'][0]
            self.assertEqual(q['attributes']['difficulty'],'hard')
            self.assertEqual(q['attribute_sources']['difficulty'],'question')
            self.assertEqual(q['attributes']['catalog_version'],'test-v1')
            self.assertEqual(db.query(AssignmentVariant).filter_by(assignment_id=pub.assignment_id).count(),1)
            fields=student_fields(pub,2013)
            self.assertEqual(fields['assignment_mode'],'uniform_mixed')
            self.assertEqual(fields['variant_questions'][0]['requirement_label'],'选做')
            self.assertNotIn('correct_answer',str(fields))
            self.assertNotIn('L1',str(fields))
            task=type('Task',(),{'assignment_id':pub.assignment_id,'student_id':2013})()
            self.assertTrue(optional_unanswered(db,task,'6','BLANK'))
            self.assertFalse(optional_unanswered(db,task,'6','A'))

    def test_published_snapshot_survives_draft_edit_and_hash_tamper_blocks(self):
        p=self.paper(); r=self.publish(p); self.assertEqual(r.status_code,200,r.text)
        self.client.put(f"/api/v1/teacher-v2/papers/{p['id']}",json={
            'expected_revision':p['revision'],'title':'后续草稿','attributes':{},'questions':[]})
        with self.Session.begin() as db:
            pub=publication_for(db,r.json()['assignment_id'])
            self.assertEqual(pub.snapshot['questions'][0]['number'],'6')
            db.execute(text('UPDATE v2_assignment_publication SET snapshot_sha256=:bad WHERE id=:id'),
                       {'bad':'0'*64,'id':pub.id})
        with self.Session() as db:
            with self.assertRaises(HTTPException):publication_for(db,r.json()['assignment_id'])

    def test_publication_is_immutable(self):
        p=self.paper();r=self.publish(p)
        with self.Session() as db:
            pub=publication_for(db,r.json()['assignment_id']);pub.mode='legacy'
            with self.assertRaises(ValueError):db.flush()

    def test_owner_student_and_subject_negative(self):
        p=self.paper()
        self.current_user=self.other_teacher
        self.assertEqual(self.client.get(f"/api/v1/teacher-v2/papers/{p['id']}").status_code,404)
        self.assertEqual(self.client.get('/api/v1/teacher-v2/papers').json()['items'],[])
        self.current_user=self.student_user
        self.assertEqual(self.client.get('/api/v1/teacher-v2/papers').status_code,403)
        self.current_user=self.teacher
        with self.Session.begin() as db:
            db.add(Class(id=3014,teacher_id=133,name='他人班',invite_code='V2-OTHER',grade='grade7',status='active'))
        self.assertIn(self.publish(p,class_id=3014).status_code,(403,404))
        self.assertEqual(self.publish(p,requirements=[{'student_id':9999,'number':'6','requirement':'optional','reason':'越权'}]).status_code,422)

    def test_empty_dashboard_has_null_rates_not_zero(self):
        p=self.paper();r=self.publish(p);self.assertEqual(r.status_code,200,r.text)
        a=r.json()['assignment_id']
        dashboard=self.client.get(f'/api/v1/teacher-v2/assignments/{a}/dashboard')
        self.assertEqual(dashboard.status_code,200,dashboard.text)
        d=dashboard.json();self.assertEqual(d['counts']['expected'],1)
        self.assertEqual(d['counts']['unsubmitted'],1)
        self.assertIsNone(d['questions'][0]['wrong_rate'])
        self.assertIsNone(d['students'][0]['required_completion'])
        self.current_user=self.other_teacher
        self.assertIn(self.client.get(f'/api/v1/teacher-v2/assignments/{a}/dashboard').status_code,(403,404))

    def test_original_hash_and_authenticated_preview(self):
        p=self.paper()
        response=self.client.get(f"/api/v1/teacher-v2/papers/{p['id']}/source")
        self.assertEqual(hashlib.sha256(response.content).hexdigest(),p['source_sha256'])
        with self.Session() as db:
            path=Path(db.get(PaperDocument,p['id']).source_locator)
        path.write_bytes(b'changed')
        self.assertEqual(self.publish(p).status_code,409)

    def test_unconfirmed_empty_and_corrupt_inputs_rejected(self):
        p=self.upload().json()['papers'][0]
        self.assertEqual(self.client.post(f"/api/v1/teacher-v2/papers/{p['id']}/confirm").status_code,409)
        self.assertEqual(self.publish(p).status_code,409)
        for name in ('bad.pdf','bad.doc','bad.png'):
            r=self.client.post('/api/v1/teacher-v2/batches',headers={'Idempotency-Key':'invalid-test'},
                data={'rights_confirmed':'true'},files=[('files',(name,b'not a valid file'))])
            self.assertIn(r.status_code,(415,422))

    def test_move_copy_and_revision_conflicts(self):
        p=self.paper();target=self.upload(key='batch-target-002').json()['papers'][0]
        body={'target_paper_id':target['id'],'number':'6','mode':'copy',
              'expected_source_revision':p['revision'],'expected_target_revision':target['revision']}
        copied=self.client.post(f"/api/v1/teacher-v2/papers/{p['id']}/transfer",json=body)
        self.assertEqual(copied.status_code,200,copied.text)
        self.assertEqual(copied.json()['target']['questions'][0]['number'],'6')
        self.assertEqual(self.client.post(f"/api/v1/teacher-v2/papers/{p['id']}/transfer",json=body).status_code,409)

    def test_subject_scoped_dashboard_calendar_and_global_denied(self):
        from datetime import date
        with self.Session.begin() as db:
            db.add(Assignment(id=9911,class_id=3013,teacher_id=131,title='数学可见',subject='math',grade='grade7',assignment_date=date(2026,10,16),status='published'))
            db.add(Assignment(id=9912,class_id=3013,teacher_id=133,title='物理不可见',subject='physics',grade='grade7',assignment_date=date(2026,10,16),status='published'))
        cal=self.client.get('/api/v1/classes/3013/calendar?month=2026-10')
        self.assertEqual(cal.status_code,200,cal.text)
        self.assertEqual(cal.json()['data']['dates'][0]['assignment_ids'],[9911])
        daily=self.client.get('/api/v1/classes/3013/daily-dashboard?date=2026-10-16')
        self.assertEqual(daily.status_code,200,daily.text)
        self.assertNotIn('物理不可见',daily.text)
        self.assertEqual(self.client.get('/api/v1/classes/3013/daily-dashboard?date=2026-10-16&assignment_id=9912').status_code,404)
        self.assertEqual(self.client.get('/api/v1/assignments/9912/questions/1/students').status_code,404)
        self.assertEqual(self.client.get('/api/v1/statistics/global').status_code,403)

    def test_catalog_reads_only_user_scope(self):
        from app.v1 import teacher_v2 as teacher_v2_routes
        catalog_path = Path(self.temp.name) / 'synthetic-catalog.jsonl'
        catalog_path.write_text(
            '{"id":"math-kp-001","raw_name":"合成数学知识点","path":"synthetic/math/001",'
            '"kind":"knowledge_point","subject":"数学"}\n',
            encoding='utf-8',
        )
        with patch.object(teacher_v2_routes, 'CATALOG', catalog_path):
            r=self.client.get('/api/v1/teacher-v2/catalog?subject=math')
            self.assertEqual(r.status_code,200,r.text)
            self.assertTrue(r.json()['items'])
            self.assertEqual(self.client.get('/api/v1/teacher-v2/catalog?subject=english').json()['items'],[])

    def test_prepare_unbound_roster_is_explicit_owner_only_and_idempotent(self):
        from models.classroom import StudentRoster
        from models.identity_relations import Student,StudentUserBinding
        with self.Session.begin() as db:
            db.add(StudentRoster(class_id=3013,student_name='未绑定甲',student_no='V2-A',status='active'))
            db.add(StudentRoster(class_id=3013,student_name='未绑定乙',student_no='V2-B',status='active'))
        r=self.client.post('/api/v1/teacher-v2/classes/3013/prepare-roster')
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['created'],2)
        self.assertEqual(self.client.post('/api/v1/teacher-v2/classes/3013/prepare-roster').json()['created'],0)
        with self.Session() as db:
            ids=[r[0] for r in db.query(StudentRoster.student_id).filter_by(class_id=3013)]
            self.assertEqual(len(set(ids)),3)
            self.assertNotIn(None,ids)
            self.assertEqual(db.query(StudentUserBinding).count(),1)
        self.current_user=self.other_teacher
        self.assertIn(self.client.post('/api/v1/teacher-v2/classes/3013/prepare-roster').status_code,(403,404))

    def test_insufficient_evidence_suggestion_does_not_change_requirements(self):
        p=self.paper()
        r=self.client.get(f"/api/v1/teacher-v2/papers/{p['id']}/suggest-requirements?class_id=3013")
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['requirements'],[])
        self.assertEqual(r.json()['default_requirement'],'required')

    def test_private_teacher_assets_not_readable_through_legacy_bank(self):
        from services.question_bank_provider import question_bank_provider
        p=self.paper();aid=p['questions'][0]['asset_id']
        with self.Session() as db:
            self.assertIsNotNone(question_bank_provider.get_question(db,aid,teacher_id=131))
            self.assertIsNone(question_bank_provider.get_question(db,aid,teacher_id=133))
            self.assertEqual(question_bank_provider.search_questions(db,subject='math',grade='grade7',teacher_id=133),[])
        self.current_user=self.other_teacher
        self.assertEqual(self.client.get('/api/v1/teacher-v2/papers').json()['items'],[])

    def test_pdf_docx_and_image_batch_container_contract(self):
        from app.v1.teacher_v2 import validate_file
        reference=synthetic_reference_pdf()
        self.assertEqual(validate_file('original.pdf',reference),'pdf')
        doc=io.BytesIO()
        with zipfile.ZipFile(doc,'w') as z:
            z.writestr('word/document.xml','<document><body><p>container fixture only</p></body></document>')
        r=self.client.post('/api/v1/teacher-v2/batches',headers={'Idempotency-Key':'format-batch-0001'},
            data={'rights_confirmed':'true'},files=[('files',('original.pdf',reference)),
              ('files',('fixture.docx',doc.getvalue())),('files',('fixture.png',self.image))])
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual([p['format'] for p in r.json()['papers']],['pdf','docx','png'])
        self.assertTrue(all(not p['ready'] for p in r.json()['papers']))

    def test_v2_original_template_cannot_be_replaced_by_generated_paper(self):
        p=self.paper();r=self.publish(p)
        a=r.json()['assignment_id']
        overview=self.client.get(f'/api/v1/known-assignments/assignments/{a}').json()
        variant=overview['variants'][0]
        self.assertEqual(variant['questions'][0]['number'],'6')
        self.assertEqual(self.client.post(f"/api/v1/known-assignments/variants/{variant['id']}/generate").status_code,409)
        replaced=self.client.post(f"/api/v1/known-assignments/variants/{variant['id']}/upload",files={'file':('other.png',b'changed')})
        self.assertEqual(replaced.status_code,409)
        legacy_edit=self.client.put(f'/api/v1/learning/assignments/{a}/variants',json={
            'allow_uniform_fallback':True,'uniform_fallback_level':'L1','variants':[
                {'level':level,'questions':[{'source_asset_id':p['questions'][0]['asset_id'],'max_score':10}]}
                for level in ('L1','L2','L3')]})
        self.assertEqual(legacy_edit.status_code,409,legacy_edit.text)
        self.assertEqual(self.client.get(f'/api/v1/learning/assignments/{a}/variants/L1/print.pdf').status_code,409)

    def test_migration_additive_idempotent_empty_rollback(self):
        e=create_engine('sqlite://')
        try:
            with e.begin() as c:
                c.execute(text('CREATE TABLE legacy_data (id INTEGER PRIMARY KEY)'))
                c.execute(text('INSERT INTO legacy_data VALUES (42)'))
            self.assertEqual(len(migrate(e)['created']),3)
            self.assertEqual(migrate(e)['created'],[])
            self.assertEqual(len(migrate(e,True)['removed']),3)
            with e.connect() as c:self.assertEqual(c.execute(text('SELECT id FROM legacy_data')).scalar_one(),42)
            self.upload()
            with self.assertRaises(ValueError):migrate(self.engine,True)
        finally:e.dispose()


if __name__=='__main__':unittest.main()


class V2KnownReviewTests(unittest.TestCase):
    """Synthetic pipeline contract; not real handwriting accuracy acceptance."""
    from tests.test_013_v01_known import Known013Tests as _known
    setUpBase=_known.setUpBase
    tearDownBase=_known.tearDownBase
    task=_known.task
    tearDown=_known.tearDown

    def setUp(self):
        self._known.setUp(self)
        from services.teacher_v2 import digest
        with self.Session.begin() as db:
            batch=PaperBatch(teacher_id=131,request_key='known-batch-test',request_hash='1'*64,attributes={})
            db.add(batch);db.flush()
            paper=PaperDocument(batch_id=batch.id,teacher_id=131,title='contract only',source_name='fixture.pdf',
                source_locator='not-used',source_sha256='2'*64,source_format='pdf',attributes={},questions=[])
            db.add(paper);db.flush()
            questions=[]
            from models.learning import AssignmentVariantQuestion
            for q in db.query(AssignmentVariantQuestion).filter_by(variant_id=1401).order_by(AssignmentVariantQuestion.sort_order):
                questions.append({'asset_id':q.source_asset_id,'variant_question_id':q.id,'number':str(q.sort_order),
                    'question_text':q.question_text,'options':q.options_json,'correct_answer':q.correct_answer,
                    'analysis':q.analysis,'max_score':5,'attributes':{'subject':'math','grade':'grade7',
                       'difficulty':'hard','knowledge_points':['发布冻结知识点'],'question_type':'choice'}})
            snap={'questions':questions,'requirements':{'2013':{str(i):{'requirement':'optional' if i==1 else 'required'} for i in range(1,9)}},'source_name':'fixture.pdf'}
            db.add(AssignmentPublication(assignment_id=1301,paper_id=paper.id,teacher_id=131,variant_id=1401,
                request_key='known-publish-test',request_hash='3'*64,snapshot=snap,snapshot_sha256=digest(snap)))

    def reviewed_task(self):
        from services.known_assignment_grading import process_known,apply_review
        from models.homework import HomeworkTask
        from models.known_assignment import ChoiceRead,QuestionPlacement
        self.task('v2-known-review')
        with self.Session() as db:
            process_known(db,'v2-known-review')
            task=db.query(HomeworkTask).filter_by(task_id='v2-known-review').one()
            self.assertEqual(task.status,'WAIT_REVIEW')
            rows=db.query(ChoiceRead).filter_by(task_id=task.task_id).all()
            self.assertTrue(all(r.status=='HOLD_REVIEW' for r in rows))
            for r in rows:
                number=db.get(QuestionPlacement,r.placement_id).question_number
                apply_review(db,task,r,131,'BLANK' if number=='1' else 'B','V2 synthetic contract review','initial-'+number)
            self.assertEqual(task.status,'SUCCESS')

    def test_optional_blank_review_reversal_no_mistake_and_denominator(self):
        from models.homework import HomeworkTask,GradingResult
        from models.known_assignment import ChoiceRead,QuestionPlacement
        from models.paper import MistakeRecord
        from services.known_assignment_grading import apply_review
        from services.teacher_v2_dashboard import build_dashboard
        self.reviewed_task()
        with self.Session() as db:
            a=db.get(Assignment,1301);d=build_dashboard(db,a)
            self.assertIsNone(d['questions'][0]['wrong_rate'])
            self.assertEqual(d['students'][0]['required_completion'],1)
            self.assertEqual(d['students'][0]['optional_done'],0)
            self.assertEqual(db.query(MistakeRecord).count(),0)
            task=db.query(HomeworkTask).filter_by(task_id='v2-known-review').one()
            read=db.query(ChoiceRead).join(QuestionPlacement,ChoiceRead.placement_id==QuestionPlacement.id).filter(QuestionPlacement.question_number=='1').one()
            apply_review(db,task,read,131,'A','teacher changes to wrong','optional-wrong')
            grade=db.get(GradingResult,read.grading_result_id)
            self.assertEqual(grade.max_score,5)
            self.assertEqual(build_dashboard(db,a)['questions'][0]['wrong_rate'],1)
            apply_review(db,task,read,131,'BLANK','teacher confirms non-participation','optional-blank')
            self.assertEqual(grade.max_score,0)
            self.assertEqual(db.query(MistakeRecord).one().status,'not_wrong')
            self.assertIsNone(build_dashboard(db,a)['questions'][0]['wrong_rate'])

    def test_frozen_knowledge_points_and_failed_latest_not_zero(self):
        from models.paper import QuestionAsset
        from models.homework import HomeworkTask
        from services.learning_advice import collect_evidence
        from services.teacher_v2_dashboard import build_dashboard
        self.reviewed_task()
        with self.Session() as db:
            db.query(QuestionAsset).update({'knowledge_points_json':['后续改动不应污染快照'],'difficulty':'easy'})
            db.commit()
            evidence=collect_evidence(db,3013,'math',[2013])[2013][0]
            self.assertTrue(evidence['sources'])
            self.assertTrue(all(s['knowledge_points']==['发布冻结知识点'] and s['difficulty']=='hard' for s in evidence['sources']))
            db.add(HomeworkTask(task_id='v2-failed-latest',user_id=132,student_id=2013,assignment_id=1301,class_id=3013,
                subject='math',grade='grade7',status='FAILED',grading_mode='known'))
            db.commit()
            d=build_dashboard(db,db.get(Assignment,1301))
            self.assertEqual(d['counts']['exceptions'],1)
            self.assertTrue(all(q['wrong_rate'] is None for q in d['questions']))

    def test_safe_recovery_does_not_overwrite_hold_or_confirmed_grades(self):
        from services.known_assignment_grading import recover_known
        from models.homework import GradingResult
        from models.known_assignment import ChoiceRead,ChoiceReviewAudit
        self.reviewed_task()
        with self.Session() as db:
            before=[(r.id,r.symbol,r.status,r.grading_result_id) for r in db.query(ChoiceRead)]
            audits=db.query(ChoiceReviewAudit).count()
            r=recover_known(db,'v2-known-review')
            self.assertEqual(r['recovered_pages'],0)
            self.assertEqual(r['paid_calls'],0)
            self.assertEqual(r['status'],'SUCCESS')
            self.assertEqual(before,[(r.id,r.symbol,r.status,r.grading_result_id) for r in db.query(ChoiceRead)])
            self.assertEqual(db.query(ChoiceReviewAudit).count(),audits)

    def test_partial_review_only_confirmed_question_flows_to_practice_no_original_reuse(self):
        from services.known_assignment_grading import process_known,apply_review
        from services.learning_advice import collect_evidence
        from models.homework import HomeworkTask
        from models.known_assignment import ChoiceRead,QuestionPlacement
        from models.paper import QuestionAsset
        from models.assignment_plan import AssignmentPlanQuestion
        self.task('v2-partial-review')
        with self.Session() as db:
            process_known(db,'v2-partial-review')
            task=db.query(HomeworkTask).filter_by(task_id='v2-partial-review').one()
            read=db.query(ChoiceRead).join(QuestionPlacement,ChoiceRead.placement_id==QuestionPlacement.id).filter(QuestionPlacement.question_number=='4').one()
            apply_review(db,task,read,131,'C','Only this clear answer confirmed','partial-4')
            self.assertEqual(task.status,'WAIT_REVIEW')
            payload=collect_evidence(db,3013,'math',[2013])[2013][0]
            self.assertEqual(len(payload['sources']),1)
            self.assertEqual(payload['sources'][0]['question_no'],'4')
            self.assertFalse(payload['sufficient'])
            for asset in db.query(QuestionAsset):
                asset.rights_basis='PROJECT_AUTHORED';asset.rights_reference='test-only'
                asset.difficulty='easy';asset.knowledge_points_json=['发布冻结知识点']
            for i in range(3):
                db.add(QuestionAsset(id=9010+i,subject='math',grade='grade7',question_text=f'New authorized practice {i}',
                    correct_answer='B',analysis='test explanation',question_type='choice',options_json={'A':'0','B':'1','C':'2','D':'3'},
                    source='PROJECT_AUTHORED',rights_basis='PROJECT_AUTHORED',rights_reference='test-only',
                    review_status='CONFIRMED',difficulty='easy',knowledge_points_json=['发布冻结知识点']))
            db.commit()
        response=self.client.post('/api/v1/learning-advice/classes/3013/math/practices',json={
            'student_ids':[2013],'count':1,'difficulty':'mixed','request_key':'v2-partial-practice'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['status'],'DRAFT')
        with self.Session() as db:
            ids={r[0] for r in db.query(AssignmentPlanQuestion.source_asset_id)}
            self.assertEqual(ids,{9010,9011,9012})
