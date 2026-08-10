"""Password, session, CSRF, and audit helpers."""

from __future__ import annotations

from datetime import timedelta, timezone
import hashlib
import secrets
import time

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import Admin, AdminSession, AuditEvent, utcnow


password_hasher = PasswordHasher()
SESSION_COOKIE = "unimate_session"
_login_failures: dict[str, list[float]] = {}


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def session_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(db: Session, admin: Admin) -> tuple[str, AdminSession]:
    token = secrets.token_urlsafe(48)
    now = utcnow()
    record = AdminSession(
        id=session_digest(token),
        admin_id=admin.id,
        csrf_token=secrets.token_urlsafe(32),
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=settings.session_max_hours),
    )
    db.add(record)
    db.flush()
    return token, record


def record_audit(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    admin_id: str | None = None,
    details: dict | None = None,
) -> None:
    db.add(
        AuditEvent(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            admin_id=admin_id,
            details=details or {},
        )
    )


def check_login_rate_limit(client_key: str) -> None:
    now = time.monotonic()
    recent = [attempt for attempt in _login_failures.get(client_key, []) if now - attempt < 300]
    _login_failures[client_key] = recent
    if len(recent) >= 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Try again later.",
        )


def record_login_failure(client_key: str) -> None:
    _login_failures.setdefault(client_key, []).append(time.monotonic())


def clear_login_failures(client_key: str) -> None:
    _login_failures.pop(client_key, None)


def require_session(
    request: Request,
    db: Session = Depends(get_db),
) -> tuple[Admin, AdminSession]:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    session = db.get(AdminSession, session_digest(token))
    now = utcnow()
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired.")
    expires_at = session.expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if session.revoked or expires_at <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired.")
    idle_limit = now - timedelta(minutes=settings.session_idle_minutes)
    last_seen_at = session.last_seen_at
    if last_seen_at.tzinfo is None:
        last_seen_at = last_seen_at.replace(tzinfo=timezone.utc)
    if last_seen_at <= idle_limit:
        session.revoked = True
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired.")
    admin = db.get(Admin, session.admin_id)
    if admin is None or not admin.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account unavailable.")
    password_change_paths = {"/api/auth/me", "/api/auth/password", "/api/auth/logout"}
    if admin.must_change_password and request.url.path not in password_change_paths:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The initial password must be changed before continuing.",
        )
    session.last_seen_at = now
    db.commit()
    return admin, session


def require_csrf(
    request: Request,
    auth: tuple[Admin, AdminSession] = Depends(require_session),
) -> tuple[Admin, AdminSession]:
    _, session = auth
    supplied = request.headers.get("X-CSRF-Token", "")
    if not supplied or not secrets.compare_digest(supplied, session.csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token.")
    return auth
