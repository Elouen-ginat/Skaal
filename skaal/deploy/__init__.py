"""`skaal.deploy` — generate cloud artefacts from a `BoundPlan`.

The deploy layer is the Phase 4 rewire of `0.3.x`'s ``skaal.deploy`` against
the new `BoundPlan` pipeline (ADR 028 §6.2 / ADR 032). Two entry points
are exposed:

- `build_artefacts(bound, app, env)` — pure templating; renders the
  Jinja2 tree under `skaal/deploy/templates/<target>/` to
  ``./.skaal/build/<env>/`` and returns the directory it wrote to. No
  Pulumi import, no network access.
- `pulumi_program_for(bound, app, env)` *(Phase 4 follow-up)* — returns a
  Pulumi-Automation-API callable that provisions the resources the
  `BoundPlan` describes; consumed by `skaal deploy`.

The package layout deliberately mirrors the `BoundResource.backend` token
names: each AWS-targeted backend has a one-file synth module under
`skaal/deploy/aws/`. Phase 4 of ADR 028 ships AWS-first; the GCP tree
lands in a 0.4.x point release (ADR 032 §"Out of scope").
"""

from __future__ import annotations

from skaal.cli._load import AppSpec
from skaal.deploy.build import build_artefacts
from skaal.deploy.tags import tags_for

__all__ = [
    "AppSpec",
    "build_artefacts",
    "tags_for",
]
