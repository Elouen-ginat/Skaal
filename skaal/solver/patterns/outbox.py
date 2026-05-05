from __future__ import annotations

from typing import cast

from skaal.plan import PatternSpec
from skaal.solver._pattern_solvers import (
    PatternSolveContext,
    register_pattern_solver,
    resolve_resource_qname,
)
from skaal.types.patterns import OutboxPatternConfig, OutboxPatternMetadata


@register_pattern_solver("outbox")
def solve_outbox(ctx: PatternSolveContext) -> PatternSpec:
    pattern_meta = cast(OutboxPatternMetadata, ctx.pattern_meta)
    channel_obj = pattern_meta["channel"]
    storage_obj = pattern_meta["storage"]
    channel_qname = resolve_resource_qname(channel_obj, ctx.all_resources)
    storage_qname = resolve_resource_qname(storage_obj, ctx.all_resources)

    outbox_backend: str | None = None
    if storage_qname and storage_qname in ctx.storage_specs:
        outbox_backend = ctx.storage_specs[storage_qname].backend

    config = OutboxPatternConfig(
        channel=channel_qname,
        storage=storage_qname,
        delivery=pattern_meta["delivery"],
    )

    return PatternSpec(
        pattern_name=ctx.qname,
        pattern_type="outbox",
        backend=outbox_backend,
        reason=(
            f"outbox: writes to {storage_qname!r}, forwards to {channel_qname!r}, "
            f"delivery={pattern_meta['delivery']!r}"
        ),
        config=config,
    )
