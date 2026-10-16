from datetime import timedelta
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import settings
from models.classroom import Class, StudentRoster
from models.user import User
from models.user_role import UserRole
from models.identity_relations import Student, StudentUserBinding
from schemas.user import (
    LoginRequest,
    TokenResponse,
    UserProfilePatch,
    UserRegisterRequest,
    UserResponse,
    WechatLoginRequest,
    WechatPhoneRequest,
)
from utils.accounts import create_phone_user
from utils.database import get_db
from utils.deps import get_current_user, get_optional_current_user
from utils.logger import logger
from utils.security import create_access_token, get_password_hash, verify_password
from services.wechat_identity import WeChatAPIError, WeChatIdentityClient

router = APIRouter(prefix="/users", tags=["用户管理"])


def get_wechat_client() -> WeChatIdentityClient:
    return WeChatIdentityClient()


def _sync_legacy_role(db: Session, user: User) -> None:
    role_code = {"admin": "platform_admin", "teacher": "teacher"}.get(user.role)
    if role_code is None:
        return
    found = (
        db.query(UserRole.user_id)
        .filter(UserRole.user_id == user.id, UserRole.role_code == role_code)
        .first()
    )
    if not found:
        db.add(UserRole(user_id=user.id, role_code=role_code, status="active"))


def _user_payload(db: Session, user: User) -> dict:
    roles = [
        role_code
        for (role_code,) in (
            db.query(UserRole.role_code)
            .filter(UserRole.user_id == user.id, UserRole.status == "active")
            .order_by(UserRole.role_code)
            .all()
        )
    ]
    payload = {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "phone": user.phone,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "roles": roles,
        "wechat_bind_status": "bound" if user.wechat_openid else "unbound",
        "phone_source": user.phone_source,
        "profile_complete": bool(user.full_name and user.phone),
    }
    if user.role == "student":
        identity_binding = (
            db.query(Student, StudentUserBinding)
            .join(StudentUserBinding, StudentUserBinding.student_id == Student.id)
            .filter(
                StudentUserBinding.user_id == user.id,
                StudentUserBinding.status == "active",
                Student.status == "active",
            )
            .order_by(Student.id)
            .first()
        )
        binding = db.query(StudentRoster, Class).join(
            Class, Class.id == StudentRoster.class_id
        ).filter(StudentRoster.bound_user_id == user.id).first()
        if identity_binding:
            payload.update({
                "bind_status": "bound",
                "student_id": identity_binding[0].id,
                "student_name": identity_binding[0].name,
            })
        if binding:
            roster, classroom = binding
            payload.update({
                "bind_status": "bound",
                "bound_class_id": classroom.id,
                "bound_class_name": classroom.name,
                "roster_id": roster.id,
                "student_name": roster.student_name,
                "student_no": roster.student_no,
            })
        elif identity_binding is None:
            payload["bind_status"] = "unbound"
    return payload


def _create_wechat_user(db: Session, openid: str, unionid: str | None) -> User:
    identity_suffix = secrets.token_hex(16)
    user = User(
        username="wx_" + identity_suffix,
        email="wx_" + identity_suffix + "@example.com",
        phone=None,
        hashed_password=get_password_hash(secrets.token_urlsafe(48)),
        full_name=None,
        role="student",  # legacy compatibility; student is not stored in UserRole.
        is_active=True,
        wechat_openid=openid,
        wechat_unionid=unionid,
        phone_source=None,
    )
    db.add(user)
    db.flush()
    return user


@router.post("/register", response_model=UserResponse)
def register_user(request: UserRegisterRequest, db: Session = Depends(get_db)):
    """公开注册只创建学生手机号账号。"""
    if request.role not in (None, "student"):
        raise HTTPException(status_code=403, detail="公开注册仅支持学生账号")
    if db.query(User.id).filter(User.phone == request.phone).first():
        raise HTTPException(status_code=409, detail="该手机号已注册")
    if request.email and db.query(User.id).filter(User.email == str(request.email)).first():
        raise HTTPException(status_code=409, detail="该邮箱已被使用")

    user = create_phone_user(
        db,
        phone=request.phone,
        password=request.password,
        role="student",
        full_name=request.full_name.strip() if request.full_name else None,
        email=str(request.email) if request.email else None,
    )
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="手机号或邮箱已被使用")

    logger.info("学生账号注册成功: user_id=%s", user.id)
    return _user_payload(db, user)


