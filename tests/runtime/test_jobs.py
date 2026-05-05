from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from skaal import App, Module, RetryPolicy, Store
from skaal.runtime.local import LocalRuntime


async def _wait_for(assertion, *, timeout: float = 1.0, interval: float = 0.01) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        try:
            await assertion()
            return
        except AssertionError:
            if asyncio.get_running_loop().time() >= deadline:
                raise
            await asyncio.sleep(interval)


def _make_jobs_app(name: str = "jobs-runtime") -> App:
    app = App(name)
    attempts: dict[str, int] = {}
    app._job_attempts = attempts

    @app.storage(read_latency="< 10ms", durability="ephemeral")
    class Counts(Store[int]):
        pass

    app._job_counts = Counts

    @app.job()
    async def increment(key: str, by: int = 1) -> None:
        current = await Counts.get(key) or 0
        await Counts.set(key, current + by)

    @app.job(retry=RetryPolicy(max_attempts=2, base_delay_ms=5, max_delay_ms=5))
    async def flaky_increment(key: str) -> None:
        attempts[key] = attempts.get(key, 0) + 1
        if attempts[key] == 1:
            raise RuntimeError("retry me")
        current = await Counts.get(key) or 0
        await Counts.set(key, current + 1)

    return app


@pytest.mark.asyncio
async def test_enqueue_executes_job() -> None:
    app = _make_jobs_app("jobs-exec")
    runtime = LocalRuntime(app)
    counts = app._job_counts

    handle = await app.enqueue("increment", "alpha", by=2)

    assert handle.job_name == "jobs-exec.increment"

    async def _eventually_incremented() -> None:
        assert await counts.get("alpha") == 2

    await _wait_for(_eventually_incremented)
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_enqueue_delay_defers_execution() -> None:
    app = _make_jobs_app("jobs-delay")
    runtime = LocalRuntime(app)
    counts = app._job_counts

    await app.enqueue("increment", "slow", delay="50ms")

    assert await counts.get("slow") is None

    async def _eventually_incremented() -> None:
        assert await counts.get("slow") == 1

    await _wait_for(_eventually_incremented)
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_enqueue_retries_failed_job() -> None:
    app = _make_jobs_app("jobs-retry")
    runtime = LocalRuntime(app)
    counts = app._job_counts

    await app.enqueue("flaky_increment", "beta")

    async def _eventually_retried() -> None:
        assert await counts.get("beta") == 1
        assert app._job_attempts["beta"] == 2

    await _wait_for(_eventually_retried)
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_enqueue_idempotency_key_deduplicates_requests() -> None:
    app = _make_jobs_app("jobs-idempotent")
    runtime = LocalRuntime(app)
    counts = app._job_counts

    first = await app.enqueue("increment", "gamma", idempotency_key="same")
    second = await app.enqueue("increment", "gamma", idempotency_key="same")

    assert second == first

    async def _eventually_incremented_once() -> None:
        assert await counts.get("gamma") == 1

    await _wait_for(_eventually_incremented_once)
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_delayed_job_survives_runtime_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "jobs.db"

    runtime = LocalRuntime.from_sqlite(_make_jobs_app("jobs-restart"), db_path)
    await runtime.enqueue_job("increment", "persisted", delay="100ms")
    await runtime.shutdown()

    restarted_app = _make_jobs_app("jobs-restart")
    restarted = LocalRuntime.from_sqlite(restarted_app, db_path)
    counts = restarted_app._job_counts

    async def _eventually_incremented() -> None:
        assert await counts.get("persisted") == 1

    await _wait_for(_eventually_incremented, timeout=2.0)
    await restarted.shutdown()


@pytest.mark.asyncio
async def test_mounted_module_job_resolves_by_qualified_name() -> None:
    app = App("jobs-root")
    child = Module("child")

    @app.storage(read_latency="< 10ms", durability="ephemeral")
    class Counts(Store[int]):
        pass

    @child.job()
    async def increment_shared(key: str) -> None:
        current = await Counts.get(key) or 0
        await Counts.set(key, current + 1)

    app.use(child)
    runtime = LocalRuntime(app)

    await app.enqueue("jobs-root.child.increment_shared", "delta")

    async def _eventually_incremented() -> None:
        assert await Counts.get("delta") == 1

    await _wait_for(_eventually_incremented)
    await runtime.shutdown()
