"""Non-regression: serve `hello_world` via `skaal run`, exercise it, stop.

The `local` target does not provision infrastructure — `skaal deploy` only
supports `aws` and `gcp`. To still exercise the local execution path on
every merge to `main`, we spawn `skaal run` in the background, wait for
the port to open, hit the deployed routes, and terminate the process. No
infra teardown or leak sweep is needed because nothing exists outside the
runner's filesystem.
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


def test_hello_world_local_run(tmp_path: Path) -> None:
    """Serve `examples/hello_world` via `skaal run`, exercise the API, stop."""
    requires_local()

    with running_app(
        tmp_path,
        example="hello_world",
        skaal_toml=SKAAL_TOML,
        env_name="local",
        app_spec="app.app:app",
    ) as app:
        with httpx.Client(base_url=app.base_url, timeout=15.0) as client:
            bumped = client.post("/increment", json={"name": "nonregression", "by": 3})
            assert bumped.status_code == 200, bumped.text
            assert bumped.json() == {"name": "nonregression", "value": 3}

            counts = client.post("/get_count", json={"name": "nonregression"})
            assert counts.status_code == 200, counts.text
            assert counts.json()["value"] == 3
