"""Tests for the per-`(ResourceKind, Target)` defaults table."""

from __future__ import annotations

import pytest

from skaal.backends._base import Backend
from skaal.binding.defaults import DEFAULTS
from skaal.binding.model import Target
from skaal.binding.registry import REGISTRY
from skaal.inference.model import ResourceKind


def test_every_resource_kind_has_a_row() -> None:
    assert set(DEFAULTS) == set(ResourceKind)


def test_every_target_is_populated_for_each_kind() -> None:
    expected = set(Target)
    for kind, row in DEFAULTS.items():
        assert set(row) == expected, f"missing targets for {kind}"


def test_every_default_token_is_a_backend_subclass() -> None:
    for kind, row in DEFAULTS.items():
        for target, token in row.items():
            assert issubclass(token, Backend), (
                f"DEFAULTS[{kind}][{target}] = {token!r} is not a Backend subclass"
            )


def test_every_default_token_is_registered() -> None:
    registered = {entry.token for entry in REGISTRY}
    for kind, row in DEFAULTS.items():
        for target, token in row.items():
            assert token in registered, (
                f"DEFAULTS[{kind}][{target}] = {token.__name__} is not in REGISTRY"
            )


def test_every_default_token_supports_the_kind_and_target() -> None:
    registered = {entry.token: entry for entry in REGISTRY}
    for kind, row in DEFAULTS.items():
        for target, token in row.items():
            entry = registered[token]
            assert target in entry.targets, (
                f"DEFAULTS[{kind}][{target}] = {token.__name__} does not target {target}"
            )
            assert kind.value in token.kinds, (
                f"DEFAULTS[{kind}][{target}] = {token.__name__} does not host kind {kind.value}"
            )


def test_defaults_table_is_read_only() -> None:
    with pytest.raises(TypeError):
        DEFAULTS[ResourceKind.STORE][Target.LOCAL] = None  # type: ignore[index]
