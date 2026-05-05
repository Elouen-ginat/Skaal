from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, TypedDict, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Page(Generic[T]):
    items: list[T]
    next_cursor: str | None
    has_more: bool


@dataclass(frozen=True)
class SecondaryIndex:
    name: str
    partition_key: str
    sort_key: str | None = None
    unique: bool = False


@dataclass(frozen=True)
class BackendIndexFields:
    partition_field: str
    sort_field: str | None = None


class CursorPayload(TypedDict, total=False):
    backend: str
    mode: str
    prefix: str
    index_name: str
    key: str
    last_key: str
    last_sort: Any
    has_last_sort: bool
    offset: int
    exclusive_start_key: dict[str, Any]
    start_after: list[Any]
    last_member: str
