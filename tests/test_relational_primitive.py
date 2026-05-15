"""Tests for the typed ``Relational[B]`` primitive (ADR 028 §6.5, ADR 032 §4.4).

`Relational` shares the backend-pin contract with `Store`, `BlobStore`,
and `Channel`, but rides through `SQLModelMetaclass`, which strips
``__orig_bases__`` from subclasses. The capture path is therefore
`__class_getitem__` → `__skaal_backend_pin__` (inherited via MRO) rather
than `__orig_bases__`. These tests pin that contract independently of
the `@app.storage(kind="relational")` decorator surface.
"""

from __future__ import annotations

from sqlmodel import Field, SQLModel

from skaal import Relational
from skaal.backends._base import Backend
from skaal.backends._tokens import Postgres, Sqlite


def test_relational_subclass_is_sqlmodel() -> None:
    class CommentsTblA(Relational[Postgres], table=True):
        id: int | None = Field(default=None, primary_key=True)
        body: str

    assert issubclass(CommentsTblA, SQLModel)
    assert CommentsTblA.__table__ is not None


def test_relational_captures_backend_pin() -> None:
    class CommentsTblC(Relational[Postgres], table=True):
        id: int | None = Field(default=None, primary_key=True)
        body: str

    assert CommentsTblC.__skaal_backend_pin__ is Postgres


def test_relational_unparametrised_leaves_pin_none() -> None:
    class NotesTblD(Relational, table=True):
        id: int | None = Field(default=None, primary_key=True)
        body: str

    assert NotesTblD.__skaal_backend_pin__ is None


def test_relational_backend_default_does_not_pin() -> None:
    """``Backend`` itself (the `TypeVar` default) must not register as a pin."""

    class NotesTblE(Relational[Backend], table=True):
        id: int | None = Field(default=None, primary_key=True)
        body: str

    assert NotesTblE.__skaal_backend_pin__ is None


def test_relational_distinct_parametrisations_are_independent() -> None:
    class CommentsPgTblF(Relational[Postgres], table=True):
        id: int | None = Field(default=None, primary_key=True)
        body: str

    class CommentsLiteTblG(Relational[Sqlite], table=True):
        id: int | None = Field(default=None, primary_key=True)
        body: str

    assert CommentsPgTblF.__skaal_backend_pin__ is Postgres
    assert CommentsLiteTblG.__skaal_backend_pin__ is Sqlite


def test_relational_unparametrised_base_has_no_pin() -> None:
    assert Relational.__skaal_backend_pin__ is None


def test_relational_class_getitem_returns_subclass() -> None:
    parametrised = Relational[Postgres]

    assert issubclass(parametrised, Relational)
    assert parametrised.__skaal_backend_pin__ is Postgres


def test_relational_in_skaal_public_api() -> None:
    import skaal

    assert "Relational" in skaal.__all__
    assert skaal.Relational is Relational
