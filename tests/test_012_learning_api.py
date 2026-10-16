import hashlib
import runpy
import tempfile
import unittest
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
from models.identity_relations import ClassTeacher, Student, StudentUserBinding
from models.learning import (
    AssignmentVariant,
    AssignmentVariantQuestion,
    AssignmentVariantSet,
    AssignmentVariantTask,
    StudentSubjectTier,
    StudentSubjectTierAudit,
)
from models.paper import QuestionAsset
from models.user import User
from utils.database import get_db
from utils.deps import get_current_user
from clients.vision_client import VisionClient
from tasks.homework_tasks import _apply_variant_grading_contract


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = SYNTHETIC_IMAGE_PATH


class LearningMigration012Tests(unittest.TestCase):
    def test_additive_migration_is_idempotent_and_preserves_legacy_rows(self):
        migrate = runpy.run_path(str(ROOT / "scripts" / "migrate_012_additive.py"))["migrate"]
        engine = create_engine("sqlite://")
        new_tables = {
            StudentSubjectTier.__table__, StudentSubjectTierAudit.__table__,
            AssignmentVariantSet.__table__, AssignmentVariant.__table__,
            AssignmentVariantQuestion.__table__, AssignmentVariantTask.__table__,
        }
        try:
            Base.metadata.create_all(
                engine,
                tables=[table for table in Base.metadata.sorted_tables if table not in new_tables],
            )
            Session = sessionmaker(bind=engine)
            with Session.begin() as db:
                db.add(User(
                    id=1, username="migration012", email="collab-test-018@example.invalid",
                    hashed_password="test-only-hashed-password-010", role="teacher", is_active=True,
                ))
            first = migrate(engine)
            second = migrate(engine)
            self.assertEqual(len(first["tables_present"]), 6)
            self.assertTrue(first["protected_rows_unchanged"])
            self.assertTrue(second["protected_rows_unchanged"])
            self.assertEqual(first["protected_rows_before"], first["protected_rows_after"])
            self.assertEqual(second["tables_present"], first["tables_present"])
        finally:
            engine.dispose()


class VariantGradingContract012Tests(unittest.TestCase):
    def test_prompt_carries_teacher_question_contract_without_changing_plain_grading(self):
        questions = [{
            "question_text": "已确认题目：8 × 7 = ?",
            "options": None,
            "correct_answer": "56",
            "analysis": "8 个 7 相加",
            "max_score": 6,
        }]
        prompt = VisionClient._assignment_variant_context(questions)
        self.assertIn("8 × 7", prompt)
        self.assertIn("\"correct_answer\":\"56\"", prompt)
        self.assertIn("\"max_score\":6.0", prompt)
        self.assertIn("不得增删题目", prompt)
        self.assertEqual(VisionClient._assignment_variant_context(None), "")

    def test_grading_result_is_bound_to_authoritative_question_and_score_contract(self):
        expected = [
            {"question_text": "教师题一", "correct_answer": "4", "analysis": "答案解释", "max_score": 6},
            {"question_text": "教师题二", "correct_answer": "9", "analysis": None, "max_score": 4},
        ]
        results = [
            {"question_no": "第2题", "question_text": "模型误识别", "score": 3, "max_score": 10, "accuracy": 30},
            {"question_no": "Q1", "question_text": "模型识别", "score": 6, "max_score": 10, "accuracy": 60},
        ]
        reconciled = _apply_variant_grading_contract(results, expected)
        self.assertEqual([row["question_text"] for row in reconciled], ["教师题一", "教师题二"])
        self.assertEqual([row["max_score"] for row in reconciled], [6.0, 4.0])
        self.assertEqual([row["accuracy"] for row in reconciled], [100.0, 75.0])
        self.assertEqual(reconciled[0]["correct_answer"], "4")
        self.assertEqual(reconciled[0]["analysis"], "答案解释")
        with self.assertRaisesRegex(ValueError, "题数"):
            _apply_variant_grading_contract(results[:1], expected)
        with self.assertRaisesRegex(ValueError, "超出"):
            _apply_variant_grading_contract(
                [{"question_no": "1", "score": 7}], expected[:1]
            )
        with self.assertRaisesRegex(ValueError, "重复"):
            _apply_variant_grading_contract(
                [{"question_no": "1"}, {"question_no": "Q1"}], expected[:2]
            )


