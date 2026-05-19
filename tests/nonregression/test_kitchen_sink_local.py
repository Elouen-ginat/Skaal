"""Non-regression: deploy the kitchen-sink app to the `local` target.

Exercises every public decorator on `App` / `Module` end-to-end through the
infer → bind → build → deploy → destroy pipeline. The local target is
cheap to run and catches codegen regressions before the AWS / GCP jobs
spend cloud minutes on the same change.
"""

from __future__ import annotations

import socket
import time
from pathlib import Path

import httpx
import pytest

from tests.nonregression.conftest import (
    deployed_stack,
    requires_local,
)

SKAAL_TOML = """
[env.prod]
target = "local"
""".lstrip()


def _wait_for_port(host: str, port: int, *, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return
        except OSError:
            time.sleep(0.5)
    raise AssertionError(f"Port {port} on {host!r} never opened within {timeout:.1f}s")


def test_kitchen_sink_local_deploy(tmp_path: Path) -> None:
    """Deploy the kitchen-sink app locally, exercise every decorator, destroy."""
    requires_local()
    pytest.importorskip("pulumi", reason="`pulumi` SDK required for stack lifecycle.")

    with deployed_stack(
        tmp_path,
        example="nonregression_kitchen_sink",
        skaal_toml=SKAAL_TOML,
        env_name="prod",
        app_spec="app.app:app",
        target="local",
        deploy_budget_seconds=180,
    ) as stack:
        host, port = "127.0.0.1", 8000
        _wait_for_port(host, port, timeout=30.0)

        with httpx.Client(base_url=f"http://{host}:{port}", timeout=15.0) as client:
            healthz = client.get("/healthz")
            assert healthz.status_code == 200, healthz.text
            assert healthz.json() == {"status": "ok", "app": "kitchen_sink"}

            created = client.post(
                "/users",
                json={"id": "nonregression-local", "name": "kitchen sink"},
            )
            assert created.status_code == 201, created.text
            assert created.json()["id"] == "nonregression-local"

            fetched = client.get("/users/nonregression-local")
            assert fetched.status_code == 200, fetched.text
            assert fetched.json()["name"] == "kitchen sink"

            listed = client.get("/users")
            assert listed.status_code == 200, listed.text
            assert "nonregression-local" in {u["id"] for u in listed.json()["users"]}

        assert stack.project_dir.exists()
