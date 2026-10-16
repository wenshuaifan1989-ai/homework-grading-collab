import runpy
import tempfile
import unittest
import importlib
from datetime import datetime, timedelta
from pathlib import Path
from tests.synthetic_fixtures import SYNTHETIC_IMAGE_PATH
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
from config import settings
from models.base import Base
from models.classroom import Assignment, Class, StudentRoster
from models.homework import GradingResult, HomeworkImage, HomeworkTask, OCRResult, QuestionBlock
from models.identity_relations import ClassTeacher, Student, StudentUserBinding
from models.paper import MistakeRecord, QuestionAssetSource
from models.model_usage import ModelCallAudit
from models.submission import HomeworkSubmissionKey
from models.user import User
from utils.database import get_db
from utils.deps import get_current_user


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = SYNTHETIC_IMAGE_PATH


class AdditiveMigration011Tests(unittest.TestCase):
    def test_only_new_tables_are_added_and_second_run_is_idempotent(self):
        migration = runpy.run_path(str(ROOT / "scripts" / "migrate_011_additive.py"))["migrate"]
        engine = create_engine("sqlite://")
        try:
            from models.paper import (
                MistakeRecord,
                PaperCorrectionAttempt,
                QuestionAsset,
                QuestionAssetSource,
                QuestionDigitizationRun,
            )

            new_tables = {
                QuestionAsset.__table__, QuestionAssetSource.__table__,
                QuestionDigitizationRun.__table__, MistakeRecord.__table__,
                PaperCorrectionAttempt.__table__,
            }
            Base.metadata.create_all(
                engine,
                tables=[table for table in Base.metadata.sorted_tables if table not in new_tables],
            )
            Session = sessionmaker(bind=engine)
            with Session.begin() as db:
                db.add(User(
                    id=11, username="migration-baseline", email="collab-test-010@example.invalid",
                    hashed_password="test-only-hashed-password-011", role="student", is_active=True,
                ))
            first = migration(engine)
            second = migration(engine)
            self.assertTrue(first["legacy_rows_unchanged"])
            self.assertTrue(second["legacy_rows_unchanged"])
            self.assertEqual(first["protected_rows_before"], first["protected_rows_after"])
            self.assertEqual(second["protected_rows_before"], second["protected_rows_after"])
            self.assertEqual(first["tables_present"], second["tables_present"])
            self.assertEqual(len(first["tables_present"]), 5)
        finally:
            engine.dispose()


