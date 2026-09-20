import json
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from commerce.api.deps import redis_dep, session_dep
from commerce.domain.models import AdminRole, AdminUser, ApiKey
from commerce.main import create_app
from commerce.services.security import generate_api_key, hash_password


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.store[key] = value
        return True

    def delete(self, key: str) -> int:
        existed = key in self.store
        self.store.pop(key, None)
        return int(existed)

    def incr(self, key: str) -> int:
        value = int(self.store.get(key, "0")) + 1
        self.store[key] = str(value)
        return value

    def expire(self, key: str, seconds: int) -> bool:
        return key in self.store

    def ping(self) -> bool:
        return True

    def dump(self) -> dict[str, object]:
        return {key: json.loads(value) for key, value in self.store.items()}


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    fake_redis = FakeRedis()
    raw_api_key = ""
    with Session(engine) as session:
        raw_api_key, prefix, key_hash = generate_api_key()
        session.add(
            AdminUser(
                email="admin@example.com",
                full_name="测试管理员",
                password_hash=hash_password("Admin@123456"),
                role=AdminRole.OWNER,
            )
        )
        session.add(
            ApiKey(
                name="测试 API Key",
                key_prefix=prefix,
                key_hash=key_hash,
                created_by_email="test-suite",
            )
        )
        session.commit()

    def override_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app = create_app()
    app.dependency_overrides[session_dep] = override_session
    app.dependency_overrides[redis_dep] = lambda: fake_redis

    with TestClient(app) as test_client:
        test_client.headers.update({"X-API-Key": raw_api_key})
        test_client.post(
            "/admin/login",
            data={"email": "admin@example.com", "password": "Admin@123456"},
            follow_redirects=False,
        )
        yield test_client
