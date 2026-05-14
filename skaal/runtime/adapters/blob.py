"""Adapter for `BLOB` resources.

Phase 4 wires the local-defaults `filesystem-blob` backend. The S3 /
GCS variants are deploy-time provisioning concerns; the local runtime
expects users to pin to `filesystem-blob` for in-process testing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from skaal.binding.model import BoundResource
    from skaal.runtime.local import LocalRuntime


def register(runtime: LocalRuntime, bound: BoundResource, target: Any) -> None:
    """Build a filesystem-backed `BlobStore` and bind it to ``target``."""
    if target is None:
        return
    if bound.external:
        return
    if bound.backend != "filesystem-blob":
        from skaal.errors import RuntimeAdapterMissing

        raise RuntimeAdapterMissing(f"blob/{bound.backend}")

    from collections.abc import Callable

    from skaal.backends.file_blob_backend import FileBlobBackend

    root: str = bound.options.get("root", "./skaal_blob")
    backend: FileBlobBackend = FileBlobBackend(root_path=root, namespace=target.__name__)
    wire: Callable[[Any], None] | None = getattr(target, "wire", None)
    if wire is not None:
        wire(backend)