class PaperWorkflowApi011Tests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.tmp = tempfile.TemporaryDirectory(prefix="paper-011-test-")
        self.old_upload_dir = settings.UPLOAD_DIR
        self.old_storage_provider = settings.STORAGE_PROVIDER
        self.old_feature_flag = settings.ENABLE_PAPER_DIGITIZATION
        settings.UPLOAD_DIR = self.tmp.name
        settings.STORAGE_PROVIDER = "local"
        settings.ENABLE_PAPER_DIGITIZATION = True
        self._seed()
        self.current_user = self.student_user

        def override_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        main.app.dependency_overrides[get_db] = override_db
        main.app.dependency_overrides[get_current_user] = lambda: self.current_user
        self.client = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()
        settings.UPLOAD_DIR = self.old_upload_dir
        settings.STORAGE_PROVIDER = self.old_storage_provider
        settings.ENABLE_PAPER_DIGITIZATION = self.old_feature_flag
        self.engine.dispose()
        self.tmp.cleanup()

    def _seed(self):
        db = self.Session()
        self.teacher = User(
            id=101, username="teacher011", email="collab-test-011@example.invalid",
            hashed_password="test-only-hashed-password-009", role="teacher", is_active=True,
        )
        self.student_user = User(
            id=102, username="student011", email="collab-test-012@example.invalid",
            hashed_password="test-only-hashed-password-009", role="student", is_active=True,
        )
        self.family_user = User(
            id=103, username="family011", email="collab-test-013@example.invalid",
            hashed_password="test-only-hashed-password-009", role="student", is_active=True,
        )
        self.unrelated_user = User(
            id=104, username="unrelated011", email="collab-test-014@example.invalid",
            hashed_password="test-only-hashed-password-009", role="student", is_active=True,
        )
        self.other_teacher = User(
            id=105, username="otherteacher011", email="collab-test-015@example.invalid",
            hashed_password="test-only-hashed-password-009", role="teacher", is_active=True,
        )
        self.admin = User(
            id=106, username="admin011", email="collab-test-016@example.invalid",
            hashed_password="test-only-hashed-password-009", role="admin", is_active=True,
        )
        self.student = Student(id=201, name="测试学生甲", status="active")
        self.classroom = Class(
            id=301, teacher_id=101, name="011 测试班", invite_code="TEST01101", status="active"
        )
        self.assignment = Assignment(
            id=401, class_id=301, teacher_id=101, title="样本数学练习",
            subject="math", grade="grade5", status="published",
        )
        self.task = HomeworkTask(
            id=501, task_id="task_paper_011_test", user_id=102,
            actor_user_id=102, student_id=201, class_id=301, assignment_id=401,
            subject="math", grade="grade5", status="SUCCESS", grading_mode="vision",
        )
        db.add_all([
            self.teacher, self.student_user, self.family_user, self.unrelated_user,
            self.other_teacher, self.admin, self.student, self.classroom,
            self.assignment, self.task,
        ])
        db.flush()
        db.add_all([
            ClassTeacher(id=601, class_id=301, teacher_user_id=101, role="owner", status="active"),
            StudentRoster(id=701, class_id=301, student_name="测试学生甲", student_no="011-01",
                          student_id=201, bound_user_id=102, status="active"),
            StudentUserBinding(id=801, student_id=201, user_id=102,
                               relationship_type="self", status="active"),
            StudentUserBinding(id=802, student_id=201, user_id=103,
                               relationship_type="mother", status="active"),
            HomeworkImage(id=901, task_id=self.task.task_id, original_url=str(SAMPLE), image_index=0),
            QuestionBlock(id=1001, task_id=self.task.task_id, question_no="1",
                          question_image_url=str(SAMPLE), x1=0, y1=0, x2=100, y2=80, image_index=0),
            QuestionBlock(id=1002, task_id=self.task.task_id, question_no="2",
                          question_image_url=str(SAMPLE), x1=0, y1=0, x2=100, y2=80, image_index=0),
            QuestionBlock(id=1003, task_id=self.task.task_id, question_no="3",
                          question_image_url=str(SAMPLE), x1=0, y1=0, x2=100, y2=80, image_index=0),
            OCRResult(id=1101, task_id=self.task.task_id, question_block_id=1001,
                      question_no="1", question_text="3 + 5 = ?", student_answer="8",
                      question_type="计算题", raw_response={}),
            OCRResult(id=1102, task_id=self.task.task_id, question_block_id=1002,
                      question_no="2", question_text="12 - 7 = ?", student_answer="6",
                      question_type="计算题", raw_response={}),
            OCRResult(id=1103, task_id=self.task.task_id, question_block_id=1003,
                      question_no="3", question_text="4 × 6 = ?", student_answer="24",
                      question_type="计算题", raw_response={}),
            GradingResult(id=1201, task_id=self.task.task_id, question_block_id=1001,
                          question_no="1", score=10, max_score=10, result="correct", confidence=0.99),
            GradingResult(id=1202, task_id=self.task.task_id, question_block_id=1002,
                          question_no="2", score=0, max_score=10, result="wrong", confidence=0.97,
                          correct_answer="5", analysis="12 减 7 等于 5", error_type="calculation_error"),
            GradingResult(id=1203, task_id=self.task.task_id, question_block_id=1003,
                          question_no="3", score=10, max_score=10, result="correct", confidence=0.99),
        ])
        db.commit()
        db.close()

    def test_cut_review_wrong_question_family_scope_correction_and_original_evidence(self):
        self.current_user = self.teacher
        first = self.client.post("/api/v1/paper/tasks/task_paper_011_test/digitize")
        self.assertEqual(first.status_code, 200, first.text)
        payload = first.json()["data"]
        self.assertGreaterEqual(len(payload["sources"]), 3)
        self.assertEqual(payload["accuracy_status"], "PENDING_REVIEW")
        q2 = min(payload["sources"], key=lambda row: abs(row["bbox"]["y1"] - 483))
        self.assertLess((q2["bbox"]["x2"] - q2["bbox"]["x1"]) *
                        (q2["bbox"]["y2"] - q2["bbox"]["y1"]), 1800 * 1050 * 0.95)

        second = self.client.post("/api/v1/paper/tasks/task_paper_011_test/digitize")
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(len(second.json()["data"]["sources"]), len(payload["sources"]))
        with self.Session() as db:
            self.assertEqual(db.query(QuestionAssetSource).count(), len(payload["sources"]))

        reviewed = self.client.patch(
            f"/api/v1/paper/sources/{q2['source_id']}/review",
            json={
                "grading_result_id": 1202,
                "question_no": "2",
                "question_text": "12 - 7 = ?",
                "question_type": "计算题",
                "manual_wrong": None,
                "confirm": True,
            },
        )
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        mistake_id = reviewed.json()["data"]["mistake_id"]
        self.assertIsNotNone(mistake_id, reviewed.text)
        duplicate_review = self.client.patch(
            f"/api/v1/paper/sources/{q2['source_id']}/review",
            json={
                "grading_result_id": 1202,
                "question_no": "2",
                "question_text": "12 - 7 = ?",
                "question_type": "计算题",
                "manual_wrong": None,
                "confirm": True,
            },
        )
        self.assertEqual(duplicate_review.status_code, 200, duplicate_review.text)
        self.assertEqual(duplicate_review.json()["data"]["mistake_id"], mistake_id)
        with self.Session() as db:
            self.assertEqual(db.query(MistakeRecord).filter_by(student_id=201).count(), 1)

        # Student and an actively bound family account see only this Student entity.
        self.current_user = self.student_user
        own = self.client.get("/api/v1/paper/students/201/mistakes")
        self.assertEqual(own.status_code, 200, own.text)
        self.assertEqual(len(own.json()["data"]["items"]), 1)
        self.current_user = self.family_user
        family = self.client.get("/api/v1/paper/students/201/mistakes")
        self.assertEqual(family.status_code, 200, family.text)
        self.current_user = self.unrelated_user
        blocked = self.client.get("/api/v1/paper/students/201/mistakes")
        self.assertEqual(blocked.status_code, 404)
        blocked_image = self.client.get(f"/api/v1/paper/mistakes/{mistake_id}/image?kind=original")
        self.assertEqual(blocked_image.status_code, 404)

        self.current_user = self.family_user
        crop = self.client.get(f"/api/v1/paper/mistakes/{mistake_id}/image?kind=crop")
        original = self.client.get(f"/api/v1/paper/mistakes/{mistake_id}/image?kind=original")
        self.assertEqual(crop.status_code, 200)
        self.assertEqual(original.status_code, 200)
        self.assertTrue(crop.content.startswith(b"\xff\xd8"))
        self.assertEqual(original.content, SAMPLE.read_bytes())

        correction = self.client.post(
            f"/api/v1/paper/mistakes/{mistake_id}/corrections",
            json={"answer": "5", "note": "重新计算并订正"},
        )
        self.assertEqual(correction.status_code, 200, correction.text)
        attempt_id = correction.json()["data"]["attempt_id"]
        history = self.client.get(f"/api/v1/paper/mistakes/{mistake_id}/history")
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual(len(history.json()["data"]["items"]), 1)

        self.current_user = self.teacher
        class_items = self.client.get("/api/v1/paper/classes/301/mistakes")
        self.assertEqual(class_items.status_code, 200, class_items.text)
        self.assertEqual(len(class_items.json()["data"]["items"]), 1)
        reviewed_attempt = self.client.post(
            f"/api/v1/paper/mistakes/{mistake_id}/corrections/{attempt_id}/review",
            json={"accepted": True, "feedback": "订正正确"},
        )
        self.assertEqual(reviewed_attempt.status_code, 200, reviewed_attempt.text)

        self.current_user = self.other_teacher
        cross_class = self.client.get("/api/v1/paper/classes/301/mistakes")
        self.assertEqual(cross_class.status_code, 404)
        self.current_user = self.admin
        admin_bulk = self.client.get("/api/v1/paper/classes/301/mistakes")
        self.assertEqual(admin_bulk.status_code, 404)
        admin_student = self.client.get("/api/v1/paper/students/201/mistakes")
        self.assertEqual(admin_student.status_code, 404)

    def test_low_confidence_wrong_is_not_automatically_added(self):
        self.current_user = self.teacher
        cut = self.client.post("/api/v1/paper/tasks/task_paper_011_test/digitize").json()["data"]["sources"]
        q2 = min(cut, key=lambda row: abs(row["bbox"]["y1"] - 483))
        # The model result is deliberately lowered for this test; no automatic mistake may be created.
        with self.Session.begin() as db:
            db.query(GradingResult).filter_by(id=1202).update({"confidence": 0.42})
        response = self.client.patch(
            f"/api/v1/paper/sources/{q2['source_id']}/review",
            json={"grading_result_id": 1202, "question_text": "12 - 7 = ?", "confirm": True},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["data"]["mistake_created"])
        self.assertIn("requires_teacher_confirmation", response.json()["data"]["mistake_status_reason"])
        with self.Session() as db:
            self.assertEqual(db.query(MistakeRecord).count(), 0)

    def test_duplicate_question_number_stays_unlinked_for_teacher_choice(self):
        routes = importlib.import_module("app.v1.paper")
        self.current_user = self.teacher
        with self.Session.begin() as db:
            db.add(QuestionBlock(
                id=1004, task_id=self.task.task_id, question_no="2",
                question_image_url=str(SAMPLE), x1=0, y1=0, x2=100, y2=80, image_index=0,
            ))
            db.add(GradingResult(
                id=1204, task_id=self.task.task_id, question_block_id=1004,
                question_no="2", score=5, max_score=10, result="partial", confidence=0.9,
            ))
        candidate = {"x1": 300, "y1": 420, "x2": 900, "y2": 530, "question_no": "2"}
        with patch.object(routes.paper_digitize_provider, "locate_regions", return_value=[candidate]):
            response = self.client.post("/api/v1/paper/tasks/task_paper_011_test/digitize")
        self.assertEqual(response.status_code, 200, response.text)
        sources = response.json()["data"]["sources"]
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["question_no"], "2")
        self.assertEqual(sources[0]["link_status"], "UNLINKED")
        self.assertIsNone(sources[0]["grading_result"])

    def test_confirmed_question_asset_is_shared_but_mistakes_are_student_scoped(self):
        self.current_user = self.teacher
        first_sources = self.client.post(
            "/api/v1/paper/tasks/task_paper_011_test/digitize"
        ).json()["data"]["sources"]
        first_source = min(first_sources, key=lambda row: abs(row["bbox"]["y1"] - 483))
        first_review = self.client.patch(
            f"/api/v1/paper/sources/{first_source['source_id']}/review",
            json={
                "grading_result_id": 1202,
                "question_no": "2",
                "question_text": "12 - 7 = ?",
                "question_type": "计算题",
                "manual_wrong": None,
                "confirm": True,
            },
        )
        self.assertEqual(first_review.status_code, 200, first_review.text)
        first_asset_id = first_review.json()["data"]["source"]["asset_id"]

        with self.Session.begin() as db:
            user = User(
                id=107, username="student011b", email="collab-test-017@example.invalid",
                hashed_password="test-only-hashed-password-009", role="student", is_active=True,
            )
            student = Student(id=202, name="测试学生乙", status="active")
            task = HomeworkTask(
                id=502, task_id="task_paper_011_student2", user_id=107,
                actor_user_id=107, student_id=202, class_id=301, assignment_id=401,
                subject="math", grade="grade5", status="SUCCESS", grading_mode="vision",
            )
            db.add_all([
                user, student, task,
                StudentRoster(id=702, class_id=301, student_name="测试学生乙", student_no="011-02",
                              student_id=202, bound_user_id=107, status="active"),
                StudentUserBinding(id=803, student_id=202, user_id=107,
                                   relationship_type="self", status="active"),
                HomeworkImage(id=902, task_id=task.task_id, original_url=str(SAMPLE), image_index=0),
                QuestionBlock(id=2001, task_id=task.task_id, question_no="2",
                              question_image_url=str(SAMPLE), x1=0, y1=0, x2=100, y2=80, image_index=0),
                OCRResult(id=2101, task_id=task.task_id, question_block_id=2001,
                          question_no="2", question_text="12 - 7 = ?", student_answer="6",
                          question_type="计算题", raw_response={}),
                GradingResult(id=2202, task_id=task.task_id, question_block_id=2001,
                              question_no="2", score=0, max_score=10, result="wrong", confidence=0.97,
                              correct_answer="5", analysis="12 减 7 等于 5"),
            ])

        second_sources = self.client.post(
            "/api/v1/paper/tasks/task_paper_011_student2/digitize"
        ).json()["data"]["sources"]
        second_source = min(second_sources, key=lambda row: abs(row["bbox"]["y1"] - 483))
        second_review = self.client.patch(
            f"/api/v1/paper/sources/{second_source['source_id']}/review",
            json={
                "grading_result_id": 2202,
                "question_no": "2",
                "question_text": "12 - 7 = ?",
                "question_type": "计算题",
                "manual_wrong": None,
                "confirm": True,
            },
        )
        self.assertEqual(second_review.status_code, 200, second_review.text)
        self.assertEqual(second_review.json()["data"]["source"]["asset_id"], first_asset_id)
        self.assertNotEqual(second_review.json()["data"]["mistake_id"], first_review.json()["data"]["mistake_id"])
        with self.Session() as db:
            records = db.query(MistakeRecord).order_by(MistakeRecord.student_id).all()
            self.assertEqual([row.student_id for row in records], [201, 202])
            self.assertEqual({row.question_asset_id for row in records}, {first_asset_id})

        self.current_user = User(id=107, username="student011b", email="collab-test-017@example.invalid",
                                 hashed_password="test-only-hashed-password-009", role="student", is_active=True)
        own = self.client.get("/api/v1/paper/students/202/mistakes")
        self.assertEqual(own.status_code, 200, own.text)
        self.assertEqual(len(own.json()["data"]["items"]), 1)

    def test_independent_photo_submission_is_student_scoped_and_idempotent(self):
        self.current_user = self.student_user
        headers = {"Idempotency-Key": "test-independent-submit-011"}
        with patch("app.v1.homework.process_homework_task.delay") as enqueue:
            responses = []
            for _ in range(2):
                with SAMPLE.open("rb") as image:
                    responses.append(self.client.post(
                        "/api/v1/homework/analyze",
                        data={
                            "subject": "math", "grade": "grade7", "mode": "vision",
                            "student_id": "201",
                        },
                        files={"files": ("practice.png", image, "image/png")},
                        headers=headers,
                    ))
            self.assertEqual(responses[0].status_code, 200, responses[0].text)
            self.assertEqual(responses[1].status_code, 200, responses[1].text)
            self.assertEqual(responses[0].json()["data"]["task_id"], responses[1].json()["data"]["task_id"])
            self.assertTrue(responses[1].json()["data"]["idempotent_replay"])
            enqueue.assert_called_once()

        task_id = responses[0].json()["data"]["task_id"]
        with self.Session() as db:
            task = db.query(HomeworkTask).filter_by(task_id=task_id).one()
            self.assertIsNone(task.assignment_id)
            self.assertIsNone(task.class_id)
            self.assertEqual(task.student_id, 201)
            self.assertEqual(db.query(HomeworkImage).filter_by(task_id=task_id).count(), 1)

        with SAMPLE.open("rb") as image:
            denied = self.client.post(
                "/api/v1/homework/analyze",
                data={"subject": "math", "grade": "grade7", "mode": "vision", "student_id": "202"},
                files={"files": ("practice.png", image, "image/png")},
            )
        self.assertEqual(denied.status_code, 403, denied.text)

    def test_stale_worker_recovery_requires_confirmation_and_is_single_use(self):
        with self.Session.begin() as db:
            task = db.query(HomeworkTask).filter_by(task_id=self.task.task_id).one()
            task.status = "GRADING"
            task.updated_at = datetime.utcnow() - timedelta(minutes=10)
            db.add(ModelCallAudit(
                call_id="stale-worker-call-011",
                task_id=task.task_id,
                attempt_no=1,
                provider="test-provider",
                model_name="test-vision-model",
                status="reserved",
            ))

        status = self.client.get(f"/api/v1/homework/status/{self.task.task_id}")
        self.assertEqual(status.status_code, 200, status.text)
        self.assertTrue(status.json()["data"]["can_retry"])
        self.assertEqual(status.json()["data"]["failure_code"], "WORKER_STATE_STALE_OUTCOME_UNKNOWN")

        with patch("app.v1.homework.process_homework_task.delay") as enqueue:
            recovered = self.client.post(
                f"/api/v1/homework/retry/{self.task.task_id}",
                json={"confirm_possible_duplicate_charge": True},
            )
            self.assertEqual(recovered.status_code, 200, recovered.text)
            self.assertTrue(recovered.json()["data"]["recovered_stale_worker"])
            enqueue.assert_called_once()
            second = self.client.post(
                f"/api/v1/homework/retry/{self.task.task_id}",
                json={"confirm_possible_duplicate_charge": True},
            )
            self.assertEqual(second.status_code, 409, second.text)
            enqueue.assert_called_once()

        with self.Session() as db:
            task = db.query(HomeworkTask).filter_by(task_id=self.task.task_id).one()
            audit = db.query(ModelCallAudit).filter_by(call_id="stale-worker-call-011").one()
            self.assertEqual(task.status, "PENDING")
            self.assertEqual(audit.status, "outcome_unknown")
            self.assertEqual(audit.error_code, "WORKER_STATE_STALE_OUTCOME_UNKNOWN")

    def test_failed_upload_rolls_back_then_marks_idempotency_record_failed(self):
        self.current_user = self.student_user
        with patch(
            "app.v1.homework.task_service.create_task_with_images",
            side_effect=RuntimeError("deterministic local persistence failure"),
        ):
            with SAMPLE.open("rb") as image:
                response = self.client.post(
                    "/api/v1/homework/analyze",
                    data={"subject": "math", "grade": "grade7", "mode": "vision", "student_id": "201"},
                    files={"files": ("practice.png", image, "image/png")},
                    headers={"Idempotency-Key": "test-failed-submit-011"},
                )
        self.assertEqual(response.status_code, 500, response.text)
        with self.Session() as db:
            record = db.query(HomeworkSubmissionKey).filter_by(
                user_id=self.student_user.id, request_key="test-failed-submit-011"
            ).one()
            self.assertEqual(record.status, "FAILED")


if __name__ == "__main__":
    unittest.main()
