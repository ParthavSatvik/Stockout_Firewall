from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.core import MerchantProfile, SupplierProfile, User, UserRole
from app.schemas.auth import CurrentUserResponse, LoginRequest, RegisterRequest, TokenResponse
from app.security import create_local_access_token, get_current_user, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    from app.config import get_settings
    if not get_settings().demo_mode:
        raise HTTPException(403, "Local registration is demo-only; use configured identity provider")
    if payload.role == UserRole.ADMIN:
        raise HTTPException(403, "Administrator accounts cannot self-register")
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        role=payload.role,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.flush()

    if payload.role == UserRole.MERCHANT:
        db.add(MerchantProfile(user_id=user.id, business_name=payload.business_name, city=payload.city))
    elif payload.role == UserRole.SUPPLIER:
        db.add(SupplierProfile(user_id=user.id, business_name=payload.business_name, city=payload.city))

    db.commit()
    token = create_local_access_token(user.id, user.role.value)
    return TokenResponse(access_token=token, role=user.role, user_id=user.id)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    from app.config import get_settings
    if not get_settings().demo_mode:
        raise HTTPException(403, "Local login is demo-only")
    user = db.query(User).filter(User.email == payload.email).first()
    if user is None or user.hashed_password is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    token = create_local_access_token(user.id, user.role.value)
    return TokenResponse(access_token=token, role=user.role, user_id=user.id)


@router.get("/me", response_model=CurrentUserResponse)
def me(user: User = Depends(get_current_user)) -> User:
    return user
