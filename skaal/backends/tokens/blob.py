"""Blob-storage backend tokens."""

from skaal.backends._base import Backend
from skaal.backends._native_types import BlobFilesystem


class S3(Backend[BlobFilesystem]):
    name = "s3"
    kinds = frozenset({"blob"})
    NativeClient = BlobFilesystem


class Gcs(Backend[BlobFilesystem]):
    name = "gcs"
    kinds = frozenset({"blob"})
    NativeClient = BlobFilesystem


class FilesystemBlob(Backend[BlobFilesystem]):
    name = "filesystem-blob"
    kinds = frozenset({"blob"})
    NativeClient = BlobFilesystem


__all__ = ["S3", "FilesystemBlob", "Gcs"]
