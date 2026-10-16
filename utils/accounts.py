import secrets

from sqlalchemy.orm import Session

from models.user import User
from utils.security import get_password_hash


def create_phone_user(
    db: Session,
    *,
    phone: str,
    password: str,
    role: str,
    full_name: str | None = None,
    email: str | None = None,
) -> User:
    if role not in {"admin", "teacher", "student"}:
        raise ValueError("不支持的账号角色")

    prefix = {"admin": "adm", "teacher": "tch", "student": "stu"}[role]
    username = f"{prefix}_{phone}"
    while db.query(User.id).filter(User.username == username).first():
        username = f"{prefix}_{phone}_{secrets.token_hex(3)}"

    if email is None:
        # Legacy email column stays populated; phone is the only login identifier
        # shown to users for these accounts. example.com is reserved for examples.
        email = f"{phone}@example.com"

    user = User(
        username=username,
        email=email,
        phone=phone,
        hashed_password=get_password_hash(password),
        full_name=full_name,
        role=role,
        is_active=True,
    )
    db.add(user)
    return user
