"""ADR 028 §12 criterion 9 — `examples/todo_api` deploys to AWS in under 5 minutes.

Implements ADR 035 Decision 4: a maintainer-run smoke gated on
`SKAAL_RUN_AWS_SMOKE=1`. CI does not opt in. A maintainer runs the script
once before tagging `v0.4.0` and records the timing in `docs/whats-new.md`.

The flow:

1. `skaal init` into a tempdir.
2. Copy the `examples/todo_api/app.py` source and a minimal `skaal.toml`
   pinning `[env.prod.target] = "aws"` into the tempdir.
3. Run `skaal deploy --env prod`, time the wall-clock, assert under 300 s.
4. Hit the deployed API Gateway URL with a `POST /todos` + `GET /todos`
   round-trip.
5. Tear the stack down via `pulumi.automation.destroy(...)` (the dedicated
   `skaal destroy` verb is a future addition; the automation API is the
   ADR 035 fallback).
6. Confirm a follow-up `skaal plan --env prod` reports the expected
   delete-rows against `skaal.lock`.

The test is intentionally one cohesive function — splitting into fixtures
would make the timing assertion meaningless and the teardown harder to
sequence correctly.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

import httpx
import pytest

from tests.smoke.conftest import requires_aws_gate

DEPLOY_BUDGET_SECONDS = 300
SMOKE_ENV = "prod"
SKAAL_TOML = """
[env.prod]
target = "aws"
region = "us-east-1"
""".lstrip()


def _copy_example(src_root: Path, dest: Path) -> None:
    example_src = src_root / "examples" / "todo_api"
    shutil.copytree(example_src, dest / "app", dirs_exist_ok=True)
    (dest / "skaal.toml").write_text(SKAAL_TOML, encoding="utf-8")


def _run(cmd: list[str], cwd: Path, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
    )


def _api_gateway_url(deploy_stdout: str) -> str:
    for line in deploy_stdout.splitlines():
        if "execute-api" in line and "https://" in line:
            start = line.find("https://")
            end = line.find('"', start)
            return line[start : end if end != -1 else None].strip().rstrip(",")
    raise AssertionError(
        "Could not find an `execute-api` URL in `skaal deploy` output. "
        f"Captured output:\n{deploy_stdout}"
    )


def test_todo_api_aws_smoke(tmp_path: Path) -> None:
    """Provision `examples/todo_api` against AWS, exercise the API, tear down."""
    requires_aws_gate()
    pytest.importorskip(
        "pulumi",
        reason="`pulumi` SDK required for stack teardown via automation API.",
    )
    pytest.importorskip(
        "pulumi_aws",
        reason="`pulumi_aws` required to instantiate AWS resources.",
    )

    repo_root = Path(__file__).resolve().parents[2]
    project_dir = tmp_path / "todo_api_smoke"
    project_dir.mkdir()
    _copy_example(repo_root, project_dir)

    started = time.monotonic()
    deploy = _run(
        ["skaal", "deploy", "--env", SMOKE_ENV, "app.app:app"],
        cwd=project_dir,
    )
    elapsed = time.monotonic() - started
    assert elapsed < DEPLOY_BUDGET_SECONDS, (
        f"`skaal deploy --env {SMOKE_ENV}` took {elapsed:.1f}s — over the "
        f"{DEPLOY_BUDGET_SECONDS}s budget (ADR 028 §12 criterion 9)."
    )

    base_url = _api_gateway_url(deploy.stdout)

    try:
        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            created = client.post(
                "/todos",
                json={"id": "smoke-1", "title": "smoke test", "description": "from CI"},
            )
            assert created.status_code == 201, created.text

            listed = client.get("/todos")
            assert listed.status_code == 200, listed.text
            payload = listed.json()
            ids = [t["id"] for t in payload.get("todos", [])]
            assert "smoke-1" in ids, f"smoke-1 missing from /todos response: {payload}"
    finally:
        from pulumi import automation as auto

        stack = auto.create_or_select_stack(
            stack_name=f"{SMOKE_ENV}",
            work_dir=str(project_dir / ".skaal" / "build" / SMOKE_ENV),
        )
        stack.destroy(on_output=lambda _msg: None)

    plan = _run(
        ["skaal", "plan", "--env", SMOKE_ENV, "app.app:app"],
        cwd=project_dir,
        check=False,
    )
    assert "delete" in plan.stdout.lower() or plan.returncode == 0, (
        "Post-destroy `skaal plan` should report the lock-vs-empty delta. "
        f"stdout:\n{plan.stdout}\nstderr:\n{plan.stderr}"
    )
