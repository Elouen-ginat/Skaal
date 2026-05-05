from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from skaal.types.compute import RetryPolicy


@dataclass(frozen=True)
class JobSpec:
    """Metadata attached to a registered background job handler."""

    name: str
    retry: RetryPolicy | None = None


@dataclass(frozen=True)
class JobHandle:
    """Opaque handle returned when work is queued for background execution."""

    job_id: str
    job_name: str
    scheduled_for: datetime


class JobStatus(str, Enum):
    """Lifecycle states for a queued background job."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class JobResult:
    """Result snapshot for a completed or terminal background job."""

    job_id: str
    status: JobStatus
    attempts: int
    last_error: str | None = None
    completed_at: datetime | None = None


__all__ = ["JobHandle", "JobResult", "JobSpec", "JobStatus"]
