from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from redis import Redis
from rq import Retry, SimpleWorker
from rq.job import Job
from rq.registry import FailedJobRegistry, ScheduledJobRegistry
from rq.scheduler import RQScheduler
from rq.serializers import JSONSerializer
from rq.timeouts import TimerDeathPenalty

from skaal.types import Duration, JobHandle, RetryPolicy

_RUNTIME_REGISTRY: dict[str, Any] = {}
_FAKE_REDIS_SERVERS: dict[str, Any] = {}


@dataclass
class JobWorkerTelemetry:
    queued: int = 0
    running: int = 0
    succeeded: int = 0
    failed: int = 0
    last_tick_at: datetime | None = None


class WindowsSimpleWorker(SimpleWorker):
    death_penalty_class = TimerDeathPenalty

    def _install_signal_handlers(self) -> None:
        return None

    def setup_work_horse_signals(self) -> None:
        return None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_scheduled_for(
    *,
    delay: Duration | str | None,
    run_at: datetime | None,
) -> datetime:
    if delay is not None and run_at is not None:
        raise ValueError("delay and run_at are mutually exclusive")
    if run_at is not None:
        if run_at.tzinfo is None:
            return run_at.replace(tzinfo=timezone.utc)
        return run_at.astimezone(timezone.utc)
    if delay is None:
        return utc_now()
    resolved = delay if isinstance(delay, Duration) else Duration.parse(delay)
    return utc_now() + timedelta(seconds=resolved.seconds)


def ensure_json_payload(
    *, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> tuple[list[Any], dict[str, Any]]:
    normalized_args = list(args)
    normalized_kwargs = dict(kwargs)
    try:
        json.dumps({"args": normalized_args, "kwargs": normalized_kwargs})
    except TypeError as exc:
        raise TypeError(
            "Background job arguments must be JSON-serializable in the local runtime"
        ) from exc
    return normalized_args, normalized_kwargs


def job_queue_name(app_name: str) -> str:
    return f"skaal:{app_name}:jobs"


def default_job_connection(app_name: str) -> Any:
    redis_url = os.getenv("SKAAL_JOBS_REDIS_URL")
    if redis_url:
        return Redis.from_url(redis_url)

    try:
        from fakeredis import FakeServer, FakeStrictRedis
    except ImportError as exc:
        raise RuntimeError(
            "Background jobs require either fakeredis or SKAAL_JOBS_REDIS_URL to be set."
        ) from exc

    server = _FAKE_REDIS_SERVERS.get(app_name)
    if server is None:
        server = FakeServer()
        _FAKE_REDIS_SERVERS[app_name] = server
    return FakeStrictRedis(server=server)


def build_rq_retry(policy: RetryPolicy | None) -> Retry | None:
    if policy is None or policy.max_attempts <= 1:
        return None
    max_retries = policy.max_attempts - 1
    intervals = []
    base_seconds = policy.base_delay_ms / 1000.0
    max_seconds = policy.max_delay_ms / 1000.0
    for attempt in range(1, max_retries + 1):
        if policy.backoff == "fixed":
            delay_seconds = base_seconds
        elif policy.backoff == "linear":
            delay_seconds = base_seconds * attempt
        else:
            delay_seconds = base_seconds * (2 ** (attempt - 1))
        intervals.append(max(0, int(min(delay_seconds, max_seconds))))
    if len(intervals) == 1:
        interval: int | list[int] = intervals[0]
    else:
        interval = intervals
    return Retry(max=max_retries, interval=interval)


def unique_job_id(job_name: str, idempotency_key: str) -> str:
    digest = hashlib.sha256(f"{job_name}:{idempotency_key}".encode("utf-8")).hexdigest()
    return f"job-{digest}"


def register_runtime(token: str, runtime: Any) -> None:
    _RUNTIME_REGISTRY[token] = runtime


def unregister_runtime(token: str) -> None:
    _RUNTIME_REGISTRY.pop(token, None)


def execute_registered_job(
    runtime_token: str,
    job_name: str,
    args: list[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
) -> Any:
    runtime = _RUNTIME_REGISTRY.get(runtime_token)
    if runtime is None:
        raise RuntimeError(f"No active runtime registered for token {runtime_token!r}")
    future = asyncio.run_coroutine_threadsafe(
        runtime._invoke_registered_job(job_name, *(args or []), **(kwargs or {})),
        runtime._job_loop,
    )
    return future.result()


def scheduled_registry(queue: Any) -> ScheduledJobRegistry:
    return ScheduledJobRegistry(queue=queue, serializer=JSONSerializer)


def failed_registry(queue: Any) -> FailedJobRegistry:
    return FailedJobRegistry(queue=queue, serializer=JSONSerializer)


def build_scheduler(queue: Any, connection: Any) -> RQScheduler:
    return RQScheduler([queue], connection=connection, serializer=JSONSerializer)


def build_worker(queue: Any, connection: Any) -> WindowsSimpleWorker:
    return WindowsSimpleWorker([queue], connection=connection, serializer=JSONSerializer)


def promote_scheduled_jobs(queue: Any, connection: Any) -> int:
    registry = ScheduledJobRegistry(queue=queue, serializer=JSONSerializer)
    job_ids = registry.get_jobs_to_schedule(int(utc_now().timestamp()))
    if not job_ids:
        return 0

    with connection.pipeline() as pipeline:
        jobs = Job.fetch_many(job_ids, connection=connection, serializer=JSONSerializer)
        for job in jobs:
            if job is not None:
                queue._enqueue_job(job, pipeline=pipeline, at_front=job.should_enqueue_at_front())
        for job_id in job_ids:
            registry.remove(job_id, pipeline=pipeline)
        pipeline.execute()
    return len(job_ids)


def job_handle_from_rq_job(job: Job, *, fallback_scheduled_for: datetime) -> JobHandle:
    scheduled_for_raw = job.meta.get("scheduled_for") if hasattr(job, "meta") else None
    if isinstance(scheduled_for_raw, str):
        scheduled_for = datetime.fromisoformat(scheduled_for_raw)
    else:
        scheduled_for = fallback_scheduled_for
    job_name = job.description or job.func_name or job.id
    return JobHandle(job_id=job.id, job_name=job_name, scheduled_for=scheduled_for)


async def close_job_connection(connection: Any) -> None:
    close = getattr(connection, "aclose", None)
    if callable(close):
        close_result = close()
        if isinstance(close_result, Awaitable):
            await close_result
        return
    close = getattr(connection, "close", None)
    if callable(close):
        close_result = close()
        if isinstance(close_result, Awaitable):
            await close_result


__all__ = [
    "JobWorkerTelemetry",
    "WindowsSimpleWorker",
    "build_rq_retry",
    "build_scheduler",
    "build_worker",
    "close_job_connection",
    "default_job_connection",
    "ensure_json_payload",
    "execute_registered_job",
    "failed_registry",
    "job_handle_from_rq_job",
    "job_queue_name",
    "normalize_scheduled_for",
    "promote_scheduled_jobs",
    "register_runtime",
    "scheduled_registry",
    "unique_job_id",
    "unregister_runtime",
    "utc_now",
]
