"""Tests for `skaal.plugins.load_plugins` entry-point discovery.

These tests inject a fake entry-point into `importlib.metadata` so we
exercise the loader without publishing a real distribution. Each test
resets the load-once flag plus the plugin-contributed entries in both
registries afterwards so cross-test isolation is preserved.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pytest

from skaal import Backend, Target
from skaal.binding.registry import BackendEntry, lookup
from skaal.errors import SkaalConfigError
from skaal.plugins import PluginRegistry, SkaalPlugin, load_plugins


class _FakePlugin(SkaalPlugin):
    """A plugin that registers one fake backend in the binding registry."""

    name = "fake-plugin"

    def register(self, registry: PluginRegistry) -> None:
        registry.add_backend(
            BackendEntry(
                token=_FakeBackend,
                targets=frozenset({Target.AWS}),
            )
        )


class _FakeBackend(Backend[object]):
    name = "fake-backend"
    kinds = frozenset({"store"})


class _BrokenPlugin(SkaalPlugin):
    name = "broken-plugin"

    def register(self, registry: PluginRegistry) -> None:
        raise RuntimeError("intentional failure")


class _FakeEntryPoint:
    def __init__(self, name: str, target: type[SkaalPlugin]) -> None:
        self.name = name
        self._target = target

    def load(self) -> Any:
        return self._target


@pytest.fixture(autouse=True)
def _reset_state() -> Iterable[None]:
    """Clear plugin state before and after each test."""
    from skaal.binding.registry import _reset_for_tests as reset_binding
    from skaal.plugins import _reset_for_tests as reset_plugins

    reset_plugins()
    reset_binding()
    yield
    reset_plugins()
    reset_binding()


def _patch_entry_points(
    monkeypatch: pytest.MonkeyPatch, entries: tuple[_FakeEntryPoint, ...]
) -> None:
    """Swap `importlib.metadata.entry_points` for one returning `entries`."""

    def fake_entry_points(group: str | None = None, **_: object) -> tuple[_FakeEntryPoint, ...]:
        if group == "skaal.plugins":
            return entries
        return ()

    monkeypatch.setattr("importlib.metadata.entry_points", fake_entry_points)


def test_load_plugins_registers_contributed_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from skaal.binding.registry import _BY_NAME

    _patch_entry_points(monkeypatch, (_FakeEntryPoint("fake", _FakePlugin),))
    # Before the load, the in-tree map does not know about the backend.
    assert "fake-backend" not in _BY_NAME

    load_plugins()
    entry = lookup("fake-backend")
    assert entry.token is _FakeBackend
    assert Target.AWS in entry.targets


def test_load_plugins_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeat loads short-circuit; the same plugin registers exactly once."""
    _patch_entry_points(monkeypatch, (_FakeEntryPoint("fake", _FakePlugin),))
    load_plugins()
    # A second load is a no-op — the same plugin would otherwise raise
    # `SkaalConfigError` on the second registration of the same backend.
    load_plugins()
    assert lookup("fake-backend").token is _FakeBackend


def test_lookup_triggers_lazy_plugin_loading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`binding.registry.lookup(...)` itself drives the first load."""
    _patch_entry_points(monkeypatch, (_FakeEntryPoint("fake", _FakePlugin),))
    # No explicit `load_plugins()` call — the lookup must drive discovery.
    entry = lookup("fake-backend")
    assert entry.token is _FakeBackend


def test_broken_plugin_does_not_break_others(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A plugin that raises in `register(...)` is logged and skipped."""
    _patch_entry_points(
        monkeypatch,
        (
            _FakeEntryPoint("broken", _BrokenPlugin),
            _FakeEntryPoint("fake", _FakePlugin),
        ),
    )
    load_plugins()
    # The healthy plugin still registered.
    assert lookup("fake-backend").token is _FakeBackend


def test_conflicting_backend_registration_raises() -> None:
    """A plugin trying to re-claim an in-tree backend name fails clean."""
    from skaal.binding.registry import register_backend

    class FakeRedis(Backend[object]):
        name = "redis"
        kinds = frozenset({"store"})

    with pytest.raises(SkaalConfigError, match="already registered"):
        register_backend(BackendEntry(token=FakeRedis, targets=frozenset({Target.AWS})))


def test_idempotent_re_registration_of_same_token() -> None:
    """Registering the exact same `BackendEntry` twice is a silent no-op."""
    from skaal.binding.registry import register_backend

    entry = BackendEntry(token=_FakeBackend, targets=frozenset({Target.AWS}))
    register_backend(entry)
    register_backend(entry)
    assert lookup("fake-backend").token is _FakeBackend
