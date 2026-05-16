"""Tests for the shared `.native()` resolver helper (ADR 033 §5.6)."""

from __future__ import annotations

import asyncio

import pytest

from skaal._native import resolve_native


class _BackendWithSyncNative:
    """Backend that exposes a plain `.native()` returning a sentinel."""

    def __init__(self) -> None:
        self.client = object()

    def native(self) -> object:
        return self.client


class _BackendWithAsyncNative:
    """Backend whose `.native()` is itself async — must be awaited."""

    def __init__(self) -> None:
        self.client = object()

    async def native(self) -> object:
        return self.client


class _PlainBackend:
    """Backend that does not implement `.native()`."""


@pytest.mark.asyncio
async def test_resolve_native_unwraps_sync_callable() -> None:
    backend = _BackendWithSyncNative()
    assert await resolve_native(backend) is backend.client


@pytest.mark.asyncio
async def test_resolve_native_awaits_async_callable() -> None:
    backend = _BackendWithAsyncNative()
    assert await resolve_native(backend) is backend.client


@pytest.mark.asyncio
async def test_resolve_native_returns_backend_when_no_method() -> None:
    backend = _PlainBackend()
    assert await resolve_native(backend) is backend


@pytest.mark.asyncio
async def test_resolve_native_returns_backend_when_attr_is_not_callable() -> None:
    """If `backend.native` is set but not callable, the backend is returned."""

    class _NonCallableNative:
        native = "not-callable"

    backend = _NonCallableNative()
    assert await resolve_native(backend) is backend


def test_resolve_native_is_a_coroutine() -> None:
    """The helper is always async — the four primitives `await` it."""
    coro = resolve_native(_PlainBackend())
    assert asyncio.iscoroutine(coro)
    coro.close()
