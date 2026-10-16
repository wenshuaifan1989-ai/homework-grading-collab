"""One isolated virtual-class journey across the 011 and 012 API/DB workflows.

The vision provider boundary is replaced with an explicit test fixture. This
proves persistence and downstream workflow wiring, not real-model accuracy.
"""

import importlib
import tempfile
import unittest
from pathlib import Path
from tests.synthetic_fixtures import SYNTHETIC_IMAGE_PATH
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
from config import settings
from models.base import Base
from models.classroom import StudentRoster
from models.homework import GradingResult, HomeworkTask
from models.learning import AssignmentVariant, AssignmentVariantTask
from models.paper import MistakeRecord
from models.user import User
from tasks import homework_tasks
from utils.database import get_db
from utils.deps import get_current_user


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = SYNTHETIC_IMAGE_PATH


class VirtualClassAcceptance011012Tests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.temp = tempfile.TemporaryDirectory(prefix="virtual-class-011012-")
        self.old_upload_dir = settings.UPLOAD_DIR
        self.old_storage_provider = settings.STORAGE_PROVIDER
        self.old_digitization = settings.ENABLE_PAPER_DIGITIZATION
        settings.UPLOAD_DIR = self.temp.name
        settings.STORAGE_PROVIDER = "local"
        settings.ENABLE_PAPER_DIGITIZATION = True
        self.users = {
            "teacher": User(id=5101, username="virtual-teacher-a", email="collab-test-001@example.invalid",
                             hashed_password="test-only-hashed-password-010", role="teacher", is_active=True),
            "collaborator": User(id=5102, username="virtual-teacher-b", email="collab-test-002@example.invalid",
                                 hashed_password="test-only-hashed-password-010", role="teacher", is_active=True),
            "s1": User(id=5111, username="virtual-student-1", email="collab-test-003@example.invalid",
                       hashed_password="test-only-hashed-password-010", role="student", is_active=True),
            "s2": User(id=5112, username="virtual-student-2", email="collab-test-004@example.invalid",
                       hashed_password="test-only-hashed-password-010", role="student", is_active=True),
            "s3": User(id=5113, username="virtual-student-3", email="collab-test-005@example.invalid",
                       hashed_password="test-only-hashed-password-010", role="student", is_active=True),
            "family": User(id=5121, username="virtual-family", email="collab-test-006@example.invalid",
                           hashed_password="test-only-hashed-password-010", role="student", is_active=True),
            "outsider": User(id=5131, username="virtual-outsider", email="collab-test-007@example.invalid",
                             hashed_password="test-only-hashed-password-010", role="student", is_active=True),
        }
        with self.Session.begin() as db:
            db.add_all(self.users.values())
        self.current_user = self.users["teacher"]

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
        settings.ENABLE_PAPER_DIGITIZATION = self.old_digitization
        self.engine.dispose()
        self.temp.cleanup()

    def _ok(self, response, expected=200):
        self.assertEqual(response.status_code, expected, response.text)
        return response.json().get("data")

    def _upload(self, assignment_id=None, student_id=None, key=None):
        body = {"subject": "math", "grade": "grade5", "mode": "vision"}
        if assignment_id is not None:
            body["assignment_id"] = str(assignment_id)
        if student_id is not None:
            body["student_id"] = str(student_id)
        headers = {"Idempotency-Key": key} if key else {}
        with SAMPLE.open("rb") as image:
            return self.client.post(
                "/api/v1/homework/analyze",
                data=body,
                files={"files": ("public-sample-math.png", image, "image/png")},
                headers=headers,
            )

    def test_single_virtual_class_journey_with_nonbillable_vision_boundary(self):
        # Teacher creates the class, enters a real roster, and invites a collaborator.
        self.current_user = self.users["teacher"]
        classroom = self._ok(self.client.post(
            "/api/v1/classes", json={"name": "011-012 虚拟综合验收班", "grade": "grade5"}
        ))
        class_id = classroom["id"]
        roster_ids = {}
        for index, name in enumerate(("验收学生甲", "验收学生乙", "验收学生丙"), start=1):
            roster = self._ok(self.client.post(
                f"/api/v1/classes/{class_id}/roster",
                json={"student_name": name, "student_no": f"VC-{index:02d}"},
            ))
            roster_ids[name] = roster["id"]

        invitation = self._ok(self.client.post(
            f"/api/v1/classes/{class_id}/contracts",
            json={"type": "TEACHER_CLASS_JOIN", "max_uses": 1},
        ))
        self.current_user = self.users["collaborator"]
        joined = self._ok(self.client.post(
            f"/api/v1/contracts/{invitation['code']}/claim", json={"subject_codes": ["math"]}
        ))
        self.assertTrue(joined["joined"])

        # Each student independently selects and binds their own roster record.
        student_ids = {}
        for key, name in (("s1", "验收学生甲"), ("s2", "验收学生乙"), ("s3", "验收学生丙")):
            self.current_user = self.users[key]
            options = self._ok(self.client.post(
                "/api/v1/students/binding-options",
                json={"invite_code": classroom["invite_code"], "student_name": name},
            ))
            self.assertEqual([row["id"] for row in options["students"]], [roster_ids[name]])
            bound = self._ok(self.client.post(
                "/api/v1/students/bind",
                json={"invite_code": classroom["invite_code"], "student_name": name,
                      "roster_id": roster_ids[name]},
            ))
            student_ids[key] = bound["student_id"]

        # Teacher publishes one assignment, assigns three independent subject tiers,
        # and stores three nonempty question sets with distinct content.
        self.current_user = self.users["teacher"]
        assignment = self._ok(self.client.post(
            f"/api/v1/classes/{class_id}/assignments",
            json={"title": "虚拟数学分层练习", "subject": "math", "grade": "grade5",
                  "assignment_date": "2026-10-15", "due_at": "2026-10-16T00:00:00"},
        ))
        assignment_id = assignment["id"]
        tiered = self._ok(self.client.put(
            f"/api/v1/learning/classes/{class_id}/tiers",
            json={"subject": "math", "entries": [
                {"student_id": student_ids["s1"], "level": "L1"},
                {"student_id": student_ids["s2"], "level": "L2"},
                {"student_id": student_ids["s3"], "level": "L3"},
            ]},
        ))
        self.assertEqual(tiered["changed_count"], 3)
        variants = self._ok(self.client.put(
            f"/api/v1/learning/assignments/{assignment_id}/variants",
            json={"allow_uniform_fallback": False, "uniform_fallback_level": None,
                  "variants": [
                      {"level": "L1", "questions": [{"question_text": "基础题：36 ÷ 6 = ?",
                                                         "correct_answer": "6", "max_score": 10}]},
                      {"level": "L2", "questions": [{"question_text": "提升题：8 × 7 = ?",
                                                         "correct_answer": "56", "max_score": 10}]},
                      {"level": "L3", "questions": [{"question_text": "挑战题：若 8x = 56，求 x。",
                                                         "correct_answer": "7", "max_score": 10}]},
                  ]},
        ))
        self.assertEqual({row["level"] for row in variants["variants"]}, {"L1", "L2", "L3"})

        visible_question_text = {}
        for key in ("s1", "s2", "s3"):
            self.current_user = self.users[key]
            items = self._ok(self.client.get(
                f"/api/v1/assignments/mine?student_id={student_ids[key]}"
            ))
            self.assertEqual(len(items), 1)
            item = items[0]
            self.assertTrue(item["variant_available"])
            self.assertNotIn("level", item)
            self.assertNotIn("correct_answer", item["variant_questions"][0])
            visible_question_text[key] = item["variant_questions"][0]["question_text"]
        self.assertEqual(len(set(visible_question_text.values())), 3)

        # Student submits once; a replay with the same idempotency key reuses one task.
        self.current_user = self.users["s1"]
        with patch("app.v1.homework.process_homework_task.delay") as enqueue:
            first = self._ok(self._upload(assignment_id, student_ids["s1"], "virtual-012-assignment"))
            second = self._ok(self._upload(assignment_id, student_ids["s1"], "virtual-012-assignment"))
            self.assertEqual(first["task_id"], second["task_id"])
            self.assertTrue(second["idempotent_replay"])
            enqueue.assert_called_once()
        task_id = first["task_id"]
        with self.Session() as db:
            task = db.query(HomeworkTask).filter_by(task_id=task_id).one()
            link = db.query(AssignmentVariantTask).filter_by(task_id=task_id).one()
            selected = db.query(AssignmentVariant).filter_by(id=link.variant_id).one()
            self.assertEqual(task.status, "PENDING")
            self.assertEqual(selected.level, "L1")
            self.assertEqual(link.student_id, student_ids["s1"])

        # Run the real Celery task function and persistence/digitization code, while
        # replacing only the paid remote Vision boundary with an explicit fixture.
        fixture_result = [{
            "question_no": "1", "image_index": 0, "question_text": "untrusted model wording",
            "student_answer": "5", "question_type": "计算题", "score": 0,
            "max_score": 10, "result": "wrong", "comment": "请复核",
            "analysis": "模型解释占位", "confidence": 0.97, "correct_answer": "not authoritative",
            "error_type": "calculation_error", "knowledge_points": ["除法"], "difficulty": "easy",
        }]
        with patch.object(homework_tasks, "SessionLocal", self.Session), \
             patch.object(homework_tasks, "_resolve_vision_config",
                          return_value=SimpleNamespace(name="test-fixture", model_id="not-called", provider="fixture")), \
             patch.object(homework_tasks.vision_client, "grade_homework_images_directly",
                          return_value=fixture_result) as vision_boundary, \
             patch.object(homework_tasks, "reserve_vision_call", return_value="nonbillable-fixture-call"), \
             patch.object(homework_tasks, "finish_vision_call"):
            processed = homework_tasks.process_homework_task.run(
                task_id=task_id, image_path=str(SAMPLE), subject="math", grade="grade5",
                user_id=self.users["s1"].id, grading_mode="vision",
            )
            vision_boundary.assert_called_once()
            self.assertEqual(vision_boundary.call_args.kwargs["assignment_questions"][0]["correct_answer"], "6")
        self.assertEqual(processed["status"], "SUCCESS")
        status = self._ok(self.client.get(f"/api/v1/homework/status/{task_id}"))
        self.assertEqual(status["status"], "SUCCESS")
        result = self._ok(self.client.get(f"/api/v1/homework/result/{task_id}"))
        self.assertEqual(result["results"][0]["question_text"], "基础题：36 ÷ 6 = ?")
        self.assertEqual(result["results"][0]["correct_answer"], "6")
        self.assertEqual(result["results"][0]["max_score"], 10)

        # Teacher confirms the actual persisted grading result as a paper asset and mistake.
        paper_routes = importlib.import_module("app.v1.paper")
        with Image.open(SAMPLE) as opened:
            width, height = opened.size
        region = {"x1": int(width * 0.08), "y1": int(height * 0.08),
                  "x2": int(width * 0.72), "y2": int(height * 0.45), "question_no": "1"}
        self.current_user = self.users["teacher"]
        with patch.object(paper_routes.paper_digitize_provider, "locate_regions", return_value=[region]):
            digitized = self._ok(self.client.post(f"/api/v1/paper/tasks/{task_id}/digitize"))
        self.assertEqual(len(digitized["sources"]), 1)
        source = digitized["sources"][0]
        with self.Session() as db:
            grading_id = db.query(GradingResult).filter_by(task_id=task_id).one().id
        reviewed_source = self._ok(self.client.patch(
            f"/api/v1/paper/sources/{source['source_id']}/review",
            json={"grading_result_id": grading_id, "question_no": "1",
                  "question_text": "基础题：36 ÷ 6 = ?", "question_type": "计算题",
                  "correct_answer": "6", "analysis": "36 除以 6 等于 6。",
                  "manual_wrong": True, "confirm": True},
        ))
        mistake_id = reviewed_source["mistake_id"]
        self.assertIsNotNone(mistake_id)

        # Student establishes a genuine family relation; student and family see the
        # same authorized mistake, while an unrelated account remains denied.
        self.current_user = self.users["s1"]
        family_invite = self._ok(self.client.post(
            f"/api/v1/students/{student_ids['s1']}/family-contract"
        ))
        self.current_user = self.users["family"]
        family_bound = self._ok(self.client.post(
            f"/api/v1/contracts/{family_invite['code']}/claim",
            json={"relationship_type": "mother"},
        ))
        self.assertTrue(family_bound["bound"])
        child_mistakes = self._ok(self.client.get(
            f"/api/v1/paper/students/{student_ids['s1']}/mistakes"
        ))
        self.assertEqual([row["id"] for row in child_mistakes["items"]], [mistake_id])
        self.current_user = self.users["outsider"]
        self._ok(self.client.get(f"/api/v1/paper/students/{student_ids['s1']}/mistakes"), expected=404)

        # Student correction is persisted and the invited collaborator reviews it.
        self.current_user = self.users["s1"]
        correction = self._ok(self.client.post(
            f"/api/v1/paper/mistakes/{mistake_id}/corrections", json={"answer": "6"}
        ))
        attempt_id = correction["attempt_id"]
        self.current_user = self.users["collaborator"]
        accepted = self._ok(self.client.post(
            f"/api/v1/paper/mistakes/{mistake_id}/corrections/{attempt_id}/review",
            json={"accepted": True, "feedback": "订正正确"},
        ))
        self.assertEqual(accepted["status"], "accepted")

        # Independent student photo submission is a separate task, not an assignment task.
        self.current_user = self.users["s3"]
        with patch("app.v1.homework.process_homework_task.delay") as enqueue:
            independent = self._ok(self._upload(None, student_ids["s3"], "virtual-independent-photo"))
            enqueue.assert_called_once()
        with self.Session() as db:
            independent_task = db.query(HomeworkTask).filter_by(task_id=independent["task_id"]).one()
            self.assertIsNone(independent_task.assignment_id)
            self.assertEqual(independent_task.student_id, student_ids["s3"])
            self.assertEqual(db.query(MistakeRecord).filter_by(id=mistake_id).count(), 1)
            self.assertEqual(db.query(StudentRoster).filter_by(class_id=class_id, status="active").count(), 3)

        self.current_user = self.users["teacher"]
        submission_rows = self._ok(self.client.get(
            f"/api/v1/assignments/{assignment_id}/submissions"
        ))
        self.assertEqual(len(submission_rows), 3)
        self.assertEqual(sum(1 for row in submission_rows if row["submitted"]), 1)


if __name__ == "__main__":
    unittest.main()
