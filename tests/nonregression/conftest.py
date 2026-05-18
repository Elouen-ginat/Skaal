"""Shared gating and teardown helpers for the non-regression deploy suite.

The suite is opt-in per target. The umbrella gate `SKAAL_RUN_NONREGRESSION=1`
is set by the CI workflow; per-target sub-gates let a maintainer opt-in to
just one target when iterating locally:

- `SKAAL_NONREGRESSION_LOCAL=1`
- `SKAAL_NONREGRESSION_AWS=1`   (requires AWS creds in the ambient env)
- `SKAAL_NONREGRESSION_GCP=1`   (requires `GOOGLE_APPLICATION_CREDENTIALS`)

Every test is responsible for tearing down the infrastructure it created.
The `deploy_and_teardown` fixture wraps the lifecycle so teardown still
runs when the body of the test raises — and surfaces a clear failure if
destroy itself fails (a dangling stack is worse than a failing test).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest

UMBRELLA_GATE = "SKAAL_RUN_NONREGRESSION"
LOCAL_GATE = "SKAAL_NONREGRESSION_LOCAL"
AWS_GATE = "SKAAL_NONREGRESSION_AWS"
GCP_GATE = "SKAAL_NONREGRESSION_GCP"

AWS_CRED_HINTS = ("AWS_ACCESS_KEY_ID", "AWS_ROLE_ARN", "AWS_WEB_IDENTITY_TOKEN_FILE")
GCP_CRED_HINT = "GOOGLE_APPLICATION_CREDENTIALS"

DEPLOY_BUDGET_SECONDS = 600


def _gate_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip() == "1"


def requires_local() -> None:
    if not (_gate_enabled(UMBRELLA_GATE) or _gate_enabled(LOCAL_GATE)):
        pytest.skip(f"local non-regression disabled — set {LOCAL_GATE}=1 to opt in.")


def requires_aws() -> None:
    if not (_gate_enabled(UMBRELLA_GATE) or _gate_enabled(AWS_GATE)):
        pytest.skip(f"AWS non-regression disabled — set {AWS_GATE}=1 to opt in.")
    if not any(os.environ.get(hint) for hint in AWS_CRED_HINTS):
        pytest.skip(
            "AWS credentials not detected. Configure OIDC via "
            "`aws-actions/configure-aws-credentials` or export `AWS_ACCESS_KEY_ID`."
        )


def requires_gcp() -> None:
    if not (_gate_enabled(UMBRELLA_GATE) or _gate_enabled(GCP_GATE)):
        pytest.skip(f"GCP non-regression disabled — set {GCP_GATE}=1 to opt in.")
    if not os.environ.get(GCP_CRED_HINT):
        pytest.skip(
            f"{GCP_CRED_HINT} unset — GCP non-regression needs a service-account "
            "key path or workload-identity-federated credentials file."
        )


@dataclass(frozen=True)
class DeployedStack:
    """Handle for a stack provisioned by a non-regression test."""

    project_dir: Path
    env_name: str
    target: str
    app_spec: str
    deploy_stdout: str
    deploy_stderr: str


def _run(
    cmd: list[str],
    cwd: Path,
    *,
    check: bool = True,
    extra_env: dict[str, str] | None = None,
    timeout: float = DEPLOY_BUDGET_SECONDS,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        cmd,
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
    )


def _copy_example(repo_root: Path, example: str, dest: Path, skaal_toml: str) -> None:
    src = repo_root / "examples" / example
    shutil.copytree(src, dest / "app", dirs_exist_ok=True)
    (dest / "skaal.toml").write_text(skaal_toml, encoding="utf-8")


def _destroy(project_dir: Path, env_name: str, app_spec: str) -> None:
    """Tear down the stack. Best-effort, but surface failures loudly.

    Tries `skaal destroy --yes` first (the supported verb). Falls back to the
    Pulumi automation API if the CLI is unavailable.
    """
    try:
        _run(
            ["skaal", "destroy", "--yes", "--env", env_name, app_spec],
            cwd=project_dir,
            check=True,
            timeout=DEPLOY_BUDGET_SECONDS,
        )
        return
    except (subprocess.CalledProcessError, FileNotFoundError) as cli_exc:
        try:
            from pulumi import automation as auto
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                f"Destroy fallback requires the `pulumi` automation API. CLI error was: {cli_exc}"
            ) from exc

        stack = auto.create_or_select_stack(
            stack_name=env_name,
            work_dir=str(project_dir / ".skaal" / "build" / env_name),
        )
        stack.destroy(on_output=lambda _msg: None)
        stack.workspace.remove_stack(env_name)


@contextmanager
def deployed_stack(
    tmp_path: Path,
    example: str,
    skaal_toml: str,
    *,
    env_name: str = "prod",
    app_spec: str = "app.app:app",
    target: str,
    deploy_budget_seconds: int = DEPLOY_BUDGET_SECONDS,
) -> Iterator[DeployedStack]:
    """Provision `example` into a tempdir, yield the handle, then destroy.

    The destroy step runs even when the body raises. If destroy itself fails,
    the original test failure is preserved and the destroy failure is chained.
    """
    repo_root = Path(__file__).resolve().parents[2]
    project_dir = tmp_path / f"{example}_{target}"
    project_dir.mkdir()
    _copy_example(repo_root, example, project_dir, skaal_toml)

    started = time.monotonic()
    deploy = _run(
        ["skaal", "deploy", "--env", env_name, app_spec],
        cwd=project_dir,
        check=True,
        timeout=deploy_budget_seconds,
    )
    elapsed = time.monotonic() - started

    handle = DeployedStack(
        project_dir=project_dir,
        env_name=env_name,
        target=target,
        app_spec=app_spec,
        deploy_stdout=deploy.stdout,
        deploy_stderr=deploy.stderr,
    )
    assert elapsed < deploy_budget_seconds, (
        f"`skaal deploy --env {env_name}` ({target}) took {elapsed:.1f}s "
        f"— over the {deploy_budget_seconds}s budget."
    )

    try:
        yield handle
    finally:
        try:
            _destroy(project_dir, env_name, app_spec)
        except Exception as destroy_exc:
            pytest.fail(
                f"Teardown failed for {target!r}/{env_name!r} — manual cleanup "
                f"likely required to avoid orphaned cloud resources: {destroy_exc}",
                pytrace=False,
            )


def find_endpoint_url(deploy_stdout: str, marker: str) -> str:
    """Scan deploy output for the first URL line containing `marker`."""
    for line in deploy_stdout.splitlines():
        if marker in line and "https://" in line:
            start = line.find("https://")
            end = line.find('"', start)
            if end == -1:
                end = None
            return line[start:end].strip().rstrip(",")
    raise AssertionError(
        f"Could not find a URL containing {marker!r} in `skaal deploy` output. "
        f"Captured stdout:\n{deploy_stdout}"
    )


__all__: list[str] = [
    "DeployedStack",
    "deployed_stack",
    "find_endpoint_url",
    "requires_aws",
    "requires_gcp",
    "requires_local",
]
