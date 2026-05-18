"""Back-compat re-export — `resolve_gcp_project` now lives in `skaal.binding._probe`."""

from __future__ import annotations

from skaal.binding._probe import resolve_gcp_project

__all__ = ["resolve_gcp_project"]
