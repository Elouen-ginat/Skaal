from __future__ import annotations

import asyncio

import pytest

from skaal import App, Store
from skaal.backends.local_backend import LocalMap
from skaal.types import TTL


@pytest.mark.asyncio
async def test_local_ttl_expires_get_list_and_scan() -> None:
    app = App("ttl-local")

    @app.storage(retention="40ms")
    class Sessions(Store[dict]):
        pass

    Sessions.wire(LocalMap())

    await Sessions.set("a", {"value": 1})
    assert await Sessions.get("a") == {"value": 1}

    await asyncio.sleep(0.06)

    assert await Sessions.get("a") is None
    assert await Sessions.list() == []
    assert await Sessions.scan("a") == []


@pytest.mark.asyncio
async def test_local_ttl_override_and_never_override() -> None:
    app = App("ttl-local-override")

    @app.storage(retention="100ms")
    class Sessions(Store[dict]):
        pass

    Sessions.wire(LocalMap())

    await Sessions.set("short", {"value": 1}, ttl="20ms")
    await Sessions.set("forever", {"value": 2}, ttl=TTL.never())

    await asyncio.sleep(0.04)

    assert await Sessions.get("short") is None
    assert await Sessions.get("forever") == {"value": 2}


@pytest.mark.asyncio
async def test_local_ttl_update_refreshes_expiry() -> None:
    app = App("ttl-local-update")

    @app.storage(retention="120ms")
    class Sessions(Store[dict]):
        pass

    Sessions.wire(LocalMap())

    await Sessions.set("a", {"count": 1})
    await asyncio.sleep(0.04)
    await Sessions.update("a", lambda current: {"count": (current or {"count": 0})["count"] + 1})
    await asyncio.sleep(0.04)

    assert await Sessions.get("a") == {"count": 2}

    await asyncio.sleep(0.09)
    assert await Sessions.get("a") is None


@pytest.mark.asyncio
async def test_local_ttl_rejects_non_positive_values_at_store_seam() -> None:
    app = App("ttl-local-invalid")

    @app.storage()
    class Sessions(Store[dict]):
        pass

    Sessions.wire(LocalMap())

    with pytest.raises(ValueError):
        await Sessions.set("a", {"value": 1}, ttl=0)

    with pytest.raises(ValueError):
        await Sessions.set("b", {"value": 2}, ttl="0s")
