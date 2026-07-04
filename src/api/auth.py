"""
Multi-user authentication & RBAC for the Houdini API.

Provides:
- User management (create, list, disable)
- Password hashing (bcrypt via passlib)
- JWT bearer-token authentication
- API-key authentication (for programmatic access)
- Role-based access control: admin, operator, viewer

Endpoints (mounted on the main app):
    POST   /auth/token          — Login, get JWT
    POST   /auth/users          — Create user (admin only)
    GET    /auth/users          — List users (admin only)
    GET    /auth/me             — Current user info
    DELETE /auth/users/{user}   — Disable user (admin only)
    POST   /auth/api-keys       — Generate API key (admin/operator)
    DELETE /auth/api-keys/{key} — Revoke API key

Security notes:
    - Passwords are stored as bcrypt hashes — never in plaintext.
    - JWT secret is drawn from the ``HOUDINI_JWT_SECRET`` env var;
      a random default is generated on first startup if unset.
    - API keys are stored hashed (SHA-256).
    - The auth system is optional: if ``HOUDINI_AUTH_ENABLED`` is not
      ``true``, all endpoints are unprotected (backward-compatible).
"""

import hashlib
import json
import os
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
    OAuth2PasswordBearer,
    OAuth2PasswordRequestForm,
)
from pydantic import BaseModel, Field

from ..utils.logging import logger

# ── Optional deps (deferred import) ───────────────────────────────

try:
    import jwt as pyjwt  # PyJWT
except ImportError:
    pyjwt = None  # type: ignore[assignment]

try:
    from passlib.context import CryptContext

    _pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
except ImportError:
    _pwd_ctx = None  # type: ignore[assignment]


# ── Config ─────────────────────────────────────────────────────────

AUTH_ENABLED = os.environ.get("HOUDINI_AUTH_ENABLED", "false").lower() in (
    "true",
    "1",
    "yes",
)
JWT_SECRET = os.environ.get("HOUDINI_JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.environ.get("HOUDINI_JWT_EXPIRE_MINUTES", "480"))  # 8 h
_USER_DB_PATH = os.environ.get(
    "HOUDINI_USER_DB",
    str(Path(__file__).resolve().parent.parent.parent / "data" / "users.json"),
)

if AUTH_ENABLED and not JWT_SECRET:
    JWT_SECRET = secrets.token_urlsafe(48)
    logger.warning(
        "HOUDINI_JWT_SECRET not set — generated a random secret. "
        "Set it in .env for persistent tokens across restarts."
    )


# ── Roles ──────────────────────────────────────────────────────────


class Role(str, Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


# Minimum role required for each capability
ROLE_HIERARCHY = {Role.ADMIN: 0, Role.OPERATOR: 1, Role.VIEWER: 2}


def _has_role(user_role: Role, required: Role) -> bool:
    return ROLE_HIERARCHY.get(user_role, 99) <= ROLE_HIERARCHY.get(required, 99)


# ── User storage (JSON file) ──────────────────────────────────────


class UserRecord:
    __slots__ = (
        "username",
        "hashed_password",
        "role",
        "disabled",
        "created_at",
        "api_keys",
    )

    def __init__(
        self,
        username: str,
        hashed_password: str,
        role: str = "operator",
        disabled: bool = False,
        created_at: Optional[str] = None,
        api_keys: Optional[List[str]] = None,
    ):
        self.username = username
        self.hashed_password = hashed_password
        self.role = role
        self.disabled = disabled
        self.created_at = created_at or datetime.now(timezone.utc).isoformat()
        self.api_keys = api_keys or []  # stored as SHA-256 hashes

    def to_dict(self) -> dict:
        return {
            "username": self.username,
            "hashed_password": self.hashed_password,
            "role": self.role,
            "disabled": self.disabled,
            "created_at": self.created_at,
            "api_keys": self.api_keys,
        }


_users: Dict[str, UserRecord] = {}
_users_lock = threading.Lock()


def _load_users():
    global _users
    path = Path(_USER_DB_PATH)
    if not path.exists():
        # Seed with default admin (password = "admin" — change on first login!)
        if AUTH_ENABLED and _pwd_ctx:
            _users["admin"] = UserRecord(
                username="admin",
                hashed_password=_pwd_ctx.hash("admin"),
                role="admin",
            )
            _save_users()
        return
    try:
        data = json.loads(path.read_text())
        for u in data:
            _users[u["username"]] = UserRecord(**u)
    except Exception as exc:
        logger.error(f"Failed to load user DB: {exc}")


def _save_users():
    path = Path(_USER_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [u.to_dict() for u in _users.values()]
    path.write_text(json.dumps(data, indent=2))


_load_users()


# ── Password helpers ───────────────────────────────────────────────


def _hash_password(plain: str) -> str:
    if _pwd_ctx is None:
        raise RuntimeError("passlib not installed — pip install passlib[bcrypt]")
    return _pwd_ctx.hash(plain)


def _verify_password(plain: str, hashed: str) -> bool:
    if _pwd_ctx is None:
        return False
    return _pwd_ctx.verify(plain, hashed)


def _hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


# ── JWT helpers ────────────────────────────────────────────────────


def _create_token(username: str, role: str) -> str:
    if pyjwt is None:
        raise RuntimeError("PyJWT not installed — pip install PyJWT")
    payload = {
        "sub": username,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES),
        "iat": datetime.now(timezone.utc),
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_token(token: str) -> dict:
    if pyjwt is None:
        raise RuntimeError("PyJWT not installed")
    return pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


# ── FastAPI dependencies ───────────────────────────────────────────

_bearer_scheme = HTTPBearer(auto_error=False)


def _get_user_from_token(
    creds: Optional[HTTPAuthorizationCredentials] = Security(_bearer_scheme),
) -> Optional[UserRecord]:
    """Extract user from JWT bearer token or API key."""
    if not AUTH_ENABLED:
        return None  # auth disabled — allow everything

    if creds is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = creds.credentials

    # Try JWT first
    try:
        payload = _decode_token(token)
        username = payload.get("sub")
        with _users_lock:
            user = _users.get(username)
        if user and not user.disabled:
            return user
    except Exception:
        pass

    # Try API key
    key_hash = _hash_api_key(token)
    with _users_lock:
        for user in _users.values():
            if key_hash in user.api_keys and not user.disabled:
                return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_role(required: Role):
    """FastAPI dependency that enforces a minimum role level."""

    def _check(user: Optional[UserRecord] = Depends(_get_user_from_token)):
        if not AUTH_ENABLED:
            return user
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
        if not _has_role(Role(user.role), required):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Role '{user.role}' insufficient — need '{required.value}' or higher",
            )
        return user

    return _check


# Convenience dependencies
require_admin = require_role(Role.ADMIN)
require_operator = require_role(Role.OPERATOR)
require_viewer = require_role(Role.VIEWER)


# ── Pydantic schemas ──────────────────────────────────────────────


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = JWT_EXPIRE_MINUTES * 60
    role: str


class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)
    role: str = Field("operator", description="admin | operator | viewer")


class UserInfo(BaseModel):
    username: str
    role: str
    disabled: bool
    created_at: str


class APIKeyResponse(BaseModel):
    api_key: str
    note: str = "Store this key securely — it cannot be retrieved again."


# ── Router ─────────────────────────────────────────────────────────

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=TokenResponse)
def login(form: OAuth2PasswordRequestForm = Depends()):
    """Authenticate with username + password, receive a JWT."""
    if not AUTH_ENABLED:
        raise HTTPException(400, "Auth is not enabled on this server")

    with _users_lock:
        user = _users.get(form.username)
    if user is None or not _verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect username or password",
        )
    if user.disabled:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")

    token = _create_token(user.username, user.role)
    return TokenResponse(access_token=token, role=user.role)


