from datetime import UTC, datetime
from uuid import UUID

from sqlmodel import Session, col, select

from commerce.domain.models import AdminUser, ApiKey
from commerce.repositories.audit import SYSTEM_ACTOR_EMAIL
from commerce.services.security import (
    extract_api_key_prefix,
    generate_api_key,
    verify_api_key,
)


def create_api_key(
    session: Session,
    *,
    name: str,
    actor: AdminUser | None,
) -> tuple[ApiKey, str]:
    raw_key, prefix, key_hash = generate_api_key()
    api_key = ApiKey(
        name=name.strip(),
        key_prefix=prefix,
        key_hash=key_hash,
        created_by_id=actor.id if actor else None,
        created_by_email=actor.email if actor else SYSTEM_ACTOR_EMAIL,
    )
    session.add(api_key)
    return api_key, raw_key


def get_api_key_by_id(session: Session, api_key_id: UUID) -> ApiKey | None:
    return session.get(ApiKey, api_key_id)


def list_api_keys(session: Session, *, limit: int = 100) -> list[ApiKey]:
    statement = select(ApiKey).order_by(col(ApiKey.created_at).desc()).limit(limit)
    return list(session.exec(statement).all())


def authenticate_api_key(session: Session, raw_key: str | None) -> ApiKey | None:
    if not raw_key:
        return None
    prefix = extract_api_key_prefix(raw_key)
    if prefix is None:
        return None
    statement = select(ApiKey).where(ApiKey.key_prefix == prefix)
    api_key = session.exec(statement).first()
    if api_key is None or not api_key.is_active:
        return None
    if not verify_api_key(raw_key, api_key.key_hash):
        return None

    api_key.last_used_at = datetime.now(UTC)
    session.add(api_key)
    session.commit()
    return api_key
