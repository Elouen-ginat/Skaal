"""Local-host probes for cloud credentials and region defaults.

These helpers introspect the developer's machine to fill in the gaps when
`skaal.toml` does not pin a value. They are used by ``skaal doctor``, the
``skaal.api.doctor`` Python entry point, and the deploy preflight — keeping
all three in sync.

`skaal.toml` (via the `Environment` model) is always the authoritative
source; the env-var/file fallbacks here only kick in when an `Environment`
leaves the field unset.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from skaal.binding.model import Environment


# ── GCP ───────────────────────────────────────────────────────────────────────


def resolve_gcp_project(env: Environment | None) -> str | None:
    """Return the active GCP project id.

    Looks first at ``[env.<name>.backends.gcp].project`` on the given
    `Environment`, then falls back to the ``GOOGLE_CLOUD_PROJECT`` and
    ``GCP_PROJECT`` env vars.
    """
    if env is not None:
        gcp_backend = env.backends.get("gcp")
        if gcp_backend is not None and gcp_backend.project:
            return gcp_backend.project
    return os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")


def detect_gcp_auth() -> str:
    """Describe which GCP credential source is currently visible."""
    credentials = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if credentials:
        return f"credentials-file:{credentials}"

    if os.getenv("GOOGLE_OAUTH_ACCESS_TOKEN"):
        return "access-token"

    appdata = os.getenv("APPDATA")
    candidate_paths: list[Path] = []
    if appdata:
        candidate_paths.append(Path(appdata) / "gcloud" / "application_default_credentials.json")
    candidate_paths.append(
        Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
    )
    if any(path.exists() for path in candidate_paths):
        return "application-default-credentials"

    return "not-detected"


# ── AWS ───────────────────────────────────────────────────────────────────────


def resolve_aws_region(env: Environment | None) -> str | None:
    """Return the active AWS region.

    Looks first at the `Environment.region`, then ``AWS_REGION``, then
    ``AWS_DEFAULT_REGION``.
    """
    if env is not None and env.region:
        return env.region
    return os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")


def detect_aws_auth() -> str:
    """Describe which AWS credential source is currently visible."""
    if os.getenv("AWS_ACCESS_KEY_ID"):
        return "env"

    profile = os.getenv("AWS_PROFILE")
    if profile:
        return f"profile:{profile}"

    aws_dir = Path.home() / ".aws"
    if (aws_dir / "credentials").exists() or (aws_dir / "config").exists():
        return "shared-config"

    return "not-detected"


# ── Docker daemon ─────────────────────────────────────────────────────────────


def detect_docker_daemon() -> str:
    """Describe Docker daemon state.

    Returns one of:
        - ``"not-installed"`` if the ``docker`` CLI is not on ``PATH``
        - ``"not-running"`` if the CLI is present but ``docker info`` fails
        - ``"running"`` if the daemon responds within 5 s

    Used by the deploy preflight (Cloud Run / Lambda image builds need a
    live daemon) and surfaced in ``skaal doctor``.
    """
    if shutil.which("docker") is None:
        return "not-installed"
    try:
        completed = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "not-running"
    return "running" if completed.returncode == 0 else "not-running"


__all__ = [
    "detect_aws_auth",
    "detect_docker_daemon",
    "detect_gcp_auth",
    "resolve_aws_region",
    "resolve_gcp_project",
]
