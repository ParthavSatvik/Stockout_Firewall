"""Authentication.

Two verification paths:
  1. Supabase-issued access tokens, verified against the project's JWKS (ES256/RS256 signing
     keys) or, for legacy projects, SUPABASE_JWT_SECRET (HS256). Roles always come from our own
     users table -- never from token metadata, which Supabase users can edit themselves.
  2. A local demo JWT (also HS256, LOCAL_JWT_SECRET) issued by our own /api/auth/login for
     local development without a Supabase project.

Passwords for the local/demo path are hashed with bcrypt via passlib-free stdlib hmac+bcrypt
through `cryptography` is overkill; we use `bcrypt`-less PBKDF2 (stdlib hashlib) to avoid
pulling in another dependency, which is adequate for a local-only demo credential store.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.core import User

settings = get_settings()
bearer_scheme = HTTPBearer(auto_error=False)

PBKDF2_ITERATIONS = 390_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    expected = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return hmac.compare_digest(expected.hex(), digest_hex)


def create_local_access_token(user_id: str, role: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "role": role,
        "iss": "stockout-firewall-local",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.local_jwt_secret, algorithm="HS256")


def _decode_local(token: str) -> dict | None:
    if not settings.demo_mode or settings.app_env == "production":
        return None
    try:
        return jwt.decode(token, settings.local_jwt_secret, algorithms=["HS256"], issuer="stockout-firewall-local", options={"require": ["exp", "sub", "iss"]})
    except jwt.PyJWTError:
        return None


_jwks_client: jwt.PyJWKClient | None = None


def _jwks() -> jwt.PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(settings.resolved_supabase_jwks_url, cache_keys=True, lifespan=600, timeout=5)
    return _jwks_client


def _decode_supabase(token: str) -> dict | None:
    if not settings.supabase_configured:
        return None
    common = dict(audience="authenticated", issuer=settings.supabase_url.rstrip("/") + "/auth/v1",
                  options={"require": ["exp", "sub", "iss", "aud"]})
    try:
        alg = jwt.get_unverified_header(token).get("alg")
        if alg in ("ES256", "RS256") and settings.resolved_supabase_jwks_url:
            key = _jwks().get_signing_key_from_jwt(token).key
            return jwt.decode(token, key, algorithms=["ES256", "RS256"], **common)
        if alg == "HS256" and settings.supabase_jwt_secret:
            return jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"], **common)
    except (jwt.PyJWTError, jwt.PyJWKClientError):
        return None
    return None


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token = credentials.credentials
    claims = _decode_local(token) or _decode_supabase(token)
    if claims is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user: User | None = None
    sub = claims.get("sub")
    if sub:
        if claims.get("iss") == "stockout-firewall-local":
            user = db.get(User, sub)
        else:
            user = db.query(User).filter(User.supabase_user_id == sub).first()
            email = (claims.get("email") or "").lower()
            if user is None and email and not claims.get("is_anonymous"):
                # First Supabase sign-in of an existing account: link once, by email. This
                # relies on Supabase "Confirm email" being enabled for the project.
                user = db.query(User).filter(User.email == email, User.supabase_user_id.is_(None)).first()
                if user is not None:
                    user.supabase_user_id = sub
                    db.commit()

    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


def require_role(*roles: str):
    def _check(user: User = Depends(get_current_user)) -> User:
        if user.role.value not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return _check
