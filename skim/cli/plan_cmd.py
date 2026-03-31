"""`skim plan` — run constraint solver, generate plan.skim.lock."""

from __future__ import annotations

import typer

app = typer.Typer(help="Run the constraint solver and generate a plan.")


@app.callback(invoke_without_command=True)
def plan(
    reoptimize: bool = typer.Option(False, "--reoptimize", help="Force re-solving all backend choices."),
    pin: list[str] = typer.Option([], "--pin", help="Pin a variable to a backend, e.g. profiles=redis."),
) -> None:
    """
    Analyze the app's constraints via Z3 and write plan.skim.lock.

    Solver output includes: backend selections, instance types, placement rules,
    estimated cost, and UNSAT explanations if constraints cannot be met.
    """
    raise NotImplementedError("`skim plan` is not yet implemented (Phase 2).")
