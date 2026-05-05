from __future__ import annotations

from typing import cast

from skaal.plan import PatternSpec
from skaal.solver._pattern_solvers import (
    PATTERN_LOG,
    PatternSolveContext,
    register_pattern_solver,
    serialize_pattern_value,
    storage_constraints_from_pattern,
)
from skaal.solver.storage import UnsatisfiableConstraints, select_backend
from skaal.types.patterns import EventLogPatternConfig, EventLogPatternMetadata


@register_pattern_solver("event-log")
def solve_event_log(ctx: PatternSolveContext) -> PatternSpec:
    pattern_meta = cast(EventLogPatternMetadata, ctx.pattern_meta)
    pattern_constraints = storage_constraints_from_pattern(pattern_meta)
    try:
        backend_name, reason = select_backend(
            ctx.qname,
            pattern_constraints,
            ctx.storage_backends,
            target=ctx.target,
        )
    except UnsatisfiableConstraints as exc:
        PATTERN_LOG.warning(
            f"EventLog {ctx.qname!r} could not be solved: {exc}. "
            "No backing store will be provisioned."
        )
        backend_name, reason = "", str(exc)

    storage_meta = pattern_meta["storage"]
    config = EventLogPatternConfig(
        retention=storage_meta["retention"],
        partitions=storage_meta["partitions"],
        durability=serialize_pattern_value(storage_meta["durability"]),
    )
    return PatternSpec(
        pattern_name=ctx.qname,
        pattern_type="event-log",
        backend=backend_name or None,
        reason=reason,
        config=config,
    )
