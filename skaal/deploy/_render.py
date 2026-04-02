"""Template rendering utilities for skaal deploy generators."""

from __future__ import annotations

import string
from pathlib import Path

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def render(template: str, **variables: str) -> str:
    """
    Render a template file from ``skaal/deploy/templates/`` using
    :class:`string.Template` (``$var`` or ``${var}`` substitution).

    Args:
        template: Relative path inside the templates directory,
                  e.g. ``"gcp/main.py"`` or ``"aws/handler.py"``.
        **variables: Template substitution variables.

    Returns:
        The rendered file content as a string.

    Raises:
        KeyError: If a ``$variable`` in the template has no matching keyword arg.
        FileNotFoundError: If the template file does not exist.
    """
    path = _TEMPLATES_DIR / template
    tmpl = string.Template(path.read_text())
    return tmpl.substitute(variables)


class _CodeWriter:
    """
    Minimal indented-code builder for Pulumi stack generation.

    Avoids the "list of strings joined with newlines" anti-pattern by
    providing a small write API that maintains indentation state.
    """

    def __init__(self) -> None:
        self._lines: list[str] = []

    def line(self, text: str = "") -> "_CodeWriter":
        self._lines.append(text)
        return self

    def blank(self) -> "_CodeWriter":
        self._lines.append("")
        return self

    def block(self, text: str) -> "_CodeWriter":
        """Append a multi-line block, stripping leading/trailing blank lines."""
        for ln in text.strip("\n").splitlines():
            self._lines.append(ln)
        return self

    def render(self) -> str:
        return "\n".join(self._lines) + "\n"
