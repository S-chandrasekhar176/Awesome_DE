"""
FastAPI dependencies for UltraBot Web.

Provides dependency injection for:
  - JWT-based authentication
  - Engine instance access
  - Repository instance access

Usage in app.py:
  from api.dependencies import set_engine, set_repository
  set_engine(engine)
  set_repository(repo)
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from config.settings import settings
from db.repository import Repository
from core.engine import UltraBotEngine

logger = logging.getLogger(__name__)

# OAuth2 scheme – expects Bearer token in Authorization header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# Module-level singletons – set by app.py after instantiation
_engine_instance: Optional[UltraBotEngine] = None
_repo_instance: Optional[Repository] = None

def set_engine(eng: UltraBotEngine) -> None:
    """Set the global engine instance. Called once from app.py."""
    global _engine_instance
    _engine_instance = eng
    logger.info("Engine instance registered in dependencies")


def set_repository(repo: Repository) -> None:
    """Set the global repository instance. Called once from app.py."""
    global _repo_instance
    _repo_instance = repo
    logger.info("Repository instance registered in dependencies")


def get_engine() -> UltraBotEngine:
    """FastAPI dependency that returns the global engine instance."""
    if _engine_instance is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Engine not initialized",
        )
    return _engine_instance


async def get_repository():
    """FastAPI dependency that yields a request-scoped repository session."""
    from db.database import async_session_factory
    async with async_session_factory() as session:
        yield Repository(session)


ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

# Hardcoded admin credentials
_ADMIN_USERNAME = "admin"
# bcrypt hash of "admin" – generated with: bcrypt.hashpw(b"admin", bcrypt.gensalt())
_ADMIN_PASSWORD_HASH = (
    "$2b$12$Wb5rmUCZlzToN7WVIzbJX.409papQngxfB/vb7LjQdUumBzErPbhG"
)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a bcrypt hash."""
    try:
        import bcrypt
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        # Fallback: check if user overrode the hash via settings
        # If no bcrypt available, allow default admin/admin
        if plain_password == "admin" and hashed_password == _ADMIN_PASSWORD_HASH:
            return True
        return False


def create_access_token(data: dict, expires_delta: Optional[int] = None) -> str:
    """Create a JWT access token."""
    from datetime import datetime, timedelta, timezone
    to_encode = data.copy()
    expire_minutes = (expires_delta or ACCESS_TOKEN_EXPIRE_HOURS) * 60
    expire = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    """Verify JWT token and return the username.

    Raises:
        HTTPException(401) if token is invalid or expired.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if username is None:
            raise credentials_exception
        return username
    except JWTError as exc:
        logger.warning("JWT validation failed: %s", exc)
        raise credentials_exception from exc
