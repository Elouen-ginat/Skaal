from __future__ import annotations

from skaal.backends._spec import BackendPlugin, Wiring
from skaal.backends.local_backend import LocalMap
from skaal.deploy.kinds import StorageKind

plugin = BackendPlugin(
    name="local-map",
    kinds=frozenset({StorageKind.KV}),
    wiring=Wiring(
        class_name="LocalMap",
        module="local_backend",
        impl=LocalMap,
    ),
    supported_targets=frozenset({"local"}),
)