class LearningApi012Tests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.temp = tempfile.TemporaryDirectory(prefix="learning-012-")
        self.old_upload_dir = settings.UPLOAD_DIR
        self.old_storage_provider = settings.STORAGE_PROVIDER
        settings.UPLOAD_DIR = self.temp.name
        settings.STORAGE_PROVIDER = "local"
        self._seed()
        self.current_user = self.teacher

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
        self.engine.dispose()
        self.temp.cleanup()

    def _seed(self):
        with self.Session.begin() as db:
            self.teacher = User(
                id=101, username="teacher012", email="collab-test-019@example.invalid",
                hashed_password="test-only-hashed-password-010", role="teacher", is_active=True,
            )
            self.student_users = [
                User(id=102, username="student012a", email="collab-test-020@example.invalid",
                     hashed_password="test-only-hashed-password-010", role="student", is_active=True),
                User(id=107, username="student012b", email="collab-test-021@example.invalid",
                     hashed_password="test-only-hashed-password-010", role="student", is_active=True),
                User(id=108, username="student012c", email="collab-test-022@example.invalid",
                     hashed_password="test-only-hashed-password-010", role="student", is_active=True),
                User(id=109, username="student012d", email="collab-test-023@example.invalid",
                     hashed_password="test-only-hashed-password-010", role="student", is_active=True),
            ]
            self.family = User(
                id=103, username="family012", email="collab-test-024@example.invalid",
                hashed_password="test-only-hashed-password-010", role="student", is_active=True,
            )
            self.other_teacher = User(
                id=105, username="teacher012-other", email="collab-test-025@example.invalid",
                hashed_password="test-only-hashed-password-010", role="teacher", is_active=True,
            )
            self.unrelated_teacher = User(
                id=106, username="teacher012-unrelated", email="collab-test-026@example.invalid",
                hashed_password="test-only-hashed-password-010", role="teacher", is_active=True,
            )
            self.students = [
                Student(id=201, name="分层测试甲", status="active"),
                Student(id=202, name="分层测试乙", status="active"),
                Student(id=203, name="分层测试丙", status="active"),
                Student(id=204, name="待分层测试丁", status="active"),
            ]
            self.classroom = Class(
                id=301, teacher_id=101, name="012隔离测试班", invite_code="TEST01201", status="active"
            )
            self.assignment = Assignment(
                id=401, class_id=301, teacher_id=101, title="同班分层数学练习",
                subject="math", grade="grade5", status="published",
            )
            db.add_all([
                self.teacher, *self.student_users, self.family, self.other_teacher,
                self.unrelated_teacher, *self.students, self.classroom, self.assignment,
                ClassTeacher(id=601, class_id=301, teacher_user_id=101, role="owner",
                            subject_codes_json=["math", "physics", "chemistry"], status="active"),
                ClassTeacher(id=602, class_id=301, teacher_user_id=105, role="collaborator",
                            subject_codes_json=["physics"], status="active"),
                QuestionAsset(
                    id=701, subject="math", grade="grade5", question_text="已确认资产题：8 × 7 = ?",
                    correct_answer="56", analysis="8 个 7 相加", review_status="CONFIRMED",
                    clean_image_status="PENDING_REVIEW", source="teacher_confirmed", asset_version="test-v1",
                ),
            ])
            for i, (student, account) in enumerate(zip(self.students, self.student_users)):
                db.add(StudentRoster(
                    id=801 + i, class_id=301, student_name=student.name,
                    student_no=f"012-{i + 1:02d}", student_id=student.id,
                    bound_user_id=account.id, status="active",
                ))
                db.add(StudentUserBinding(
                    id=901 + i, student_id=student.id, user_id=account.id,
                    relationship_type="self", status="active",
                ))
            db.add(StudentUserBinding(
                id=905, student_id=201, user_id=103, relationship_type="mother", status="active"
            ))

    def _save_tiers(self):
        return self.client.put(
            "/api/v1/learning/classes/301/tiers",
            json={"subject": "math", "entries": [
                {"student_id": 201, "level": "L3"},
                {"student_id": 202, "level": "L1"},
                {"student_id": 203, "level": "L2"},
            ]},
        )

    def _variant_payload(self, allow_fallback=False, fallback_level=None):
        return {
            "allow_uniform_fallback": allow_fallback,
            "uniform_fallback_level": fallback_level,
            "variants": [
                {"level": "L1", "questions": [
                    {"question_text": "基础巩固：36 ÷ 6 = ?", "correct_answer": "6", "max_score": 10}
                ]},
                {"level": "L2", "questions": [
                    {"source_asset_id": 701, "max_score": 10}
                ]},
                {"level": "L3", "questions": [
                    {"question_text": "拓展挑战：若 8x = 56，求 x。", "correct_answer": "7", "max_score": 10}
                ]},
            ],
        }

    def test_subject_tier_is_class_and_subject_scoped_audited_and_teacher_authorized(self):
        initial = self.client.get("/api/v1/learning/classes/301/tiers?subject=math")
        self.assertEqual(initial.status_code, 200, initial.text)
        self.assertTrue(all(row["level"] is None for row in initial.json()["data"]["students"]))

        saved = self._save_tiers()
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["data"]["changed_count"], 3)
        with self.Session() as db:
            self.assertEqual(db.query(StudentSubjectTierAudit).count(), 3)
            self.assertEqual(db.query(StudentSubjectTier).filter_by(student_id=201, subject="math").one().level, "L3")

        physics = self.client.put(
            "/api/v1/learning/classes/301/tiers",
            json={"subject": "physics", "entries": [{"student_id": 201, "level": "L1"}]},
        )
        self.assertEqual(physics.status_code, 200, physics.text)
        with self.Session() as db:
            levels = {(row.subject, row.level) for row in db.query(StudentSubjectTier).filter_by(student_id=201)}
            self.assertEqual(levels, {("math", "L3"), ("physics", "L1")})

        history = self.client.get(
            "/api/v1/learning/classes/301/tier-history?subject=math&student_id=201"
        )
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual(history.json()["data"]["items"][0]["to_level"], "L3")

        self.current_user = self.other_teacher
        denied_subject = self.client.get("/api/v1/learning/classes/301/tiers?subject=math")
        self.assertEqual(denied_subject.status_code, 403, denied_subject.text)
        allowed_subject = self.client.get("/api/v1/learning/classes/301/tiers?subject=physics")
        self.assertEqual(allowed_subject.status_code, 200, allowed_subject.text)
        self.current_user = self.unrelated_teacher
        no_class = self.client.get("/api/v1/learning/classes/301/tiers?subject=math")
        self.assertEqual(no_class.status_code, 404, no_class.text)

    def test_three_variants_are_real_content_private_to_student_and_server_bound_on_submission(self):
        self.assertEqual(self._save_tiers().status_code, 200)
        created = self.client.put(
            "/api/v1/learning/assignments/401/variants", json=self._variant_payload()
        )
        self.assertEqual(created.status_code, 200, created.text)
        variants = created.json()["data"]["variants"]
        self.assertEqual({row["level"] for row in variants}, {"L1", "L2", "L3"})
        self.assertEqual({row["questions"][0]["source_type"] for row in variants}, {"MANUAL", "ASSET"})

        seen_hashes = set()
        self.current_user = self.teacher
        for level in ("L1", "L2", "L3"):
            pdf = self.client.get(f"/api/v1/learning/assignments/401/variants/{level}/print.pdf")
            self.assertEqual(pdf.status_code, 200, pdf.text[:200])
            self.assertEqual(pdf.headers["content-type"], "application/pdf")
            self.assertTrue(pdf.content.startswith(b"%PDF-"))
            self.assertGreater(len(pdf.content), 1000)
            seen_hashes.add(hashlib.sha256(pdf.content).hexdigest())
        self.assertEqual(len(seen_hashes), 3)

        self.current_user = self.student_users[0]
        mine_a = self.client.get("/api/v1/assignments/mine?student_id=201")
        self.assertEqual(mine_a.status_code, 200, mine_a.text)
        assignment_a = mine_a.json()["data"][0]
        self.assertEqual(assignment_a["variant_questions"][0]["question_text"], "拓展挑战：若 8x = 56，求 x。")
        self.assertNotIn("level", assignment_a)
        self.assertNotIn("tier", assignment_a)
        self.assertNotIn("correct_answer", assignment_a["variant_questions"][0])

        self.current_user = self.student_users[1]
        mine_b = self.client.get("/api/v1/assignments/mine?student_id=202")
        self.assertEqual(mine_b.status_code, 200, mine_b.text)
        self.assertEqual(mine_b.json()["data"][0]["variant_questions"][0]["question_text"], "基础巩固：36 ÷ 6 = ?")

        self.current_user = self.student_users[2]
        mine_c = self.client.get("/api/v1/assignments/mine?student_id=203")
        self.assertEqual(mine_c.status_code, 200, mine_c.text)
        self.assertEqual(mine_c.json()["data"][0]["variant_questions"][0]["question_text"], "已确认资产题：8 × 7 = ?")

        self.current_user = self.family
        family_items = self.client.get("/api/v1/assignments/mine?student_id=201")
        self.assertEqual(family_items.status_code, 200, family_items.text)
        family_assignment = family_items.json()["data"][0]
        self.assertEqual(family_assignment["variant_questions"][0]["question_text"], assignment_a["variant_questions"][0]["question_text"])
        self.assertFalse(any(key in family_assignment for key in ("level", "tier", "variant_level")))

        self.current_user = self.student_users[3]
        unconfigured = self.client.get("/api/v1/assignments/mine?student_id=204")
        self.assertEqual(unconfigured.status_code, 200, unconfigured.text)
        self.assertFalse(unconfigured.json()["data"][0]["variant_available"])
        self.assertNotIn("L1", unconfigured.text)
        with SAMPLE.open("rb") as image, patch("app.v1.homework.process_homework_task.delay") as enqueue:
            blocked = self.client.post(
                "/api/v1/homework/analyze",
                data={"subject": "math", "grade": "grade5", "mode": "vision", "assignment_id": "401", "student_id": "204"},
                files={"files": ("p.png", image, "image/png")},
            )
        self.assertEqual(blocked.status_code, 409, blocked.text)
        enqueue.assert_not_called()

        self.current_user = self.student_users[0]
        with SAMPLE.open("rb") as image, patch("app.v1.homework.process_homework_task.delay") as enqueue:
            submitted = self.client.post(
                "/api/v1/homework/analyze",
                data={"subject": "math", "grade": "grade5", "mode": "vision", "assignment_id": "401", "student_id": "201"},
                files={"files": ("p.png", image, "image/png")},
                headers={"Idempotency-Key": "variant-submit-test-012"},
            )
            self.assertEqual(submitted.status_code, 200, submitted.text)
            enqueue.assert_called_once()
        task_id = submitted.json()["data"]["task_id"]
        with self.Session() as db:
            link = db.query(AssignmentVariantTask).filter_by(task_id=task_id).one()
            variant = db.query(AssignmentVariant).filter_by(id=link.variant_id).one()
            question = db.query(AssignmentVariantQuestion).filter_by(variant_id=variant.id).one()
            self.assertEqual(link.student_id, 201)
            self.assertEqual(variant.level, "L3")
            self.assertEqual(question.question_text, "拓展挑战：若 8x = 56，求 x。")

        with self.Session.begin() as db:
            tier = db.query(StudentSubjectTier).filter_by(student_id=201, class_id=301, subject="math").one()
            tier.level = "L1"
        held_variant = self.client.get("/api/v1/assignments/mine?student_id=201")
        self.assertEqual(held_variant.status_code, 200, held_variant.text)
        self.assertEqual(held_variant.json()["data"][0]["variant_questions"][0]["question_text"], "拓展挑战：若 8x = 56，求 x。")

    def test_teacher_controls_uniform_fallback_and_invalid_or_unreviewed_assets_are_rejected(self):
        self.assertEqual(self._save_tiers().status_code, 200)
        invalid = self._variant_payload()
        invalid["variants"][1]["questions"][0]["source_asset_id"] = 999
        rejected = self.client.put("/api/v1/learning/assignments/401/variants", json=invalid)
        self.assertEqual(rejected.status_code, 422, rejected.text)

        fallback = self._variant_payload(allow_fallback=True, fallback_level="L2")
        saved = self.client.put("/api/v1/learning/assignments/401/variants", json=fallback)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.current_user = self.student_users[3]
        items = self.client.get("/api/v1/assignments/mine?student_id=204")
        self.assertEqual(items.status_code, 200, items.text)
        self.assertTrue(items.json()["data"][0]["variant_available"])
        self.assertEqual(items.json()["data"][0]["variant_questions"][0]["question_text"], "已确认资产题：8 × 7 = ?")
        self.assertNotIn("L2", items.text)


if __name__ == "__main__":
    unittest.main()
