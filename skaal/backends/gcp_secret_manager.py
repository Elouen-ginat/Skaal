"""Public import path for the `GcpSecretManager` backend token (ADR 032 §4.5).

Re-exports the token from `skaal.backends._tokens`. User code that pins a
primitive to this backend writes ``from skaal.backends.gcp_secret_manager import GcpSecretManager``
and uses it as the second generic parameter on a primitive class.
"""

from __future__ import annotations

from skaal.backends._tokens import GcpSecretManager

__all__ = ["GcpSecretManager"]
