from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Literal, TypeAlias, TypeVar

from pydantic import BaseModel
from typing_extensions import TypedDict

from skaal.types.constraints import AccessPattern
from skaal.types.protocols import AsyncPublishRef, AsyncPublishTarget

TSource = TypeVar("TSource")
TView = TypeVar("TView")
TOutbox = TypeVar("TOutbox")

OutboxDelivery = Literal["at-least-once", "exactly-once"]

ProjectionHandlerResult: TypeAlias = object | None
ProjectionHandler: TypeAlias = Callable[
    [type[TView], TSource],
    ProjectionHandlerResult | Awaitable[ProjectionHandlerResult],
]


class EventLogStorageMetadata(TypedDict):
    access_pattern: AccessPattern
    durability: object
    retention: str
    partitions: int
    throughput: object | None


class EventLogPatternMetadata(TypedDict):
    pattern_type: Literal["event-log"]
    storage: EventLogStorageMetadata


class EventLogPatternConfig(BaseModel):
    retention: str
    partitions: int
    durability: str | None


class ProjectionFailureError(TypedDict):
    type: str
    message: str


class ProjectionFailurePayload(TypedDict):
    pattern: Literal["projection"]
    handler: str
    offset: int
    event: object
    error: ProjectionFailureError


ProjectionDeadLetterSink: TypeAlias = AsyncPublishTarget[ProjectionFailurePayload]
ProjectionDeadLetterRef: TypeAlias = AsyncPublishRef[ProjectionFailurePayload]


class ProjectionPatternMetadata(TypedDict):
    pattern_type: Literal["projection"]
    source: object
    target: type[object]
    handler: str
    consistency: object
    checkpoint_every: int
    strict: bool
    dead_letter: ProjectionDeadLetterRef | None


class ProjectionPatternConfig(BaseModel):
    source: str | None
    target: str | None
    handler: str
    dead_letter: str | None
    consistency: str | None
    checkpoint_every: int
    strict: bool


class SagaStepMetadata(TypedDict):
    function: str
    compensate: str
    timeout_ms: int | None


class SagaPatternMetadata(TypedDict):
    pattern_type: Literal["saga"]
    name: str
    steps: list[SagaStepMetadata]
    coordination: Literal["compensation", "2pc"]
    timeout_ms: int | None


class SagaPatternConfig(BaseModel):
    name: str
    steps: list[SagaStepMetadata]
    coordination: Literal["compensation", "2pc"]
    timeout_ms: int | None
    missing_references: list[str]


OutboxChannelRef: TypeAlias = AsyncPublishRef[TOutbox]


class OutboxPatternMetadata(TypedDict):
    pattern_type: Literal["outbox"]
    channel: object
    storage: type[object]
    delivery: OutboxDelivery


class OutboxPatternConfig(BaseModel):
    channel: str | None
    storage: str | None
    delivery: OutboxDelivery


PatternMetadata: TypeAlias = (
    EventLogPatternMetadata
    | ProjectionPatternMetadata
    | SagaPatternMetadata
    | OutboxPatternMetadata
)
PatternConfig: TypeAlias = (
    EventLogPatternConfig | ProjectionPatternConfig | SagaPatternConfig | OutboxPatternConfig
)


__all__ = [
    "EventLogPatternConfig",
    "EventLogPatternMetadata",
    "EventLogStorageMetadata",
    "OutboxChannelRef",
    "OutboxPatternConfig",
    "OutboxDelivery",
    "OutboxPatternMetadata",
    "PatternConfig",
    "PatternMetadata",
    "ProjectionDeadLetterRef",
    "ProjectionDeadLetterSink",
    "ProjectionFailureError",
    "ProjectionFailurePayload",
    "ProjectionHandler",
    "ProjectionHandlerResult",
    "ProjectionPatternConfig",
    "ProjectionPatternMetadata",
    "SagaPatternConfig",
    "SagaPatternMetadata",
    "SagaStepMetadata",
]
