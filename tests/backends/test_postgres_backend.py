from __future__ import annotations

import asyncio
from typing import Any

import pytest

from skaal.backends.postgres_backend import PostgresBackend
from skaal.types.storage import SecondaryIndex


class _FakePostgresConnection:
    def __init__(self) -> None:
        self.executed: list[str] = []

    async def execute(self, sql: str, *_: Any) -> None:
        self.executed.append(sql)


class _FakeAcquire:
    def __init__(self, connection: _FakePostgresConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> _FakePostgresConnection:
        return self.connection

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


class _FakePool:
    def __init__(self, connection: _FakePostgresConnection) -> None:
        self.connection = connection

    def acquire(self) -> _FakeAcquire:
        return _FakeAcquire(self.connection)


@pytest.mark.asyncio
async def test_ensure_indexes_creates_deterministic_expression_indexes() -> None:
    connection = _FakePostgresConnection()
    backend = PostgresBackend("postgresql://example/test", namespace="team.members")
    backend._pool = _FakePool(connection)
    backend._pool_loop = asyncio.get_running_loop()
    setattr(
        backend,
        "_skaal_secondary_indexes",
        {
            "by_team": SecondaryIndex(name="by_team", partition_key="team", sort_key="score"),
            "by_email": SecondaryIndex(name="by_email", partition_key="email"),
        },
    )

    await backend.ensure_indexes()

    assert connection.executed == [
        "CREATE INDEX IF NOT EXISTS \"skaal_kv_idx_team_members_by_team\" ON skaal_kv (ns, (value #> '{team}'), (value #> '{score}'), key)",
        "CREATE INDEX IF NOT EXISTS \"skaal_kv_idx_team_members_by_email\" ON skaal_kv (ns, (value #> '{email}'), key)",
    ]
