"""Tests for the local runtime's per-kind dispatch table."""

from __future__ import annotations

from skaal.inference.model import ResourceKind
from skaal.runtime.local.dispatch import LOCAL_DISPATCH, dispatch_for


def test_every_resource_kind_has_an_adapter() -> None:
    for kind in ResourceKind:
        assert kind in LOCAL_DISPATCH, f"no adapter wired for {kind.value}"


def test_dispatch_for_returns_callable() -> None:
    for kind in ResourceKind:
        assert callable(dispatch_for(kind))
