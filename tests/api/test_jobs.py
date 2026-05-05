from __future__ import annotations

import pytest

from skaal import App, JobSpec


def test_job_decorator_registers_handler_and_metadata() -> None:
    app = App("jobs-api")

    @app.job()
    async def send_email(user_id: str) -> None:
        del user_id

    assert "send_email" in app._jobs
    assert app._jobs["send_email"] is send_email
    assert getattr(send_email, "__skaal_job__") == JobSpec(name="send_email", retry=None)


@pytest.mark.asyncio
async def test_enqueue_requires_bound_runtime() -> None:
    app = App("jobs-no-runtime")

    @app.job()
    async def warm_cache(key: str) -> None:
        del key

    with pytest.raises(RuntimeError, match="No active Skaal runtime"):
        await app.enqueue(warm_cache, "home")


def test_describe_includes_jobs() -> None:
    app = App("jobs-describe")

    @app.job()
    async def reconcile(account_id: str) -> None:
        del account_id

    desc = app.describe()
    assert "jobs" in desc
    assert desc["jobs"] == ["reconcile"]
