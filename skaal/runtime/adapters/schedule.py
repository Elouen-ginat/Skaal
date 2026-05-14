"""Adapter for `SCHEDULE` resources.

Phase 4 ships a minimal hook that imports the existing
`apscheduler`-backed runner from `skaal.schedule` and registers the
callable. The richer scheduler lifecycle (graceful shutdown, jitter,
clustering) is part of the broader runtime work and will be filled in
alongside the deploy-side EventBridge / Cloud Scheduler synth.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from skaal.binding.model import BoundResource
    from skaal.runtime.local import LocalRuntime


def register(runtime: LocalRuntime, bound: BoundResource, target: Any) -> None:
    """Register the callable with an in-process scheduler started on serve()."""
    if target is None:
        return
    if bound.backend != "apscheduler":
        from skaal.errors import RuntimeAdapterMissing

        raise RuntimeAdapterMissing(f"schedule/{bound.backend}")

    runtime.state.setdefault("schedules", []).append((bound, target))

    if "scheduler_started" in runtime.state:
        return
    runtime.state["scheduler_started"] = True

    async def _startup() -> None:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger

        from skaal.schedule import Cron, Every

        sched = AsyncIOScheduler()
        for resource, fn in runtime.state.get("schedules", []):
            metadata = getattr(fn, "__skaal_schedule__", None) or {}
            trigger = metadata.get("trigger")
            timezone = metadata.get("timezone", "UTC")
            if isinstance(trigger, Every):
                aps_trigger = IntervalTrigger(seconds=trigger.seconds, timezone=timezone)
            elif isinstance(trigger, Cron):
                aps_trigger = CronTrigger.from_crontab(trigger.expression, timezone=timezone)
            else:
                continue
            sched.add_job(fn, trigger=aps_trigger, id=resource.inferred.id)
        sched.start()
        runtime.state["scheduler"] = sched

    async def _shutdown() -> None:
        sched = runtime.state.get("scheduler")
        if sched is not None:
            sched.shutdown(wait=False)

    runtime.add_startup_hook(_startup)
    runtime.add_shutdown_hook(_shutdown)
