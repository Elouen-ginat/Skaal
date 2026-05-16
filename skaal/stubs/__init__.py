"""Cross-process typed stub emission for Skaal apps (ADR 028 §6.6.1, ADR 033).

`skaal stubs --from <src> --to <out> [--as <pkg>]` emits a PEP 561
`partial-stub` package describing every `Store` / `Relational` / `BlobStore`
/ `Channel` / `@app.function` in a source app. The consuming project
points `pyrightconfig.json` (or `pyproject.toml`) at the output directory
and gets typed LSP completion for the cross-service callable surface
without importing the source app's runtime.

This package never runs at server runtime — only when a developer invokes
the CLI. Single-process callers use the primitive classes directly.
"""

from __future__ import annotations

from skaal.stubs.emit import discover_app, emit_stubs
from skaal.stubs.manifest import StubManifest, StubResourceRef

__all__ = [
    "StubManifest",
    "StubResourceRef",
    "discover_app",
    "emit_stubs",
]
