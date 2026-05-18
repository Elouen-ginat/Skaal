"""Shared gating for `tests/smoke/`.

Smoke tests provision real cloud resources (AWS, BigQuery) and only run when
the caller has opted in with an explicit environment variable. The default
`pytest tests/` collection picks the files up; without the gate set, every
test inside skips with a clear reason.

ADR 035 Decision 4 (`SKAAL_RUN_AWS_SMOKE=1`) and Decision 3
(`SKAAL_RUN_BIGQUERY_SMOKE=1` + `GOOGLE_APPLICATION_CREDENTIALS`) are the two
opt-in handshakes; see `notes/design/035-docs-examples-and-v040-cut-implementation-plan.md`.
"""

from __future__ import annotations

import os

import pytest

AWS_GATE = "SKAAL_RUN_AWS_SMOKE"
BIGQUERY_GATE = "SKAAL_RUN_BIGQUERY_SMOKE"
BIGQUERY_CREDS = "GOOGLE_APPLICATION_CREDENTIALS"


def requires_aws_gate() -> None:
    """Skip the calling test unless `SKAAL_RUN_AWS_SMOKE=1` is set."""
    if os.environ.get(AWS_GATE) != "1":
        pytest.skip(
            f"AWS smoke disabled — set {AWS_GATE}=1 to opt in. "
            "Maintainer-run per ADR 035 Decision 4; CI does not opt in."
        )


def requires_bigquery_gate() -> None:
    """Skip the calling test unless the BigQuery gate + credentials are set."""
    if os.environ.get(BIGQUERY_GATE) != "1":
        pytest.skip(
            f"BigQuery smoke disabled — set {BIGQUERY_GATE}=1 to opt in. "
            "Maintainer-run per ADR 035 Decision 3; CI does not opt in."
        )
    if not os.environ.get(BIGQUERY_CREDS):
        pytest.skip(
            f"{BIGQUERY_CREDS} unset — BigQuery smoke needs a service-account "
            "key path to authenticate against the live dataset."
        )
