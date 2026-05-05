from __future__ import annotations

from typing import Protocol, TypeAlias, TypeVar

TSend_contra = TypeVar("TSend_contra", contravariant=True)
TAppend_contra = TypeVar("TAppend_contra", contravariant=True)
TPublish = TypeVar("TPublish")


class SupportsAsyncSend(Protocol[TSend_contra]):
    async def send(self, item: TSend_contra) -> None: ...


class SupportsAsyncAppend(Protocol[TAppend_contra]):
    async def append(self, item: TAppend_contra) -> object: ...


AsyncPublishTarget: TypeAlias = SupportsAsyncSend[TPublish] | SupportsAsyncAppend[TPublish]
AsyncPublishRef: TypeAlias = AsyncPublishTarget[TPublish] | type[object]


__all__ = ["AsyncPublishRef", "AsyncPublishTarget", "SupportsAsyncAppend", "SupportsAsyncSend"]
