"""`skaal.deploy` — generate cloud artefacts from a `BoundPlan`.

The deploy layer is the Phase 4 rewire of `0.3.x`'s ``skaal.deploy`` against
the new `BoundPlan` pipeline (ADR 028 §6.2 / ADR 032). Public entry points:

- `build_artefacts(bound, env, app_spec)` — pure templating; renders the
  Jinja2 tree under `skaal/deploy/templates/<target>/` to
  ``./.skaal/build/<env>/`` and returns the directory it wrote to. No
  Pulumi import, no network access. The per-resource artefacts are a
  `Dockerfile`, `handler.py`, `bootstrap.py`, and a `pyproject.toml`
  consumed by `uv` inside the rendered Dockerfile.
- `pulumi_program_for(bound, app, env)` *(Phase 4 follow-up)* — returns a
  Pulumi-Automation-API callable that provisions the resources the
  `BoundPlan` describes; consumed by `skaal deploy`.

Build-time data structures are all pydantic models in
`skaal.deploy.models`: `SkaalTags`, `BuildContext`, `BuildManifest`,
`ManifestResourceEntry`, `BuildPyProject`. Re-exported here for
programmatic consumers.

The package layout deliberately mirrors the `BoundResource.backend` token
names: each AWS-targeted backend has a one-file synth module under
`skaal/deploy/aws/`. Phase 4 of ADR 028 ships AWS-first; the GCP tree
lands in a 0.4.x point release (ADR 032 §"Out of scope").
"""

from __future__ import annotations

from skaal.cli._load import AppSpec
from skaal.deploy.build import build_artefacts
from skaal.deploy.models import (
    BuildContext,
    BuildManifest,
    BuildPyProject,
    ManifestResourceEntry,
    SkaalTags,
)
from skaal.deploy.program import PulumiProgram, pulumi_program_for
from skaal.deploy.tags import tags_for

__all__ = [
    "AppSpec",
    "BuildContext",
    "BuildManifest",
    "BuildPyProject",
    "ManifestResourceEntry",
    "PulumiProgram",
    "SkaalTags",
    "build_artefacts",
    "pulumi_program_for",
    "tags_for",
]
