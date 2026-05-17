"""Adapter that hydrates secrets via the local `DotenvSecret` backend.

The local defaults table emits `dotenv` for the `SECRET` kind. The
adapter exports secret values from a `.env` file (per `python-dotenv`
semantics) into the process environment at startup. Apps consuming
secrets through `os.environ[name]` see them in place by the time the
first request lands.

The parsing is delegated to ``python-dotenv``'s `load_dotenv` so the
local runtime matches every behaviour Docker Compose / Lambda Powertools
users already rely on (quoted values, variable expansion, multiline
values).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from dotenv import load_dotenv

if TYPE_CHECKING:
    from skaal.binding.model import PlannedResource
    from skaal.runtime.local import LocalRuntime


def register(runtime: LocalRuntime, bound: PlannedResource, target: Any) -> None:
    """Stage a startup hook that loads the configured `.env` file."""
    if bound.backend != "dotenv":
        # Other secret backends (AWS Secrets Manager, GCP Secret Manager)
        # are deploy-target concerns; the local runtime no-ops on them.
        return

    path: Path = Path(bound.options.get("path", ".env"))

    async def _startup() -> None:
        # `override=False` matches the documented "first writer wins"
        # ordering — env-vars already set in the parent process keep
        # their value, which is the usual story for CI overrides.
        load_dotenv(dotenv_path=path, override=False)

    runtime.add_startup_hook(_startup)
