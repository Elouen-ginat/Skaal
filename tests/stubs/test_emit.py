"""Tests for the stub emitter (ADR 033 §5.1, §5.3)."""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import pytest

from skaal import App, Store
from skaal.stubs.emit import (
    StubEmitError,
    discover_app,
    emit_stubs,
)
from skaal.stubs.manifest import StubManifest


def _build_example_app() -> App:
    app = App("example")

    @app.storage
    class Customers(Store[dict]):  # pragma: no cover - typed placeholder
        pass

    @app.expose()
    async def signup(name: str) -> dict:  # pragma: no cover - typed placeholder
        return {"name": name}

    return app


def test_emit_writes_expected_layout(tmp_path: Path) -> None:
    out = tmp_path / "billing_stubs"
    written = emit_stubs(app=_build_example_app(), out_dir=out, package_name="billing_stubs")

    assert written == out
    assert (out / "py.typed").exists()
    assert (out / "_manifest.json").exists()
    assert (out / "__init__.pyi").exists()
    assert (out / "stores.pyi").exists()
    assert (out / "functions.pyi").exists()


def test_emit_init_reexports_all_public_names(tmp_path: Path) -> None:
    out = tmp_path / "billing_stubs"
    emit_stubs(app=_build_example_app(), out_dir=out, package_name="billing_stubs")
    init = (out / "__init__.pyi").read_text()

    assert "from .stores import Customers" in init
    assert "from .functions import signup" in init
    # `__all__` lists every covered symbol alphabetically.
    assert "__all__" in init
    assert '"Customers"' in init
    assert '"signup"' in init


def test_emitted_pyi_files_parse_as_python(tmp_path: Path) -> None:
    """Every emitted `.pyi` must parse with `ast.parse` so type checkers
    can consume it. A regression here would silently break downstream
    LSP completion.
    """
    out = tmp_path / "billing_stubs"
    emit_stubs(app=_build_example_app(), out_dir=out, package_name="billing_stubs")
    for pyi in out.glob("*.pyi"):
        ast.parse(pyi.read_text(), filename=str(pyi))


def test_emit_manifest_roundtrips(tmp_path: Path) -> None:
    out = tmp_path / "billing_stubs"
    emit_stubs(app=_build_example_app(), out_dir=out, package_name="billing_stubs")
    manifest = StubManifest.from_json((out / "_manifest.json").read_text())

    assert manifest.package_name == "billing_stubs"
    assert manifest.source_app == "example"
    assert manifest.app_fingerprint  # non-empty
    kinds = {ref.kind for ref in manifest.resources}
    assert "store" in kinds
    assert "function" in kinds


def test_emit_rejects_invalid_package_name(tmp_path: Path) -> None:
    with pytest.raises(StubEmitError):
        emit_stubs(
            app=_build_example_app(),
            out_dir=tmp_path / "out",
            package_name="not-an-identifier",
        )


def test_emit_idempotent_on_matching_package(tmp_path: Path) -> None:
    """Re-running with the same args overwrites only generated files."""
    out = tmp_path / "billing_stubs"
    emit_stubs(app=_build_example_app(), out_dir=out, package_name="billing_stubs")
    sidecar = out / "README.md"
    sidecar.write_text("preserved by user")

    emit_stubs(app=_build_example_app(), out_dir=out, package_name="billing_stubs")

    assert sidecar.read_text() == "preserved by user"
    assert (out / "_manifest.json").exists()


def test_emit_rejects_mismatched_existing_package(tmp_path: Path) -> None:
    out = tmp_path / "shared"
    emit_stubs(app=_build_example_app(), out_dir=out, package_name="first_stubs")
    with pytest.raises(StubEmitError, match="first_stubs"):
        emit_stubs(app=_build_example_app(), out_dir=out, package_name="second_stubs")


def test_discover_app_imports_module_attribute_form(tmp_path: Path) -> None:
    """`--from module:attribute` short-circuits filesystem discovery."""
    pkg_dir = tmp_path / "billing_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        textwrap.dedent(
            """
            from skaal import App
            app = App("billing")
            """
        )
    )

    import sys

    sys.path.insert(0, str(tmp_path))
    try:
        resolved = discover_app(Path("billing_pkg:app"))
    finally:
        sys.path.remove(str(tmp_path))
    assert resolved.name == "billing"


def test_discover_app_errors_on_missing_app(tmp_path: Path) -> None:
    pkg_dir = tmp_path / "empty_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("# no App here\n")

    import sys

    sys.path.insert(0, str(tmp_path))
    try:
        with pytest.raises(StubEmitError):
            discover_app(pkg_dir)
    finally:
        sys.path.remove(str(tmp_path))
