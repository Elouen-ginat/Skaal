from __future__ import annotations

from skaal.backends._spec import BackendPlugin, Wiring
from skaal.backends.dynamodb_backend import DynamoBackend
from skaal.deploy.kinds import StorageKind

plugin = BackendPlugin(
    name="dynamodb",
    kinds=frozenset({StorageKind.KV}),
    wiring=Wiring(
        class_name="DynamoBackend",
        module="dynamodb_backend",
        impl=DynamoBackend,
        env_prefix="SKAAL_TABLE",
    ),
    supported_targets=frozenset({"aws"}),
    local_fallbacks={StorageKind.KV: "local-map"},
)
