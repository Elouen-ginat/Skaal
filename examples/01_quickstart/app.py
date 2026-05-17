"""Quickstart — a counter app with a Dash UI on top of Skaal storage.

This is the smallest end-to-end Skaal example. It shows:

- `App` — the central registry.
- `@app.storage(...)` + `Store[T]` — declarative typed storage with constraints.
- `@app.function()` — async business logic the runtime can route over HTTP.
- `app.mount_wsgi(...)` — co-hosting a Dash UI inside the Skaal runtime.

Run locally:

    pip install "skaal[serve,examples]" dash dash-bootstrap-components
    python examples/01_quickstart/app.py

Then open http://localhost:8050 in your browser.

The `Counts` storage is declared once and the solver picks `LocalMap`
(in-process dict) for the `local` target. Swap the catalog with `--catalog
catalogs/aws.toml` and the same code runs against DynamoDB without touching
the function bodies.
"""

from __future__ import annotations

import asyncio

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, html

from skaal import App, Store

# ── Skaal app ─────────────────────────────────────────────────────────────────

app = App("quickstart")


@app.storage(read_latency="< 5ms", durability="ephemeral")
class Counts(Store[int]):
    """Named integer counters, keyed by counter name."""


@app.function()
async def increment(name: str, by: int = 1) -> dict[str, int | str]:
    """Atomically increment a counter and return its new value."""
    new_value = await Counts.update(name, lambda current: (current or 0) + by)
    return {"name": name, "value": new_value}


@app.function()
async def reset(name: str) -> dict[str, int | str]:
    """Reset a counter to zero."""
    await Counts.delete(name)
    return {"name": name, "value": 0}


# ── Dash UI ───────────────────────────────────────────────────────────────────

dash_app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

dash_app.layout = dbc.Container(
    [
        html.H2("Skaal Quickstart — Counters"),
        html.P(
            "Each click is routed to a Skaal `@app.function`, which mutates a "
            "constraint-declared `Store[int]`.",
            className="text-muted",
        ),
        dbc.InputGroup(
            [
                dbc.InputGroupText("Counter"),
                dbc.Input(id="counter-name", value="hits", type="text"),
                dbc.InputGroupText("By"),
                dbc.Input(id="counter-by", value=1, type="number", min=1, max=100),
                dbc.Button("Increment", id="inc-btn", color="primary"),
                dbc.Button("Reset", id="reset-btn", color="secondary", outline=True),
            ],
            className="my-3",
        ),
        html.Div(id="last-result", className="lead"),
        html.Hr(),
        html.H5("All counters"),
        html.Div(id="all-counts"),
    ],
    className="py-4",
)


def _counters_view() -> html.Div:
    entries = Counts.sync_list()
    if not entries:
        return html.Div("No counters yet.", className="text-muted")
    return dbc.ListGroup(
        [
            dbc.ListGroupItem(f"{name}: {value}", className="d-flex justify-content-between")
            for name, value in sorted(entries)
        ],
        flush=True,
    )


@callback(
    Output("last-result", "children"),
    Output("all-counts", "children"),
    Input("inc-btn", "n_clicks"),
    Input("reset-btn", "n_clicks"),
    State("counter-name", "value"),
    State("counter-by", "value"),
    prevent_initial_call=True,
)
def handle_click(inc_clicks: int, reset_clicks: int, name: str, by: int) -> tuple[str, html.Div]:
    triggered = dash.callback_context.triggered_id
    name = (name or "hits").strip()
    if triggered == "inc-btn":
        result = asyncio.run(increment(name=name, by=int(by or 1)))
        message = f"Incremented {result['name']!r} to {result['value']}."
    else:
        result = asyncio.run(reset(name=name))
        message = f"Reset {result['name']!r}."
    return message, _counters_view()


# ── Mount Dash inside Skaal ───────────────────────────────────────────────────

app.mount_wsgi(dash_app.server, attribute="dash_app.server")


if __name__ == "__main__":
    from skaal.runtime.local import LocalRuntime

    runtime = LocalRuntime(app, port=8050)
    asyncio.run(runtime.serve())
