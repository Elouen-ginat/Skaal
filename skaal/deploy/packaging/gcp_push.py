from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

try:
    import google.auth
    from google.auth.transport.requests import Request
except ModuleNotFoundError:
    google = SimpleNamespace(auth=SimpleNamespace(default=None))
    Request = None

from skaal.deploy.packaging.docker_builder import (
    DockerProgress,
    build_image,
    login_registry,
    push_image,
)


def build_and_push_image(
    artifacts_dir: Path,
    project: str,
    region: str,
    repository: str,
    app_name: str,
    progress: DockerProgress = None,
) -> None:
    if Request is None or getattr(google.auth, "default", None) is None:
        raise ModuleNotFoundError(
            "google-auth is required for GCP image pushes. Install the gcp extra."
        )
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(Request())
    if credentials.token is None:
        raise RuntimeError("Google credentials did not yield an access token.")

    registry = f"{region}-docker.pkg.dev"
    image_repository = f"{registry}/{project}/{repository}/{app_name}"
    image_tag = f"{image_repository}:latest"

    login_registry(
        registry=registry,
        username="oauth2accesstoken",
        password=credentials.token,
    )
    build_image(context_dir=artifacts_dir.resolve(), tag=image_tag, progress=progress)
    push_image(repository=image_repository, tag="latest", progress=progress)
