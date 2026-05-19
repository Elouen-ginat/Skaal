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
import re
import shutil
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import lru_cache
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
    if not _aws_credentials_are_usable():
        pytest.skip(
            "AWS credentials were detected in the environment but are not currently usable. "
            "Refresh the session or re-run OIDC credential setup before running AWS non-regression."
        )


@lru_cache(maxsize=1)
def _aws_credentials_are_usable() -> bool:
    try:
        import boto3
    except ImportError:
        return False

    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
    try:
        boto3.client("sts", region_name=region).get_caller_identity()
    except Exception:
        return False
    return True


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
    # `skaal deploy` calls `importlib.import_module(spec.module)` and the
    # Python console-script entry point does NOT add the cwd to `sys.path`
    # (only `python script.py` / `python -c` do). Prepend `cwd` to PYTHONPATH
    # so the user's example package becomes importable.
    existing_path = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{cwd}{os.pathsep}{existing_path}" if existing_path else str(cwd)
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

    body_exc: BaseException | None = None
    try:
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

        yield handle
    except BaseException as exc:
        body_exc = exc
        raise
    finally:
        # `pulumi up` may have partially created resources even when it
        # ultimately failed, and those resources are referenced by the local
        # stack state. Always attempt destroy — skip only when no stack
        # workdir was ever produced (e.g. the deploy aborted before Pulumi
        # was invoked at all).
        destroy_error: BaseException | None = None
        if _stack_workdir(project_dir, env_name).exists():
            try:
                _destroy(project_dir, env_name, app_spec)
            except Exception as exc:
                destroy_error = exc

        if body_exc is not None:
            # The original deploy/body error will propagate via `raise`.
            # Attach the teardown outcome so a maintainer reading the
            # failure knows whether they still need to clean up manually.
            if destroy_error is not None:
                body_exc.add_note(
                    "Best-effort teardown after the failure above also raised: "
                    f"{destroy_error}. Cloud resources may be orphaned — verify "
                    "and clean up manually."
                )
            else:
                body_exc.add_note(
                    "Best-effort teardown after the failure above completed — "
                    "no orphaned resources expected."
                )
        else:
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


_URL_TERMINATOR_RE = re.compile(r"[\s\"',<>]")


def find_endpoint_url(deploy_stdout: str, marker: str) -> str:
    """Scan deploy output for the first URL line containing `marker`.

    Stops the URL at any whitespace, quote, comma, or angle-bracket so a
    captured URL never picks up trailing markup (Rich ANSI resets, log
    suffixes, etc.). Strips a trailing slash too — when the test joins
    paths via `httpx.Client(base_url=...).post("/foo")`, httpx adds the
    leading slash itself, and a trailing one would produce `//foo`.
    """
    for line in deploy_stdout.splitlines():
        if marker in line and "https://" in line:
            start = line.find("https://")
            terminator = _URL_TERMINATOR_RE.search(line, start)
            end = terminator.start() if terminator else len(line)
            return line[start:end].rstrip("/")
    raise AssertionError(
        f"Could not find a URL containing {marker!r} in `skaal deploy` output. "
        f"Captured stdout:\n{deploy_stdout}"
    )


@dataclass(frozen=True)
class RunningApp:
    """Handle for a locally-served Skaal app under `skaal run`."""

    project_dir: Path
    host: str
    port: int

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


def _wait_for_port(host: str, port: int, *, timeout: float = 30.0) -> None:
    import socket

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return
        except OSError:
            time.sleep(0.5)
    raise AssertionError(f"Port {port} on {host!r} never opened within {timeout:.1f}s")


@contextmanager
def running_app(
    tmp_path: Path,
    example: str,
    skaal_toml: str,
    *,
    env_name: str = "local",
    app_spec: str = "app.app:app",
    host: str = "127.0.0.1",
    port: int = 8000,
    boot_timeout_seconds: float = 60.0,
) -> Iterator[RunningApp]:
    """Spawn `skaal run` in the background, wait for the port, yield, then stop.

    The `local` target does not provision infrastructure — `skaal build` /
    `skaal deploy` only support `aws` and `gcp`. For non-regression coverage
    of the local execution path we run the app under uvicorn (which is what
    `skaal run` does) and probe its HTTP surface, then terminate the process.
    No infra teardown or leak check is needed: nothing exists outside the
    runner.
    """
    repo_root = Path(__file__).resolve().parents[2]
    project_dir = tmp_path / f"{example}_local"
    project_dir.mkdir()
    _copy_example(repo_root, example, project_dir, skaal_toml)

    env = os.environ.copy()
    existing_path = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{project_dir}{os.pathsep}{existing_path}" if existing_path else str(project_dir)
    )

    cmd = [
        "skaal",
        "run",
        "--env",
        env_name,
        "--host",
        host,
        "--port",
        str(port),
        app_spec,
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=project_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        try:
            _wait_for_port(host, port, timeout=boot_timeout_seconds)
        except AssertionError:
            # Server never came up — surface what it printed so the failure
            # message is actionable rather than just "port never opened".
            try:
                stdout, stderr = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate()
            raise AssertionError(
                f"`skaal run` never bound to {host}:{port} within "
                f"{boot_timeout_seconds:.1f}s.\n"
                f"--- stdout ---\n{stdout}\n--- stderr ---\n{stderr}"
            ) from None

        yield RunningApp(project_dir=project_dir, host=host, port=port)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


__all__: list[str] = [
    "DeployedStack",
    "LeakReport",
    "RunningApp",
    "deployed_stack",
    "find_endpoint_url",
    "requires_aws",
    "requires_gcp",
    "requires_local",
    "running_app",
]
