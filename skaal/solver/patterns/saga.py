from __future__ import annotations

from typing import cast

from skaal.plan import PatternSpec
from skaal.solver._pattern_solvers import PATTERN_LOG, PatternSolveContext, register_pattern_solver
from skaal.types.patterns import SagaPatternConfig, SagaPatternMetadata


@register_pattern_solver("saga")
def solve_saga(ctx: PatternSolveContext) -> PatternSpec:
    pattern_meta = cast(SagaPatternMetadata, ctx.pattern_meta)
    steps = pattern_meta["steps"]
    missing: list[str] = []
    for step in steps:
        fn_name = step["function"]
        comp_name = step["compensate"]
        if fn_name not in ctx.registered_functions:
            missing.append(f"function={fn_name!r}")
        if comp_name not in ctx.registered_functions:
            missing.append(f"compensate={comp_name!r}")
    if missing:
        PATTERN_LOG.warning(
            f"Saga {ctx.qname!r} references unregistered names: {', '.join(missing)}. "
            "Register them via @app.function before deploying."
        )

    config = SagaPatternConfig(
        name=pattern_meta["name"],
        steps=steps,
        coordination=pattern_meta["coordination"],
        timeout_ms=pattern_meta["timeout_ms"],
        missing_references=missing,
    )

    return PatternSpec(
        pattern_name=ctx.qname,
        pattern_type="saga",
        backend=None,
        reason=(
            f"saga {pattern_meta['name']!r}: {len(steps)} step(s), "
            f"coordination={pattern_meta['coordination']!r}"
        ),
        config=config,
    )
