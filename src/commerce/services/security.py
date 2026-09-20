from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from time import time
from uuid import UUID

from sqlmodel import Session, select

from commerce.core.config import get_settings
from commerce.domain.models import AdminUser

SESSION_COOKIE_NAME = "commerce_admin_session"
PASSWORD_ITERATIONS = 310_000
API_KEY_PREFIX_BYTES = 6
API_KEY_SECRET_BYTES = 24


@dataclass(frozen=True)
class SessionToken:
    user_id: UUID
    expires_at: int


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return (
        f"pbkdf2_sha256${PASSWORD_ITERATIONS}$"
        f"{base64.urlsafe_b64encode(salt).decode()}$"
        f"{base64.urlsafe_b64encode(digest).decode()}"
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode())
        expected = base64.urlsafe_b64decode(digest_text.encode())
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            int(iterations_text),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def authenticate_admin(session: Session, email: str, password: str) -> AdminUser | None:
    statement = select(AdminUser).where(AdminUser.email == email.strip().lower())
    admin = session.exec(statement).first()
    if admin is None or not admin.is_active:
        return None
    if not verify_password(password, admin.password_hash):
        return None
    return admin


def create_session_cookie(admin: AdminUser) -> str:
    settings = get_settings()
    expires_at = int(time()) + settings.admin_session_ttl_seconds
    payload = f"{admin.id}:{expires_at}"
    signature = _sign(payload)
    token = f"{payload}:{signature}"
    return base64.urlsafe_b64encode(token.encode()).decode()


def read_session_cookie(value: str | None) -> SessionToken | None:
    if not value:
        return None
    try:
        token = base64.urlsafe_b64decode(value.encode()).decode()
        user_id_text, expires_text, signature = token.rsplit(":", 2)
        payload = f"{user_id_text}:{expires_text}"
        if not hmac.compare_digest(signature, _sign(payload)):
            return None
        expires_at = int(expires_text)
        if expires_at < int(time()):
            return None
        return SessionToken(user_id=UUID(user_id_text), expires_at=expires_at)
    except (ValueError, TypeError):
        return None


def get_admin_from_cookie(session: Session, value: str | None) -> AdminUser | None:
    token = read_session_cookie(value)
    if token is None:
        return None
    admin = session.get(AdminUser, token.user_id)
    if admin is None or not admin.is_active:
        return None
    return admin


def make_demo_password() -> str:
    return secrets.token_urlsafe(12)


def generate_api_key() -> tuple[str, str, str]:
    prefix = f"ck_live_{secrets.token_urlsafe(API_KEY_PREFIX_BYTES)}"
    secret = secrets.token_urlsafe(API_KEY_SECRET_BYTES)
    raw_key = f"{prefix}.{secret}"
    return raw_key, prefix, hash_api_key(raw_key)


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def extract_api_key_prefix(raw_key: str) -> str | None:
    if "." not in raw_key:
        return None
    prefix, _secret = raw_key.split(".", 1)
    if not prefix.startswith("ck_live_"):
        return None
    return prefix


def verify_api_key(raw_key: str, key_hash: str) -> bool:
    return hmac.compare_digest(hash_api_key(raw_key), key_hash)


def _sign(payload: str) -> str:
    settings = get_settings()
    digest = hmac.new(
        settings.admin_session_secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).decode()
