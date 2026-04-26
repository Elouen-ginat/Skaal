from __future__ import annotations

from skaal.backends._spec import BackendPlugin, Wiring
from skaal.backends.chroma_backend import ChromaVectorBackend
from skaal.deploy.kinds import StorageKind

plugin = BackendPlugin(
    name="chroma-local",
    kinds=frozenset({StorageKind.VECTOR}),
    wiring=Wiring(
        class_name="ChromaVectorBackend",
        module="chroma_backend",
        impl=ChromaVectorBackend,
        path_default="/app/data/chroma",
        uses_namespace=True,
        dependency_sets=("chroma-runtime",),
    ),
    supported_targets=frozenset({"local"}),
)
