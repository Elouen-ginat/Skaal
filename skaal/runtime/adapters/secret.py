"""Adapter that hydrates secrets via the local `DotenvSecret` backend.

The local defaults table emits `dotenv` for the `SECRET` kind. The
adapter exports secret values from a `.env` file (per `python-dotenv`
semantics) into the process environment at startup. Apps consuming
secrets through `os.environ[name]` see them in place by the time the
first request lands.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from skaal.binding.model import BoundResource
    from skaal.runtime.local import LocalRuntime


def register(runtime: LocalRuntime, bound: BoundResource, target: Any) -> None:
    """Stage a startup hook that loads the configured `.env` file."""
    if bound.backend != "dotenv":
        # Other secret backends (AWS Secrets Manager, GCP Secret Manager)
        # are deploy-target concerns; the local runtime no-ops on them.
        return

    path = Path(bound.options.get("path", ".env"))

    async def _startup() -> None:
        _load_dotenv(path)

    runtime.add_startup_hook(_startup)


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
