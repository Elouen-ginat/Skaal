"""Typed blob storage primitives.

Use `BlobStore` for binary assets such as uploads, reports, or generated media.
Blob models are registered with `App.storage(kind="blob")` and are wired to a
backend by the local runtime or deployment layer.

Examples:
    class Assets(BlobStore):
        pass

    await Assets.put_bytes("avatars/alice.png", png_bytes, content_type="image/png")
    avatar = await Assets.stat("avatars/alice.png")

See Also:
    `Store`: Typed key-value storage for structured records.
    `VectorStore`: Similarity search for embedding-backed models.
"""

from __future__ import annotations

import builtins
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Generic, overload

from typing_extensions import TypeVar

from skaal.backends._base import Backend
from skaal.storage import _decode_cursor, _encode_cursor, _normalize_limit
from skaal.sync import run as _sync_run
from skaal.types import BlobItem, Page

if TYPE_CHECKING:
    from skaal.backends._native_types import BlobFilesystem
    from skaal.backends.base import BlobBackend
    from skaal.backends.tokens.blob import S3, FilesystemBlob, Gcs


B = TypeVar("B", bound="Backend[Any]", default="Backend[Any]")


def is_blob_model(obj: Any) -> bool:
    """Return whether `obj` is a Skaal blob storage model.

    Args:
        obj: Value to inspect.

    Returns:
        `True` when `obj` is a class registered through
        `@app.storage(kind="blob")`.
    """
    from skaal.inference.model import BlueprintResource, ResourceKind

    if not isinstance(obj, type):
        return False
    inferred = getattr(obj, "__skaal_inferred__", None)
    return isinstance(inferred, BlueprintResource) and inferred.kind == ResourceKind.BLOB


def validate_blob_model(store_cls: object) -> None:
    """Validate that `store_cls` is a concrete `BlobStore` subclass.

    Args:
        store_cls: Candidate storage class.

    Raises:
        TypeError: If `store_cls` is not a `BlobStore` subclass.
    """
    if not isinstance(store_cls, type) or not issubclass(store_cls, BlobStore):
        raise TypeError('@app.storage(kind="blob") requires a skaal.BlobStore subclass.')


