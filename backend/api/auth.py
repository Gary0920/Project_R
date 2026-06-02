from datetime import datetime, timedelta, timezone
from os import getenv
from pathlib import Path
import uuid

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.time_models import UTCDateTimeModel
from core.system_accounts import SYSTEM_ADMIN_USERNAME, ensure_system_admin, is_system_admin_user
from models import BASE_DIR, get_db
from models.audit_log import AuditLog
from models.message import ChatMessage
from models.session import ChatSession
from models.user import User

load_dotenv(BASE_DIR / ".env")

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = getenv("APP_SECRET_KEY", "dev-secret-key-change-me")
JWT_EXPIRY_HOURS = int(getenv("JWT_EXPIRY_HOURS", "24"))
ALGORITHM = "HS256"
AVATAR_ROOT = Path(getenv("USER_AVATAR_ROOT", str(BASE_DIR / "user_data" / "avatars")))
MAX_AVATAR_BYTES = 2 * 1024 * 1024
AVATAR_CONTENT_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(UTCDateTimeModel):
    token: str
    user_id: int
    username: str
    role: str
    nickname: str
    avatar: str = ""
    work_group: str = ""
    last_login_at: datetime | None = None


class CurrentUserResponse(UTCDateTimeModel):
    user_id: int
    username: str
    role: str
    nickname: str
    avatar: str = ""
    work_group: str = ""
    last_login_at: datetime | None = None


class UpdateCurrentUserRequest(BaseModel):
    nickname: str | None = None
    avatar: str | None = None


def create_jwt(user: User) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _current_user_response(user: User) -> CurrentUserResponse:
    return CurrentUserResponse(
        user_id=user.id,
        username=user.username,
        role=user.role,
        nickname=user.nickname or user.username,
        avatar=user.avatar or "",
        work_group=user.work_group or "",
        last_login_at=user.last_login_at,
    )


def _token_response(token: str, user: User) -> TokenResponse:
    return TokenResponse(
        token=token,
        user_id=user.id,
        username=user.username,
        role=user.role,
        nickname=user.nickname or user.username,
        avatar=user.avatar or "",
        work_group=user.work_group or "",
        last_login_at=user.last_login_at,
    )


def _delete_user_avatar_files(user_id: int) -> None:
    user_dir = AVATAR_ROOT / str(user_id)
    if not user_dir.exists():
        return
    for old_file in user_dir.glob("avatar-*"):
        if old_file.is_file():
            old_file.unlink(missing_ok=True)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="无效的 Token")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    if is_system_admin_user(user):
        ensure_system_admin(db)
        db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    username = req.username.strip()
    if username == SYSTEM_ADMIN_USERNAME:
        ensure_system_admin(db)
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active or not pwd_context.verify(req.password, user.password_hash):
        db.add(AuditLog(user_id=0, action="login", detail=f"登录失败: {req.username}", success=False))
        db.commit()
        raise HTTPException(status_code=401, detail="账号或密码错误")

    token = create_jwt(user)
    user.last_login_at = datetime.now(timezone.utc)
    _ensure_welcome_session(db, user)

    db.add(AuditLog(user_id=user.id, action="login", detail="登录成功", success=True))
    db.commit()
    db.refresh(user)

    return _token_response(token, user)


def _ensure_welcome_session(db: Session, user: User) -> None:
    existing = db.query(ChatSession).filter(ChatSession.user_id == user.id).first()
    if existing:
        return

    session = ChatSession(user_id=user.id, title="了解 Project_R")
    db.add(session)
    db.commit()
    db.refresh(session)

    db.add(
        ChatMessage(
            session_id=session.id,
            user_id=user.id,
            role="assistant",
            content=(
                "欢迎使用 Project_R。\n\n"
                "你可以从三个方向开始：\n"
                "1. 直接询问公司流程、项目资料和培训内容。\n"
                "2. 新建项目，把不同项目或业务主题分开管理。\n"
                "3. 在对话中沉淀可复用知识，后续接入 RAG 后会引用公司 Wiki 回答。"
            ),
            status="success",
        )
    )
    db.commit()


@router.get("/me", response_model=CurrentUserResponse)
def me(user: User = Depends(get_current_user)):
    return _current_user_response(user)


@router.put("/me", response_model=CurrentUserResponse)
def update_me(
    req: UpdateCurrentUserRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if is_system_admin_user(user):
        raise HTTPException(status_code=400, detail="系统内置管理员账号不可修改")
    if req.nickname is not None:
        nickname = req.nickname.strip()
        if not nickname:
            raise HTTPException(status_code=400, detail="昵称不能为空")
        if len(nickname) > 64:
            raise HTTPException(status_code=400, detail="昵称不能超过 64 个字符")
        user.nickname = nickname
    if req.avatar is not None:
        avatar = req.avatar.strip()
        if len(avatar) > 256:
            raise HTTPException(status_code=400, detail="头像标识不能超过 256 个字符")
        if avatar != (user.avatar or ""):
            _delete_user_avatar_files(user.id)
        user.avatar = avatar
    db.add(AuditLog(user_id=user.id, action="profile_update", detail="更新个人资料", success=True))
    db.commit()
    db.refresh(user)
    return _current_user_response(user)


@router.post("/me/avatar", response_model=CurrentUserResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if is_system_admin_user(user):
        raise HTTPException(status_code=400, detail="系统内置管理员账号不可修改")
    content_type = (file.content_type or "").lower()
    extension = AVATAR_CONTENT_TYPES.get(content_type)
    if not extension:
        raise HTTPException(status_code=400, detail="仅支持 PNG、JPG、GIF 或 WebP 头像")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="头像文件为空")
    if len(data) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=400, detail="头像文件不能超过 2MB")

    user_dir = AVATAR_ROOT / str(user.id)
    user_dir.mkdir(parents=True, exist_ok=True)
    _delete_user_avatar_files(user.id)
    filename = f"avatar-{uuid.uuid4().hex}{extension}"
    target = user_dir / filename
    target.write_bytes(data)
    user.avatar = f"/auth/avatars/{user.id}/{filename}"
    db.add(AuditLog(user_id=user.id, action="profile_avatar_update", detail="更新头像", success=True))
    db.commit()
    db.refresh(user)
    return _current_user_response(user)


@router.get("/avatars/{user_id}/{filename}")
def get_avatar(user_id: int, filename: str):
    if "/" in filename or "\\" in filename or not filename.startswith("avatar-"):
        raise HTTPException(status_code=404, detail="头像不存在")
    path = AVATAR_ROOT / str(user_id) / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="头像不存在")
    return FileResponse(path)
