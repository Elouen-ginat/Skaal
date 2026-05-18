"""Non-regression: deploy `todo_api` against GCP, exercise the API, destroy.

Uses Cloud Run + Firestore (the default GCP slots in the binding defaults
table). The GCP project is selected from the `SKAAL_NONREGRESSION_GCP_PROJECT`
environment variable so this test does not bake a project id into the repo.
"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

import httpx
import pytest

from tests.nonregression.conftest import (
    deployed_stack,
    find_endpoint_url,
    requires_gcp,
)

GCP_PROJECT_ENV = "SKAAL_NONREGRESSION_GCP_PROJECT"
GCP_REGION_ENV = "SKAAL_NONREGRESSION_GCP_REGION"


def _skaal_toml(project: str, region: str) -> str:
    return textwrap.dedent(
        f"""
        [env.prod]
        target = "gcp"
        region = "{region}"

        [env.prod.backends.gcp]
        project = "{project}"
        """
    ).lstrip()


def test_todo_api_gcp_deploy(tmp_path: Path) -> None:
    """Provision `examples/todo_api` against GCP Cloud Run, then tear down."""
    requires_gcp()
    pytest.importorskip("pulumi", reason="`pulumi` automation API required.")
    pytest.importorskip("pulumi_gcp", reason="`pulumi_gcp` required for GCP resources.")

    project = os.environ.get(GCP_PROJECT_ENV)
    if not project:
        pytest.skip(
            f"{GCP_PROJECT_ENV} unset — set it to the GCP project that should "
            "host the throwaway non-regression stack."
        )
    region = os.environ.get(GCP_REGION_ENV, "us-central1")

    with deployed_stack(
        tmp_path,
        example="todo_api",
        skaal_toml=_skaal_toml(project, region),
        env_name="prod",
        app_spec="app.app:app",
        target="gcp",
        deploy_budget_seconds=600,
    ) as stack:
        base_url = find_endpoint_url(stack.deploy_stdout, marker="run.app")

        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            created = client.post(
                "/todos",
                json={
                    "id": "nonregression-gcp",
                    "title": "nonregression",
                    "description": "from CI",
                },
            )
            assert created.status_code == 201, created.text

            listed = client.get("/todos")
            assert listed.status_code == 200, listed.text
            ids = [t["id"] for t in listed.json().get("todos", [])]
            assert "nonregression-gcp" in ids, (
                f"nonregression-gcp missing from /todos response: {listed.json()}"
            )
