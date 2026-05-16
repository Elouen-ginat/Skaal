"""Grep gate against declaration-site string backends (ADR 028 §6.13.3).

ADR 028 §6.13 commits to *class-token* declarations everywhere a backend
is selected in code:

    class Cache(Store[Session, Redis]): ...   # OK — class token
    class Cache(Store[Session], backend="redis"): ...  # NOT OK — string

The string form survives in two legitimate places:

1. `skaal.toml` env overrides (Phase 3) — the user-facing config surface.
2. The pydantic `ResourceOverrides.backend: str | None` field — the
   internal carry from class-token → registry → bound plan.

This gate scans Python source for declaration-site string backends and
fails if any are found outside `skaal/binding/` (the registry / lookup
layer) or `skaal/inference/` (the override carrier model). Tests, the
deploy layer's config models, and the runtime adapters are all
in-scope: a regression there would put a string backend back at a
user-visible declaration site.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKAAL_PKG = _REPO_ROOT / "skaal"
_EXAMPLES = _REPO_ROOT / "examples"

# Match ``backend = "..."`` and ``backend="..."``; the runtime configuration
# carrier lives on `ResourceOverrides.backend` and the binding registry's
# string-keyed envinronment overrides, both of which are exempt.
_PATTERN = re.compile(r"\bbackend\s*=\s*[\"\'][^\"\']+[\"\']")

_EXEMPT_PREFIXES = (
    _SKAAL_PKG / "binding",
    _SKAAL_PKG / "inference",
    _SKAAL_PKG / "stubs",  # emitter manifest payload
    _SKAAL_PKG / "backends" / "__init__.py",
)


def _is_exempt(path: Path) -> bool:
    return any(str(path).startswith(str(prefix)) for prefix in _EXEMPT_PREFIXES)


def _candidate_files() -> list[Path]:
    files: list[Path] = []
    for root in (_SKAAL_PKG, _EXAMPLES):
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            if _is_exempt(path):
                continue
            files.append(path)
    return files


@pytest.mark.parametrize("path", _candidate_files(), ids=lambda p: str(p.relative_to(_REPO_ROOT)))
def test_no_string_backend_declaration(path: Path) -> None:
    """A source file outside the binding/inference layers must not pin a
    backend via a string. Use the class-token form (`Store[T, Redis]`)
    instead.
    """
    text = path.read_text(encoding="utf-8")
    matches: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if _PATTERN.search(line):
            matches.append(f"{path.relative_to(_REPO_ROOT)}:{lineno}: {line.strip()}")
    assert not matches, (
        "Declaration-site string backend(s) found:\n"
        + "\n".join(matches)
        + "\nUse a typed `Backend` token instead (e.g. `Store[T, Redis]`)."
    )
