"""Public import path for the `DynamoDB` backend token (ADR 032 §4.5).

Re-exports the token from `skaal.backends._tokens`. User code that pins a
primitive to this backend writes ``from skaal.backends.dynamodb import DynamoDB``
and uses it as the second generic parameter on a primitive class.
"""

from __future__ import annotations

from skaal.backends._tokens import DynamoDB

__all__ = ["DynamoDB"]
