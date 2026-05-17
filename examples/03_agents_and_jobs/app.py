"""Agents, jobs, and schedules — Skaal's dynamic surface in one Dash UI.

This example covers the dynamic, time-driven half of Skaal:

- `@app.agent(persistent=True)` — a virtual actor with a persistent identity.
  Each `room_id` gets its own single-threaded `ChatRoom` instance that
  survives runtime restarts.
- `@app.job(retry=...)` + `app.enqueue(...)` — background work executed on
  the runtime worker, with retries on failure.
- `@app.schedule(trigger=Every("5s"))` — a periodic task wired up by the
  runtime scheduler.
- `RetryPolicy` on a flaky `@app.function()` so transient failures heal
  themselves.

Run locally:

    pip install "skaal[serve,examples]" dash dash-bootstrap-components
    python examples/03_agents_and_jobs/app.py

Then open http://localhost:8050.
"""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone
from typing import Any

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dcc, html

from skaal import Agent, App, Every, RetryPolicy, Store, handler
from skaal.types import Persistent

# ── Skaal app ─────────────────────────────────────────────────────────────────

app = App("agents-and-jobs")


@app.storage(read_latency="< 5ms", durability="persistent")
class JobLog(Store[list[str]]):
    """Append-only log of completed background jobs, keyed by `"log"`."""


@app.storage(read_latency="< 5ms", durability="ephemeral")
class Heartbeats(Store[str]):
    """Last-seen timestamps written by the scheduled task."""


# ── Virtual actor — persistent per-room state ────────────────────────────────


@app.agent(persistent=True)
class ChatRoom(Agent):
    """One persistent actor instance per room id.

    Skaal serializes calls to the same identity, so `bump` is race-free even
    under concurrent HTTP traffic. Fields annotated with `Persistent[...]`
    survive runtime restarts.
    """

    message_count: Persistent[int] = 0
    last_speaker: Persistent[str] = ""

    @handler
    async def bump(self, speaker: str) -> dict[str, Any]:
        self.message_count += 1
        self.last_speaker = speaker
        return {"count": self.message_count, "last_speaker": self.last_speaker}

    @handler
    async def snapshot(self) -> dict[str, Any]:
        return {"count": self.message_count, "last_speaker": self.last_speaker}


# ── Background job — executed by the runtime worker ──────────────────────────


@app.job(retry=RetryPolicy(max_attempts=3, base_delay_ms=10, max_delay_ms=50))
async def index_message(room_id: str, body: str) -> None:
    """Pretend-expensive work; retried automatically on transient failure."""
    if random.random() < 0.3:
        raise RuntimeError("transient indexing failure")
    log = await JobLog.get("log") or []
    log.append(f"{datetime.now(timezone.utc).isoformat()} — {room_id}: {body[:40]}")
    await JobLog.set("log", log[-20:])


# ── Periodic task — fires every 5 seconds ────────────────────────────────────


@app.schedule(trigger=Every(interval="5s"))
async def heartbeat() -> None:
    """Write the current timestamp every five seconds."""
    await Heartbeats.set("last", datetime.now(timezone.utc).isoformat())


# ── Resilient function — retries on a flaky upstream ─────────────────────────


@app.function(retry=RetryPolicy(max_attempts=4, base_delay_ms=20, max_delay_ms=100))
async def maybe_fail(message: str) -> dict[str, Any]:
    """Fail ~50% of the time; the runtime retries until success or budget."""
    if random.random() < 0.5:
        raise RuntimeError("flaky upstream rejected the request")
    return {"echoed": message, "at": datetime.now(timezone.utc).isoformat()}


# ── Dash UI ───────────────────────────────────────────────────────────────────

dash_app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

