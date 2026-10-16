import runpy
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401 - register all ORM tables
from app.v1.user import bind_wechat_phone, login_user, update_my_profile, wechat_login
from models.base import Base
from models.user import User
from models.user_role import UserRole
from schemas.user import (
    LoginRequest,
    UserProfilePatch,
    UserResponse,
    WechatLoginRequest,
    WechatPhoneRequest,
)
from services.wechat_identity import WeChatAPIError, WeChatIdentityClient
from utils.accounts import create_phone_user
from utils.security import verify_password


class FakeWechatClient:
    def __init__(self, openid="openid-test-1", unionid="unionid-test-1", phone=('' + "138" + '00000001')):
        self.openid = openid
        self.unionid = unionid
        self.phone = phone

    def exchange_login_code(self, code):
        if not code:
            raise AssertionError("code is required")
        return self.openid, self.unionid

    def exchange_phone_code(self, code):
        if not code:
            raise AssertionError("phone code is required")
        return self.phone


class WechatIdentityTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_existing_roles_login_and_wrong_password(self):
        accounts = {}
        for role, phone in (("teacher", ('' + "138" + '00000002')), ("student", ('' + "138" + '00000003')), ("admin", ('' + "138" + '00000004'))):
            user = create_phone_user(
                self.db, phone=phone, password="test-only-password-001", role=role, full_name=role
            )
            accounts[role] = user
        self.db.commit()

        for role, user in accounts.items():
            response = login_user(LoginRequest(phone=user.phone, password="test-only-password-001"), self.db)
            self.assertEqual(response["user"]["role"], role)
            self.assertTrue(response["access_token"])
        with self.assertRaises(HTTPException) as caught:
            login_user(LoginRequest(phone=accounts["teacher"].phone, password="test-only-password-002"), self.db)
        self.assertEqual(caught.exception.status_code, 401)
        self.assertEqual(caught.exception.detail, "账号或密码错误")

    def test_login_by_username(self):
        admin = create_phone_user(
            self.db,
            phone=('' + "138" + '00000005'),
            password="test-only-password-001",
            role="admin",
            full_name="admin",
        )
        admin.username = "superadmin"
        self.db.commit()

        response = login_user(
            LoginRequest(identifier="superadmin", password="test-only-password-001"),
            self.db,
        )
        self.assertEqual(response["user"]["username"], "superadmin")
        self.assertEqual(response["user"]["role"], "admin")

    def test_wechat_first_and_repeat_login_reuse_user_and_bind_optional_phone(self):
        client = FakeWechatClient()
        first = wechat_login(
            WechatLoginRequest.model_validate({
                "code": "one-time-code", "openid": "client-supplied-forgery"
            }),
            self.db,
            None,
            client,
        )
        second = wechat_login(WechatLoginRequest(code="another-code"), self.db, None, client)
        self.assertEqual(first["user"]["id"], second["user"]["id"])
        self.assertEqual(self.db.query(User).count(), 1)
        user = self.db.query(User).one()
        self.assertEqual(user.wechat_openid, "openid-test-1")
        self.assertEqual(user.phone, None)
        self.assertEqual(first["user"]["wechat_bind_status"], "bound")
        self.assertEqual(UserResponse.model_validate(first["user"]).id, user.id)

        profile = update_my_profile(
            UserProfilePatch(full_name="微信用户", phone=('' + "138" + '00000006')), self.db, user
        )
        self.assertEqual(profile["phone_source"], "manual")
        verified = bind_wechat_phone(
            WechatPhoneRequest(code="phone-code"), self.db, user,
            FakeWechatClient(phone=('' + "138" + '00000007'))
        )
        self.assertEqual(verified["phone_source"], "wechat")
        self.assertEqual(verified["phone"], ('' + "138" + '00000007'))

    def test_authenticated_wechat_login_links_current_teacher_without_changing_legacy_role(self):
        teacher = create_phone_user(
            self.db, phone=('' + "138" + '00000005'), password="test-only-password-003", role="teacher"
        )
        self.db.commit()
        response = wechat_login(
            WechatLoginRequest(code="one-time-code"), self.db, teacher, FakeWechatClient()
        )
        self.assertEqual(response["user"]["role"], "teacher")
        self.assertEqual(response["user"]["roles"], ["teacher"])
        self.assertEqual(teacher.wechat_openid, "openid-test-1")
        self.assertTrue(verify_password("test-only-password-003", teacher.hashed_password))

    def test_existing_openid_cannot_be_taken_over_by_another_authenticated_user(self):
        wechat_login(
            WechatLoginRequest(code="first-code"), self.db, None, FakeWechatClient()
        )
        teacher = create_phone_user(
            self.db, phone=('' + "138" + '00000008'), password="test-only-password-003", role="teacher"
        )
        self.db.commit()
        with self.assertRaises(HTTPException) as caught:
            wechat_login(
                WechatLoginRequest(code="second-code"), self.db, teacher, FakeWechatClient()
            )
        self.assertEqual(caught.exception.status_code, 409)
        self.assertIsNone(teacher.wechat_openid)

    def test_wechat_identity_http_client_returns_only_identity_not_session_key(self):
        client = WeChatIdentityClient(app_id="test-app", app_secret="test-only-app-secret-004")
        with patch.object(client, "_request_json", return_value={
            "openid": "openid-test", "unionid": "unionid-test", "session_key": "never-return"
        }) as request:
            identity = client.exchange_login_code("single-use-code")
        self.assertEqual(identity, ("openid-test", "unionid-test"))
        self.assertEqual(request.call_args.kwargs["params"]["js_code"], "single-use-code")
        self.assertNotIn("session_key", identity)

    def test_wechat_phone_code_uses_server_exchange_and_normalizes_number(self):
        client = WeChatIdentityClient(app_id="test-app", app_secret="test-only-app-secret-004")
        with patch.object(client, "_request_json", side_effect=[
            {"access_token": "temporary-token"},
            {"phone_info": {"phoneNumber": ('+86' + "138" + '00000007')}},
        ]) as request:
            phone = client.exchange_phone_code("phone-one-time-code")
        self.assertEqual(phone, ('' + "138" + '00000007'))
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args.kwargs["payload"], {"code": "phone-one-time-code"})

    def test_missing_wechat_configuration_fails_closed_without_network_call(self):
        client = WeChatIdentityClient(app_id="", app_secret="")
        with patch("services.wechat_identity.urlopen") as network:
            with self.assertRaises(WeChatAPIError):
                client.exchange_login_code("one-time-code")
        network.assert_not_called()

    def test_migration_is_idempotent_preserves_users_and_backfills_only_admin_teacher(self):
        migration_path = Path(__file__).parents[1] / "scripts" / "migrate_009a.py"
        migrate = runpy.run_path(str(migration_path))["migrate"]
        bind = create_engine("sqlite://")
        with bind.begin() as connection:
            connection.execute(text(
                'CREATE TABLE "user" (id INTEGER PRIMARY KEY, role VARCHAR(20) NOT NULL, phone VARCHAR(20))'
            ))
            connection.execute(text(
                'INSERT INTO "user" (id, role, phone) VALUES '
                "(1, 'admin', 'test-phone-00000002'), (2, 'teacher', 'test-phone-00000003'), (3, 'student', NULL)"
            ))

        first = migrate(bind)
        second = migrate(bind)
        self.assertEqual(first["user_count_before"], 3)
        self.assertEqual(first["user_count_after"], 3)
        self.assertEqual(first["user_role_rows_inserted"], 2)
        self.assertEqual(first["phone_sources_backfilled"], 2)
        self.assertEqual(second["user_role_rows_inserted"], 0)
        self.assertTrue({"wechat_openid", "wechat_unionid", "phone_source"}.issubset(
            {column["name"] for column in inspect(bind).get_columns("user")}
        ))
        with bind.connect() as connection:
            rows = connection.execute(text(
                "SELECT user_id, role_code FROM user_role ORDER BY user_id"
            )).all()
            count = connection.execute(text('SELECT COUNT(*) FROM "user"')).scalar_one()
        self.assertEqual(rows, [(1, "platform_admin"), (2, "teacher")])
        self.assertEqual(count, 3)
        bind.dispose()


if __name__ == "__main__":
    unittest.main(verbosity=2)
