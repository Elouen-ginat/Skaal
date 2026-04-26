from __future__ import annotations

from skaal.backends._spec import BackendPlugin, Wiring
from skaal.backends.firestore_backend import FirestoreBackend
from skaal.deploy.kinds import StorageKind

plugin = BackendPlugin(
    name="firestore",
    kinds=frozenset({StorageKind.KV}),
    wiring=Wiring(
        class_name="FirestoreBackend",
        module="firestore_backend",
        impl=FirestoreBackend,
        env_prefix="SKAAL_COLLECTION",
    ),
    supported_targets=frozenset({"gcp"}),
    local_fallbacks={StorageKind.KV: "local-map"},
)
