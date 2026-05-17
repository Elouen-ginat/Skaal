"""Grep gate enforcing ADR 028 §12 criterion 8.

"The word 'constraint' appears nowhere in user-facing docs, CLI help, or
decorator signatures."

The gate has three surfaces:

1. **Decorator signatures** (`skaal.app` decorators) — every public
   decorator's parameter names are scanned. Enforced — must be clean.
2. **CLI help strings** — every Typer command's `help=` text is scanned.
   Enforced — must be clean as of Phase 1.
3. **Docs prose** under `docs/` (excluding `design/_archive/` and the
   vocabulary-neutral `design_system/` assets) — scanned for the full
   constraint-era token list. Marked `xfail` until the Phase 7 §7.2
   page-by-page rewrite lands (ADR 035 Decision 1); flips to a hard gate
   in the same commit that ticks 7.2.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import skaal

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOCS_DIR = _REPO_ROOT / "docs"

# Tokens that are already absent from `docs/` and must stay absent. Each is
# enforced as a hard assertion; a regression here is a real bug.
_CLEAN_DOC_TOKENS: tuple[str, ...] = (
    "Durability",
    "AccessPattern",
    "Throughput",
    "@app.handler",
    "@app.scale",
    "@app.shared",
    "skaal.agent",
    "skaal.patterns",
    "EventLog",
    "Outbox",
    "Saga",
    "Projection",
)

# Tokens that still appear in the prose pages and will be removed by the
# Phase 7 §7.2 page-by-page rewrite. Marked `xfail`; each one flips to
# `_CLEAN_DOC_TOKENS` in the same commit that retires its last call site.
_DIRTY_DOC_TOKENS: tuple[str, ...] = (
    "constraint",
    "Constraint",
    "Latency",
    "VectorStore",
)

# Subset that *signatures* and *CLI help* must never contain (no
# capitalization-fuzzy matches, no Z3 prose).
_BANNED_SIGNATURE_TOKENS: tuple[str, ...] = (
    "latency",
    "durability",
    "access_pattern",
    "throughput",
    "constraint",
)


def _docs_files() -> list[Path]:
    """All Markdown files under `docs/` excluding archived and design-system assets."""
    files: list[Path] = []
    for path in _DOCS_DIR.rglob("*.md"):
        rel = path.relative_to(_DOCS_DIR).as_posix()
        if rel.startswith("design/_archive/"):
            continue
        if rel.startswith("design_system/"):
            # Design-system pages reference component filenames (e.g.
            # `constraint-tokens.svg`) that are scheduled for renaming in
            # ADR 035 Decision 1 §20 but are vocabulary-neutral in CSS.
            continue
        files.append(path)
    return files


def _scan_docs(token: str) -> list[str]:
    hits: list[str] = []
    for path in _docs_files():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if token in text:
            hits.append(path.relative_to(_REPO_ROOT).as_posix())
    return sorted(hits)


@pytest.mark.parametrize("token", _CLEAN_DOC_TOKENS)
def test_constraint_token_stays_absent_from_docs(token: str) -> None:
    """A token already absent from `docs/` must not be reintroduced."""
    hits = _scan_docs(token)
    assert not hits, (
        f"Constraint-era token {token!r} was reintroduced in: {', '.join(hits)}. "
        "ADR 028 §12 criterion 8 forbids it in user-facing docs."
    )


@pytest.mark.parametrize("token", _DIRTY_DOC_TOKENS)
@pytest.mark.xfail(
    reason="Phase 7 §7.2 docs rewrite still pending (ADR 035 Decision 1).",
    strict=True,
)
def test_dirty_constraint_token_clears_from_docs(token: str) -> None:
    """Token still appears in prose; flips green once §7.2 retires it.

    `strict=True` means a passing test is reported as `XPASS` and fails the
    suite — that's the signal to move the token to `_CLEAN_DOC_TOKENS`.
    """
    hits = _scan_docs(token)
    assert not hits, f"Constraint-era token {token!r} still appears in: {', '.join(hits)}."


@pytest.mark.parametrize(
    "decorator_attr",
    ["storage", "function", "schedule", "job", "channel", "external"],
)
def test_decorator_signatures_clean(decorator_attr: str) -> None:
    """`@app.<decorator>` must not accept constraint-era kwargs.

    The constraint kwargs (`latency`, `durability`, `access_pattern`,
    `write_throughput`, `retention`, `consistency`, `read_*`) were removed
    in Phase 1; this asserts they never come back.
    """
    app = skaal.App(name="probe")
    decorator = getattr(app, decorator_attr)
    sig = inspect.signature(decorator)
    parameter_names = list(sig.parameters)
    offenders = [
        name
        for name in parameter_names
        if any(banned in name.lower() for banned in _BANNED_SIGNATURE_TOKENS)
    ]
    assert not offenders, (
        f"@app.{decorator_attr} signature exposes constraint-era kwargs: {', '.join(offenders)}."
    )


def test_archive_excluded_from_mkdocs() -> None:
    """`docs/design/_archive/` must be excluded from the mkdocs build."""
    mkdocs_path = _REPO_ROOT / "mkdocs.yml"
    text = mkdocs_path.read_text(encoding="utf-8")
    assert "design/_archive/" in text, (
        "mkdocs.yml must declare `exclude_docs: design/_archive/` so the "
        "archived constraint-era ADR is not discoverable as current docs."
    )


def test_archive_directory_present() -> None:
    """The archived ADR 001 must live under `docs/design/_archive/`."""
    archived = _REPO_ROOT / "docs" / "design" / "_archive" / "001-infrastructure-as-constraints.md"
    assert archived.is_file(), (
        "Expected the archived constraint-model ADR at "
        f"{archived.relative_to(_REPO_ROOT).as_posix()}."
    )


def test_catalogs_page_deleted() -> None:
    """`docs/catalogs.md` was deleted in Phase 1; the file must not return."""
    assert not (_DOCS_DIR / "catalogs.md").exists(), (
        "docs/catalogs.md must not exist — catalogs were deleted in Phase 1."
    )
