"""Schedule triggers and helpers for `@app.schedule()`.

Trigger types are Pydantic models that validate on construction and serialize
cleanly into plan metadata.

Examples:
    @app.schedule(trigger=Every(interval="5m"))
    async def cleanup() -> None:
        ...

    @app.schedule(trigger=Cron(expression="0 8 * * *"))
    async def daily_report() -> None:
        ...

Notes:
    `Every` maps to AWS `rate(...)` expressions and local interval triggers.
    `Cron` maps to AWS `cron(...)` expressions and cron-compatible schedulers.
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, TypeAlias, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator

from skaal.types import AsyncPublishTarget

# ── Interval parsing ──────────────────────────────────────────────────────────

_INTERVAL_RE = re.compile(
    r"^(\d+(?:\.\d+)?)\s*(s|sec|seconds?|m|min|minutes?|h|hr|hours?)$",
    re.IGNORECASE,
)

_UNIT_SECONDS: dict[str, float] = {
    "s": 1,
    "sec": 1,
    "second": 1,
    "seconds": 1,
    "m": 60,
    "min": 60,
    "minute": 60,
    "minutes": 60,
    "h": 3600,
    "hr": 3600,
    "hour": 3600,
    "hours": 3600,
}


def _parse_seconds(interval: str) -> float:
    """Parse a human-readable interval into seconds.

    Args:
        interval: Interval string such as `30s`, `5m`, or `2h`.

    Returns:
        Interval duration in seconds.

    Raises:
        ValueError: If `interval` does not use a recognized unit.
    """
    match = _INTERVAL_RE.match(interval.strip())
    if not match:
        raise ValueError(
            f"Invalid interval {interval!r}. "
            "Use a number followed by s/m/h (e.g. '30s', '5m', '2h')."
        )
    value = float(match.group(1))
    unit = match.group(2).lower().rstrip(".")
    return value * _UNIT_SECONDS[unit]


# ── Public types ──────────────────────────────────────────────────────────────


class Every(BaseModel):
    """Repeat on a fixed interval.

    Accepts `30s`, `5m`, and `2h` style strings.

    Examples:
        @app.schedule(trigger=Every(interval="5m"))
        async def cleanup() -> None:
            ...

    See Also:
        `Cron`: Use cron syntax for calendar-based schedules.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["every"] = "every"
    interval: str

    @field_validator("interval")
    @classmethod
    def _validate_interval(cls, v: str) -> str:
        _parse_seconds(v)  # raises ValueError on bad format
        return v

    @property
    def seconds(self) -> float:
        """Return the interval duration in seconds.

        Returns:
            Interval duration converted to seconds.
        """
        return _parse_seconds(self.interval)

    def as_rate_expression(self) -> str:
        """Return the AWS EventBridge `rate(N unit)` representation.

        Returns:
            EventBridge rate expression for this interval.

        See Also:
            `as_cron_expression`: Convert the same interval into a cron form when possible.
        """
        secs = self.seconds
        if secs >= 3600 and secs % 3600 == 0:
            n = int(secs // 3600)
            unit = "hour" if n == 1 else "hours"
        elif secs >= 60 and secs % 60 == 0:
            n = int(secs // 60)
            unit = "minute" if n == 1 else "minutes"
        else:
            n = int(secs)
            unit = "second" if n == 1 else "seconds"
        return f"rate({n} {unit})"

    def as_cron_expression(self) -> str:
        """Return a 5-field cron expression when the interval is cron-compatible.

        Returns:
            Cron expression for schedulers that expect 5-field cron syntax.

        Raises:
            ValueError: If the interval is sub-minute or cannot be expressed as a whole number
                of minutes.

        Notes:
            Sub-minute intervals remain local-runtime only because standard cron syntax cannot
            represent them.
        """
        secs = self.seconds
        if secs < 60:
            raise ValueError(
                f"Interval {self.interval!r} ({secs}s) is sub-minute and cannot be "
                "expressed as a cron expression. Use APScheduler's IntervalTrigger for "
                "sub-minute schedules (local only)."
            )
        mins = secs / 60
        if mins >= 60 and mins % 60 == 0:
            hrs = int(mins // 60)
            return f"0 */{hrs} * * *"
        if mins % 1 != 0:
            raise ValueError(
                f"Interval {self.interval!r} ({secs}s) does not divide evenly into "
                "minutes and cannot be expressed as a cron expression."
            )
        return f"*/{int(mins)} * * * *"


class Cron(BaseModel):
    """Standard 5-field cron expression.

    Examples:
        @app.schedule(trigger=Cron(expression="0 8 * * *"))
        async def daily_report() -> None:
            ...

    See Also:
        `Every`: Use interval syntax for fixed-rate schedules.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["cron"] = "cron"
    expression: str

    @field_validator("expression")
    @classmethod
    def _validate_expression(cls, v: str) -> str:
        fields = v.split()
        if len(fields) != 5:
            raise ValueError(
                f"Cron expression must have exactly 5 fields, got {len(fields)}: {v!r}. "
                "Format: 'minute hour day-of-month month day-of-week'"
            )
        return v

    def as_aws_expression(self) -> str:
        """Return the AWS EventBridge 6-field cron representation.

        Returns:
            EventBridge cron expression with the year wildcard appended.
        """
        min_, hr, dom, mon, dow = self.expression.split()
        return f"cron({min_} {hr} {dom} {mon} {dow} *)"


class ScheduleContext(BaseModel):
    """Context injected into scheduled callables that accept `ctx`.

    Examples:
        @app.schedule(trigger=Every(interval="1h"))
        async def hourly_job(ctx: ScheduleContext) -> None:
            print(ctx.fired_at)
    """

    fired_at: datetime
    model_config = ConfigDict(frozen=True)


# Discriminated union used by `ResourceOverrides.trigger` so pydantic
# can re-validate either shape from the canonical JSON form.
Schedule: TypeAlias = Annotated[Every | Cron, Field(discriminator="kind")]


def build_apscheduler_trigger(trigger: Schedule, *, timezone: str) -> Any:
    """Build an APScheduler trigger from Skaal schedule metadata.

    Args:
        trigger: Skaal schedule definition.
        timezone: IANA timezone name for the trigger.

    Returns:
        APScheduler trigger instance matching `trigger`.
    """
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    if isinstance(trigger, Every):
        return IntervalTrigger(seconds=trigger.seconds, timezone=timezone)
    return CronTrigger.from_crontab(trigger.expression, timezone=timezone)


def build_scheduled_job(
    fn: Callable[..., Any],
    *,
    name: str,
    emit_to: AsyncPublishTarget[object] | None = None,
    logger: Any | None = None,
    log_lifecycle: bool = False,
) -> Callable[[], Awaitable[None]]:
    """Wrap a scheduled callable with Skaal runtime behavior.

    Args:
        fn: User-defined scheduled callable.
        name: Logical job name used in logs.
        emit_to: Optional channel or append-only target for non-`None` results.
        logger: Logger used for lifecycle messages.
        log_lifecycle: Whether to emit start and completion log messages.

    Returns:
        Awaitable zero-argument callable ready for scheduler registration.

    Notes:
        If `fn` declares `ctx`, Skaal injects a `ScheduleContext` instance automatically.
    """

    async def _job() -> None:
        ctx = ScheduleContext(fired_at=datetime.now(UTC))
        if logger is not None and log_lifecycle:
            logger.info("[skaal/schedule] %s fired at %s", name, ctx.fired_at.isoformat())
        try:
            if "ctx" in inspect.signature(fn).parameters:
                result = await fn(ctx=ctx) if inspect.iscoroutinefunction(fn) else fn(ctx=ctx)
            else:
                result = await fn() if inspect.iscoroutinefunction(fn) else fn()
            if emit_to is not None and result is not None:
                await _publish_schedule_result(emit_to, result)
            if logger is not None and log_lifecycle:
                logger.info("[skaal/schedule] %s completed", name)
        except Exception as exc:
            if logger is not None:
                prefix = "[skaal/schedule]" if log_lifecycle else "[schedule/%s]"
                if log_lifecycle:
                    logger.warning("%s %s ERROR: %s", prefix, name, exc)
                else:
                    logger.warning(prefix, name, exc)

    return _job


async def _publish_schedule_result(target: AsyncPublishTarget[object], payload: object) -> None:
    send = cast(Callable[[object], Awaitable[None]] | None, getattr(target, "send", None))
    if callable(send):
        await send(payload)
        return

    append = cast(Callable[[object], Awaitable[object]] | None, getattr(target, "append", None))
    if callable(append):
        await append(payload)
        return

    raise TypeError("Scheduled emit target must provide send() or append()")


__all__ = [
    "Cron",
    "Every",
    "Schedule",
    "ScheduleContext",
    "build_apscheduler_trigger",
    "build_scheduled_job",
]