class BlobStore(Generic[B]):
    """Typed object storage with async and sync convenience methods.

    Subclass `BlobStore` to model binary assets that should be stored in a blob
    backend. The async methods map directly to the configured backend, while the
    `sync_*` helpers run the same operations through `skaal.sync.run`.

    The optional generic parameter ``B`` is a `Backend` type-pin (ADR 028
    §6.6, ADR 032 §4.4). ``class Reports(BlobStore[S3])`` pins the
    resource to S3 regardless of environment defaults; the un-pinned
    ``class Assets(BlobStore)`` leaves the binding open for the defaults
    table.

    Examples:
        class Assets(BlobStore):
            pass

        await Assets.put_file("reports/q1.pdf", "./reports/q1.pdf")
        metadata = await Assets.list_page(prefix="reports/")

    Notes:
        `BlobObject` instances contain metadata about a stored object. Use
        `get_bytes` or `download_file` to read the payload itself.

    See Also:
        `Store`: Typed key-value storage for structured records.
        `VectorStore`: Similarity search for embedding-backed models.
    """

    _backend: ClassVar[BlobBackend | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls is BlobStore:
            return
        from skaal.decorators import _attach_storage_inferred

        _attach_storage_inferred(cls, kind="blob")

    @classmethod
    def wire(cls, backend: BlobBackend) -> None:
        """Bind a blob backend to this storage class.

        Args:
            backend: Backend implementation used for subsequent blob operations.
        """
        cls._backend = backend

    @classmethod
    def _ensure_wired(cls) -> None:
        if cls._backend is None:
            raise NotImplementedError(
                f"{cls.__name__} blob store not wired. Use LocalRuntime or deploy first."
            )

    @classmethod
    @overload
    async def native(cls: type[BlobStore[S3]]) -> BlobFilesystem: ...

    @classmethod
    @overload
    async def native(cls: type[BlobStore[Gcs]]) -> BlobFilesystem: ...

    @classmethod
    @overload
    async def native(cls: type[BlobStore[FilesystemBlob]]) -> BlobFilesystem: ...

    @classmethod
    async def native(cls) -> Any:
        """Return the native SDK client for the wired backend (ADR 028 §6.13).

        For type-pinned subclasses (``class Reports(BlobStore[S3])``),
        Pylance resolves the concrete SDK type via the backend token's
        ``NativeClient`` declaration in Phase 5b. In Phase 5a the runtime
        unwraps `backend.native()` when defined, else returns the backend
        instance itself.
        """
        from skaal._native import resolve_native

        cls._ensure_wired()
        assert cls._backend is not None
        return await resolve_native(cls._backend)

    @classmethod
    async def put_bytes(
        cls,
        key: str,
        data: bytes,
        *,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> BlobItem:
        """Store raw bytes under `key`.

        Args:
            key: Logical object key inside the blob store.
            data: Raw payload to persist.
            content_type: MIME type recorded with the object, if known.
            metadata: User-defined metadata stored alongside the object.

        Returns:
            Metadata describing the stored object.

        See Also:
            `put_file`: Store content from an on-disk file.
        """
        cls._ensure_wired()
        assert cls._backend is not None
        return await cls._backend.put_bytes(
            key,
            data,
            content_type=content_type,
            metadata=metadata,
        )

    @classmethod
    async def put_file(
        cls,
        key: str,
        source: str | Path,
        *,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> BlobItem:
        """Upload a file from disk into the blob store.

        Args:
            key: Logical object key inside the blob store.
            source: Local file path to read from.
            content_type: MIME type recorded with the object, if known.
            metadata: User-defined metadata stored alongside the object.

        Returns:
            Metadata describing the stored object.

        See Also:
            `put_bytes`: Store in-memory bytes directly.
        """
        cls._ensure_wired()
        assert cls._backend is not None
        return await cls._backend.put_file(
            key,
            source,
            content_type=content_type,
            metadata=metadata,
        )

    @classmethod
    async def get_bytes(cls, key: str) -> bytes:
        """Return the raw bytes stored under `key`.

        Args:
            key: Logical object key inside the blob store.

        Returns:
            The stored payload.

        Raises:
            FileNotFoundError: If the backend cannot find `key`.

        See Also:
            `download_file`: Stream the object into a local file.
        """
        cls._ensure_wired()
        assert cls._backend is not None
        return await cls._backend.get_bytes(key)

    @classmethod
    async def download_file(cls, key: str, destination: str | Path) -> Path:
        """Download an object into a local file.

        Args:
            key: Logical object key inside the blob store.
            destination: Destination file path.

        Returns:
            The resolved destination path written by the backend.

        See Also:
            `get_bytes`: Read the payload into memory instead.
        """
        cls._ensure_wired()
        assert cls._backend is not None
        return await cls._backend.download_file(key, destination)

    @classmethod
    async def stat(cls, key: str) -> BlobItem | None:
        """Return metadata for `key` without downloading the payload.

        Args:
            key: Logical object key inside the blob store.

        Returns:
            The object metadata, or `None` when the object does not exist.
        """
        cls._ensure_wired()
        assert cls._backend is not None
        return await cls._backend.stat(key)

    @classmethod
    async def exists(cls, key: str) -> bool:
        """Return whether an object exists.

        Args:
            key: Logical object key inside the blob store.

        Returns:
            `True` if the object exists.
        """
        cls._ensure_wired()
        assert cls._backend is not None
        return await cls._backend.exists(key)

    @classmethod
    async def delete(cls, key: str) -> None:
        """Delete an object if it exists.

        Args:
            key: Logical object key inside the blob store.
        """
        cls._ensure_wired()
        assert cls._backend is not None
        await cls._backend.delete(key)

    @classmethod
    async def list_page(
        cls,
        prefix: str = "",
        *,
        limit: int = 100,
        cursor: str | None = None,
    ) -> Page[BlobItem]:
        """List a single page of object metadata.

        Args:
            prefix: Restrict results to keys that start with this prefix.
            limit: Maximum number of items to return.
            cursor: Opaque pagination cursor from a previous page.

        Returns:
            A `Page` of `BlobObject` items.

        See Also:
            `list`: Materialize all matching objects across pages.
        """
        cls._ensure_wired()
        assert cls._backend is not None
        return await cls._backend.list_page(prefix=prefix, limit=limit, cursor=cursor)

    @classmethod
    async def list(cls, prefix: str = "") -> builtins.list[BlobItem]:
        """Return all object metadata matching `prefix`.

        Args:
            prefix: Restrict results to keys that start with this prefix.

        Returns:
            All matching object metadata.

        Notes:
            This helper drains every page into memory. Use `list_page` when you
            need cursor-based pagination.
        """
        items: builtins.list[BlobItem] = []
        cursor: str | None = None
        while True:
            page = await cls.list_page(prefix=prefix, limit=1000, cursor=cursor)
            items.extend(page.items)
            if not page.has_more:
                return items
            cursor = page.next_cursor

    @classmethod
    def sync_put_bytes(
        cls,
        key: str,
        data: bytes,
        *,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> BlobItem:
        """Synchronously store raw bytes under `key`.

        Args:
            key: Logical object key inside the blob store.
            data: Raw payload to persist.
            content_type: MIME type recorded with the object, if known.
            metadata: User-defined metadata stored alongside the object.

        Returns:
            Metadata describing the stored object.

        See Also:
            `put_bytes`: Async variant.
        """
        return _sync_run(cls.put_bytes(key, data, content_type=content_type, metadata=metadata))

    @classmethod
    def sync_put_file(
        cls,
        key: str,
        source: str | Path,
        *,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> BlobItem:
        """Synchronously upload a file from disk.

        Args:
            key: Logical object key inside the blob store.
            source: Local file path to read from.
            content_type: MIME type recorded with the object, if known.
            metadata: User-defined metadata stored alongside the object.

        Returns:
            Metadata describing the stored object.

        See Also:
            `put_file`: Async variant.
        """
        return _sync_run(cls.put_file(key, source, content_type=content_type, metadata=metadata))

    @classmethod
    def sync_get_bytes(cls, key: str) -> bytes:
        """Synchronously return the raw bytes stored under `key`.

        Args:
            key: Logical object key inside the blob store.

        Returns:
            The stored payload.

        See Also:
            `get_bytes`: Async variant.
        """
        return _sync_run(cls.get_bytes(key))

    @classmethod
    def sync_download_file(cls, key: str, destination: str | Path) -> Path:
        """Synchronously download an object into a local file.

        Args:
            key: Logical object key inside the blob store.
            destination: Destination file path.

        Returns:
            The resolved destination path written by the backend.

        See Also:
            `download_file`: Async variant.
        """
        return _sync_run(cls.download_file(key, destination))

    @classmethod
    def sync_stat(cls, key: str) -> BlobItem | None:
        """Synchronously return metadata for `key`.

        Args:
            key: Logical object key inside the blob store.

        Returns:
            The object metadata, or `None` when the object does not exist.

        See Also:
            `stat`: Async variant.
        """
        return _sync_run(cls.stat(key))

    @classmethod
    def sync_exists(cls, key: str) -> bool:
        """Synchronously return whether an object exists.

        Args:
            key: Logical object key inside the blob store.

        Returns:
            `True` if the object exists.

        See Also:
            `exists`: Async variant.
        """
        return _sync_run(cls.exists(key))

    @classmethod
    def sync_delete(cls, key: str) -> None:
        """Synchronously delete an object if it exists.

        Args:
            key: Logical object key inside the blob store.

        See Also:
            `delete`: Async variant.
        """
        _sync_run(cls.delete(key))

    @classmethod
    def sync_list_page(
        cls,
        prefix: str = "",
        *,
        limit: int = 100,
        cursor: str | None = None,
    ) -> Page[BlobItem]:
        """Synchronously list a single page of object metadata.

        Args:
            prefix: Restrict results to keys that start with this prefix.
            limit: Maximum number of items to return.
            cursor: Opaque pagination cursor from a previous page.

        Returns:
            A `Page` of `BlobObject` items.

        See Also:
            `list_page`: Async variant.
        """
        return _sync_run(cls.list_page(prefix=prefix, limit=limit, cursor=cursor))

    @classmethod
    def sync_list(cls, prefix: str = "") -> builtins.list[BlobItem]:
        """Synchronously return all object metadata matching `prefix`.

        Args:
            prefix: Restrict results to keys that start with this prefix.

        Returns:
            All matching object metadata.

        See Also:
            `list`: Async variant.
        """
        return _sync_run(cls.list(prefix=prefix))


def encode_blob_cursor(*, prefix: str, last_key: str) -> str:
    """Encode blob pagination state into an opaque cursor.

    Args:
        prefix: Listing prefix associated with the page.
        last_key: Last key returned in the current page.

    Returns:
        Opaque cursor string that can be supplied to `list_page`.
    """
    return _encode_cursor({"mode": "blob", "prefix": prefix, "last_key": last_key})


def decode_blob_cursor(cursor: str | None, *, prefix: str) -> str | None:
    """Decode and validate a blob pagination cursor.

    Args:
        cursor: Opaque cursor returned by `encode_blob_cursor`.
        prefix: Listing prefix expected for the cursor.

    Returns:
        The last key stored in the cursor, or `None` when no cursor was provided.

    Raises:
        ValueError: If the cursor does not belong to the requested prefix or is malformed.
    """
    if cursor is None:
        return None
    decoded = _decode_cursor(cursor)
    if decoded.get("mode") != "blob" or decoded.get("prefix") != prefix:
        raise ValueError("Cursor does not match this blob listing")
    last_key: Any = decoded.get("last_key")
    if last_key is None:
        return None
    if not isinstance(last_key, str):
        raise ValueError("Invalid blob cursor")
    return last_key


def normalize_blob_limit(limit: int) -> int:
    """Validate and normalize a blob page size.

    Args:
        limit: Requested page size.

    Returns:
        The validated page size.

    Raises:
        ValueError: If `limit` is less than one.
    """
    return _normalize_limit(limit)
