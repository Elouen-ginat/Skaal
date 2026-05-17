"""AWS runtime package."""

from __future__ import annotations

from skaal.runtime.aws.bootstrap import wire_app_from_environment

__all__ = ["wire_app_from_environment"]
