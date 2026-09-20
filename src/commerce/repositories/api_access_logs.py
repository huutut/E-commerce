from sqlmodel import Session, col, select

from commerce.domain.models import ApiAccessLog, ApiKey


def record_api_access(
    session: Session,
    *,
    api_key: ApiKey | None,
    key_prefix: str,
    method: str,
    path: str,
    status: str,
    status_code: int,
) -> ApiAccessLog:
    log = ApiAccessLog(
        api_key_id=api_key.id if api_key else None,
        key_prefix=key_prefix,
        method=method,
        path=path[:300],
        status=status,
        status_code=status_code,
    )
    session.add(log)
    return log


def list_api_access_logs(session: Session, *, limit: int = 100) -> list[ApiAccessLog]:
    statement = select(ApiAccessLog).order_by(col(ApiAccessLog.created_at).desc()).limit(limit)
    return list(session.exec(statement).all())
