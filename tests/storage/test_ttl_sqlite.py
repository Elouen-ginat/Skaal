from __future__ import annotations

import asyncio

import pytest

from skaal.backends.sqlite_backend import SqliteBackend


@pytest.mark.asyncio
async def test_sqlite_backend_expires_rows_from_all_read_paths(tmp_path) -> None:
    backend = SqliteBackend(tmp_path / "ttl.db", namespace="ttl")
    try:
        await backend.set("ephemeral", {"value": 1}, ttl=0.02)
        await backend.set("stable", {"value": 2})

        await asyncio.sleep(0.05)

        assert await backend.get("ephemeral") is None
        assert dict(await backend.list()) == {"stable": {"value": 2}}
        assert dict(await backend.scan("")) == {"stable": {"value": 2}}
    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_sqlite_backend_atomic_update_refreshes_ttl(tmp_path) -> None:
    backend = SqliteBackend(tmp_path / "ttl-update.db", namespace="ttl")
    try:
        await backend.set("counter", {"count": 1}, ttl=0.12)
        await asyncio.sleep(0.03)
        updated = await backend.atomic_update(
            "counter",
            lambda current: {"count": (current or {"count": 0})["count"] + 1},
            ttl=0.12,
        )
        assert updated == {"count": 2}

        await asyncio.sleep(0.08)
        assert await backend.get("counter") == {"count": 2}

        await asyncio.sleep(0.06)
        assert await backend.get("counter") is None
    finally:
        await backend.close()
