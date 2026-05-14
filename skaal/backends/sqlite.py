"""Public import path for the `Sqlite` backend token (ADR 032 §4.5).

Re-exports the token from `skaal.backends._tokens`. User code that pins a
primitive to this backend writes ``from skaal.backends.sqlite import Sqlite``
and uses it as ``Store[User, Sqlite]``.
"""

from __future__ import annotations

from skaal.backends._tokens import Sqlite

__all__ = ["Sqlite"]
