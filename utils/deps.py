from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from utils.database import get_db
from models.user import User
from utils.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/users/login")
oauth2_optional_scheme = OAuth2PasswordBearer(
    tokenUrl="api/v1/users/login", auto_error=False
)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=401,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    user_id = payload.get("user_id")
    username = payload.get("sub")
    if isinstance(user_id, int):
        user = db.query(User).filter(User.id == user_id).first()
    elif isinstance(username, str):
        # Backward compatibility for JWTs issued before user_id became canonical.
        user = db.query(User).filter(User.username == username).first()
    else:
        raise credentials_exception
    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(status_code=401, detail="用户已被禁用")

    return user


async def get_optional_current_user(
    token: str | None = Depends(oauth2_optional_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    if not token:
        return None
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="无法验证凭据")
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if isinstance(user_id, int):
        user = db.query(User).filter(User.id == user_id).first()
    elif isinstance(username, str):
        user = db.query(User).filter(User.username == username).first()
    else:
        user = None
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="无法验证凭据")
    return user


__all__ = [
    "get_current_user",
    "get_optional_current_user",
    "oauth2_scheme",
    "oauth2_optional_scheme",
]
