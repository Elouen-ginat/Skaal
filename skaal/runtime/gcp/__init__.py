"""GCP runtime package (ADR 042)."""

from __future__ import annotations

from skaal.runtime.gcp.bootstrap import wire_app_from_environment

__all__ = ["wire_app_from_environment"]
