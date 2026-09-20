from uuid import UUID

from sqlmodel import Session, col, select

from commerce.domain.models import AdminUser, AuditLog

SYSTEM_ACTOR_EMAIL = "system@local"


def record_audit_log(
    session: Session,
    *,
    actor: AdminUser | None,
    action: str,
    entity_type: str,
    entity_id: str | UUID,
    summary: str,
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor.id if actor else None,
        actor_email=actor.email if actor else SYSTEM_ACTOR_EMAIL,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        summary=summary[:500],
    )
    session.add(entry)
    return entry


def list_audit_logs(session: Session, *, limit: int = 100) -> list[AuditLog]:
    statement = select(AuditLog).order_by(col(AuditLog.created_at).desc()).limit(limit)
    return list(session.exec(statement).all())
