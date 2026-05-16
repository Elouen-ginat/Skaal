"""SQLModel integration helpers for Skaal relational storage.

This module exposes two entry points for declaring relational tables:

* The original form — subclass ``SQLModel`` directly with ``table=True`` and
  decorate with ``@app.storage(kind="relational")``.
* The typed form — subclass ``Relational[B]`` and decorate. The single
  generic parameter ``B`` is a `Backend` type-pin (ADR 028 §6.6, ADR 032
  §4.4) so ``class Sales(Relational[BigQuery], table=True)`` flows the
  ``bigquery`` pin into `ResourceOverrides.backend` without an env
  override. The class body *is* the row schema — there is no companion
  DTO model and no field duplication. ``SQLModelMetaclass`` swallows
  ``__orig_bases__`` on subclasses, so the pin is captured via
  ``__class_getitem__`` and inherited through the standard MRO.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, ClassVar, Generic, cast

from sqlmodel import SQLModel
from typing_extensions import TypeVar

from skaal.backends._base import Backend

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession


B = TypeVar("B", bound="Backend[Any]", default="Backend[Any]")

_RELATIONAL_BACKEND_ATTR = "__skaal_relational_backend__"


class Relational(SQLModel, Generic[B]):
    """Typed relational table primitive.

    Subclass ``Relational[B]`` to declare a relational table whose
    backend is pinned at declaration time:

        class Comments(Relational[Postgres], table=True):
            id: int | None = Field(default=None, primary_key=True)
            todo_id: str = Field(index=True)
            body: str

    The class body is the row schema; there is no separate DTO model.
    ``B`` is a `Backend` token (``Postgres``, ``Sqlite``, ``BigQuery``,
    …). Omitting the parameter leaves the binding to the defaults table:

        class Notes(Relational, table=True): ...

    `SQLModelMetaclass` overwrites ``__orig_bases__`` on subclasses, so
    `_extract_backend_pin` cannot read the pin off ``Comments`` directly.
    Instead, ``__class_getitem__`` stashes the captured backend token on
    the intermediate parametrised class as `__skaal_backend_pin__`;
    concrete subclasses inherit it via the normal MRO and
    `_extract_backend_pin` reads it from there.
    """

    __skaal_backend_pin__: ClassVar[type[Backend[Any]] | None] = None

    def __class_getitem__(cls, params: Any) -> Any:
        sub: Any = super().__class_getitem__(params)
        param_tuple: tuple[Any, ...] = (
            cast("tuple[Any, ...]", params) if isinstance(params, tuple) else (params,)
        )
        if param_tuple:
            backend_arg: Any = param_tuple[0]
            if (
                isinstance(backend_arg, type)
                and issubclass(backend_arg, Backend)
                and backend_arg is not Backend
            ):
                sub.__skaal_backend_pin__ = backend_arg
        return sub

    @classmethod
    async def native(cls) -> Any:
        """Return the native SDK client for the wired backend (ADR 028 §6.13).

        For type-pinned subclasses (``class Sales(Relational[BigQuery])``),
        Pylance resolves the concrete SDK type via the backend token's
        ``NativeClient`` declaration in Phase 5b; Phase 5a returns the
        backend object directly (or unwraps ``backend.native()`` when
        defined) so user-land code can run backend-specific SQL.

        Raises:
            NotImplementedError: If the relational model has not been
                wired by the runtime yet.
        """
        from skaal._native import resolve_native

        backend = get_backend(cls)
        return await resolve_native(backend)


def validate_relational_model(model_cls: object) -> None:
    """Raise if *model_cls* is not a concrete ``SQLModel`` table model."""
    if not isinstance(model_cls, type) or not issubclass(model_cls, SQLModel):
        raise TypeError('@app.storage(kind="relational") requires a SQLModel subclass.')
    if getattr(model_cls, "__table__", None) is None:
        raise TypeError(
            '@app.storage(kind="relational") requires a concrete SQLModel table (`table=True`).'
        )


def is_relational_model(obj: Any) -> bool:
    """Return ``True`` if *obj* is a relational model registered with Skaal."""
    from skaal.inference.model import InferredResource, ResourceKind

    if not isinstance(obj, type):
        return False
    inferred = getattr(obj, "__skaal_inferred__", None)
    return isinstance(inferred, InferredResource) and inferred.kind == ResourceKind.RELATIONAL


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
    setattr(model_cls, _RELATIONAL_BACKEND_ATTR, backend)


def get_backend(model_cls: type) -> Any:
    """Return the backend currently wired to *model_cls*."""
    validate_relational_model(model_cls)
    backend = getattr(model_cls, _RELATIONAL_BACKEND_ATTR, None)
    if backend is None:
        raise NotImplementedError(
            f"{model_cls.__name__} relational model not wired. Use LocalRuntime or deploy first."
        )
    return backend


async def ensure_schema(model_cls: type) -> None:
    """Create any missing tables for *model_cls* on its wired backend.

    First-run safety net only. For evolving schemas, see
    :func:`skaal.api.relational_upgrade` and ``skaal migrate relational``.
    """
    backend = get_backend(model_cls)
    await backend.ensure_relational_schema(model_cls)


@asynccontextmanager
async def open_session(model_cls: type) -> AsyncIterator[AsyncSession]:
    """Yield an ``AsyncSession`` bound to *model_cls*'s wired backend."""
    backend = get_backend(model_cls)
    await backend.ensure_relational_schema(model_cls)
    async with backend.open_relational_session(model_cls) as session:
        yield session
