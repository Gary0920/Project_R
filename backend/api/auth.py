from datetime import datetime, timedelta, timezone
from os import getenv

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.orm import Session

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


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    token: str
    user_id: int
    username: str
    role: str
    nickname: str
    avatar: str = ""


class CurrentUserResponse(BaseModel):
    user_id: int
    username: str
    role: str
    nickname: str
    avatar: str = ""


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
    return user


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not user.is_active or not pwd_context.verify(req.password, user.password_hash):
        db.add(AuditLog(user_id=0, action="login", detail=f"登录失败: {req.username}", success=False))
        db.commit()
        raise HTTPException(status_code=401, detail="账号或密码错误")

    token = create_jwt(user)
    _ensure_welcome_session(db, user)

    db.add(AuditLog(user_id=user.id, action="login", detail="登录成功", success=True))
    db.commit()

    return TokenResponse(
        token=token,
        user_id=user.id,
        username=user.username,
        role=user.role,
        nickname=user.nickname or user.username,
        avatar=user.avatar,
    )


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
    return CurrentUserResponse(
        user_id=user.id,
        username=user.username,
        role=user.role,
        nickname=user.nickname or user.username,
        avatar=user.avatar,
    )


@router.put("/me", response_model=CurrentUserResponse)
def update_me(
    req: UpdateCurrentUserRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
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
        user.avatar = avatar
    db.add(AuditLog(user_id=user.id, action="profile_update", detail="更新个人资料", success=True))
    db.commit()
    db.refresh(user)
    return CurrentUserResponse(
        user_id=user.id,
        username=user.username,
        role=user.role,
        nickname=user.nickname or user.username,
        avatar=user.avatar,
    )
