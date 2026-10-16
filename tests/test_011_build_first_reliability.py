import runpy
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from clients.vision_client import VisionClient, VisionResponseTimeout
from config import ModelConfig, settings
from models.base import Base
from models.homework import HomeworkTask
from models.model_usage import ModelCallAudit, ModelDailyUsage
from models.submission import HomeworkSubmissionKey
from models.user import User
from services.model_quota import ModelQuotaExceeded, finish_vision_call, reserve_vision_call
from services.task_service import task_service


ROOT = Path(__file__).resolve().parents[1]


class BuildFirstReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.old_limit = settings.VISION_DAILY_REQUEST_LIMIT

    def tearDown(self):
        settings.VISION_DAILY_REQUEST_LIMIT = self.old_limit
        self.engine.dispose()

    def test_additive_retry_safety_migration_is_idempotent(self):
        migrate = runpy.run_path(
            str(ROOT / "scripts" / "migrate_011_build_first_additive.py")
        )["migrate"]
        engine = create_engine("sqlite://")
        try:
            retry_tables = {
                ModelCallAudit.__table__, ModelDailyUsage.__table__,
                HomeworkSubmissionKey.__table__,
            }
            Base.metadata.create_all(
                engine,
                tables=[table for table in Base.metadata.sorted_tables if table not in retry_tables],
            )
            first = migrate(engine)
            second = migrate(engine)
            self.assertEqual(first["tables_present"], second["tables_present"])
            self.assertEqual(len(first["tables_present"]), 3)
            self.assertTrue(first["protected_rows_unchanged"])
            self.assertTrue(second["protected_rows_unchanged"])
        finally:
            engine.dispose()

    def test_daily_quota_is_atomic_and_timeout_call_is_audited_unknown(self):
        settings.VISION_DAILY_REQUEST_LIMIT = 1
        with self.Session() as db:
            db.add(User(
                id=501, username="quota-test", email="collab-test-008@example.invalid",
                hashed_password="test-only-hashed-password-011", role="student", is_active=True,
            ))
            db.add(HomeworkTask(
                task_id="task_quota_test", user_id=501, subject="math", grade="grade7",
                status="PENDING", grading_mode="vision",
            ))
            db.commit()

            call_id = reserve_vision_call(db, "task_quota_test", "deepseek", "unit-test-model")
            with self.assertRaises(ModelQuotaExceeded):
                reserve_vision_call(db, "task_quota_test", "deepseek", "unit-test-model")
            finish_vision_call(
                db, call_id, "outcome_unknown", VisionResponseTimeout.code
            )

            usage = db.query(ModelDailyUsage).one()
            audit = db.query(ModelCallAudit).one()
            self.assertEqual(usage.request_count, 1)
            self.assertEqual(audit.call_id, call_id)
            self.assertEqual(audit.status, "outcome_unknown")
            self.assertEqual(audit.error_code, VisionResponseTimeout.code)

    def test_duplicate_worker_message_is_claimed_only_once(self):
        with self.Session() as db:
            db.add(User(
                id=601, username="claim-test", email="collab-test-009@example.invalid",
                hashed_password="test-only-hashed-password-011", role="student", is_active=True,
            ))
            db.add(HomeworkTask(
                task_id="task_claim_test", user_id=601, subject="math", grade="grade7",
                status="PENDING", grading_mode="vision",
            ))
            db.commit()
            self.assertTrue(task_service.claim_task_for_processing(db, "task_claim_test"))
            self.assertFalse(task_service.claim_task_for_processing(db, "task_claim_test"))

    def test_response_read_timeout_is_classified_as_unknown_remote_outcome(self):
        client = VisionClient()
        model = ModelConfig(
            name="unit-test-vision", provider="deepseek", api_key="test-only-api-key-012",
            base_url="https://api.deepseek.com", model_id="unit-test-model", type="vision",
        )
        with patch("urllib.request.urlopen", side_effect=TimeoutError("fixture timeout")):
            with self.assertRaises(VisionResponseTimeout) as caught:
                client._call_vision_api_content([], model)
        self.assertEqual(caught.exception.code, "VISION_RESPONSE_TIMEOUT_OUTCOME_UNKNOWN")


if __name__ == "__main__":
    unittest.main()
