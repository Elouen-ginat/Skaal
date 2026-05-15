"""Tests for the typed ``Relational[T, B]`` primitive (ADR 028 §6.5, ADR 032 §4.4).

`Relational` shares the second-generic backend-pin contract with `Store`,
`BlobStore`, and `Channel`, but rides through `SQLModelMetaclass`, which
strips ``__orig_bases__`` from subclasses. The capture path is therefore
`__class_getitem__` → `__skaal_backend_pin__` (inherited via MRO) rather
than `__orig_bases__`. These tests pin that contract independently of
the `@app.storage(kind="relational")` decorator surface.
"""

from __future__ import annotations

from typing import get_args

from pydantic import BaseModel
from sqlmodel import Field, SQLModel

from skaal import Relational
from skaal.backends._base import Backend
from skaal.backends._tokens import Postgres, Sqlite


class _Row(BaseModel):
    id: int
    body: str


def test_relational_subclass_is_sqlmodel() -> None:
    class CommentsTblA(Relational[_Row, Postgres], table=True):
        id: int | None = Field(default=None, primary_key=True)
        body: str

    assert issubclass(CommentsTblA, SQLModel)
    assert CommentsTblA.__table__ is not None


def test_relational_captures_value_type() -> None:
    class CommentsTblB(Relational[_Row, Postgres], table=True):
        id: int | None = Field(default=None, primary_key=True)
        body: str

    assert CommentsTblB.__skaal_value_type__ is _Row


def test_relational_captures_backend_pin() -> None:
    class CommentsTblC(Relational[_Row, Postgres], table=True):
        id: int | None = Field(default=None, primary_key=True)
        body: str

    assert CommentsTblC.__skaal_backend_pin__ is Postgres


def test_relational_single_arg_leaves_pin_none() -> None:
    class NotesTblD(Relational[_Row], table=True):
        id: int | None = Field(default=None, primary_key=True)
        body: str

    assert NotesTblD.__skaal_value_type__ is _Row
    assert NotesTblD.__skaal_backend_pin__ is None


def test_relational_backend_default_does_not_pin() -> None:
    """``Backend`` itself (the `TypeVar` default) must not register as a pin."""

    class NotesTblE(Relational[_Row, Backend], table=True):
        id: int | None = Field(default=None, primary_key=True)
        body: str

    assert NotesTblE.__skaal_backend_pin__ is None


def test_relational_distinct_parametrisations_are_independent() -> None:
    class CommentsPgTblF(Relational[_Row, Postgres], table=True):
        id: int | None = Field(default=None, primary_key=True)
        body: str

    class CommentsLiteTblG(Relational[_Row, Sqlite], table=True):
        id: int | None = Field(default=None, primary_key=True)
        body: str

    assert CommentsPgTblF.__skaal_backend_pin__ is Postgres
    assert CommentsLiteTblG.__skaal_backend_pin__ is Sqlite


def test_relational_unparametrised_base_has_no_pin() -> None:
    assert Relational.__skaal_value_type__ is None
    assert Relational.__skaal_backend_pin__ is None


def test_relational_class_getitem_returns_subclass() -> None:
    parametrised = Relational[_Row, Postgres]

    assert issubclass(parametrised, Relational)
    assert parametrised.__skaal_value_type__ is _Row
    assert parametrised.__skaal_backend_pin__ is Postgres
    # The pure-typing form is unaffected — args() should still mirror what
    # subscript syntax exposes on the generic alias.
    assert get_args(parametrised) == ()  # SQLModel returns a concrete subclass


def test_relational_in_skaal_public_api() -> None:
    import skaal

    assert "Relational" in skaal.__all__
    assert skaal.Relational is Relational
