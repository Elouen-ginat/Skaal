from __future__ import annotations

from skaal.backends._spec import BackendPlugin, Wiring
from skaal.backends.redis_backend import RedisBackend
from skaal.deploy.kinds import StorageKind

plugin = BackendPlugin(
    name="local-redis",
    kinds=frozenset({StorageKind.KV}),
    wiring=Wiring(
        class_name="RedisBackend",
        module="redis_backend",
        impl=RedisBackend,
        env_prefix="SKAAL_REDIS_URL",
        uses_namespace=True,
        local_service="redis",
        local_env_value="redis://redis:6379",
        dependency_sets=("redis-runtime",),
    ),
    supported_targets=frozenset({"local"}),
)
