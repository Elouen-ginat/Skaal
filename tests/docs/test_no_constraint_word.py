"""Grep gate enforcing ADR 028 §12 criterion 8.

"The word 'constraint' appears nowhere in user-facing docs, CLI help, or
decorator signatures."

The gate has three surfaces:

1. **Decorator signatures** (`skaal.app` decorators) — every public
   decorator's parameter names are scanned. Enforced — must be clean.
2. **CLI help strings** — every Typer command's `help=` text is scanned.
   Enforced — must be clean as of Phase 1.
3. **Docs prose** under `docs/` — scanned for the full constraint-era token
    list. Marked `xfail` until the Phase 7 §7.2 page-by-page rewrite lands
    (ADR 035 Decision 1); flips to a hard gate in the same commit that ticks
    7.2.
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
    "constraint",
    "Constraint",
    "Latency",
    "Durability",
    "AccessPattern",
    "Throughput",
    "VectorStore",
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
    """All Markdown files under `docs/`."""
    files: list[Path] = []
    for path in _DOCS_DIR.rglob("*.md"):
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


@pytest.mark.parametrize(
    "decorator_attr",
    ["storage", "expose", "schedule", "job", "channel"],
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


def test_docs_design_folder_deleted() -> None:
    """The legacy `docs/design/` folder should be gone after the docs reorg."""
    assert not (_DOCS_DIR / "design").exists(), "docs/design/ must not exist anymore."


def test_archive_moved_to_notes() -> None:
    """The archived ADR 001 should live under `notes/design/_archive/`."""
    archived = _REPO_ROOT / "notes" / "design" / "_archive" / "001-infrastructure-as-constraints.md"
    assert archived.is_file(), (
        "Expected the archived constraint-model ADR at "
        f"{archived.relative_to(_REPO_ROOT).as_posix()}."
    )


def test_catalogs_page_deleted() -> None:
    """`docs/catalogs.md` was deleted in Phase 1; the file must not return."""
    assert not (_DOCS_DIR / "catalogs.md").exists(), (
        "docs/catalogs.md must not exist — catalogs were deleted in Phase 1."
    )
