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

from collections.abc import Mapping
from importlib import import_module
from threading import Lock
from typing import TYPE_CHECKING

from skaal.deploy._registry import register_target
from skaal.deploy.gcp._config import GcpConfig
from skaal.deploy.gcp._target import GcpTarget

if TYPE_CHECKING:
    from skaal.deploy._protocol import ConsoleUrlResolver, SynthFn
    from skaal.inference.model import ResourceKind

_SYNTH_PATHS: tuple[tuple[str, str], ...] = (
    ("skaal.deploy.gcp.bigquery", "BigQuerySynth"),
    ("skaal.deploy.gcp.cloud_run_fn", "CloudRunFunctionSynth"),
    ("skaal.deploy.gcp.cloud_scheduler", "CloudSchedulerSynth"),
    ("skaal.deploy.gcp.cloud_tasks", "CloudTasksWorkerSynth"),
    ("skaal.deploy.gcp.firestore", "FirestoreSynth"),
    ("skaal.deploy.gcp.gcs", "GcsSynth"),
    ("skaal.deploy.gcp.postgres", "CloudSqlPostgresSynth"),
    ("skaal.deploy.gcp.pubsub", "PubsubChannelSynth"),
    ("skaal.deploy.gcp.secrets", "SecretManagerSynth"),
)


class _LazyGcpTarget(GcpTarget):
    def __init__(self) -> None:
        super().__init__()
        self._builtins_loaded = False
        self._builtins_lock = Lock()

    def lookup_synth(self, backend_name: str) -> SynthFn | None:
        self._ensure_builtin_synths()
        return super().lookup_synth(backend_name)

    def supported_backends(self) -> frozenset[str]:
        self._ensure_builtin_synths()
        return super().supported_backends()

    def where_console_url_resolvers(self) -> Mapping[str, ConsoleUrlResolver]:
        self._ensure_builtin_synths()
        return super().where_console_url_resolvers()

    def where_resource_type_preferences(self) -> Mapping[ResourceKind, tuple[str, ...]]:
        self._ensure_builtin_synths()
        return super().where_resource_type_preferences()

    def _ensure_builtin_synths(self) -> None:
        if self._builtins_loaded:
            return

        with self._builtins_lock:
            if self._builtins_loaded:
                return
            for module_name, attr_name in _SYNTH_PATHS:
                module = import_module(module_name)
                synth_cls = getattr(module, attr_name)
                self.register_synth(synth_cls())
            self._builtins_loaded = True


TARGET = _LazyGcpTarget()
register_target(TARGET)


__all__ = ["TARGET", "GcpConfig", "GcpTarget"]
