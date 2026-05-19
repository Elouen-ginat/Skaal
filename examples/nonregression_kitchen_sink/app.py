"""Kitchen-sink Skaal app — every public decorator exercised at once.

Layout:

- KV `Store` (`Users`), blob `BlobStore` (`Attachments`), relational `Table`
  (`AuditLog`).
- A typed `Topic` channel (`Notifications`).
- A `Module` mounted via `app.use(analytics, namespace="analytics")` that
  contributes its own KV store and exported function.
- An `@app.expose()` function carrying every resilience policy (retry,
  circuit breaker, rate limit, bulkhead).
- An `@app.job()` background handler.
- Two schedules: one driven by `Every`, one by `Cron`.
- A FastAPI surface mounted at `/` so the non-regression suite can exercise
  the deployed endpoint over HTTP.

The handlers deliberately keep their bodies small — the point is to make the
inference + binding + deploy pipeline take every decorator end-to-end, not
to ship realistic business logic.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel
from sqlmodel import Field

from skaal import (
    App,
    BlobStore,
    Bulkhead,
    CircuitBreaker,
    Cron,
    Every,
    Module,
    RateLimit,
    Retry,
    Store,
    Table,
    Topic,
)

# ── App + sub-module wiring ────────────────────────────────────────────────────

app = App("kitchen_sink")
api = FastAPI(title="Skaal kitchen-sink non-regression app")

analytics = Module("analytics")


# ── Domain models ──────────────────────────────────────────────────────────────


class User(BaseModel):
    id: str
    name: str
    created_at: str


class Notification(BaseModel):
    user_id: str
    body: str
    sent_at: str


class AnalyticsEvent(BaseModel):
    id: str
    type: str
    at: str


# ── Sub-module storage + function (exported into the root app) ────────────────


@analytics.storage
class EventLog(Store[AnalyticsEvent]):
    """Recent analytics events. Owned by the `analytics` sub-module."""


@analytics.expose()
async def record_event(id: str, type: str) -> dict[str, Any]:
    """Record an analytics event. Re-exported via `analytics.<name>`."""
    event = AnalyticsEvent(id=id, type=type, at=datetime.now(timezone.utc).isoformat())
    await EventLog.set(id, event)
    return event.model_dump()


analytics.export(EventLog, record_event)
app.use(analytics, namespace="analytics")


# ── Root-app storage primitives ────────────────────────────────────────────────


@app.storage
class Users(Store[User]):
    """Primary user table — KV-shaped."""


@app.storage(kind="blob")
class Attachments(BlobStore):
    """Object storage for user uploads."""


@app.storage(kind="relational")
class AuditLog(Table, table=True):
    """Append-only audit log. Exercises the relational backend slot."""

    __tablename__ = "kitchen_sink_audit_log"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    actor: str = Field(index=True)
    action: str
    at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ── Channel ────────────────────────────────────────────────────────────────────


@app.channel(buffer=128)
class Notifications(Topic[Notification]):
    """Pub/sub topic for user-facing notifications."""


# ── Functions ──────────────────────────────────────────────────────────────────


@app.expose(
    retry=Retry(max_attempts=3, base_delay_ms=50, max_delay_ms=500),
    circuit_breaker=CircuitBreaker(failure_threshold=5, recovery_timeout_ms=30_000),
    rate_limit=RateLimit(requests_per_second=20.0, burst=40),
    bulkhead=Bulkhead(max_concurrent_calls=4, max_wait_ms=250),
)
async def create_user(id: str, name: str) -> dict[str, Any]:
    """Create a user and audit the action.

    Carries every resilience policy so the binding/deploy layers must emit
    the matching middleware configuration on whichever target hosts it.
    """
    user = User(id=id, name=name, created_at=datetime.now(timezone.utc).isoformat())
    await Users.set(id, user)

    async with AuditLog.session() as session:
        session.add(AuditLog(actor=id, action="create_user"))
        await session.commit()

    return user.model_dump()


@app.expose()
async def get_user(id: str) -> dict[str, Any]:
    """Fetch a user by id."""
    user = await Users.get(id)
    return user.model_dump() if user else {"error": f"User {id!r} not found"}


@app.expose()
async def list_users() -> dict[str, Any]:
    """Return every known user. Demonstrates a streaming-style read path."""
    entries = await Users.list()
    return {"users": [v.model_dump() for _, v in entries], "count": len(entries)}


# ── Background job ─────────────────────────────────────────────────────────────


@app.job(retry=Retry(max_attempts=2, base_delay_ms=100, max_delay_ms=1_000))
async def reindex_user(user_id: str) -> None:
    """Background job — reindex a user's audit trail. Exercises the JOB kind."""
    async with AuditLog.session() as session:
        session.add(AuditLog(actor=user_id, action="reindex"))
        await session.commit()


# ── Schedules ──────────────────────────────────────────────────────────────────


@app.schedule(trigger=Every(interval="60s"))
async def heartbeat() -> None:
    """Frequent heartbeat — exercises the `Every` schedule trigger."""
    async with AuditLog.session() as session:
        session.add(AuditLog(actor="system", action="heartbeat"))
        await session.commit()


@app.schedule(trigger=Cron(expression="0 * * * *"))
async def hourly_compaction() -> None:
    """Hourly compaction stub — exercises the `Cron` schedule trigger."""


# ── HTTP surface ───────────────────────────────────────────────────────────────


class CreateUserPayload(BaseModel):
    id: str
    name: str


@api.post("/users", status_code=201)
async def http_create_user(payload: CreateUserPayload) -> dict[str, Any]:
    return await create_user(id=payload.id, name=payload.name)


@api.get("/users/{user_id}")
async def http_get_user(user_id: str) -> dict[str, Any]:
    return await get_user(id=user_id)


@api.get("/users")
async def http_list_users() -> dict[str, Any]:
    return await list_users()


@api.get("/healthz")
async def http_healthz() -> dict[str, str]:
    return {"status": "ok", "app": "kitchen_sink"}


app.mount("/", api)
