"""Tests for the Phase 4 generic-parameter `Backend` type-pin (ADR 032 §4.4)."""

from __future__ import annotations

from pydantic import BaseModel
from sqlmodel import Field

from skaal import App, BlobStore, Store, Table, Topic
from skaal.backends._tokens import S3, Postgres, Redis, RedisChannel, Sqlite
from skaal.decorators import _extract_backend_pin


class User(BaseModel):
    id: str
    name: str


def test_store_un_pinned_has_no_backend_override() -> None:
    app = App("test-no-pin")

    @app.storage
    class Users(Store[User]):
        pass

    inferred = Users.__skaal_inferred__
    assert inferred.overrides.backend is None


def test_store_pinned_populates_overrides_backend() -> None:
    app = App("test-pin")

    @app.storage
    class Cache(Store[User, Redis]):
        pass

    inferred = Cache.__skaal_inferred__
    assert inferred.overrides.backend == "redis"


def test_store_pinned_to_sqlite_populates_overrides_backend() -> None:
    app = App("test-pin-sqlite")

    @app.storage
    class Users(Store[User, Sqlite]):
        pass

    assert Users.__skaal_inferred__.overrides.backend == "sqlite"


def test_blob_store_pinned_populates_overrides_backend() -> None:
    app = App("test-blob-pin")

    @app.storage(kind="blob")
    class Reports(BlobStore[S3]):
        pass

    assert Reports.__skaal_inferred__.overrides.backend == "s3"


def test_blob_store_un_pinned_has_no_backend_override() -> None:
    app = App("test-blob-no-pin")

    @app.storage(kind="blob")
    class Assets(BlobStore):
        pass

    assert Assets.__skaal_inferred__.overrides.backend is None


def test_channel_pinned_populates_overrides_backend() -> None:
    app = App("test-channel-pin")

    @app.channel(buffer=10)
    class Events(Topic[dict, RedisChannel]):
        pass

    assert Events.__skaal_inferred__.overrides.backend == "redis-channel"


def test_channel_un_pinned_has_no_backend_override() -> None:
    app = App("test-channel-no-pin")

    @app.channel(buffer=10)
    class Events(Topic[dict]):
        pass

    assert Events.__skaal_inferred__.overrides.backend is None


def test_extract_backend_pin_helper_direct() -> None:
    class Pinned(Store[User, Redis]):
        pass

    class UnPinned(Store[User]):
        pass

    assert _extract_backend_pin(Pinned) is Redis
    assert _extract_backend_pin(UnPinned) is None


def test_relational_pinned_populates_overrides_backend() -> None:
    app = App("test-relational-pin")

    @app.storage(kind="relational")
    class Comments(Table[Postgres], table=True):
        id: int | None = Field(default=None, primary_key=True)
        body: str

    assert Comments.__skaal_inferred__.overrides.backend == "postgres"
    assert Comments.__skaal_backend_pin__ is Postgres


def test_relational_un_pinned_has_no_backend_override() -> None:
    app = App("test-relational-no-pin")

    @app.storage(kind="relational")
    class Notes(Table, table=True):
        id: int | None = Field(default=None, primary_key=True)
        body: str

    assert Notes.__skaal_inferred__.overrides.backend is None
    assert Notes.__skaal_backend_pin__ is None


def test_relational_two_distinct_pins_do_not_alias() -> None:
    """Two parametrisations of `Table` must not share state.

    `Table[Postgres]` and `Table[Sqlite]` create two distinct
    intermediate classes; the pin captured on one must not leak into
    the other.
    """

    app_a = App("test-relational-distinct-a")
    app_b = App("test-relational-distinct-b")

    @app_a.storage(kind="relational")
    class CommentsA(Table[Postgres], table=True):
        id: int | None = Field(default=None, primary_key=True)
        body: str

    @app_b.storage(kind="relational")
    class CommentsB(Table[Sqlite], table=True):
        id: int | None = Field(default=None, primary_key=True)
        body: str

    assert CommentsA.__skaal_inferred__.overrides.backend == "postgres"
    assert CommentsB.__skaal_inferred__.overrides.backend == "sqlite"


def test_extract_backend_pin_helper_on_relational() -> None:
    class PinnedRelational(Table[Postgres], table=True):
        id: int | None = Field(default=None, primary_key=True)
        body: str

    class UnPinnedRelational(Table, table=True):
        id: int | None = Field(default=None, primary_key=True)
        body: str

    assert _extract_backend_pin(PinnedRelational) is Postgres
    assert _extract_backend_pin(UnPinnedRelational) is None
