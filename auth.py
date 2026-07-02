"""
===================================================================
Project: Wolf Host - لوحة استضافة البوتات
Author: @BLACK_ZERO2
Channel: https://t.me/ROXScripts2
Year: 2026
License: MIT
===================================================================
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from config import settings

security = HTTPBearer(auto_error=False)


def verify_password(plain_password: str) -> bool:
    """Check if the provided password matches the admin credentials."""
    return plain_password == settings.ADMIN_PASSWORD


def verify_username(username: str) -> bool:
    """Check if the provided username matches the admin credentials."""
    return username == settings.ADMIN_USERNAME


def create_access_token(
    data: dict, expires_delta: Optional[timedelta] = None
) -> str:
    """Generate a signed JWT access token with expiry.

    Args:
        data: Payload to encode in the token.
        expires_delta: Optional custom expiration duration.

    Returns:
        Encoded JWT string.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token.

    Args:
        token: The JWT string to decode.

    Returns:
        Decoded payload dict, or None if invalid/expired.
    """
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except JWTError:
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """FastAPI dependency that enforces JWT authentication.

    Raises:
        HTTPException: 401 if no credentials or token is invalid.

    Returns:
        Decoded token payload dict.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload
