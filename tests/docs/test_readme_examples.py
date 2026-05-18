"""Regression tests for the README's current example surface."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel

from skaal import App, Store
from skaal.backends.tokens import Redis
from skaal.inference import ResourceKind

_README = Path(__file__).resolve().parents[2] / "README.md"
_BANNED_README_TOKENS: tuple[str, ...] = (
    "Latency",
    "Durability",
    "AccessPattern",
    "@app.handler",
    "@app.scale",
    "@app.shared",
    "skaal.backends.redis import Redis",
    "await Users.put",
)


def test_readme_quickstart_pattern_builds_store_and_function_resources() -> None:
    app = App("counter")

    @app.storage
    class Counts(Store[int]):
        pass

    @app.expose()
    async def increment(name: str, by: int = 1) -> dict[str, Any]:
        current = await Counts.get(name) or 0
        new_value = current + by
        await Counts.set(name, new_value)
        return {"name": name, "value": new_value}

    @app.expose()
    async def get_count(name: str) -> dict[str, Any]:
        return {"name": name, "value": await Counts.get(name) or 0}

    plan = app.blueprint()
    kinds = [resource.kind for resource in plan.resources]

    assert kinds.count(ResourceKind.STORE) == 1
    assert kinds.count(ResourceKind.FUNCTION) == 2


def test_readme_backend_pin_pattern_sets_redis_override() -> None:
    app = App("session-cache")

    class SessionRecord(BaseModel):
        id: str
        user_id: str

    @app.storage
    class Sessions(Store[SessionRecord, Redis]):
        default_ttl: ClassVar[str] = "30m"

    assert Sessions.default_ttl == "30m"
    assert Sessions.__skaal_inferred__.overrides.backend == "redis"


def test_readme_drops_constraint_era_tokens() -> None:
    text = _README.read_text(encoding="utf-8")

    for token in _BANNED_README_TOKENS:
        assert token not in text, f"README.md reintroduced stale token {token!r}."
