from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


def _empty_metadata() -> dict[str, str]:
    return {}


@dataclass(frozen=True)
class BlobItem:
    key: str
    size: int
    content_type: str | None = None
    etag: str | None = None
    updated_at: datetime | None = None
    metadata: dict[str, str] = field(default_factory=_empty_metadata)
