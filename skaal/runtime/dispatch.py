"""Per-kind adapter dispatch for the local runtime.

The runtime walks `BoundPlan.resources` and looks up the matching
adapter by `BoundResource.inferred.kind`. Each adapter is a small,
duck-typed module exporting a `register(runtime, bound, target)`
callable; there is no abstract base.

The table is closed: a `BoundPlan` carrying a kind we have not yet
wired raises `RuntimeAdapterMissing` rather than failing silently.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from skaal.inference.model import ResourceKind
from skaal.runtime.adapters import (
    asgi as asgi_adapter,
)
from skaal.runtime.adapters import (
    blob as blob_adapter,
)
from skaal.runtime.adapters import (
    channel as channel_adapter,
)
from skaal.runtime.adapters import (
    function as function_adapter,
)
from skaal.runtime.adapters import (
    job as job_adapter,
)
from skaal.runtime.adapters import (
    relational as relational_adapter,
)
from skaal.runtime.adapters import (
    schedule as schedule_adapter,
)
from skaal.runtime.adapters import (
    secret as secret_adapter,
)
from skaal.runtime.adapters import (
    store as store_adapter,
)

if TYPE_CHECKING:
    from skaal.binding.model import PlannedResource
    from skaal.runtime.local import LocalRuntime


AdapterFn = Callable[["LocalRuntime", "PlannedResource", Any], None]


LOCAL_DISPATCH: dict[ResourceKind, AdapterFn] = {
    ResourceKind.STORE: store_adapter.register,
    ResourceKind.RELATIONAL: relational_adapter.register,
    ResourceKind.BLOB: blob_adapter.register,
    ResourceKind.CHANNEL: channel_adapter.register,
    ResourceKind.FUNCTION: function_adapter.register,
    ResourceKind.SCHEDULE: schedule_adapter.register,
    ResourceKind.JOB: job_adapter.register,
    ResourceKind.ASGI_SERVICE: asgi_adapter.register,
    ResourceKind.SECRET: secret_adapter.register,
}


def dispatch_for(kind: ResourceKind) -> AdapterFn:
    """Return the adapter registration callable for ``kind``.

    Raises:
        RuntimeAdapterMissing: if no adapter has been wired for the kind.
    """
    fn = LOCAL_DISPATCH.get(kind)
    if fn is None:
        from skaal.errors import RuntimeAdapterMissing

        raise RuntimeAdapterMissing(kind.value)
    return fn
