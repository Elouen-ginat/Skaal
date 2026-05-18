"""Tests for the backend registry."""

from __future__ import annotations

import pytest

from skaal.backends._tokens import ALL_TOKENS, Redis, Sqlite
from skaal.binding.model import Target
from skaal.binding.registry import (
    REGISTRY,
    BackendCapabilities,
    BackendSpec,
    default_entry_for,
    lookup,
    lookup_token,
    tokens_for,
)
from skaal.errors import UnknownBackendError
from skaal.inference.model import ResourceKind


def test_registry_contains_every_token() -> None:
    registered = {entry.token for entry in REGISTRY}
    assert registered == set(ALL_TOKENS)


def test_registry_has_no_duplicate_names() -> None:
    names = [entry.token.name for entry in REGISTRY]
    assert len(names) == len(set(names))


def test_every_entry_has_capabilities_and_options_schema() -> None:
    for entry in REGISTRY:
        assert isinstance(entry, BackendSpec)
        assert isinstance(entry.capabilities, BackendCapabilities)
        assert entry.options_schema is not None


def test_lookup_finds_known_backend() -> None:
    entry = lookup("sqlite")
    assert entry.token is Sqlite


def test_lookup_raises_for_unknown_backend() -> None:
    with pytest.raises(UnknownBackendError) as exc_info:
        lookup("nonesuch")
    assert "nonesuch" in str(exc_info.value)
    assert "sqlite" in str(exc_info.value)


def test_lookup_token_finds_by_class_identity() -> None:
    entry = lookup_token(Redis)
    assert entry.token is Redis


def test_default_entry_for_returns_registry_defaults() -> None:
    sqlite = default_entry_for(ResourceKind.STORE, Target.LOCAL)
    postgres = default_entry_for(ResourceKind.RELATIONAL, Target.AWS)

    assert sqlite.token is Sqlite
    assert sqlite.is_default_for(ResourceKind.STORE, Target.LOCAL)
    assert postgres.token.name == "postgres"
    assert postgres.is_default_for(ResourceKind.RELATIONAL, Target.AWS)


def test_default_roles_stay_consistent_with_backend_traits() -> None:
    for entry in REGISTRY:
        for default in entry.default_for:
            assert default.target in entry.targets
            assert default.kind in entry.kinds


def test_tokens_for_filters_by_kind_and_target() -> None:
    matches = tokens_for(ResourceKind.STORE.value, Target.LOCAL)
    tokens = {entry.token for entry in matches}
    assert Sqlite in tokens
    for entry in matches:
        assert Target.LOCAL in entry.targets
        assert ResourceKind.STORE.value in entry.token.kinds


def test_tokens_for_returns_empty_when_no_match() -> None:
    assert tokens_for("nonsense-kind", Target.LOCAL) == ()
