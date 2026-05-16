"""`skaal.deploy` — generate cloud artefacts from a `BoundPlan`.

Public entry points:

- `build_artefacts(bound, env, app_spec)` — pure templating; renders the
  Jinja2 tree under `skaal/deploy/templates/<target>/` to
  ``./.skaal/build/<env>/`` and returns the directory it wrote to. No
  Pulumi import, no network access.
- `pulumi_program_for(bound, env, build_dir)` — returns a typed
  `PulumiProgram` callable for the Pulumi Automation API. Defers all
  cloud-SDK imports until the closure is invoked.
- `synthesize_stack(bound, env, build_dir)` — programmatic entry point
  for the same dispatch logic without the Pulumi Automation wrapper
  (used by tests with `pulumi.runtime.set_mocks`).
- `register_target(...)` / `get_target(...)` / `registered_targets()` —
  the target registry. Each `skaal.deploy.<target>` package registers
  itself at import time; adding a new target (GCP, Azure, …) is a matter
  of dropping a new package and registering its `DeployTarget`.

The deploy layer never reaches into a target package directly. It
dispatches through the `DeployTarget` protocol — synth dispatch, stack
naming, config loading, and required-extras checks all flow through the
target instance returned by `get_target(env.target)`.
"""

from __future__ import annotations

from skaal.cli._load import AppSpec
from skaal.deploy._base_target import BaseDeployTarget
from skaal.deploy._protocol import (
    ConsoleUrlResolver,
    DeployTarget,
    SynthContext,
    SynthFn,
    SynthModule,
    SynthResult,
    SynthSpec,
    TargetConfig,
    WherePreference,
    WhereSpec,
)
from skaal.deploy._registry import (
    get_target,
    register_target,
    registered_targets,
)
from skaal.deploy.build import build_artefacts
from skaal.deploy.models import (
    BuildContext,
    BuildManifest,
    BuildPyProject,
    ManifestResourceEntry,
    SkaalTags,
)
from skaal.deploy.program import (
    PulumiProgram,
    pulumi_program_for,
    synthesize_stack,
)
from skaal.deploy.tags import tags_for
from skaal.plugins import PluginRegistry, SkaalPlugin, load_plugins

__all__ = [
    "AppSpec",
    "BaseDeployTarget",
    "BuildContext",
    "BuildManifest",
    "BuildPyProject",
    "ConsoleUrlResolver",
    "DeployTarget",
    "ManifestResourceEntry",
    "PluginRegistry",
    "PulumiProgram",
    "SkaalPlugin",
    "SkaalTags",
    "SynthContext",
    "SynthFn",
    "SynthModule",
    "SynthResult",
    "SynthSpec",
    "TargetConfig",
    "WherePreference",
    "WhereSpec",
    "build_artefacts",
    "get_target",
    "load_plugins",
    "pulumi_program_for",
    "register_target",
    "registered_targets",
    "synthesize_stack",
    "tags_for",
]
