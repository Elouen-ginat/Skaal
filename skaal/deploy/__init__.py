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

from importlib import import_module
from typing import TYPE_CHECKING, Any

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

if TYPE_CHECKING:
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
    from skaal.plugins import Plugin, PluginRegistry, load_plugins

__all__ = [
    "AppSpec",
    "BaseDeployTarget",
    "BuildContext",
    "BuildManifest",
    "BuildPyProject",
    "ConsoleUrlResolver",
    "DeployTarget",
    "ManifestResourceEntry",
    "Plugin",
    "PluginRegistry",
    "PulumiProgram",
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


_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "BuildContext": ("skaal.deploy.models", "BuildContext"),
    "BuildManifest": ("skaal.deploy.models", "BuildManifest"),
    "BuildPyProject": ("skaal.deploy.models", "BuildPyProject"),
    "ManifestResourceEntry": ("skaal.deploy.models", "ManifestResourceEntry"),
    "Plugin": ("skaal.plugins", "Plugin"),
    "PluginRegistry": ("skaal.plugins", "PluginRegistry"),
    "PulumiProgram": ("skaal.deploy.program", "PulumiProgram"),
    "SkaalTags": ("skaal.deploy.models", "SkaalTags"),
    "build_artefacts": ("skaal.deploy.build", "build_artefacts"),
    "load_plugins": ("skaal.plugins", "load_plugins"),
    "pulumi_program_for": ("skaal.deploy.program", "pulumi_program_for"),
    "synthesize_stack": ("skaal.deploy.program", "synthesize_stack"),
    "tags_for": ("skaal.deploy.tags", "tags_for"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr_name = target
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