@router.post("/login", response_model=TokenResponse)
def login_user(login: LoginRequest, db: Session = Depends(get_db)):
    query = db.query(User)
    if login.identifier:
        by_username = query.filter(User.username == login.identifier).first()
        by_phone = query.filter(User.phone == login.identifier).first()
        if by_username and by_phone and by_username.id != by_phone.id:
            raise HTTPException(status_code=409, detail="登录账号冲突，请联系管理员")
        user = by_username or by_phone
    elif login.phone:
        user = query.filter(User.phone == login.phone).first()
    else:
        user = query.filter(User.email == str(login.email)).first()
    if user is None or not verify_password(login.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="账号或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="账号已停用")

    token = create_access_token(
        data={"sub": user.username, "user_id": user.id},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    logger.info("账号登录成功: user_id=%s", user.id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": _user_payload(db, user),
    }


@router.get("/me", response_model=UserResponse)
def get_my_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _user_payload(db, current_user)


@router.post("/wechat-login")
def wechat_login(
    request: WechatLoginRequest,
    db: Session = Depends(get_db),
    authenticated_user: User | None = Depends(get_optional_current_user),
    client: WeChatIdentityClient = Depends(get_wechat_client),
):
    try:
        openid, unionid = client.exchange_login_code(request.code)
    except WeChatAPIError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None

    user_by_openid = db.query(User).filter(User.wechat_openid == openid).first()
    if authenticated_user:
        if user_by_openid and user_by_openid.id != authenticated_user.id:
            raise HTTPException(status_code=409, detail="该微信身份已关联其他账号")
        if authenticated_user.wechat_openid and authenticated_user.wechat_openid != openid:
            raise HTTPException(status_code=409, detail="当前账号已关联其他微信身份")
        user = authenticated_user
        user.wechat_openid = openid
        user.wechat_unionid = unionid or user.wechat_unionid
    elif user_by_openid:
        user = user_by_openid
        user.wechat_unionid = unionid or user.wechat_unionid
    else:
        user = _create_wechat_user(db, openid, unionid)

    _sync_legacy_role(db, user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        # A concurrent first login may have inserted the same unique OpenID.
        user = db.query(User).filter(User.wechat_openid == openid).first()
        if user is None:
            raise HTTPException(status_code=409, detail="微信身份关联冲突，请重试") from None
    token = create_access_token(
        data={"sub": user.username, "user_id": user.id},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    logger.info("微信身份登录成功: user_id=%s", user.id)
    return {"access_token": token, "token_type": "bearer", "user": _user_payload(db, user)}


@router.post("/wechat-phone", response_model=UserResponse)
def bind_wechat_phone(
    request: WechatPhoneRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    client: WeChatIdentityClient = Depends(get_wechat_client),
):
    try:
        phone = client.exchange_phone_code(request.code)
    except WeChatAPIError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    duplicate = db.query(User.id).filter(User.phone == phone, User.id != current_user.id).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="该手机号已关联其他账号")
    current_user.phone = phone
    current_user.phone_source = "wechat"
    try:
        db.commit()
        db.refresh(current_user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="该手机号已关联其他账号") from None
    return _user_payload(db, current_user)


@router.patch("/me/profile", response_model=UserResponse)
def update_my_profile(
    request: UserProfilePatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    fields = request.model_fields_set
    if "full_name" in fields:
        current_user.full_name = request.full_name or None
    if "phone" in fields:
        phone = request.phone or None
        if phone:
            duplicate = db.query(User.id).filter(User.phone == phone, User.id != current_user.id).first()
            if duplicate:
                raise HTTPException(status_code=409, detail="该手机号已关联其他账号")
        current_user.phone = phone
        current_user.phone_source = "manual" if phone else None
    try:
        db.commit()
        db.refresh(current_user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="资料与现有账号冲突") from None
    return _user_payload(db, current_user)


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.id != user_id and current_user.role != "admin":
        raise HTTPException(status_code=404, detail="用户不存在")
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return _user_payload(db, user)


@router.put("/{user_id}/status", response_model=UserResponse)
def update_user_status(
    user_id: int,
    is_active: bool,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="权限不足")
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.is_active = is_active
    db.commit()
    db.refresh(user)
    return _user_payload(db, user)
