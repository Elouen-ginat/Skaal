"""Typed storage containers: Map[K, V] and Collection[T].

These are the recommended way to declare structured storage in Skaal.
They pair with any backend (LocalMap, Redis, SQLite, Postgres, DynamoDB)
and provide automatic Pydantic validation on write and deserialization on read.

Usage::

    from pydantic import BaseModel
    from skaal import App, Map, Collection

    class Address(BaseModel):
        street: str
        city: str

    class User(BaseModel):
        id: str
        name: str
        address: Address
        tags: list[str] = []

    app = App("users")

    # Explicit key-value: you provide the key
    @app.storage(read_latency="< 10ms", durability="persistent")
    class Users(Map[str, User]):
        pass

    # Model-centric: key is extracted from user.id automatically
    @app.storage(read_latency="< 10ms", durability="persistent")
    class UserStore(Collection[User]):
        pass

    # In a function:
    user = User(id="u1", name="Alice", address=Address(street="1 Main", city="NYC"))

    await Users.set("u1", user)           # stores serialized User
    alice = await Users.get("u1")         # returns User instance
    all_users = await Users.list()        # list[tuple[str, User]]

    await UserStore.add(user)             # key inferred from user.id
    await UserStore.all()                 # list[User]
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar, get_args, get_origin

K = TypeVar("K")
V = TypeVar("V")
T = TypeVar("T")


def _is_pydantic(t: Any) -> bool:
    try:
        from pydantic import BaseModel

        return isinstance(t, type) and issubclass(t, BaseModel)
    except ImportError:
        return False


def _primary_key_field(model: type) -> str:
    """Infer the primary key field name from a Pydantic model."""
    if not hasattr(model, "model_fields"):
        return "id"
    fields = list(model.model_fields.keys())
    for candidate in ("id", "pk", "key"):
        if candidate in fields:
            return candidate
    return fields[0] if fields else "id"


def _schema_hints(cls: type) -> dict[str, Any]:
    """
    Extract solver-visible hints from a Map or Collection subclass.

    These are stored in ``__skim_storage__["schema_hints"]`` and surfaced
    in ``skaal plan`` output.  They do not yet change backend selection —
    that is reserved for a future solver pass.
    """
    hints: dict[str, Any] = {}
    value_type = getattr(cls, "__skaal_value_type__", None)
    if not _is_pydantic(value_type) or value_type is None:
        return hints

    fields = value_type.model_fields
    nested_count = sum(1 for f in fields.values() if _is_pydantic(f.annotation))
    list_count = sum(
        1 for f in fields.values() if f.annotation is not None and get_origin(f.annotation) is list
    )
    hints["model"] = value_type.__name__
    hints["field_count"] = len(fields)
    hints["nested_models"] = nested_count
    hints["list_fields"] = list_count
    # Hint: deeply nested / wide schemas fit better in SQL/JSONB backends
    hints["prefers_sql"] = nested_count > 0 or len(fields) > 10
    return hints


class Map(Generic[K, V]):
    """
    Typed key-value storage.

    ``K`` is the key type (informational — all backends use string keys).
    ``V`` is the value type:

    - If ``V`` is a Pydantic ``BaseModel``:
      - ``set()`` accepts a ``V`` instance *or* a plain ``dict`` (coerced via
        ``V.model_validate()``).
      - ``get()`` returns a ``V`` instance (or ``None``).
      - ``list()`` / ``scan()`` return ``list[tuple[str, V]]``.

    - Otherwise, ``V`` is stored and returned as-is (any JSON-serialisable type).

    Subclass inside ``@app.storage()``::

        @app.storage(read_latency="< 5ms", durability="persistent")
        class Sessions(Map[str, SessionToken]):
            pass

    Methods below are **type stubs** for IDE autocomplete.  The runtime
    (:func:`~skaal.backends.local_backend.patch_storage_class`) replaces them
    with real implementations backed by the selected storage backend.
    """

    __skaal_key_type__: type = str
    __skaal_value_type__: type | None = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        for base in getattr(cls, "__orig_bases__", []):
            origin = get_origin(base)
            if origin is Map or (isinstance(origin, type) and issubclass(origin, Map)):
                args = get_args(base)
                if len(args) >= 1:
                    cls.__skaal_key_type__ = args[0]
                if len(args) >= 2:
                    cls.__skaal_value_type__ = args[1]
                break

    # ── Type stubs (replaced at runtime by patch_storage_class) ───────────

    @staticmethod
    async def get(key: str) -> Any | None:
        """Return the value for *key*, or ``None`` if not found."""
        raise NotImplementedError("Storage not wired. Use LocalRuntime or deploy first.")

    @staticmethod
    async def set(key: str, value: Any) -> None:
        """Store *value* under *key*."""
        raise NotImplementedError("Storage not wired. Use LocalRuntime or deploy first.")

    @staticmethod
    async def delete(key: str) -> None:
        """Remove *key* (no-op if not present)."""
        raise NotImplementedError("Storage not wired. Use LocalRuntime or deploy first.")

    @staticmethod
    async def list() -> list[tuple[str, Any]]:
        """Return all ``(key, value)`` pairs."""
        raise NotImplementedError("Storage not wired. Use LocalRuntime or deploy first.")

    @staticmethod
    async def scan(prefix: str = "") -> list[tuple[str, Any]]:
        """Return all ``(key, value)`` pairs where key starts with *prefix*."""
        raise NotImplementedError("Storage not wired. Use LocalRuntime or deploy first.")

    @staticmethod
    async def close() -> None:
        """Release any resources held by the backend."""
        raise NotImplementedError("Storage not wired. Use LocalRuntime or deploy first.")

    @staticmethod
    def sync_get(key: str) -> Any | None:
        """Synchronous wrapper for :meth:`get`. Safe in Dash / Flask callbacks."""
        raise NotImplementedError("Storage not wired. Use LocalRuntime or deploy first.")

    @staticmethod
    def sync_set(key: str, value: Any) -> None:
        """Synchronous wrapper for :meth:`set`."""
        raise NotImplementedError("Storage not wired. Use LocalRuntime or deploy first.")

    @staticmethod
    def sync_delete(key: str) -> None:
        """Synchronous wrapper for :meth:`delete`."""
        raise NotImplementedError("Storage not wired. Use LocalRuntime or deploy first.")

    @staticmethod
    def sync_list() -> list[tuple[str, Any]]:
        """Synchronous wrapper for :meth:`list`."""
        raise NotImplementedError("Storage not wired. Use LocalRuntime or deploy first.")

    @staticmethod
    def sync_scan(prefix: str = "") -> list[tuple[str, Any]]:
        """Synchronous wrapper for :meth:`scan`."""
        raise NotImplementedError("Storage not wired. Use LocalRuntime or deploy first.")


class Collection(Generic[T]):
    """
    Typed collection of Pydantic models with auto-extracted primary keys.

    The primary key field is resolved in this order:

    1. ``cls.__skaal_key_field__`` if explicitly set on the subclass.
    2. A field named ``"id"``, ``"pk"``, or ``"key"`` in ``T.model_fields``.
    3. The first field in ``T.model_fields``.

    In addition to the standard ``get / set / delete / list / scan`` methods
    (shared with ``Map``), ``Collection`` adds:

    - ``add(item)``      — store using the auto-extracted key.
    - ``remove(key)``    — alias for ``delete``.
    - ``update(key, item)`` — replace the value at ``key``.
    - ``all()``          — return all items as ``list[T]``.
    - ``find(prefix)``   — scan by key prefix, return ``list[T]``.

    Usage::

        @app.storage(durability="persistent")
        class Products(Collection[Product]):
            pass

        await Products.add(Product(id="p1", name="Widget"))
        widget = await Products.get("p1")     # Product instance
        all_products = await Products.all()   # list[Product]
    """

    __skaal_value_type__: type | None = None
    __skaal_key_field__: str = "id"

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        for base in getattr(cls, "__orig_bases__", []):
            origin = get_origin(base)
            if origin is Collection or (
                isinstance(origin, type) and issubclass(origin, Collection)
            ):
                args = get_args(base)
                if args:
                    cls.__skaal_value_type__ = args[0]
                    # Only infer key field if the subclass hasn't overridden it
                    if not cls.__dict__.get("__skaal_key_field__"):
                        cls.__skaal_key_field__ = _primary_key_field(args[0])
                break

    # ── Type stubs (replaced at runtime by patch_storage_class) ───────────
    # Collection inherits get/set/delete/list/scan/close from Map via
    # patch_storage_class.  The additional methods below are Collection-only.

    @staticmethod
    async def get(key: str) -> Any | None:
        """Return the item for *key*, or ``None``."""
        raise NotImplementedError("Storage not wired. Use LocalRuntime or deploy first.")

    @staticmethod
    async def set(key: str, value: Any) -> None:
        """Store *value* under *key*."""
        raise NotImplementedError("Storage not wired. Use LocalRuntime or deploy first.")

    @staticmethod
    async def delete(key: str) -> None:
        """Remove *key*."""
        raise NotImplementedError("Storage not wired. Use LocalRuntime or deploy first.")

    @staticmethod
    async def list() -> list[tuple[str, Any]]:
        """Return all ``(key, value)`` pairs."""
        raise NotImplementedError("Storage not wired. Use LocalRuntime or deploy first.")

    @staticmethod
    async def scan(prefix: str = "") -> list[tuple[str, Any]]:
        """Return all ``(key, value)`` pairs matching *prefix*."""
        raise NotImplementedError("Storage not wired. Use LocalRuntime or deploy first.")

    @staticmethod
    async def close() -> None:
        """Release backend resources."""
        raise NotImplementedError("Storage not wired. Use LocalRuntime or deploy first.")

    @staticmethod
    async def add(item: Any) -> None:
        """Store *item* using its auto-extracted primary key."""
        raise NotImplementedError("Storage not wired. Use LocalRuntime or deploy first.")

    @staticmethod
    async def remove(key: str) -> None:
        """Remove the item with *key*. Alias for ``delete``."""
        raise NotImplementedError("Storage not wired. Use LocalRuntime or deploy first.")

    @staticmethod
    async def update(key: str, item: Any) -> None:
        """Replace the value at *key* with *item*."""
        raise NotImplementedError("Storage not wired. Use LocalRuntime or deploy first.")

    @staticmethod
    async def all() -> list[Any]:
        """Return all items as a flat list."""
        raise NotImplementedError("Storage not wired. Use LocalRuntime or deploy first.")

    @staticmethod
    async def find(prefix: str = "") -> list[Any]:
        """Return items whose key starts with *prefix*."""
        raise NotImplementedError("Storage not wired. Use LocalRuntime or deploy first.")

    @staticmethod
    def sync_get(key: str) -> Any | None:
        """Synchronous wrapper for :meth:`get`."""
        raise NotImplementedError("Storage not wired. Use LocalRuntime or deploy first.")

    @staticmethod
    def sync_set(key: str, value: Any) -> None:
        """Synchronous wrapper for :meth:`set`."""
        raise NotImplementedError("Storage not wired. Use LocalRuntime or deploy first.")

    @staticmethod
    def sync_delete(key: str) -> None:
        """Synchronous wrapper for :meth:`delete`."""
        raise NotImplementedError("Storage not wired. Use LocalRuntime or deploy first.")

    @staticmethod
    def sync_list() -> list[tuple[str, Any]]:
        """Synchronous wrapper for :meth:`list`."""
        raise NotImplementedError("Storage not wired. Use LocalRuntime or deploy first.")

    @staticmethod
    def sync_scan(prefix: str = "") -> list[tuple[str, Any]]:
        """Synchronous wrapper for :meth:`scan`."""
        raise NotImplementedError("Storage not wired. Use LocalRuntime or deploy first.")

    @staticmethod
    def sync_add(item: Any) -> None:
        """Synchronous wrapper for :meth:`add`."""
        raise NotImplementedError("Storage not wired. Use LocalRuntime or deploy first.")

    @staticmethod
    def sync_all() -> list[Any]:
        """Synchronous wrapper for :meth:`all`."""
        raise NotImplementedError("Storage not wired. Use LocalRuntime or deploy first.")

    @staticmethod
    def sync_find(prefix: str = "") -> list[Any]:
        """Synchronous wrapper for :meth:`find`."""
        raise NotImplementedError("Storage not wired. Use LocalRuntime or deploy first.")
