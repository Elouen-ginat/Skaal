"""Frontend — a Skaal `App` that calls the backend through `AppRef`.

The frontend is also a Skaal application, but it owns no storage — it only
mounts a Dash UI and declares an `AppRef` pointing at the backend.

`AppRef("backend")` resolves automatically from `SKAAL_APPREF_BACKEND_URL`
and the runtime appends the canonical `/_skaal/invoke/<fn>` prefix to each
call. `skaal run --all` and `skaal deploy --all` set that env var for you.

A streaming endpoint is consumed via raw `httpx.stream` (line 261), since
`AppRef` is JSON-only by design.

Run with the orchestrator:

    pip install "skaal[serve,examples]" dash dash-bootstrap-components httpx
    skaal run --all      # backend on 8000, frontend on 8050

Or by hand:

    skaal run examples.04_fullstack_split.backend:app --port 8000
    SKAAL_APPREF_BACKEND_URL=http://localhost:8000 \\
        python examples/04_fullstack_split/frontend.py

Then open http://localhost:8050.
"""

from __future__ import annotations

import asyncio

import dash
import dash_bootstrap_components as dbc
import httpx
from dash import Input, Output, State, callback, dcc, html, no_update

from skaal import App, AppRef, RetryPolicy

# ── Skaal app ─────────────────────────────────────────────────────────────────

app = App("fullstack-frontend")
backend = AppRef("backend", timeout_ms=10_000, fallback_url="http://localhost:8000")
app.attach(backend)


# Optional: wrap remote calls in `@app.function` to layer retry policies on
# the frontend side. This is purely additive — Dash callbacks could call
# `backend.create_task(...)` directly and bypass the wrapper.
@app.function(retry=RetryPolicy(max_attempts=3, base_delay_ms=20, max_delay_ms=200))
async def create_task(id: str, title: str) -> dict:
    return await backend.call("create_task", id=id, title=title)


@app.function()
async def list_tasks() -> dict:
    return await backend.call("list_tasks")


@app.function()
async def complete_task(id: str) -> dict:
    return await backend.call("complete_task", id=id)


@app.function()
async def delete_task(id: str) -> dict:
    return await backend.call("delete_task", id=id)


def _run(coro: object) -> object:
    return asyncio.run(coro)  # type: ignore[arg-type]


# ── Dash UI ───────────────────────────────────────────────────────────────────

dash_app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    title="Skaal Fullstack — Frontend",
)

dash_app.layout = dbc.Container(
    [
        html.H2("Skaal Fullstack — Dash + AppRef Frontend"),
        html.P(
            f"Backend: {backend.url}. The frontend is itself a Skaal `App` "
            "that holds no storage; it talks to the backend through `AppRef` "
            "(POST /_skaal/invoke/<fn>).",
            className="text-muted",
        ),
        dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.H5("Create / list tasks"),
                                dbc.InputGroup(
                                    [
                                        dbc.InputGroupText("id"),
                                        dbc.Input(id="task-id", type="text"),
                                        dbc.InputGroupText("title"),
                                        dbc.Input(id="task-title", type="text"),
                                        dbc.Button("Create", id="create-btn", color="primary"),
                                    ],
                                    className="mt-2",
                                ),
                                html.Div(id="task-status", className="mt-3 small text-muted"),
                                html.Hr(),
                                html.B("Tasks"),
                                html.Div(id="task-list", className="mt-2"),
                                dcc.Interval(id="poll", interval=2000, n_intervals=0),
                            ]
                        )
                    ),
                    md=7,
                ),
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.H5("Stream progress (SSE)"),
                                html.Small(
                                    "AppRef is JSON-only, so streaming uses raw httpx.",
                                    className="text-muted",
                                ),
                                dbc.InputGroup(
                                    [
                                        dbc.InputGroupText("task id"),
                                        dbc.Input(id="stream-id", type="text", value="demo"),
                                        dbc.Button("Stream", id="stream-btn", outline=True),
                                    ],
                                    className="mt-2",
                                ),
                                html.Pre(
                                    id="stream-output",
                                    style={
                                        "maxHeight": "260px",
                                        "overflowY": "auto",
                                        "fontSize": "0.85rem",
                                        "background": "#f7f7f7",
                                        "padding": "0.5rem",
                                        "marginTop": "1rem",
                                    },
                                ),
                            ]
                        )
                    ),
                    md=5,
                ),
            ]
        ),
    ],
    fluid=True,
    className="py-4",
)


