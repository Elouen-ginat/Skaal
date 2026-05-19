"""Non-regression: deploy `hello_world` against the `local` target.

`local` exercises the same `infer → bind → build → deploy → destroy` pipeline
as the cloud targets, but provisions everything inside the workspace (SQLite
backed `Store`, uvicorn server). It gives us a fast pre-flight for the rest
of the matrix and catches regressions in the codegen / runtime layers before
we spend cloud minutes on AWS or GCP.
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


def test_hello_world_local_deploy(tmp_path: Path) -> None:
    """Deploy `examples/hello_world` to the local target, hit it, destroy."""
    requires_local()
    pytest.importorskip("pulumi", reason="`pulumi` SDK required for stack lifecycle.")

    with deployed_stack(
        tmp_path,
        example="hello_world",
        skaal_toml=SKAAL_TOML,
        env_name="prod",
        app_spec="app.app:app",
        target="local",
        deploy_budget_seconds=120,
    ) as stack:
        # The local target writes its bind output and serves on a known port;
        # the deploy command prints the bound URL on success.
        host, port = "127.0.0.1", 8000
        _wait_for_port(host, port, timeout=30.0)

        with httpx.Client(base_url=f"http://{host}:{port}", timeout=15.0) as client:
            bumped = client.post("/increment", json={"name": "nonregression", "by": 3})
            assert bumped.status_code == 200, bumped.text
            assert bumped.json() == {"name": "nonregression", "value": 3}

            counts = client.post("/get_count", json={"name": "nonregression"})
            assert counts.status_code == 200, counts.text
            assert counts.json()["value"] == 3

        # Touch the project_dir so static checkers do not flag the unused handle.
        assert stack.project_dir.exists()
