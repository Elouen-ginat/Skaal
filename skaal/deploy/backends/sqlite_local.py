from __future__ import annotations

from skaal.backends._spec import BackendPlugin, Wiring
from skaal.backends.sqlite_backend import SqliteBackend
from skaal.deploy.kinds import StorageKind

plugin = BackendPlugin(
    name="sqlite",
    kinds=frozenset({StorageKind.KV, StorageKind.RELATIONAL}),
    wiring=Wiring(
        class_name="SqliteBackend",
        module="sqlite_backend",
        impl=SqliteBackend,
        env_prefix="SKAAL_SQLITE_PATH",
        local_env_value="/app/data/skaal.db",
        dependency_sets=("sqlite-driver",),
    ),
    supported_targets=frozenset({"local"}),
)
