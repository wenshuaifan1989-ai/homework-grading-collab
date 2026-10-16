import runpy
import unittest
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from models.base import Base
from models.classroom import Assignment, Class, StudentRoster
from models.homework import GradingResult, HomeworkTask, QuestionBlock
from models.identity_relations import (
    ClassTeacher,
    Contract,
    Student,
    StudentUserBinding,
)
from models.user import User
from services.identity_relations import user_can_access_student
from services.task_service import TaskService
from app.v1.relations import (
    claim_contract,
    create_class_contract,
    create_family_contract,
    list_class_relation_requests,
    remove_family_binding,
    review_family_binding,
    review_student_leave,
    transfer_class_owner,
)
from schemas.identity_relations import (
    ContractClaimRequest,
    ContractCreateRequest,
    OwnerTransferRequest,
    RelationshipReviewRequest,
    StudentLeaveReviewRequest,
)
from services.dashboard_service import build_daily_dashboard
from app.v1.school import list_my_students
from app.v1.user import _user_payload
from app.v1.platform import admin_students, admin_users, create_custom_school, search_schools
from schemas.identity_relations import SchoolCreateRequest


PROJECT_ROOT = Path(__file__).parents[1]


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        with self.engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE user (id INTEGER PRIMARY KEY, role VARCHAR(20))"
            ))
            connection.execute(text(
                "CREATE TABLE classroom (id INTEGER PRIMARY KEY, teacher_id BIGINT, invite_code VARCHAR(12))"
            ))
            connection.execute(text(
                "CREATE TABLE student_roster (id INTEGER PRIMARY KEY, class_id BIGINT, "
                "student_name VARCHAR(100), bound_user_id BIGINT, status VARCHAR(20))"
            ))
            connection.execute(text(
                "CREATE TABLE homework_task (id INTEGER PRIMARY KEY, user_id BIGINT)"
            ))
            connection.execute(text(
                "INSERT INTO user(id,role) VALUES (1,'teacher'),(2,'student'),(3,'student')"
            ))
            connection.execute(text(
                "INSERT INTO classroom(id,teacher_id,invite_code) VALUES (10,1,'JOIN00010'),(11,1,'JOIN00011')"
            ))
            connection.execute(text(
                "INSERT INTO student_roster(id,class_id,student_name,bound_user_id,status) VALUES "
                "(20,10,'林同学',2,'active'),(21,11,'林同学',2,'active'),"
                "(22,10,'同名学生',NULL,'active'),(23,11,'同名学生',NULL,'active')"
            ))
            connection.execute(text(
                "INSERT INTO homework_task(id,user_id) VALUES (30,2),(31,3),(32,1)"
            ))
        self.migrate = runpy.run_path(
            str(PROJECT_ROOT / "scripts" / "migrate_009bcd.py")
        )["migrate"]

    def tearDown(self):
        self.engine.dispose()

    def test_migration_backfills_by_user_and_roster_seat_and_is_idempotent(self):
        first = self.migrate(self.engine)
        second = self.migrate(self.engine)

        self.assertEqual(first["counts_before"]["user"], 3)
        self.assertEqual(first["counts_after"]["user"], 3)
        self.assertEqual(first["students_inserted"], 3)
        self.assertEqual(first["bindings_inserted"], 1)
        self.assertEqual(first["rosters_linked"], 4)
        self.assertEqual(first["homework_student_subjects_backfilled"], 1)
        self.assertEqual(first["class_owners_inserted"], 2)
        self.assertEqual(first["legacy_student_contracts_seeded"], 2)
        self.assertEqual(second["students_inserted"], 0)
        self.assertEqual(second["bindings_inserted"], 0)
        self.assertEqual(second["rosters_linked"], 0)
        self.assertEqual(second["class_owners_inserted"], 0)
        self.assertEqual(second["legacy_student_contracts_seeded"], 0)
        with self.engine.connect() as connection:
            same_user_students = connection.execute(text(
                "SELECT COUNT(DISTINCT student_id) FROM student_roster WHERE bound_user_id=2"
            )).scalar_one()
            unbound_students = connection.execute(text(
                "SELECT COUNT(DISTINCT student_id) FROM student_roster WHERE bound_user_id IS NULL"
            )).scalar_one()
            task_rows = connection.execute(text(
                "SELECT id,student_id,actor_user_id FROM homework_task ORDER BY id"
            )).all()
        self.assertEqual(same_user_students, 1)
        self.assertEqual(unbound_students, 2)
        self.assertEqual(task_rows, [(30, 1, 2), (31, None, 3), (32, None, 1)])


class StudentIdentityTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.Session()
        self.teacher = User(
            id=101, username="teacher", email="teacher@example.com",
            hashed_password="test-only-hashed-password-009", role="teacher", is_active=True,
        )
        self.parent = User(
            id=102, username="parent", email="parent@example.com",
            hashed_password="test-only-hashed-password-009", role="student", is_active=True,
        )
        self.other = User(
            id=103, username="other", email="other@example.com",
            hashed_password="test-only-hashed-password-009", role="student", is_active=True,
        )
        self.admin = User(
            id=105, username="admin", email="admin@example.com",
            hashed_password="test-only-hashed-password-009", role="admin", is_active=True,
        )
        self.student = Student(id=201, name="学生甲", status="active")
        self.classroom = Class(id=301, teacher_id=101, name="测试班", invite_code="ABC12345")
        self.db.add_all([self.teacher, self.parent, self.other, self.admin, self.student, self.classroom])
        self.db.flush()
        self.db.add_all([
            StudentRoster(id=401, class_id=301, student_name="学生甲", student_id=201, status="active"),
            StudentUserBinding(
                student_id=201, user_id=102, relationship_type="mother", status="active"
            ),
            ClassTeacher(
                class_id=301, teacher_user_id=101, role="owner", status="active"
            ),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_access_is_limited_to_active_binding_or_class_teacher(self):
        self.assertTrue(user_can_access_student(self.db, self.parent, 201))
        self.assertFalse(user_can_access_student(self.db, self.other, 201))
        self.assertTrue(user_can_access_student(self.db, self.teacher, 201, class_id=301))
        self.assertFalse(user_can_access_student(self.db, self.teacher, 999, class_id=301))
        self.db.query(StudentUserBinding).filter_by(user_id=102).update({"status": "revoked"})
        self.db.commit()
        self.assertFalse(user_can_access_student(self.db, self.parent, 201))

    def test_family_account_profile_and_student_list_use_student_binding(self):
        profile = _user_payload(self.db, self.parent)
        self.assertEqual(profile["bind_status"], "bound")
        self.assertEqual(profile["student_id"], 201)
        students = list_my_students(self.db, self.parent).data
        self.assertEqual(students[0]["student_id"], 201)
        self.assertEqual(students[0]["classes"][0]["class_id"], 301)

    def test_homework_task_can_record_student_subject_and_actor_separately(self):
        task = TaskService().create_task_with_images(
            self.db,
            "task_009bcd_foundation",
            self.parent.id,
            "math",
            "grade7",
            [],
            grading_mode="vision",
            student_id=self.student.id,
            actor_user_id=self.parent.id,
        )
        self.assertEqual(task.student_id, self.student.id)
        self.assertEqual(task.actor_user_id, self.parent.id)
        self.assertNotEqual(task.user_id, task.student_id)

    def test_008_dashboard_aggregates_family_task_by_student_not_actor(self):
        assignment = Assignment(
            id=501, class_id=301, teacher_id=101, title="练习", subject="math",
            grade="grade7", assignment_date=date(2026, 10, 5), status="published",
        )
        task = HomeworkTask(
            id=601, task_id="task_family_dashboard", user_id=102, actor_user_id=102,
            student_id=201, assignment_id=501, class_id=301, subject="math", grade="grade7",
            status="SUCCESS", total_score=10, grading_mode="vision",
        )
        self.db.add_all([assignment, task])
        self.db.flush()
        block = QuestionBlock(
            id=701, task_id=task.task_id, question_no="1", question_image_url="test.png",
            x1=0, y1=0, x2=10, y2=10,
        )
        self.db.add(block)
        self.db.flush()
        self.db.add(GradingResult(
            id=801, task_id=task.task_id, question_block_id=block.id,
            question_no="1", score=10, max_score=10, result="正确",
        ))
        self.db.commit()

        payload = build_daily_dashboard(self.db, self.classroom, date(2026, 10, 5))
        self.assertEqual(payload["class"]["bound_count"], 1)
        self.assertEqual(payload["assignments"][0]["completed_count"], 1)
        self.assertEqual(payload["students"][0]["student_id"], 201)
        self.assertEqual(payload["question_stats"][0]["correct_count"], 1)

    def test_student_model_has_no_login_identity_fields(self):
        names = {column["name"] for column in inspect(self.engine).get_columns("student")}
        self.assertTrue({"id", "name", "status", "created_at", "updated_at"}.issubset(names))
        self.assertTrue({"openid", "password", "role"}.isdisjoint(names))

    def test_family_contract_and_class_contract_preserve_one_student_identity(self):
        family_contract = create_family_contract(201, self.db, self.parent).data
        claim_result = claim_contract(
            family_contract["code"],
            ContractClaimRequest(relationship_type="father"),
            self.db,
            self.other,
        ).data
        self.assertTrue(claim_result["bound"])
        self.assertEqual(claim_result["student_id"], 201)

        join_contract = create_class_contract(
            301, ContractCreateRequest(type="STUDENT_CLASS_JOIN"), self.db, self.teacher
        ).data
        join_result = claim_contract(
            join_contract["code"],
            ContractClaimRequest(student_id=201, student_name="学生甲"),
            self.db,
            self.parent,
        ).data
        self.assertTrue(join_result["joined"])
        self.assertEqual(join_result["student_id"], 201)
        self.assertEqual(
            self.db.query(StudentUserBinding).filter_by(student_id=201, user_id=102).one().relationship_type,
            "mother",
        )
        self.assertIsNone(self.db.query(StudentRoster).filter_by(id=401).one().bound_user_id)
        self.assertEqual(
            self.db.query(Contract).filter_by(id=join_contract["id"]).one().used_count,
            1,
        )

    def test_teacher_invite_owner_transfer_and_last_family_binding_review(self):
        invited = User(
            id=104, username="invited", email="invited@example.com",
            hashed_password="test-only-hashed-password-009", role="teacher", is_active=True,
        )
        self.db.add(invited)
        self.db.commit()
        invite = create_class_contract(
            301,
            ContractCreateRequest(type="TEACHER_CLASS_JOIN", max_uses=1),
            self.db,
            self.teacher,
        ).data
        accepted = claim_contract(
            invite["code"], ContractClaimRequest(subject_codes=["math"]), self.db, invited
        ).data
        self.assertTrue(accepted["joined"])
        membership = self.db.query(ClassTeacher).filter_by(
            class_id=301, teacher_user_id=104, status="active"
        ).one()
        self.assertEqual(membership.subject_codes_json, ["math"])

        changed = transfer_class_owner(
            301, OwnerTransferRequest(teacher_user_id=104), self.db, self.teacher
        ).data
        self.assertEqual(changed["owner_user_id"], 104)
        self.assertEqual(self.db.query(Class).filter_by(id=301).one().teacher_id, 104)
        self.assertEqual(self.db.query(ClassTeacher).filter_by(class_id=301, teacher_user_id=104).one().role, "owner")

        pending = remove_family_binding(201, 102, self.db, self.parent).data
        self.assertTrue(pending["requires_review"])
        reviewed = review_family_binding(
            201, 102, RelationshipReviewRequest(approve=True), self.db, invited
        ).data
        self.assertEqual(reviewed["status"], "revoked")

    def test_owner_can_discover_pending_student_leave_and_family_review(self):
        roster = self.db.query(StudentRoster).filter_by(class_id=301, student_id=201).one()
        roster.status = "pending_leave"
        binding = self.db.query(StudentUserBinding).filter_by(student_id=201, user_id=102).one()
        binding.status = "pending_review"
        self.db.commit()

        requests = list_class_relation_requests(301, self.db, self.teacher).data
        self.assertEqual(requests["student_leave"][0]["student_id"], 201)
        self.assertEqual(requests["family_binding"][0]["user_id"], 102)
        family_result = review_family_binding(
            201, 102, RelationshipReviewRequest(approve=True), self.db, self.teacher
        ).data
        self.assertEqual(family_result["status"], "revoked")
        leave_result = review_student_leave(
            301, 201, StudentLeaveReviewRequest(approve=True), self.db, self.teacher
        ).data
        self.assertEqual(leave_result["status"], "left")

    def test_custom_school_is_pending_and_platform_admin_reading_is_restricted(self):
        created = create_custom_school(
            SchoolCreateRequest(official_name="示例学校", stage="junior_high"),
            self.db,
            self.teacher,
        ).data
        self.assertTrue(created["is_custom"])
        self.assertEqual(created["status"], "pending_normalization")
        found = search_schools("示例", "junior_high", None, None, None, 25, self.db, self.teacher).data
        self.assertEqual(found[0]["id"], created["id"])

        users = admin_users(None, 0, 50, self.db, self.admin).data
        students = admin_students(None, 0, 100, self.db, self.admin).data
        self.assertTrue(any(row["id"] == 105 for row in users))
        self.assertEqual(students[0]["id"], 201)
        with self.assertRaises(Exception) as blocked:
            admin_users(None, 0, 50, self.db, self.teacher)
        self.assertEqual(getattr(blocked.exception, "status_code", None), 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)
