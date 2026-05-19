"""GCP deploy target (ADR 042).

This package contributes one `DeployTarget` (`GcpTarget`) to the registry
at import time. Each synth module under this package exports a single
`SynthModule` subclass that declares its `SPEC: ClassVar[SynthSpec]` and
implements `synthesize(ctx)`. `GcpTarget.from_classes(_SYNTHS)` walks the
tuple, instantiates each class, and assembles the dispatch table.

**Adding a new GCP backend**: drop a new module with a `SynthModule`
subclass, then add the class to `_SYNTHS`. Cloud Run-shaped backends
should inherit from `CloudRunSynth` so they reuse the Artifact Registry
+ image + service-account + Cloud Run scaffold; storage backends inherit
directly from `SynthModule[GcpConfig]`.
"""

from __future__ import annotations

from skaal.deploy._registry import register_target
from skaal.deploy.gcp._config import GcpConfig
from skaal.deploy.gcp._target import GcpTarget


TARGET = GcpTarget()
register_target(TARGET)


__all__ = ["TARGET", "GcpConfig", "GcpTarget"]
