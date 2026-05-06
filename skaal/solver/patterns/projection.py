from __future__ import annotations

from typing import cast

from skaal.plan import PatternSpec
from skaal.solver._pattern_solvers import (
    PATTERN_LOG,
    PatternSolveContext,
    register_pattern_solver,
    resolve_resource_qname,
    serialize_pattern_value,
)
from skaal.types.patterns import ProjectionPatternConfig, ProjectionPatternMetadata


@register_pattern_solver("projection")
def solve_projection(ctx: PatternSolveContext) -> PatternSpec:
    pattern_meta = cast(ProjectionPatternMetadata, ctx.pattern_meta)
    source = pattern_meta["source"]
    target_obj = pattern_meta["target"]
    handler = pattern_meta["handler"]
    dead_letter_obj = pattern_meta["dead_letter"]

    source_qname = resolve_resource_qname(source, ctx.all_resources)
    target_qname = resolve_resource_qname(target_obj, ctx.all_resources)
    dead_letter_qname = (
        resolve_resource_qname(dead_letter_obj, ctx.all_resources)
        if dead_letter_obj is not None
        else None
    )

    if handler not in ctx.registered_functions:
        PATTERN_LOG.warning(
            f"Projection {ctx.qname!r} references unknown handler {handler!r}. "
            "Make sure it is registered via @app.function."
        )

    if target_qname and source_qname and target_qname in ctx.storage_specs:
        existing = ctx.storage_specs[target_qname]
        ctx.storage_specs[target_qname] = existing.model_copy(
            update={"collocate_with": source_qname}
        )

    config = ProjectionPatternConfig(
        source=source_qname,
        target=target_qname,
        handler=handler,
        dead_letter=dead_letter_qname,
        consistency=serialize_pattern_value(pattern_meta["consistency"]),
        checkpoint_every=pattern_meta["checkpoint_every"],
        strict=pattern_meta["strict"],
    )
    return PatternSpec(
        pattern_name=ctx.qname,
        pattern_type="projection",
        backend=None,
        reason=(
            f"projection {ctx.qname!r}: {source_qname!r} → {target_qname!r} via handler={handler!r}"
        ),
        config=config,
    )
