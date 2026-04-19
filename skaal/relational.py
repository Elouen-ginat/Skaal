"""SQLModel integration helpers for Skaal relational storage."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncIterator, cast
from weakref import WeakKeyDictionary

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession


_RELATIONAL_BACKENDS: WeakKeyDictionary[type, Any] = WeakKeyDictionary()


def _require_sqlmodel() -> type:
    try:
        from sqlmodel import SQLModel
    except ImportError as exc:  # pragma: no cover - exercised when optional dep missing
        raise ImportError(
            "Relational storage requires SQLModel. Install it with `pip install sqlmodel`."
        ) from exc
    return SQLModel


def validate_relational_model(model_cls: type) -> None:
    """Raise if *model_cls* is not a concrete ``SQLModel`` table model."""
    SQLModel = _require_sqlmodel()
    if not isinstance(model_cls, type) or not issubclass(model_cls, SQLModel):
        raise TypeError("@app.relational requires a SQLModel subclass.")
    if getattr(model_cls, "__table__", None) is None:
        raise TypeError("@app.relational requires a concrete SQLModel table (`table=True`).")


def is_relational_model(obj: Any) -> bool:
    """Return ``True`` if *obj* is a relational model registered with Skaal."""
    return (
        isinstance(obj, type)
        and hasattr(obj, "__skaal_storage__")
        and getattr(obj, "__skaal_storage__", {}).get("kind") == "relational"
    )


def _schema_hints(model_cls: type) -> dict[str, Any]:
    """Extract solver-visible schema hints from a relational SQLModel class."""
    validate_relational_model(model_cls)

    typed_model = cast(Any, model_cls)
    table = typed_model.__table__
    columns = list(table.columns)
    return {
        "model": typed_model.__name__,
        "table": table.name,
        "field_count": len(columns),
        "primary_key": [column.name for column in table.primary_key.columns],
        "index_count": len(table.indexes),
        "relationship_count": len(getattr(typed_model, "__sqlmodel_relationships__", {})),
    }


def wire_relational_model(model_cls: type, backend: Any) -> None:
    """Bind *backend* to a relational model class."""
    validate_relational_model(model_cls)
    _RELATIONAL_BACKENDS[model_cls] = backend


def get_backend(model_cls: type) -> Any:
    """Return the backend currently wired to *model_cls*."""
    validate_relational_model(model_cls)
    backend = _RELATIONAL_BACKENDS.get(model_cls)
    if backend is None:
        raise NotImplementedError(
            f"{model_cls.__name__} relational model not wired. Use LocalRuntime or deploy first."
        )
    return backend


async def ensure_schema(model_cls: type) -> None:
    """Create any missing tables for *model_cls* on its wired backend."""
    backend = get_backend(model_cls)
    await backend.ensure_relational_schema(model_cls)


@asynccontextmanager
async def open_session(model_cls: type) -> AsyncIterator["AsyncSession"]:
    """Yield an ``AsyncSession`` bound to *model_cls*'s wired backend."""
    backend = get_backend(model_cls)
    await backend.ensure_relational_schema(model_cls)
    async with backend.open_relational_session(model_cls) as session:
        yield session