def _render_tasks(items: list[dict]) -> html.Div:
    if not items:
        return html.Div("No tasks yet.", className="text-muted")
    rows = []
    for task in items:
        right = (
            dbc.Badge("done", color="success", className="ms-2")
            if task["done"]
            else dbc.Button(
                "complete",
                id={"type": "complete-btn", "task_id": task["id"]},
                size="sm",
                color="success",
                outline=True,
                className="ms-2",
            )
        )
        delete_btn = dbc.Button(
            "delete",
            id={"type": "delete-btn", "task_id": task["id"]},
            size="sm",
            color="danger",
            outline=True,
            className="ms-2",
        )
        rows.append(
            dbc.ListGroupItem(
                [html.Span(f"{task['id']} — {task['title']}"), right, delete_btn],
                className="d-flex justify-content-between align-items-center",
            )
        )
    return dbc.ListGroup(rows, flush=True)


@callback(
    Output("task-status", "children"),
    Output("task-id", "value"),
    Output("task-title", "value"),
    Input("create-btn", "n_clicks"),
    State("task-id", "value"),
    State("task-title", "value"),
    prevent_initial_call=True,
)
def create(_clicks: int, task_id: str, title: str) -> tuple[str, str, str]:
    task_id = (task_id or "").strip()
    title = (title or "").strip()
    if not task_id or not title:
        return "Enter both id and title.", no_update, no_update
    result = _run(app.invoke(create_task, id=task_id, title=title))
    if isinstance(result, dict) and "error" in result:
        return result["error"], no_update, no_update
    return f"Created task {task_id!r}.", "", ""


@callback(
    Output("task-list", "children"),
    Input("poll", "n_intervals"),
    Input("create-btn", "n_clicks"),
    Input({"type": "complete-btn", "task_id": dash.ALL}, "n_clicks"),
    Input({"type": "delete-btn", "task_id": dash.ALL}, "n_clicks"),
)
def refresh_tasks(*_args: object) -> html.Div:
    triggered = dash.callback_context.triggered_id
    if isinstance(triggered, dict):
        task_id = triggered["task_id"]
        if triggered["type"] == "complete-btn":
            _run(app.invoke(complete_task, id=task_id))
        elif triggered["type"] == "delete-btn":
            _run(app.invoke(delete_task, id=task_id))
    response = _run(app.invoke(list_tasks))
    items = response.get("items", []) if isinstance(response, dict) else []
    return _render_tasks(items)


@callback(
    Output("stream-output", "children"),
    Input("stream-btn", "n_clicks"),
    State("stream-id", "value"),
    prevent_initial_call=True,
)
def stream(_clicks: int, task_id: str) -> str:
    task_id = (task_id or "demo").strip()
    chunks: list[str] = []
    with httpx.stream("GET", f"{backend.url}/tasks/{task_id}/progress", timeout=None) as response:
        for line in response.iter_lines():
            if line.startswith("data:"):
                chunks.append(line.removeprefix("data:").strip())
    return "\n".join(chunks)


# ── Mount Dash inside the frontend Skaal app ─────────────────────────────────

app.mount_wsgi(dash_app.server, attribute="dash_app.server")


if __name__ == "__main__":
    from skaal.runtime.local import LocalRuntime

    runtime = LocalRuntime(app, port=8050)
    asyncio.run(runtime.serve())
