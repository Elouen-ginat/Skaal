"""Tests for the `@app.external` decorator (ADR 032 §4.4)."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from skaal import App, Store
from skaal.backends._tokens import Postgres, Redis
from skaal.errors import SkaalConfigError


class Row(BaseModel):
    id: str
    name: str


def test_external_requires_type_pin() -> None:
    app = App("test-external-no-pin")

    with pytest.raises(SkaalConfigError, match="type-pin"):

        @app.external(name="legacy")
        class LegacyDb(Store[Row]):
            pass


def test_external_with_pin_marks_overrides_external() -> None:
    app = App("test-external-pin")

    @app.external(name="legacy_db")
    class LegacyDb(Store[Row, Postgres]):
        pass

    inferred = LegacyDb.__skaal_inferred__
    assert inferred.overrides.backend == "postgres"
    assert inferred.overrides.external is True
    assert inferred.overrides.external_name == "legacy_db"


def test_external_kv_with_redis_pin() -> None:
    app = App("test-external-redis")

    @app.external(name="session_cache", kind="kv")
    class SessionCache(Store[Row, Redis]):
        pass

    inferred = SessionCache.__skaal_inferred__
    assert inferred.overrides.backend == "redis"
    assert inferred.overrides.external is True
    assert inferred.overrides.external_name == "session_cache"
