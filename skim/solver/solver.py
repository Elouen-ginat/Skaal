"""Main solve() entry point — orchestrates storage and compute solvers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from skim.app import App
    from skim.plan import PlanFile


def solve(app: "App", catalog: dict[str, Any]) -> "PlanFile":
    """
    Run the Z3 constraint solver over all registered storage and compute
    declarations, producing a concrete infrastructure plan.

    Args:
        app:     The Skim App whose decorators define the constraints.
        catalog: Parsed TOML catalog entries (backends and their characteristics).

    Returns:
        A PlanFile with concrete backend and instance selections.

    Raises:
        UnsatisfiableConstraints: If no backend can satisfy the declared constraints.
    """
    raise NotImplementedError(
        "solve() is not yet implemented. "
        "Run `skim plan` once Phase 2 is complete."
    )


class UnsatisfiableConstraints(Exception):
    """Raised when the Z3 solver cannot satisfy the declared constraints."""

    def __init__(self, variable_name: str, unsat_core: Any) -> None:
        self.variable_name = variable_name
        self.unsat_core = unsat_core
        super().__init__(
            f"Cannot satisfy constraints for {variable_name!r}. "
            f"Conflicting constraints: {unsat_core}"
        )
