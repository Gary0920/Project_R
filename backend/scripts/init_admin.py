"""首次使用初始化脚本：创建第一个管理员账号。

用法：
  cd backend
  ..\venv\Scripts\python scripts\init_admin.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from passlib.context import CryptContext

from models import BASE_DIR, init_db, SessionLocal
from models.user import User

load_dotenv(BASE_DIR / ".env")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def main():
    init_db()
    db = SessionLocal()

    existing = db.query(User).filter(User.role == "admin").first()
    if existing:
        print(f"管理员账号已存在（用户名: {existing.username}），跳过创建。")
        db.close()
        return

    import getpass

    print("=== 创建第一个管理员账号 ===")
    username = input("用户名（默认 admin）: ").strip() or "admin"

    while True:
        password = getpass.getpass("密码（至少 6 位）: ")
        if len(password) < 6:
            print("密码太短，请重新输入。")
            continue
        confirm = getpass.getpass("确认密码: ")
        if password != confirm:
            print("两次密码不一致，请重新输入。")
            continue
        break

    nickname = input("昵称（默认 管理员）: ").strip() or "管理员"

    user = User(
        username=username,
        password_hash=pwd_context.hash(password),
        role="admin",
        nickname=nickname,
    )
    db.add(user)
    db.commit()
    db.close()

    print(f"\n✅ 管理员账号创建成功！")
    print(f"   用户名: {username}")
    print(f"   昵称:   {nickname}")
    print(f"   角色:   管理员")


if __name__ == "__main__":
    main()
