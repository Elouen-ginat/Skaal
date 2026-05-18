"""Typed wrappers around Typer parameter factories for Pyright."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import typer

if TYPE_CHECKING:

    def Argument(*args: Any, **kwargs: Any) -> Any: ...

    def Option(*args: Any, **kwargs: Any) -> Any: ...
else:
    Argument = typer.Argument
    Option = typer.Option

__all__ = ["Argument", "Option"]
