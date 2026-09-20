from uuid import UUID

from sqlmodel import Session, col, select

from commerce.domain.models import AdminUser


def get_admin_by_email(session: Session, email: str) -> AdminUser | None:
    statement = select(AdminUser).where(AdminUser.email == email.strip().lower())
    return session.exec(statement).first()


def get_admin_by_id(session: Session, admin_id: UUID) -> AdminUser | None:
    return session.get(AdminUser, admin_id)


def list_admins(session: Session, *, limit: int = 100) -> list[AdminUser]:
    statement = select(AdminUser).order_by(col(AdminUser.created_at).desc()).limit(limit)
    return list(session.exec(statement).all())
