# Extending Skaal — Custom Backends

Every backend the Skaal solver can pick is just a Python class that
implements one of the protocols in `skaal.backends.base`. Adding a new
backend is three steps:

1. **Implement the protocol** for your storage tier.
2. **Register an entry point** so Skaal can discover it.
3. **Add a catalog entry** so the solver can pick it.

This page walks through a small but realistic example: a key-value backend
backed by a JSON file on disk. The same shape applies to relational, blob,
vector, and channel backends — only the protocol differs.

## 1. Implement the protocol

The KV protocol lives in [`skaal/backends/base.py`](https://github.com/Elouen-ginat/Skaal/blob/main/skaal/backends/base.py)
as `StorageBackend`. The full async surface (`get`, `set`, `delete`,
`list`, `list_page`, `scan`, `scan_page`, `query_index`, `ensure_indexes`,
`increment_counter`, `atomic_update`, `close`) is documented inline. For a
toy backend you can lean on the helpers already exported by
`skaal.storage` to handle paging and secondary-index emulation.

Save this as `myskaal/json_backend.py`:

```python title="myskaal/json_backend.py"
from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from skaal.storage import (
    _list_page_from_entries,
    _query_index_from_entries,
    _scan_page_from_entries,
)
from skaal.types.storage import Page


class JsonFileBackend:
    """A persistent key-value backend that stores entries in a single JSON file.

    Implements the `StorageBackend` Protocol from `skaal.backends.base` so
    the runtime and solver treat it like any built-in backend.
    """

    def __init__(self, path: str | Path, *, namespace: str = "default") -> None:
        self._path = Path(path)
        self._namespace = namespace
        self._lock = asyncio.Lock()
        self._data: dict[str, Any] = self._load()
        self._expires_at: dict[str, float] = {}

    # ── Persistence helpers ───────────────────────────────────────────────

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text(encoding="utf-8")).get(self._namespace, {})

    def _flush_locked(self) -> None:
        existing = {}
        if self._path.exists():
            existing = json.loads(self._path.read_text(encoding="utf-8"))
        existing[self._namespace] = self._data
        self._path.write_text(json.dumps(existing, default=str), encoding="utf-8")

    def _purge_expired_locked(self) -> None:
        now = time.time()
        expired = [k for k, deadline in self._expires_at.items() if deadline <= now]
        for key in expired:
            self._data.pop(key, None)
            self._expires_at.pop(key, None)

    # ── Protocol methods ──────────────────────────────────────────────────

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            self._purge_expired_locked()
            return self._data.get(key)

    async def set(self, key: str, value: Any, *, ttl: float | None = None) -> None:
        async with self._lock:
            self._purge_expired_locked()
            self._data[key] = value
            if ttl is None:
                self._expires_at.pop(key, None)
            else:
                self._expires_at[key] = time.time() + ttl
            self._flush_locked()

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._data.pop(key, None)
            self._expires_at.pop(key, None)
            self._flush_locked()

    async def list(self) -> list[tuple[str, Any]]:
        async with self._lock:
            self._purge_expired_locked()
            return list(self._data.items())

    async def list_page(self, *, limit: int, cursor: str | None) -> Page[tuple[str, Any]]:
        return _list_page_from_entries(await self.list(), limit=limit, cursor=cursor)

    async def scan(self, prefix: str = "") -> list[tuple[str, Any]]:
        return [(k, v) for k, v in await self.list() if k.startswith(prefix)]

    async def scan_page(
        self, prefix: str = "", *, limit: int, cursor: str | None
    ) -> Page[tuple[str, Any]]:
        return _scan_page_from_entries(
            await self.scan(prefix), prefix=prefix, limit=limit, cursor=cursor
        )

    async def query_index(
        self, index_name: str, key: Any, *, limit: int, cursor: str | None
    ) -> Page[Any]:
        return _query_index_from_entries(
            await self.list(),
            backend=self,
            index_name=index_name,
            key=key,
            limit=limit,
            cursor=cursor,
        )

    async def ensure_indexes(self) -> None:
        return None

    async def increment_counter(self, key: str, delta: int = 1) -> int:
        async with self._lock:
            current = int(self._data.get(key, 0))
            self._data[key] = current + delta
            self._flush_locked()
            return current + delta

    async def atomic_update(
        self, key: str, fn: Callable[[Any], Any], *, ttl: float | None = None
    ) -> Any:
        async with self._lock:
            self._purge_expired_locked()
            current = self._data.get(key)
            updated = fn(current)
            self._data[key] = updated
            if ttl is not None:
                self._expires_at[key] = time.time() + ttl
            self._flush_locked()
            return updated

    async def close(self) -> None:
        return None

    def __repr__(self) -> str:
        return f"JsonFileBackend(path={self._path!s}, namespace={self._namespace!r})"
```

The `_lock` makes concurrent `set` and `atomic_update` safe — the protocol
demands atomicity, and Skaal will route concurrent calls into the same
backend instance.

## 2. Register an entry point

Skaal discovers backends through Python entry points. In your
`pyproject.toml`:

```toml title="pyproject.toml"
[project.entry-points."skaal.backends"]
json-file = "myskaal.json_backend:JsonFileBackend"
```

After `pip install -e .`, the planner can resolve the `json-file` backend
by name. The same group covers KV, blob, and vector backends; the runtime
inspects the registered class to know which protocol it satisfies. Channel
backends register under `skaal.channels` instead.

## 3. Add a catalog entry

Catalogs tell the solver which backends are available for a target and
what constraints they satisfy. Add a section to `catalogs/local.toml`:

```toml title="catalogs/local.toml"
[storage.json-file.wire]
class_name      = "JsonFileBackend"
module          = "myskaal.json_backend"
env_prefix      = "MYSKAAL_JSON_PATH"
uses_namespace  = true
local_env_value = "/app/data/skaal.json"
extra_deps      = []

[storage.json-file]
display_name    = "JSON file (custom)"
read_latency    = { min = 0.5, max = 50.0, unit = "ms" }
write_latency   = { min = 1.0, max = 100.0, unit = "ms" }
durability      = ["persistent"]
max_size_gb     = 1
storage_kinds   = ["kv"]
access_patterns = ["random-read", "random-write"]
cost_per_gb_month = 0.0
supports_ttl    = true
notes           = "Single-file JSON store. Useful for small demo apps."
```

The solver now considers `json-file` whenever a `Store[T]` is declared with
`durability="persistent"` and matching latency bands. The `[wire]` table
tells the deploy generators how to instantiate the backend at runtime —
`env_prefix` becomes a per-storage-class environment variable
(`MYSKAAL_JSON_PATH_<NAME>`), and `extra_deps` flow into the generated
`pyproject.toml` for the deployed artifact.

## 4. Verify

Run the planner and ask it to pin the new backend:

```bash
skaal plan examples.01_quickstart.app:app \
    --target local \
    --catalog catalogs/local.toml \
    --pin Counts=json-file
```

If the constraints declared on `Counts` are satisfied by the catalog
entry, the lock file will reference `json-file` and `skaal run` will wire
your `JsonFileBackend` automatically. If they are not, the solver will
report which dimension fell short — that is the feedback loop you tune
the catalog with.

## Drop-in wiring for tests

When you do not want the runtime in the loop — for example, in a unit
test — call `wire(...)` directly:

```python
from myskaal.json_backend import JsonFileBackend

Counts.wire(JsonFileBackend("/tmp/skaal.json", namespace="Counts"))
await Counts.set("hits", 1)
```

`Store[T]` carries the protocol contract, so any backend that satisfies
the protocol — yours, a built-in, or a mock — slots in here.

## Next steps

- Implement `BlobBackend` for arbitrary bytes (see
  [`skaal/backends/file_blob_backend.py`](https://github.com/Elouen-ginat/Skaal/blob/main/skaal/backends/file_blob_backend.py)
  for a reference).
- Implement a channel backend by registering a `wire_<name>` function
  under the `skaal.channels` entry-point group; see
  [`skaal/backends/redis_channel.py`](https://github.com/Elouen-ginat/Skaal/blob/main/skaal/backends/redis_channel.py).
- Publish your backend as `skaal-<name>` on PyPI and the entry-point group
  makes it available to any Skaal user with no core change.
