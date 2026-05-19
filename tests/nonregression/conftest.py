"""Shared gating and teardown helpers for the non-regression deploy suite.

The suite is opt-in per target. The umbrella gate `SKAAL_RUN_NONREGRESSION=1`
is set by the CI workflow; per-target sub-gates let a maintainer opt-in to
just one target when iterating locally:

- `SKAAL_NONREGRESSION_LOCAL=1`
- `SKAAL_NONREGRESSION_AWS=1`   (requires AWS creds in the ambient env)
- `SKAAL_NONREGRESSION_GCP=1`   (requires `GOOGLE_APPLICATION_CREDENTIALS`)

Every test is responsible for tearing down the infrastructure it created.
The `deployed_stack` context manager wraps the lifecycle so teardown still
runs when the body of the test raises — and after teardown it runs a
leak-detection sweep so a partially-failed destroy fails the test instead
of leaving orphaned cloud resources to discover via the AWS / GCP bill.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import pytest

UMBRELLA_GATE = "SKAAL_RUN_NONREGRESSION"
LOCAL_GATE = "SKAAL_NONREGRESSION_LOCAL"
AWS_GATE = "SKAAL_NONREGRESSION_AWS"
GCP_GATE = "SKAAL_NONREGRESSION_GCP"
DEEP_LEAK_GATE = "SKAAL_NONREGRESSION_DEEP_LEAK_CHECK"

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
    app_name: str
    deploy_stdout: str
    deploy_stderr: str


@dataclass
class LeakReport:
    """Result of the post-destroy leak sweep."""

    pulumi_resources: list[str] = field(default_factory=list)
    cloud_resources: list[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not self.pulumi_resources and not self.cloud_resources

    def format(self) -> str:
        chunks: list[str] = []
        if self.pulumi_resources:
            chunks.append(
                "Pulumi state still tracks resources after destroy:\n  - "
                + "\n  - ".join(self.pulumi_resources)
            )
        if self.cloud_resources:
            chunks.append(
                "Cloud provider still reports tagged resources:\n  - "
                + "\n  - ".join(self.cloud_resources)
            )
        return "\n".join(chunks) or "no leaks detected"


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
    # `check=False` here so we can re-raise with the captured output attached;
    # the bare `CalledProcessError` `subprocess.run(check=True)` raises hides
    # stderr inside a private attribute and pytest only prints the exit code.
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
    )
    if check and proc.returncode != 0:
        exc = subprocess.CalledProcessError(
            proc.returncode,
            cmd,
            output=proc.stdout,
            stderr=proc.stderr,
        )
        # `CalledProcessError.__str__` only includes the exit code; attach
        # captured output as a PEP 678 note so pytest renders it in the
        # failure section without us needing a custom exception type.
        exc.add_note(f"cwd: {cwd}\n--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}")
        raise exc
    return proc


def _copy_example(repo_root: Path, example: str, dest: Path, skaal_toml: str) -> None:
    src = repo_root / "examples" / example
    shutil.copytree(src, dest / "app", dirs_exist_ok=True)
    (dest / "skaal.toml").write_text(skaal_toml, encoding="utf-8")


def _stack_workdir(project_dir: Path, env_name: str) -> Path:
    return project_dir / ".skaal" / "build" / env_name


def _resolve_app_name(project_dir: Path, app_spec: str) -> str:
    """Best-effort: derive the `App` name for tag-based leak detection."""
    # `app_spec` is `module:attr`. We expect the user's example module to
    # define `app = App("<name>")` at top-level; recover it via a short
    # subprocess so the parent test process does not import the example.
    module, _, attr = app_spec.partition(":")
    code = (
        "import sys, importlib;"
        f"sys.path.insert(0, {str(project_dir)!r});"
        f"m = importlib.import_module({module!r});"
        f"print(getattr(m, {attr!r}).name)"
    )
    proc = subprocess.run(
        ["python", "-c", code],
        cwd=project_dir,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def _destroy(project_dir: Path, env_name: str, app_spec: str) -> None:
    """Tear down the stack. Tries `skaal destroy --yes` first, then Pulumi."""
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
            work_dir=str(_stack_workdir(project_dir, env_name)),
        )
        stack.destroy(on_output=lambda _msg: None)
        stack.workspace.remove_stack(env_name)


def _pulumi_resources_after_destroy(project_dir: Path, env_name: str) -> list[str]:
    """Return URNs Pulumi still tracks after destroy.

    A clean destroy leaves the stack root (`pulumi:pulumi:Stack`) and nothing
    else. Anything beyond that is a leak — the destroy claimed success but
    state still references infrastructure that may exist in the cloud.
    """
    try:
        from pulumi import automation as auto
    except ImportError:  # pragma: no cover
        return []

    work_dir = _stack_workdir(project_dir, env_name)
    if not work_dir.exists():
        # The destroy fallback already removed the stack from state.
        return []
    try:
        stack = auto.select_stack(
            stack_name=env_name,
            work_dir=str(work_dir),
            program=lambda: None,
        )
    except auto.CommandError:
        return []

    deployment = stack.export_stack()
    resources = deployment.deployment.get("resources", []) if deployment.deployment else []
    leaks: list[str] = []
    for res in resources:
        urn = str(res.get("urn", ""))
        res_type = str(res.get("type", ""))
        if res_type == "pulumi:pulumi:Stack":
            continue
        if res.get("delete") or res.get("pendingReplacement"):
            # Resource is marked for deletion but the destroy failed midway.
            leaks.append(f"{res_type} {urn} (marked for delete)")
            continue
        leaks.append(f"{res_type} {urn}")
    return leaks


def _aws_tagged_resources(app_name: str, env_name: str, region: str) -> list[str]:
    """Query AWS Resource Groups Tagging API for resources Skaal owns.

    Only runs when `boto3` is importable and `SKAAL_NONREGRESSION_DEEP_LEAK_CHECK=1`.
    The filter uses `skaal:app` + `skaal:env`, which every `skaal.deploy.tags`
    helper writes onto every Pulumi resource.
    """
    if not _gate_enabled(DEEP_LEAK_GATE):
        return []
    try:
        import boto3  # type: ignore[import-untyped]
    except ImportError:
        return []

    client = boto3.client("resourcegroupstaggingapi", region_name=region)
    paginator = client.get_paginator("get_resources")
    arns: list[str] = []
    for page in paginator.paginate(
        TagFilters=[
            {"Key": "skaal:app", "Values": [app_name]},
            {"Key": "skaal:env", "Values": [env_name]},
        ],
        ResourcesPerPage=100,
    ):
        for mapping in page.get("ResourceTagMappingList", []):
            arn = mapping.get("ResourceARN")
            if arn:
                arns.append(arn)
    return arns


def _gcp_labeled_resources(app_name: str, env_name: str, project: str) -> list[str]:
    """Query the Cloud Asset Inventory for resources Skaal labeled.

    Only runs when `google-cloud-asset` is importable and the deep gate is
    set. Skaal tags map to GCP labels with `_` substituted for `:` because
    GCP labels disallow `:`.
    """
    if not _gate_enabled(DEEP_LEAK_GATE):
        return []
    try:
        from google.cloud import asset_v1  # type: ignore[import-untyped]
    except ImportError:
        return []

    client = asset_v1.AssetServiceClient()
    scope = f"projects/{project}"
    query = f'labels.skaal_app="{app_name}" AND labels.skaal_env="{env_name}"'
    names: list[str] = []
    for resource in client.search_all_resources(scope=scope, query=query):
        names.append(resource.name)
    return names


def _leak_check(
    *,
    target: str,
    app_name: str,
    env_name: str,
    region: str | None,
    project: str | None,
    project_dir: Path,
) -> LeakReport:
    report = LeakReport()
    report.pulumi_resources = _pulumi_resources_after_destroy(project_dir, env_name)

    if not app_name:
        return report
    if target == "aws" and region:
        report.cloud_resources = _aws_tagged_resources(app_name, env_name, region)
    elif target == "gcp" and project:
        report.cloud_resources = _gcp_labeled_resources(app_name, env_name, project)
    return report


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
    leak_check: bool = True,
    aws_region: str | None = None,
    gcp_project: str | None = None,
) -> Iterator[DeployedStack]:
    """Provision `example`, yield the handle, destroy, and leak-check.

    `aws_region` / `gcp_project` are only used by the deep-leak scan (gated
    by `SKAAL_NONREGRESSION_DEEP_LEAK_CHECK=1`). The Pulumi-state leak check
    runs unconditionally — it has no dependency on cloud SDKs because the
    state file is local to the runner.

    If destroy itself fails, or the leak sweep finds dangling resources,
    the test fails with `pytrace=False` and the full leak report so the
    maintainer immediately sees what to clean up.
    """
    repo_root = Path(__file__).resolve().parents[2]
    project_dir = tmp_path / f"{example}_{target}"
    project_dir.mkdir()
    _copy_example(repo_root, example, project_dir, skaal_toml)

    app_name = _resolve_app_name(project_dir, app_spec)

    started = time.monotonic()
    deploy = _run(
        ["skaal", "deploy", "--yes", "--env", env_name, app_spec],
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
        app_name=app_name,
        deploy_stdout=deploy.stdout,
        deploy_stderr=deploy.stderr,
    )
    assert elapsed < deploy_budget_seconds, (
        f"`skaal deploy --env {env_name}` ({target}) took {elapsed:.1f}s "
        f"— over the {deploy_budget_seconds}s budget."
    )

    destroy_error: BaseException | None = None
    try:
        yield handle
    finally:
        try:
            _destroy(project_dir, env_name, app_spec)
        except Exception as exc:
            destroy_error = exc

        if destroy_error is not None:
            pytest.fail(
                f"Teardown failed for {target!r}/{env_name!r} — manual cleanup "
                f"likely required to avoid orphaned cloud resources: {destroy_error}",
                pytrace=False,
            )

        if leak_check:
            report = _leak_check(
                target=target,
                app_name=app_name,
                env_name=env_name,
                region=aws_region,
                project=gcp_project,
                project_dir=project_dir,
            )
            if not report.is_clean:
                pytest.fail(
                    f"Leak check failed after destroying {target!r}/{env_name!r}:\n"
                    f"{report.format()}",
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
    "LeakReport",
    "deployed_stack",
    "find_endpoint_url",
    "requires_aws",
    "requires_gcp",
    "requires_local",
]
