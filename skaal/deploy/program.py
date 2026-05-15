"""`pulumi_program_for(bound, env, build_dir)` — the deploy-side entry point.

The Pulumi Automation API expects a parameterless callable that runs
inside its stack context. `pulumi_program_for` returns that callable as a
closure capturing `bound`, `env`, and the `build_dir` produced by
`build_artefacts(...)`. The closure walks `bound.resources` and delegates
to per-backend synth modules under `skaal.deploy.<target>`.

The `pulumi` / `pulumi_aws` / `pulumi_docker` imports are deferred until
the closure is *invoked*. Building the closure itself works without the
optional extras installed — only the actual `pulumi up` (which calls the
closure) requires them. This keeps `skaal.deploy.program` importable
from the CLI without forcing pulumi as a hard dependency.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from skaal.binding.model import BoundPlan, Environment, Target
from skaal.errors import MissingExtraError, SkaalDeployError

PulumiProgram = Callable[[], None]


def pulumi_program_for(
    bound: BoundPlan, env: Environment, build_dir: Path
) -> PulumiProgram:
    """Return a parameterless Pulumi program callable for `bound`.

    The returned callable is what `pulumi.automation.create_stack(...)`
    accepts as its ``program=`` argument. It captures the three inputs by
    reference and dispatches to the target-specific synth driver under
    `skaal.deploy.<target>`.

    Args:
        bound: The bound plan whose resources will be provisioned.
        env: The active environment. ``env.target`` picks the synth tree.
        build_dir: The directory `build_artefacts(...)` wrote to. Each
            compute synth uses ``build_dir / <resource_slug>`` as its
            Docker build context.

    Returns:
        A callable Pulumi can invoke inside its stack context.

    Raises:
        SkaalDeployError: If ``env.target`` is not supported (Phase 4
            ships AWS only).
    """
    if env.target is not Target.AWS:
        raise SkaalDeployError(
            f"Pulumi synth is only wired for target {Target.AWS.value!r} in "
            f"0.4.0-alpha; env {env.name!r} targets {env.target.value!r}. "
            "GCP support lands in a 0.4.x point release per ADR 032."
        )

    def program() -> None:
        _require_pulumi_extras()
        from skaal.deploy.aws import synthesize_stack

        synthesize_stack(bound, env, build_dir)

    return program


def _require_pulumi_extras() -> None:
    """Check that the deploy + aws optional extras are importable.

    Raised inside the program closure (not at `pulumi_program_for` call
    time) so unit tests that only build the closure do not need the
    Pulumi SDK installed — only the actual ``pulumi up`` run does.
    """
    missing: list[str] = []
    for module in ("pulumi", "pulumi_aws", "pulumi_docker"):
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    if missing:
        raise MissingExtraError(
            "`skaal deploy` requires the Pulumi SDKs. Install them with "
            "`pip install 'skaal[deploy,aws]'` "
            f"(missing modules: {', '.join(missing)})."
        )


__all__ = ["PulumiProgram", "pulumi_program_for"]
