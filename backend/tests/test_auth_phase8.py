import os
import tempfile
import unittest
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.NamedTemporaryFile(delete=False).name}"

import api.auth as auth_api
from api.auth import CurrentUserResponse, LoginRequest, UpdateCurrentUserRequest, _ensure_welcome_session, login, me, pwd_context, update_me
from fastapi import HTTPException
from models import Base, SessionLocal, engine
from models.audit_log import AuditLog
from models.message import ChatMessage
from models.session import ChatSession
from models.user import User
from models.workspace import Workspace


class AuthPhase8Tests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()
        self.avatar_root = tempfile.TemporaryDirectory()
        self.original_avatar_root = auth_api.AVATAR_ROOT
        auth_api.AVATAR_ROOT = Path(self.avatar_root.name)

    def tearDown(self):
        auth_api.AVATAR_ROOT = self.original_avatar_root
        self.avatar_root.cleanup()
        self.db.close()

    def test_me_returns_current_user_without_token(self):
        user = User(
            id=42,
            username="phase8",
            password_hash="hash",
            role="admin",
            nickname="Phase 8",
            avatar="P",
        )

        response = me(user)

        self.assertIsInstance(response, CurrentUserResponse)
        self.assertEqual(response.user_id, 42)
        self.assertEqual(response.username, "phase8")
        self.assertEqual(response.role, "admin")
        self.assertEqual(response.nickname, "Phase 8")
        self.assertEqual(response.avatar, "P")

    def test_update_me_persists_profile_fields(self):
        user = User(username="profile", password_hash="hash", role="employee", nickname="Old")
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)

        response = update_me(
            UpdateCurrentUserRequest(nickname="New Name", avatar="N"),
            user,
            self.db,
        )

        self.assertEqual(response.nickname, "New Name")
        self.assertEqual(response.avatar, "N")
        self.assertEqual(self.db.get(User, user.id).nickname, "New Name")
        self.assertEqual(self.db.query(AuditLog).filter(AuditLog.action == "profile_update").count(), 1)

    def test_update_me_replaces_avatar_value_and_removes_old_avatar_file(self):
        user = User(username="profile", password_hash="hash", role="employee", nickname="Old")
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        user_dir = auth_api.AVATAR_ROOT / str(user.id)
        user_dir.mkdir(parents=True)
        old_file = user_dir / "avatar-old.png"
        old_file.write_bytes(b"old")
        user.avatar = f"/auth/avatars/{user.id}/{old_file.name}"
        self.db.commit()

        response = update_me(UpdateCurrentUserRequest(avatar="🙂"), user, self.db)

        self.assertEqual(response.avatar, "🙂")
        self.assertFalse(old_file.exists())
        self.assertEqual(list(user_dir.glob("avatar-*")), [])

    def test_login_updates_last_login_time(self):
        user = User(
            username="login-user",
            password_hash=pwd_context.hash("Password123"),
            role="employee",
            nickname="Login User",
        )
        self.db.add(user)
        self.db.commit()

        response = login(LoginRequest(username="login-user", password="Password123"), self.db)

        self.assertIsNotNone(response.last_login_at)
        self.assertIsNotNone(self.db.get(User, user.id).last_login_at)

    def test_update_me_rejects_empty_nickname(self):
        user = User(username="profile", password_hash="hash", role="employee", nickname="Old")

        with self.assertRaises(HTTPException) as exc:
            update_me(UpdateCurrentUserRequest(nickname=" "), user, self.db)

        self.assertEqual(exc.exception.status_code, 400)

    def test_welcome_session_is_created_once_for_new_user(self):
        user = User(username="new", password_hash="hash", role="employee", nickname="New")
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)

        _ensure_welcome_session(self.db, user)
        _ensure_welcome_session(self.db, user)

        sessions = self.db.query(ChatSession).filter(ChatSession.user_id == user.id).all()
        messages = self.db.query(ChatMessage).filter(ChatMessage.user_id == user.id).all()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].title, "了解 Project_R")
        self.assertEqual(len(messages), 1)
        self.assertIn("欢迎使用 Project_R", messages[0].content)


if __name__ == "__main__":
    unittest.main()
