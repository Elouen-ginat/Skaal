"""Non-regression: deploy the kitchen-sink app to GCP.

Exercises every public decorator (KV + blob + relational storage, channel,
function with full resilience policies, job, two schedule kinds, sub-module
composition) on top of the GCP deploy path: Cloud Run + Firestore +
Cloud SQL + GCS + Cloud Scheduler + Pub/Sub.
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


def test_kitchen_sink_gcp_deploy(tmp_path: Path) -> None:
    """Deploy the kitchen-sink app to GCP, hit the API, destroy, leak-check."""
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
        example="nonregression_kitchen_sink",
        skaal_toml=_skaal_toml(project, region),
        env_name="prod",
        app_spec="app.app:app",
        target="gcp",
        deploy_budget_seconds=900,
        gcp_project=project,
    ) as stack:
        base_url = find_endpoint_url(stack.deploy_stdout, marker="run.app")

        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            healthz = client.get("/healthz")
            assert healthz.status_code == 200, healthz.text

            created = client.post(
                "/users",
                json={"id": "nonregression-gcp-sink", "name": "kitchen sink"},
            )
            assert created.status_code == 201, created.text

            listed = client.get("/users")
            assert listed.status_code == 200, listed.text
            ids = {u["id"] for u in listed.json().get("users", [])}
            assert "nonregression-gcp-sink" in ids, (
                f"nonregression-gcp-sink missing from /users response: {listed.json()}"
            )
