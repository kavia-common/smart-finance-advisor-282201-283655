from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.config import get_env
from src.db.models import User
from src.db.session import get_db

# Password hashing context using bcrypt
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Auth settings via env (do not hard-code secrets)
def _jwt_secret() -> str:
    secret = get_env("JWT_SECRET", None)
    if not secret:
        # For local/dev default only; strongly recommend setting JWT_SECRET in .env
        secret = "CHANGE_ME_DEV_SECRET"
    return secret


def _jwt_algorithm() -> str:
    return get_env("JWT_ALGORITHM", "HS256") or "HS256"


def _jwt_expiration_minutes() -> int:
    try:
        return int(get_env("JWT_EXPIRE_MINUTES", "60") or "60")
    except Exception:
        return 60


# PUBLIC_INTERFACE
def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return _pwd_context.hash(password)


# PUBLIC_INTERFACE
def verify_password(plain_password: str, password_hash: str | None) -> bool:
    """Verify a plaintext password against a stored hash. Returns False if hash is missing."""
    if not password_hash:
        return False
    try:
        return _pwd_context.verify(plain_password, password_hash)
    except Exception:
        return False


# PUBLIC_INTERFACE
def create_access_token(subject: str | int, expires_delta: Optional[timedelta] = None, extra_claims: Optional[dict] = None) -> str:
    """Create a signed JWT access token for the given subject (user id)."""
    to_encode: dict[str, Any] = {"sub": str(subject)}
    if extra_claims:
        to_encode.update(extra_claims)
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=_jwt_expiration_minutes()))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, _jwt_secret(), algorithm=_jwt_algorithm())
    return encoded_jwt


_http_bearer = HTTPBearer(auto_error=False)


# PUBLIC_INTERFACE
def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_http_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Dependency to resolve the current authenticated user from Bearer token.

    Raises:
        HTTPException 401 if no/invalid credentials.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token = credentials.credentials
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[_jwt_algorithm()])
        sub = payload.get("sub")
        if sub is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    try:
        user_id = int(sub)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")

    user = db.get(User, user_id)
    if user is None:
        # Attempt fallback lookup via email claim if present
        email = payload.get("email")
        if email:
            user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return user
