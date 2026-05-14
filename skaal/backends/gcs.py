"""Public import path for the `Gcs` backend token (ADR 032 §4.5).

Re-exports the token from `skaal.backends._tokens`. User code that pins a
primitive to this backend writes ``from skaal.backends.gcs import Gcs``
and uses it as the second generic parameter on a primitive class.
"""

from __future__ import annotations

from skaal.backends._tokens import Gcs

__all__ = ["Gcs"]
