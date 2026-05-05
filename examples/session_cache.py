"""Session cache example demonstrating class-level retention and per-call TTL overrides.

Run locally:

    skaal run examples.session_cache:app

Try it:

    curl -s localhost:8000/sessions/demo -X POST | jq
    curl -s localhost:8000/sessions/demo | jq
    curl -s localhost:8000/sessions/demo/touch -X POST | jq
    curl -s localhost:8000/tokens/demo -X POST | jq
    curl -s localhost:8000/sessions | jq
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from skaal import App, Store

app = App("session-cache")
api = FastAPI(title="Skaal Session Cache Example")


class SessionRecord(BaseModel):
    id: str
    user_id: str
    issued_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_seen_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class TokenRecord(BaseModel):
    id: str
    scope: str
    issued_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@app.storage(read_latency="< 5ms", durability="ephemeral", retention="30m")
class Sessions(Store[SessionRecord]):
    """Session rows expire after 30 minutes unless a write overrides the TTL."""


@app.storage(read_latency="< 5ms", durability="ephemeral", retention="15m")
class Tokens(Store[TokenRecord]):
    """Short-lived token cache with per-call TTL overrides."""


@app.function()
async def create_session(session_id: str, user_id: str) -> dict:
    record = SessionRecord(id=session_id, user_id=user_id)
    await Sessions.set(session_id, record)
    return record.model_dump()


@app.function()
async def touch_session(session_id: str, extend_for: str = "45m") -> dict:
    session = await Sessions.get(session_id)
    if session is None:
        return {"error": f"Session {session_id!r} not found"}
    session.last_seen_at = datetime.now(timezone.utc).isoformat()
    await Sessions.set(session_id, session, ttl=extend_for)
    return {"session": session.model_dump(), "ttl": extend_for}


@app.function()
async def issue_token(token_id: str, scope: str = "api") -> dict:
    token = TokenRecord(id=token_id, scope=scope)
    await Tokens.add(token, ttl="5m")
    return {"token": token.model_dump(), "ttl": "5m"}


@app.function()
async def get_session(session_id: str) -> dict:
    session = await Sessions.get(session_id)
    if session is None:
        return {"error": f"Session {session_id!r} not found or expired"}
    return session.model_dump()


@app.function()
async def list_sessions() -> dict:
    return {"sessions": [session.model_dump() for _, session in await Sessions.list()]}


@api.post("/sessions/{session_id}")
async def create_session_route(session_id: str, user_id: str = "demo-user") -> dict:
    return await create_session(session_id=session_id, user_id=user_id)


@api.get("/sessions/{session_id}")
async def get_session_route(session_id: str) -> dict:
    result = await get_session(session_id=session_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@api.post("/sessions/{session_id}/touch")
async def touch_session_route(session_id: str, extend_for: str = "45m") -> dict:
    result = await touch_session(session_id=session_id, extend_for=extend_for)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@api.post("/tokens/{token_id}")
async def issue_token_route(token_id: str, scope: str = "api") -> dict:
    return await issue_token(token_id=token_id, scope=scope)


@api.get("/sessions")
async def list_sessions_route() -> dict:
    return await list_sessions()


app.mount_asgi(api, attribute="api")

__all__ = ["app", "api"]
