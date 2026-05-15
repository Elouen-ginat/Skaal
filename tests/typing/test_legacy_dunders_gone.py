"""Grep gate enforcing the Phase 4 §4.9 legacy-dunder deletion (ADR 032).

After Phase 4 the only contract decorated objects expose is
``__skaal_inferred__``; the per-decorator attributes
(`__skaal_storage__`, `__skaal_function__`, `__skaal_schedule__`,
`__skaal_channel__`, `__skaal_job__`, `__skaal_secrets__`) must not appear
in production source.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKAAL_PKG = _REPO_ROOT / "skaal"
_BANNED = (
    "__skaal_storage__",
    "__skaal_function__",
    "__skaal_schedule__",
    "__skaal_channel__",
    "__skaal_job__",
    "__skaal_secrets__",
)


@pytest.mark.parametrize("token", _BANNED)
def test_banned_token_not_in_skaal_package(token: str) -> None:
    """Fail loudly if a legacy per-decorator dunder is reintroduced."""
    hits: list[str] = []
    for path in _SKAAL_PKG.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if token in text:
            hits.append(str(path.relative_to(_REPO_ROOT)))
    assert not hits, (
        f"Legacy dunder {token!r} reintroduced in: {', '.join(hits)}. "
        "Use `__skaal_inferred__` instead (ADR 032 §4.9)."
    )
