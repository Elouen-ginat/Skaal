"""Non-regression: serve the kitchen-sink app via `skaal run`, exercise it, stop.

Exercises every public decorator on `App` / `Module` through the local
execution path (uvicorn). `skaal build` / `skaal deploy` only support
`aws` and `gcp`, so the local target uses `skaal run` instead — see the
sibling AWS and GCP tests for the Pulumi-backed deploy + destroy + leak
check matrix.
"""

from __future__ import annotations

from pathlib import Path

import httpx

from tests.nonregression.conftest import (
    requires_local,
    running_app,
)

SKAAL_TOML = """
[env.local]
target = "local"
""".lstrip()


def test_kitchen_sink_local_run(tmp_path: Path) -> None:
    """Serve the kitchen-sink app via `skaal run`, exercise every decorator."""
    requires_local()

    with running_app(
        tmp_path,
        example="nonregression_kitchen_sink",
        skaal_toml=SKAAL_TOML,
        env_name="local",
        app_spec="app.app:app",
    ) as app:
        with httpx.Client(base_url=app.base_url, timeout=15.0) as client:
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
