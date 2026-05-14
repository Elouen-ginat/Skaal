"""Tests for the Phase 4 second-generic `Backend` type-pin (ADR 032 §4.4)."""

from __future__ import annotations

from pydantic import BaseModel

from skaal import App, BlobStore, Channel, Store
from skaal.backends._tokens import S3, Redis, RedisChannel, Sqlite
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
    class Events(Channel[dict, RedisChannel]):
        pass

    assert Events.__skaal_inferred__.overrides.backend == "redis-channel"


def test_channel_un_pinned_has_no_backend_override() -> None:
    app = App("test-channel-no-pin")

    @app.channel(buffer=10)
    class Events(Channel[dict]):
        pass

    assert Events.__skaal_inferred__.overrides.backend is None


def test_extract_backend_pin_helper_direct() -> None:
    class Pinned(Store[User, Redis]):
        pass

    class UnPinned(Store[User]):
        pass

    assert _extract_backend_pin(Pinned) is Redis
    assert _extract_backend_pin(UnPinned) is None
