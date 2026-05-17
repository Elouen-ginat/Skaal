"""Adapter for `SCHEDULE` resources."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from skaal.binding.model import PlannedResource
    from skaal.runtime.local.runtime import LocalRuntime


def register(runtime: LocalRuntime, bound: PlannedResource, target: Any) -> None:
    if target is None:
        return
    if bound.backend != "apscheduler":
        from skaal.errors import RuntimeAdapterMissing

        raise RuntimeAdapterMissing(f"schedule/{bound.backend}")

    runtime.state.schedules.append((bound, target))

    if runtime.state.scheduler_started:
        return
    runtime.state.scheduler_started = True

    async def _startup() -> None:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger

        from skaal.schedule import Cron, Every

        sched: AsyncIOScheduler = AsyncIOScheduler()
        for resource, fn in runtime.state.schedules:
            overrides = resource.inferred.overrides
            trigger = overrides.trigger
            timezone: str = overrides.schedule_timezone or "UTC"
            aps_trigger: Any
            if isinstance(trigger, Every):
                aps_trigger = IntervalTrigger(seconds=int(trigger.seconds), timezone=timezone)
            elif isinstance(trigger, Cron):
                aps_trigger = cast(Any, CronTrigger).from_crontab(
                    trigger.expression, timezone=timezone
                )
            else:
                continue
            cast(Any, sched).add_job(fn, trigger=aps_trigger, id=resource.inferred.id)
        sched.start()
        runtime.state.scheduler = sched

    async def _shutdown() -> None:
        sched: Any = runtime.state.scheduler
        if sched is not None:
            sched.shutdown(wait=False)

    runtime.add_startup_hook(_startup)
    runtime.add_shutdown_hook(_shutdown)
