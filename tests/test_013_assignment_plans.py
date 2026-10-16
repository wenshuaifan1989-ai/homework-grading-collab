import json
import runpy
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
from models.base import Base
from models.classroom import Assignment, Class, StudentRoster
from models.identity_relations import ClassTeacher, Student, StudentUserBinding
from models.learning import AssignmentVariant, AssignmentVariantQuestion, StudentSubjectTier
from models.paper import QuestionAsset
from models.user import User
from utils.database import get_db
from utils.deps import get_current_user
from services.question_bank_provider import question_fingerprint
import services.question_bank_provider as question_bank_provider


ROOT = Path(__file__).resolve().parents[1]


class AssignmentPlan013Tests(unittest.TestCase):
    def setUp(self):
        self.old_local_dataset = question_bank_provider.LOCAL_DATASET
        question_bank_provider.LOCAL_DATASET = Path(__file__).parent / "fixtures" / "synthetic_question_bank.jsonl"
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.teacher = User(
            id=131, username="teacher013", email="collab-test-027@example.invalid",
            hashed_password="test-only-hashed-password-010", role="teacher", is_active=True,
        )
        self.student_user = User(
            id=132, username="student013", email="collab-test-028@example.invalid",
            hashed_password="test-only-hashed-password-010", role="student", is_active=True,
        )
        self.other_teacher = User(
            id=133, username="teacher013-other", email="collab-test-029@example.invalid",
            hashed_password="test-only-hashed-password-010", role="teacher", is_active=True,
        )
        with self.Session.begin() as db:
            db.add_all([
                self.teacher,
                self.student_user,
                self.other_teacher,
                Class(
                    id=3013, teacher_id=131, name="013计划测试班", invite_code="TEST01301",
                    grade="grade7", status="active",
                ),
                ClassTeacher(
                    id=6013, class_id=3013, teacher_user_id=131, role="owner",
                    subject_codes_json=["math"], status="active",
                ),
                Student(id=2013, name="013测试学生", status="active"),
                StudentRoster(
                    id=8013, class_id=3013, student_name="013测试学生", student_no="013-01",
                    student_id=2013, bound_user_id=132, status="active",
                ),
                StudentUserBinding(
                    id=9013, student_id=2013, user_id=132,
                    relationship_type="self", status="active",
                ),
                StudentSubjectTier(
                    id=10013, student_id=2013, class_id=3013, subject="math",
                    level="L1", updated_by=131,
                ),
            ])

        self.current_user = self.teacher

        def override_db():
            with self.Session() as db:
                yield db

        main.app.dependency_overrides[get_db] = override_db
        main.app.dependency_overrides[get_current_user] = lambda: self.current_user
        self.client = TestClient(main.app)

    def tearDown(self):
        question_bank_provider.LOCAL_DATASET = self.old_local_dataset
        main.app.dependency_overrides.pop(get_db, None)
        main.app.dependency_overrides.pop(get_current_user, None)
        self.engine.dispose()

    def test_safe_additive_migration_preserves_existing_question_asset_rows(self):
        migrate = runpy.run_path(str(ROOT / "scripts" / "migrate_013_additive.py"))["migrate"]
        engine = create_engine("sqlite://")
        try:
            with engine.begin() as connection:
                connection.execute(text(
                    "CREATE TABLE question_asset (id INTEGER PRIMARY KEY, subject VARCHAR(40))"
                ))
                connection.execute(text("INSERT INTO question_asset (id, subject) VALUES (1, 'math')"))
            result = migrate(engine)
            self.assertTrue(result["protected_rows_unchanged"])
            self.assertEqual(result["protected_rows_before"]["question_asset"], 1)
            self.assertEqual(result["protected_rows_after"]["question_asset"], 1)
            self.assertEqual(set(result["added_question_asset_columns"]), {"rights_basis", "rights_reference"})
            self.assertTrue(inspect(engine).has_table("assignment_plan"))
            self.assertTrue(inspect(engine).has_table("assignment_plan_question"))
            second = migrate(engine)
            self.assertEqual(second["added_question_asset_columns"], [])
            self.assertTrue(second["protected_rows_unchanged"])
        finally:
            engine.dispose()

    def test_question_identity_includes_correct_answer(self):
        base = {
            "subject": "math", "grade": "grade7", "question_text": "计算：1+1。",
            "question_type": "计算题", "options": None,
        }
        first = question_fingerprint(**base, correct_answer="2")
        conflicting_answer = question_fingerprint(**base, correct_answer="3")
        self.assertNotEqual(first, conflicting_answer)

    def test_manual_local_question_plan_pdf_confirm_publish_and_student_receipt(self):
        imported = self.client.post(
            "/api/v1/assignment-plans/question-bank/import-local?subject=math&grade=grade7"
        )
        self.assertEqual(imported.status_code, 200, imported.text)
        # The versioned legal local corpus may grow; 015 adds eight exact QA
        # paper questions. Assert the actual dataset contract, not a stale count.
        from services.question_bank_provider import LOCAL_DATASET
        corpus_count=sum(bool(line.strip()) for line in LOCAL_DATASET.read_text(encoding='utf-8').splitlines())
        self.assertEqual(imported.json()["data"]["created"], corpus_count)
        repeated_import = self.client.post(
            "/api/v1/assignment-plans/question-bank/import-local?subject=math&grade=grade7"
        )
        self.assertEqual(repeated_import.status_code, 200, repeated_import.text)
        self.assertEqual(repeated_import.json()["data"]["created"], 0)
        self.assertEqual(repeated_import.json()["data"]["reused"], corpus_count)

        with self.Session.begin() as db:
            db.add(QuestionAsset(
                id=99913, subject="math", grade="grade7", question_text="来源未知题目",
                question_type="计算题", correct_answer="0", analysis="未知来源",
                source="paper_digitization", asset_version="011-v1",
                review_status="CONFIRMED", clean_image_status="CONFIRMED",
            ))
            db.add(QuestionAsset(
                id=99914, subject="math", grade="grade7", question_text="缺少答案的题目",
                question_type="计算题", correct_answer="", analysis="没有答案不能发布",
                difficulty="easy", knowledge_points_json=["有理数运算"],
                source="local_test", asset_version="013-test",
                rights_basis="PROJECT_AUTHORED", rights_reference="test-only",
                review_status="CONFIRMED", clean_image_status="NOT_REQUIRED",
            ))

        search = self.client.get(
            "/api/v1/assignment-plans/question-bank/search",
            params={"class_id": 3013, "subject": "math", "grade": "grade7"},
        )
        self.assertEqual(search.status_code, 200, search.text)
        items = search.json()["data"]["items"]
        self.assertEqual(len(items), corpus_count)
        self.assertTrue(all(item["rights_basis"] == "PROJECT_AUTHORED" for item in items))
        no_hit = self.client.get(
            "/api/v1/assignment-plans/question-bank/search",
            params={"class_id": 3013, "subject": "math", "grade": "grade8"},
        )
        self.assertEqual(no_hit.status_code, 200, no_hit.text)
        self.assertEqual(no_hit.json()["data"]["items"], [])
        easy = [item for item in items if item["difficulty"] == "easy"][:2]
        medium = [item for item in items if item["difficulty"] == "medium"][:2]
        hard = [item for item in items if item["difficulty"] == "hard"][:2]

        request_body = {
            "idempotency_key": "plan013-idempotency-001",
            "class_id": 3013,
            "title": "七年级数学原创分层练习",
            "description": "013本地原创题库测试计划",
            "subject": "math",
            "grade": "grade7",
            "assignment_date": "2026-10-15",
            "target_knowledge_points": ["有理数运算"],
            "question_types": [],
            "question_count_per_tier": 2,
            "difficulty": "mixed",
            "duration_minutes": 20,
            "tier_strategy": {
                "L1": "基础计算与概念巩固",
                "L2": "综合应用与步骤表达",
                "L3": "多步骤迁移与推理",
            },
            "variants": [
                {"level": "L1", "questions": [{"source_asset_id": item["id"], "max_score": 10} for item in easy]},
                {"level": "L2", "questions": [{"source_asset_id": item["id"], "max_score": 10} for item in medium]},
                {"level": "L3", "questions": [{"source_asset_id": item["id"], "max_score": 10} for item in hard]},
            ],
        }
        unauthorized_request = json.loads(json.dumps(request_body))
        unauthorized_request["idempotency_key"] = "plan013-no-rights-001"
        unauthorized_request["variants"][0]["questions"][0]["source_asset_id"] = 99913
        rejected = self.client.post("/api/v1/assignment-plans", json=unauthorized_request)
        self.assertEqual(rejected.status_code, 422, rejected.text)
        incomplete_request = json.loads(json.dumps(request_body))
        incomplete_request["idempotency_key"] = "plan013-incomplete-001"
        incomplete_request["variants"] = incomplete_request["variants"][:2]
        incomplete = self.client.post("/api/v1/assignment-plans", json=incomplete_request)
        self.assertEqual(incomplete.status_code, 422, incomplete.text)

        created = self.client.post("/api/v1/assignment-plans", json=request_body)
        self.assertEqual(created.status_code, 200, created.text)
        plan = created.json()["data"]
        self.assertEqual(plan["idempotency_key"], request_body["idempotency_key"])
        self.assertEqual(plan["status"], "DRAFT")
        self.assertEqual({v["level"] for v in plan["variants"]}, {"L1", "L2", "L3"})
        loaded = self.client.get(f"/api/v1/assignment-plans/{plan['id']}").json()["data"]
        self.assertEqual(loaded["target_knowledge_points"], ["有理数运算"])
        self.assertEqual(loaded["tier_strategy"]["L3"], "多步骤迁移与推理")

        repeated = self.client.post("/api/v1/assignment-plans", json=request_body)
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertEqual(repeated.json()["data"]["id"], plan["id"])
        changed = dict(request_body, title="同幂等键异内容")
        self.assertEqual(self.client.post("/api/v1/assignment-plans", json=changed).status_code, 409)

        edited = dict(request_body, title="七年级数学原创分层练习（已编辑）")
        updated = self.client.put(f"/api/v1/assignment-plans/{plan['id']}", json=edited)
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["data"]["title"], edited["title"])

        pdf_hashes = set()
        from app.v1.assignment_plans import _variant_pdf

        expected_questions = {
            "L1": [item["question_text"] for item in easy],
            "L2": [item["question_text"] for item in medium],
            "L3": [item["question_text"] for item in hard],
        }
        for level in ("L1", "L2", "L3"):
            with patch("app.v1.assignment_plans._variant_pdf", wraps=_variant_pdf) as pdf_builder:
                pdf = self.client.get(f"/api/v1/assignment-plans/{plan['id']}/variants/{level}/print.pdf")
            ordered_questions = [item.question_text for item in pdf_builder.call_args.args[2]]
            self.assertEqual(ordered_questions, expected_questions[level])
            self.assertEqual(pdf.status_code, 200, pdf.text[:200])
            self.assertTrue(pdf.content.startswith(b"%PDF-"))
            self.assertGreater(len(pdf.content), 1000)
            pdf_hashes.add(__import__("hashlib").sha256(pdf.content).hexdigest())
        self.assertEqual(len(pdf_hashes), 3)

        with self.Session.begin() as db:
            db.query(QuestionAsset).filter_by(id=easy[0]["id"]).one().review_status = "REJECTED"
        blocked_confirmation = self.client.post(f"/api/v1/assignment-plans/{plan['id']}/confirm")
        self.assertEqual(blocked_confirmation.status_code, 422, blocked_confirmation.text)
        with self.Session() as db:
            statuses_after_block = {
                row.id: row.review_status for row in db.query(QuestionAsset).filter(
                    QuestionAsset.id.in_({item["id"] for item in [*easy, *medium, *hard]})
                ).all()
            }
            self.assertEqual(statuses_after_block[easy[0]["id"]], "REJECTED")
            self.assertEqual(sum(value == "CONFIRMED" for value in statuses_after_block.values()), 0)
        with self.Session.begin() as db:
            db.query(QuestionAsset).filter_by(id=easy[0]["id"]).one().review_status = "PENDING_REVIEW"

        confirmed = self.client.post(f"/api/v1/assignment-plans/{plan['id']}/confirm")
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(confirmed.json()["data"]["status"], "CONFIRMED")
        with self.Session() as db:
            selected_ids = {item["id"] for item in [*easy, *medium, *hard]}
            statuses = {row.id: row.review_status for row in db.query(QuestionAsset).filter(
                QuestionAsset.id.in_(selected_ids)
            ).all()}
            self.assertEqual(set(statuses.values()), {"CONFIRMED"})
            self.assertEqual(db.query(QuestionAsset).filter_by(id=99913).one().review_status, "CONFIRMED")

        published = self.client.post(f"/api/v1/assignment-plans/{plan['id']}/publish")
        self.assertEqual(published.status_code, 200, published.text)
        assignment_id = published.json()["data"]["assignment_id"]
        self.assertIsNotNone(assignment_id)
        repeated_publish = self.client.post(f"/api/v1/assignment-plans/{plan['id']}/publish")
        self.assertEqual(repeated_publish.status_code, 200, repeated_publish.text)
        self.assertEqual(repeated_publish.json()["data"]["assignment_id"], assignment_id)
        self.assertTrue(repeated_publish.json()["data"]["already_published"])

        with self.Session() as db:
            self.assertEqual(db.query(AssignmentVariant).filter_by(assignment_id=assignment_id).count(), 3)
            self.assertEqual(db.query(AssignmentVariantQuestion).filter(
                AssignmentVariantQuestion.variant_id.in_(
                    db.query(AssignmentVariant.id).filter_by(assignment_id=assignment_id)
                )
            ).count(), 6)

        self.current_user = self.student_user
        received = self.client.get("/api/v1/assignments/mine?student_id=2013")
        self.assertEqual(received.status_code, 200, received.text)
        assignment = next(item for item in received.json()["data"] if item["id"] == assignment_id)
        self.assertEqual(
            [item["question_text"] for item in assignment["variant_questions"]],
            [item["question_text"] for item in easy],
        )
        self.assertTrue(all("correct_answer" not in item for item in assignment["variant_questions"]))
        self.assertNotIn("level", assignment)

    def test_ai_endpoint_is_closed_without_external_request_and_teacher_access_is_scoped(self):
        status = self.client.get("/api/v1/assignment-plans/ai-status").json()["data"]
        self.assertEqual(status["status"], "PENDING_AUTHORIZATION")
        self.assertEqual(status["enabled"], False)
        self.assertEqual(status["daily_request_limit"], 0)
        with patch("urllib.request.urlopen") as network:
            response = self.client.post("/api/v1/assignment-plans/ai-proposal", json={
                "class_id": 3013, "subject": "math", "grade": "grade7",
                "prompt": "布置一份有理数运算练习，基础与提升各一题",
            })
        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json()["detail"]["model_request_sent"])
        network.assert_not_called()
        self.current_user = self.other_teacher
        denied = self.client.get(
            "/api/v1/assignment-plans/question-bank/search",
            params={"class_id": 3013, "subject": "math", "grade": "grade7"},
        )
        self.assertIn(denied.status_code, (403, 404))


if __name__ == "__main__":
    unittest.main()
