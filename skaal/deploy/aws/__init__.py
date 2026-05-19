"""AWS deploy target.

This package contributes one `DeployTarget` (`AwsTarget`) to the registry
at import time. Each synth module under this package exports a single
`SynthModule` subclass that declares its `SPEC: ClassVar[SynthSpec]` and
implements `synthesize(ctx)`. `AwsTarget.from_classes(_SYNTHS)` walks the
tuple, instantiates each class, and assembles the dispatch table.

**Adding a new AWS backend**: drop a new module with a `SynthModule`
subclass, then add the class to `_SYNTHS`. Lambda-shaped backends should
inherit from `LambdaSynth` so they reuse the ECR + image + IAM + log
group + function scaffold; storage backends inherit directly from
`SynthModule[AwsConfig]`.

No backend-name → function dict literal is edited; no IAM-policy table
is edited (override `AwsConfig.iam.policies` via `skaal.toml`); no
config-defaults are edited (override `AwsConfig.<section>` via TOML).
"""

from __future__ import annotations

from collections.abc import Mapping
from importlib import import_module
from threading import Lock
from typing import TYPE_CHECKING

from skaal.deploy._registry import register_target
from skaal.deploy.aws._config import AwsConfig
from skaal.deploy.aws._target import AwsTarget

if TYPE_CHECKING:
    from skaal.deploy._protocol import ConsoleUrlResolver, SynthFn
    from skaal.inference.model import ResourceKind

_SYNTH_PATHS: tuple[tuple[str, str], ...] = (
    ("skaal.deploy.aws.apigw_lambda", "ApigwLambdaSynth"),
    ("skaal.deploy.aws.dynamodb", "DynamoDBSynth"),
    ("skaal.deploy.aws.eventbridge", "EventBridgeLambdaSynth"),
    ("skaal.deploy.aws.lambda_fn", "PlainLambdaSynth"),
    ("skaal.deploy.aws.postgres", "PostgresSynth"),
    ("skaal.deploy.aws.redis", "RedisSynth"),
    ("skaal.deploy.aws.s3", "S3Synth"),
    ("skaal.deploy.aws.secrets", "SecretsManagerSynth"),
    ("skaal.deploy.aws.sqs", "SqsChannelSynth"),
    ("skaal.deploy.aws.sqs_worker", "SqsWorkerSynth"),
)


class _LazyAwsTarget(AwsTarget):
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


TARGET = _LazyAwsTarget()
register_target(TARGET)


__all__ = ["TARGET", "AwsConfig", "AwsTarget"]
