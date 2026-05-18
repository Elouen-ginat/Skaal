"""Fingerprinting for `InferredPlan` and `InferredResource`.

The fingerprint is the SHA-256 of the canonical JSON payload (resources and
edges sorted, keys sorted, no whitespace), truncated to the first 16 hex
characters. It is byte-stable across reorderings — the same plan constructed
in two different resource orders produces the same fingerprint.

See ADR 030 §2.3 for the design.
"""

from __future__ import annotations

import hashlib

from skaal.inference.model import (
    Blueprint,
    BlueprintResource,
    _canonical_payload,
    _canonical_resource_payload,
)

_FINGERPRINT_HEX_LEN = 16


def fingerprint_plan(plan: Blueprint) -> str:
    """Return the 16-char SHA-256 fingerprint of ``plan``.

    The fingerprint excludes ``plan.fingerprint`` itself, so feeding a freshly
    fingerprinted plan back through this function yields the same value.
    """
    payload = _canonical_payload(plan)
    return hashlib.sha256(payload).hexdigest()[:_FINGERPRINT_HEX_LEN]


def fingerprint_resource(res: BlueprintResource) -> str:
    """Return the 16-char SHA-256 fingerprint of a single resource.

    Used by the binding layer (Phase 3) to detect when a resource's *shape*
    changes between deploys (which invalidates the `LockEntry` for that id).
    """
    payload = _canonical_resource_payload(res)
    return hashlib.sha256(payload).hexdigest()[:_FINGERPRINT_HEX_LEN]
