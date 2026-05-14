"""Tests for `App.mount(path, asgi_app)` inference (ADR 032 §4.6)."""

from __future__ import annotations

from skaal import App
from skaal.inference.model import ResourceKind


def _fake_asgi(scope, receive, send):
    raise NotImplementedError


def test_mount_path_form_emits_asgi_service_resource() -> None:
    app = App("test-mount-path")
    app.mount("/api", _fake_asgi)
    plan = app.infer()
    asgi_resources = [r for r in plan.resources if r.kind == ResourceKind.ASGI_SERVICE]
    assert len(asgi_resources) == 1
    assert asgi_resources[0].overrides.options.get("path") == "/api"


def test_mount_multiple_paths_emit_multiple_resources() -> None:
    app = App("test-mount-paths")
    app.mount("/api", _fake_asgi)
    app.mount("/admin", _fake_asgi)
    plan = app.infer()
    asgi_resources = [r for r in plan.resources if r.kind == ResourceKind.ASGI_SERVICE]
    paths = sorted(r.overrides.options["path"] for r in asgi_resources)
    assert paths == ["/admin", "/api"]


def test_mount_path_rejects_non_slash_prefix() -> None:
    app = App("test-mount-bad-path")
    try:
        app.mount("api", _fake_asgi)
    except ValueError as exc:
        assert "must start with" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_mount_path_rejects_duplicate() -> None:
    app = App("test-mount-dup")
    app.mount("/api", _fake_asgi)
    try:
        app.mount("/api", _fake_asgi)
    except ValueError as exc:
        assert "already mounted" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_mount_path_rejects_skaal_reserved_prefix() -> None:
    app = App("test-mount-reserved")
    try:
        app.mount("/_skaal", _fake_asgi)
    except ValueError as exc:
        assert "_skaal" in str(exc)
    else:
        raise AssertionError("expected ValueError")
