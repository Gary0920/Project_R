from passlib.context import CryptContext
from sqlalchemy.orm import Session

from models.user import User

SYSTEM_ADMIN_USERNAME = "sysadmin"
SYSTEM_ADMIN_PASSWORD = "Admin123"
SYSTEM_ADMIN_ROLE = "admin"
SYSTEM_ADMIN_NICKNAME = "System Admin"
SYSTEM_ADMIN_AVATAR = ""

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def is_system_admin_user(user: User | None) -> bool:
    return bool(user and user.username == SYSTEM_ADMIN_USERNAME)


def ensure_system_admin(db: Session) -> User:
    user = db.query(User).filter(User.username == SYSTEM_ADMIN_USERNAME).first()
    password_hash = pwd_context.hash(SYSTEM_ADMIN_PASSWORD)
    if not user:
        user = User(
            username=SYSTEM_ADMIN_USERNAME,
            password_hash=password_hash,
            role=SYSTEM_ADMIN_ROLE,
            nickname=SYSTEM_ADMIN_NICKNAME,
            avatar=SYSTEM_ADMIN_AVATAR,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    changed = False
    if user.role != SYSTEM_ADMIN_ROLE:
        user.role = SYSTEM_ADMIN_ROLE
        changed = True
    if user.nickname != SYSTEM_ADMIN_NICKNAME:
        user.nickname = SYSTEM_ADMIN_NICKNAME
        changed = True
    if user.avatar != SYSTEM_ADMIN_AVATAR:
        user.avatar = SYSTEM_ADMIN_AVATAR
        changed = True
    if not user.is_active:
        user.is_active = True
        changed = True
    if not pwd_context.verify(SYSTEM_ADMIN_PASSWORD, user.password_hash):
        user.password_hash = password_hash
        changed = True

    if changed:
        db.commit()
        db.refresh(user)
    return user
