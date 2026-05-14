"""Public import path for the `Apscheduler` backend token (ADR 032 §4.5).

Re-exports the token from `skaal.backends._tokens`. User code that pins a
primitive to this backend writes ``from skaal.backends.apscheduler import Apscheduler``
and uses it as the second generic parameter on a primitive class.
"""

from __future__ import annotations

from skaal.backends._tokens import Apscheduler

__all__ = ["Apscheduler"]
