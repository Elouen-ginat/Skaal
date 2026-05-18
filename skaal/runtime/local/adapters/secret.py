"""Adapter that hydrates secrets via the local `DotenvSecret` backend."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from dotenv import load_dotenv

if TYPE_CHECKING:
    from skaal.binding.model import PlannedResource
    from skaal.runtime.local.runtime import LocalRuntime


def register(runtime: LocalRuntime, bound: PlannedResource, target: Any) -> None:
    del target
    if bound.backend != "dotenv":
        return

    path: Path = Path(bound.options.get("path", ".env"))

    async def _startup() -> None:
        load_dotenv(dotenv_path=path, override=False)

    runtime.add_startup_hook(_startup)
