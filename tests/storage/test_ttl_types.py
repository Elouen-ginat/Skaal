from __future__ import annotations

import pytest

from skaal import App, Store
from skaal.types import TTL, Duration, Retention


def test_duration_parse_accepts_supported_units() -> None:
    parsed = Duration.parse("30m")
    assert parsed.seconds == 1800
    assert parsed.expr == "30m"


@pytest.mark.parametrize("value", ["0s", "-1s", "12", 5, 0.0, "10x"])
def test_duration_parse_rejects_invalid_values(value: object) -> None:
    with pytest.raises(ValueError):
        Duration.parse(value)  # type: ignore[arg-type]


def test_ttl_coerce_supports_duration_strings_and_numbers() -> None:
    assert TTL.coerce("2s") == TTL(seconds=2.0, expr="2s")
    assert TTL.coerce(2) == TTL(seconds=2.0, expr="2")


def test_retention_parse_supports_never_and_duration() -> None:
    assert Retention.parse("never") == Retention(duration=None, policy="never")
    retention = Retention.parse("15m")
    assert retention is not None
    assert retention.policy == "expire"
    assert retention.default_ttl_seconds == 900


def test_storage_decorator_coerces_retention() -> None:
    app = App("ttl-metadata")

    @app.storage(retention="30m")
    class Sessions(Store[dict]):
        pass

    retention = Sessions.__skaal_storage__["retention"]
    assert isinstance(retention, Retention)
    assert retention.default_ttl_seconds == 1800


def test_storage_decorator_rejects_invalid_retention() -> None:
    app = App("ttl-metadata-invalid")

    with pytest.raises(ValueError):

        @app.storage(retention="soonish")
        class Sessions(Store[dict]):
            pass