dash_app.layout = dbc.Container(
    [
        html.H2("Skaal — Agents, Jobs, Schedules"),
        html.P(
            "Each card exercises a different runtime feature. Tail the logs "
            "to watch retries and scheduled ticks land.",
            className="text-muted",
        ),
        dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.H5("ChatRoom — virtual actor"),
                                html.Small(
                                    "Persistent state per room id, single-threaded per identity.",
                                    className="text-muted",
                                ),
                                dbc.Input(
                                    id="room-id",
                                    placeholder="room id (e.g. lobby)",
                                    className="mt-2",
                                ),
                                dbc.Input(id="speaker", placeholder="speaker", className="mt-2"),
                                dbc.Button(
                                    "Bump", id="bump-btn", color="primary", className="mt-2"
                                ),
                                html.Div(id="room-state", className="mt-3 small"),
                            ]
                        )
                    ),
                    md=6,
                    className="mb-4",
                ),
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.H5("Background job — index_message"),
                                html.Small(
                                    "Enqueued via app.enqueue(); retried on failure.",
                                    className="text-muted",
                                ),
                                dbc.Input(id="job-room", placeholder="room id", className="mt-2"),
                                dbc.Input(
                                    id="job-body", placeholder="message body", className="mt-2"
                                ),
                                dbc.Button(
                                    "Enqueue", id="enqueue-btn", color="primary", className="mt-2"
                                ),
                                html.Div(id="job-status", className="mt-2 small"),
                            ]
                        )
                    ),
                    md=6,
                    className="mb-4",
                ),
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.H5("Resilient function — maybe_fail"),
                                html.Small(
                                    "RetryPolicy(max_attempts=4) heals transient failures.",
                                    className="text-muted",
                                ),
                                dbc.Input(id="fn-input", placeholder="message", className="mt-2"),
                                dbc.Button(
                                    "Invoke", id="invoke-btn", color="primary", className="mt-2"
                                ),
                                html.Div(id="fn-result", className="mt-3 small"),
                            ]
                        )
                    ),
                    md=6,
                    className="mb-4",
                ),
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.H5("Scheduled task — every 5s"),
                                html.Small(
                                    "@app.schedule(Every('5s')) writes a heartbeat.",
                                    className="text-muted",
                                ),
                                dcc.Interval(id="poll", interval=1000, n_intervals=0),
                                html.Div(id="heartbeat-view", className="mt-3 small"),
                                html.Hr(),
                                html.B("Recent jobs"),
                                html.Pre(
                                    id="job-log",
                                    style={
                                        "maxHeight": "200px",
                                        "overflowY": "auto",
                                        "fontSize": "0.8rem",
                                    },
                                ),
                            ]
                        )
                    ),
                    md=6,
                    className="mb-4",
                ),
            ]
        ),
    ],
    fluid=True,
    className="py-4",
)


def _runtime() -> Any:
    """Resolve the LocalRuntime bound to this app (set by `runtime.serve()`)."""
    runtime_ref = app._runtime_ref
    runtime = runtime_ref() if runtime_ref is not None else None
    if runtime is None:
        raise RuntimeError("Skaal runtime is not running yet.")
    return runtime


@callback(
    Output("room-state", "children"),
    Input("bump-btn", "n_clicks"),
    State("room-id", "value"),
    State("speaker", "value"),
    prevent_initial_call=True,
)
def bump_room(_clicks: int, room_id: str, speaker: str) -> str:
    if not (room_id and speaker):
        return "Enter a room id and speaker."
    state = asyncio.run(_runtime().invoke_agent("ChatRoom", room_id, "bump", speaker))
    return f"Room {room_id!r}: {state['count']} messages — last by {state['last_speaker']}."


@callback(
    Output("job-status", "children"),
    Input("enqueue-btn", "n_clicks"),
    State("job-room", "value"),
    State("job-body", "value"),
    prevent_initial_call=True,
)
def enqueue_job(_clicks: int, room_id: str, body: str) -> str:
    if not (room_id and body):
        return "Enter a room id and message body."
    handle = asyncio.run(app.enqueue("index_message", room_id, body))
    return f"Enqueued {handle.job_name}."


@callback(
    Output("fn-result", "children"),
    Input("invoke-btn", "n_clicks"),
    State("fn-input", "value"),
    prevent_initial_call=True,
)
def call_resilient(_clicks: int, message: str) -> str:
    message = (message or "").strip() or "hello"
    try:
        result = asyncio.run(app.invoke("maybe_fail", message=message))
    except Exception as exc:
        return f"Failed after retries: {exc}"
    return f"Echoed {result['echoed']!r} at {result['at']}."


@callback(
    Output("heartbeat-view", "children"),
    Output("job-log", "children"),
    Input("poll", "n_intervals"),
)
def refresh_state(_n: int) -> tuple[str, str]:
    last = Heartbeats.sync_get("last") or "(no heartbeat yet)"
    log = JobLog.sync_get("log") or []
    return f"Last heartbeat: {last}", "\n".join(reversed(log)) or "(no jobs run yet)"


# ── Mount Dash inside Skaal ───────────────────────────────────────────────────

app.mount_wsgi(dash_app.server, attribute="dash_app.server")


if __name__ == "__main__":
    from skaal.runtime.local import LocalRuntime

    runtime = LocalRuntime(app, port=8050)
    asyncio.run(runtime.serve())
