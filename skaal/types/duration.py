from __future__ import annotations

import difflib
import math
import re
from dataclasses import dataclass
from typing import Literal

_DURATION_RE = re.compile(r"^(?P<amount>[\d.]+)\s*(?P<unit>ms|s|m|h|d|w)$")
_UNIT_SECONDS = {
    "ms": 0.001,
    "s": 1.0,
    "m": 60.0,
    "h": 3600.0,
    "d": 86400.0,
    "w": 604800.0,
}


def _format_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return format(value, "g")


def _duration_hint(value: object) -> str:
    suggestions = difflib.get_close_matches(str(value), list(_UNIT_SECONDS), n=1)
    if suggestions:
        return f" Did you mean a value ending in {suggestions[0]!r}?"
    return " Expected one of: ms, s, m, h, d, w."


@dataclass(frozen=True)
class Duration:
    """Parsed duration value."""

    seconds: float
    expr: str

    def __init__(self, value: str | int | float | Duration, unit: str | None = None) -> None:
        parsed = self.parse(value if unit is None else f"{value}{unit}")
        object.__setattr__(self, "seconds", parsed.seconds)
        object.__setattr__(self, "expr", parsed.expr)

    @classmethod
    def parse(cls, value: str | int | float | Duration) -> Duration:
        if isinstance(value, cls):
            return value
        if isinstance(value, (int, float)):
            raise ValueError("Duration values must include a unit suffix such as '30m' or '5s'.")
        if not isinstance(value, str):
            raise TypeError("Duration.parse expects a duration string or Duration instance.")
        match = _DURATION_RE.match(value.strip())
        if match is None:
            raise ValueError(f"Invalid duration {value!r}.{_duration_hint(value)}")

        amount = float(match.group("amount"))
        if amount <= 0:
            raise ValueError(f"Duration must be > 0, got {value!r}.")

        unit = match.group("unit")
        expr = f"{_format_number(amount)}{unit}"
        return cls.__new_from_parts__(seconds=amount * _UNIT_SECONDS[unit], expr=expr)

    @classmethod
    def __new_from_parts__(cls, *, seconds: float, expr: str) -> Duration:
        self = object.__new__(cls)
        object.__setattr__(self, "seconds", seconds)
        object.__setattr__(self, "expr", expr)
        return self

    def __str__(self) -> str:
        return self.expr


@dataclass(frozen=True)
class TTL:
    """Runtime per-call TTL."""

    seconds: float | None
    expr: str | None = None

    @classmethod
    def never(cls) -> TTL:
        return cls(seconds=None, expr="never")

    @property
    def is_never(self) -> bool:
        return self.expr == "never"

    @classmethod
    def coerce(cls, value: TTL | Duration | str | int | float | None) -> TTL | None:
        if value is None:
            return None
        if isinstance(value, cls):
            if value.is_never:
                return value
            if value.seconds is None or value.seconds <= 0:
                raise ValueError("ttl must be > 0 seconds.")
            return value
        if isinstance(value, Duration):
            return cls(seconds=value.seconds, expr=value.expr)
        if isinstance(value, str):
            duration = Duration.parse(value)
            return cls(seconds=duration.seconds, expr=duration.expr)
        if not isinstance(value, (int, float)):
            raise TypeError("ttl must be a duration string, number of seconds, or TTL value.")
        seconds = float(value)
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError("ttl must be a finite number of seconds > 0.")
        return cls(seconds=seconds, expr=_format_number(seconds))


@dataclass(frozen=True)
class Retention:
    """Class-level retention policy declared via @app.storage(retention=...)."""

    duration: Duration | None
    policy: Literal["expire", "never"]

    @classmethod
    def parse(cls, value: Retention | Duration | str | None) -> Retention | None:
        if value is None or isinstance(value, cls):
            return value
        if isinstance(value, Duration):
            return cls(duration=value, policy="expire")
        if not isinstance(value, str):
            raise TypeError("Retention.parse expects a duration string, 'never', or Retention.")
        raw = value.strip().lower()
        if raw == "never":
            return cls(duration=None, policy="never")
        duration = Duration.parse(value)
        return cls(duration=duration, policy="expire")

    @property
    def default_ttl_seconds(self) -> float | None:
        if self.policy != "expire" or self.duration is None:
            return None
        return self.duration.seconds

    def __str__(self) -> str:
        if self.policy == "never":
            return "never"
        assert self.duration is not None
        return self.duration.expr