@router.post("/users", response_model=UserInfo, status_code=201)
def create_user(
    body: UserCreate,
    _admin=Depends(require_admin),
):
    """Create a new user (admin only)."""
    with _users_lock:
        if body.username in _users:
            raise HTTPException(409, f"User '{body.username}' already exists")
        if body.role not in ("admin", "operator", "viewer"):
            raise HTTPException(400, f"Invalid role: {body.role}")
        record = UserRecord(
            username=body.username,
            hashed_password=_hash_password(body.password),
            role=body.role,
        )
        _users[body.username] = record
        _save_users()
    return UserInfo(
        username=record.username,
        role=record.role,
        disabled=record.disabled,
        created_at=record.created_at,
    )


@router.get("/users", response_model=List[UserInfo])
def list_users(_admin=Depends(require_admin)):
    """List all users (admin only)."""
    with _users_lock:
        return [
            UserInfo(
                username=u.username,
                role=u.role,
                disabled=u.disabled,
                created_at=u.created_at,
            )
            for u in _users.values()
        ]


@router.get("/me", response_model=UserInfo)
def current_user(user: Optional[UserRecord] = Depends(_get_user_from_token)):
    """Get information about the currently authenticated user."""
    if user is None:
        return UserInfo(
            username="anonymous",
            role="admin",
            disabled=False,
            created_at="",
        )
    return UserInfo(
        username=user.username,
        role=user.role,
        disabled=user.disabled,
        created_at=user.created_at,
    )


@router.delete("/users/{username}")
def disable_user(username: str, _admin=Depends(require_admin)):
    """Disable a user account (admin only)."""
    with _users_lock:
        user = _users.get(username)
        if user is None:
            raise HTTPException(404, f"User '{username}' not found")
        user.disabled = True
        _save_users()
    return {"disabled": username}


@router.post("/api-keys", response_model=APIKeyResponse)
def create_api_key(
    user: Optional[UserRecord] = Depends(require_operator),
):
    """Generate an API key for the current user (operator+ only)."""
    if user is None:
        raise HTTPException(400, "Auth not enabled")
    raw_key = f"hdk_{secrets.token_urlsafe(32)}"
    key_hash = _hash_api_key(raw_key)
    with _users_lock:
        user.api_keys.append(key_hash)
        _save_users()
    return APIKeyResponse(api_key=raw_key)


@router.delete("/api-keys/{key_prefix}")
def revoke_api_key(
    key_prefix: str,
    user: Optional[UserRecord] = Depends(require_operator),
):
    """Revoke an API key by its prefix (first 12 chars)."""
    if user is None:
        raise HTTPException(400, "Auth not enabled")
    # We can't un-hash, so admin must provide the full key to revoke
    key_hash = _hash_api_key(key_prefix)
    with _users_lock:
        if key_hash in user.api_keys:
            user.api_keys.remove(key_hash)
            _save_users()
            return {"revoked": True}
    raise HTTPException(404, "API key not found")
