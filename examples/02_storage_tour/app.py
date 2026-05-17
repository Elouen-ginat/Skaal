"""Storage tour — KV, relational, blob, and vector storage behind one Dash UI.

This example shows the four storage tiers Skaal supports, each declared as
a constraint-bearing class:

- `Profiles` — `Store[Profile]` (KV) with a secondary index on `email`.
- `Notes` — `@app.storage(kind="relational")` SQLModel rows.
- `Attachments` — `BlobStore` for arbitrary file uploads.
- `NoteIndex` — `VectorStore[NoteDocument]` for semantic search.

The Dash UI exposes one card per tier so you can poke each surface from a
browser without writing curl commands.

Run locally:

    pip install "skaal[serve,examples,vector]" dash dash-bootstrap-components
    python examples/02_storage_tour/app.py

Then open http://localhost:8050.
"""

from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timezone
from typing import Any

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dcc, html, no_update
from pydantic import BaseModel
from sqlalchemy import desc
from sqlmodel import Field, SQLModel, select

from skaal import App, BlobStore, SecondaryIndex, Store, VectorStore, open_relational_session

# ── Domain types ──────────────────────────────────────────────────────────────


class Profile(BaseModel):
    id: str
    name: str
    email: str


class NoteDocument(BaseModel):
    id: str
    title: str
    content: str


# ── Skaal app ─────────────────────────────────────────────────────────────────

app = App("storage-tour")


@app.storage(
    read_latency="< 10ms",
    durability="persistent",
    indexes=[SecondaryIndex(name="by_email", partition_key="email", unique=True)],
)
class Profiles(Store[Profile]):
    """KV profiles with a unique secondary index on email."""


@app.storage(kind="relational", read_latency="< 20ms", durability="persistent")
class Notes(SQLModel, table=True):
    """Relational notes — one row per note."""

    id: int | None = Field(default=None, primary_key=True)
    profile_id: str = Field(index=True)
    title: str
    body: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@app.storage(kind="blob", read_latency="< 500ms", durability="durable")
class Attachments(BlobStore):
    """Arbitrary binary payloads, addressable by key."""


@app.storage(
    kind="vector",
    dim=64,
    metric="cosine",
    read_latency="< 30ms",
    durability="persistent",
)
class NoteIndex(VectorStore[NoteDocument]):
    """Semantic index over note titles and bodies."""

    __skaal_vector_text_fields__ = ("title", "content")


# ── Async helpers (each one closes over a single storage tier) ───────────────


async def _save_profile(profile_id: str, name: str, email: str) -> Profile:
    profile = Profile(id=profile_id, name=name, email=email)
    await Profiles.set(profile_id, profile)
    return profile


async def _find_by_email(email: str) -> Profile | None:
    page = await Profiles.query_index("by_email", email, limit=1)
    return page.items[0] if page.items else None


async def _add_note(profile_id: str, title: str, body: str) -> Notes:
    async with open_relational_session(Notes) as session:
        note = Notes(profile_id=profile_id, title=title, body=body)
        session.add(note)
        await session.commit()
        await session.refresh(note)
    assert note.id is not None
    doc_id = f"note:{note.id}"
    await NoteIndex.delete([doc_id])
    await NoteIndex.add([NoteDocument(id=doc_id, title=title, content=body)])
    return note


async def _list_notes(profile_id: str, limit: int = 5) -> list[Notes]:
    async with open_relational_session(Notes) as session:
        result = await session.exec(
            select(Notes)
            .where(Notes.profile_id == profile_id)
            .order_by(desc(Notes.id))
            .limit(limit)
        )
        return list(result.all())


async def _semantic_search(query: str, k: int = 3) -> list[NoteDocument]:
    return await NoteIndex.similarity_search(query, k=k)


async def _store_attachment(name: str, payload: bytes, content_type: str) -> dict[str, Any]:
    obj = await Attachments.put_bytes(f"attachments/{name}", payload, content_type=content_type)
    return {"key": obj.key, "size": obj.size, "content_type": obj.content_type}


async def _list_attachments(limit: int = 10) -> list[dict[str, Any]]:
    page = await Attachments.list_page(prefix="attachments/", limit=limit, cursor=None)
    return [{"key": item.key, "size": item.size} for item in page.items]


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# ── Dash UI ───────────────────────────────────────────────────────────────────

dash_app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True,
)

dash_app.layout = dbc.Container(
    [
        html.H2("Skaal — Storage Tour"),
        html.P(
            "Each card touches a different storage tier (KV, relational, blob, vector). "
            "All four are declared with the same `@app.storage` decorator.",
            className="text-muted",
        ),
        dbc.Row(
            [
                # ── KV ────────────────────────────────────────────────────────
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.H5("KV — Profiles"),
                                html.Small(
                                    "Store[Profile] + secondary index", className="text-muted"
                                ),
                                dbc.Input(
                                    id="kv-id", placeholder="id", type="text", className="mt-2"
                                ),
                                dbc.Input(
                                    id="kv-name", placeholder="name", type="text", className="mt-2"
                                ),
                                dbc.Input(
                                    id="kv-email",
                                    placeholder="email",
                                    type="email",
                                    className="mt-2",
                                ),
                                dbc.Button(
                                    "Save profile", id="kv-save", color="primary", className="mt-2"
                                ),
                                dbc.Button(
                                    "Look up by email",
                                    id="kv-lookup",
                                    color="secondary",
                                    outline=True,
                                    className="mt-2 ms-2",
                                ),
                                html.Div(id="kv-status", className="mt-3 small"),
                            ]
                        )
                    ),
                    md=6,
                    className="mb-4",
                ),
                # ── Relational ─────────────────────────────────────────────────
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.H5("Relational — Notes"),
                                html.Small(
                                    "SQLModel rows via open_relational_session",
                                    className="text-muted",
                                ),
                                dbc.Input(
                                    id="rel-profile",
                                    placeholder="profile id",
                                    type="text",
                                    className="mt-2",
                                ),
                                dbc.Input(
                                    id="rel-title",
                                    placeholder="title",
                                    type="text",
                                    className="mt-2",
                                ),
                                dcc.Textarea(
                                    id="rel-body",
                                    placeholder="note body",
                                    style={
                                        "width": "100%",
                                        "height": "60px",
                                        "marginTop": "0.5rem",
                                    },
                                ),
                                dbc.Button(
                                    "Save note", id="rel-save", color="primary", className="mt-2"
                                ),
                                html.Div(id="rel-list", className="mt-3 small"),
                            ]
                        )
                    ),
                    md=6,
                    className="mb-4",
                ),
                # ── Blob ───────────────────────────────────────────────────────
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.H5("Blob — Attachments"),
                                html.Small("BlobStore for arbitrary bytes", className="text-muted"),
                                dcc.Upload(
                                    id="blob-upload",
                                    children=html.Div(["Drag & drop or ", html.A("select a file")]),
                                    className="mt-2 p-3 text-center border rounded",
                                    multiple=False,
                                ),
                                html.Div(id="blob-status", className="mt-3 small"),
                                html.Div(id="blob-list", className="mt-2 small"),
                            ]
                        )
                    ),
                    md=6,
                    className="mb-4",
                ),
                # ── Vector ─────────────────────────────────────────────────────
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.H5("Vector — Semantic search"),
                                html.Small("VectorStore[NoteDocument]", className="text-muted"),
                                dbc.Input(
                                    id="vec-query",
                                    placeholder="Find notes about deploys",
                                    type="text",
                                    className="mt-2",
                                ),
                                dbc.Button(
                                    "Search", id="vec-search", color="primary", className="mt-2"
                                ),
                                html.Div(id="vec-results", className="mt-3 small"),
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


# ── KV callbacks ─────────────────────────────────────────────────────────────


@callback(
    Output("kv-status", "children"),
    Input("kv-save", "n_clicks"),
    Input("kv-lookup", "n_clicks"),
    State("kv-id", "value"),
    State("kv-name", "value"),
    State("kv-email", "value"),
    prevent_initial_call=True,
)
def kv_action(_save: int, _lookup: int, profile_id: str, name: str, email: str) -> str:
    triggered = dash.callback_context.triggered_id
    if triggered == "kv-save":
        if not (profile_id and name and email):
            return "id, name and email are required."
        profile = _run(_save_profile(profile_id, name, email))
        return f"Saved profile {profile.id} — query the index by email next."
    if not email:
        return "Enter an email to look up."
    found = _run(_find_by_email(email))
    return f"Found {found.id} ({found.name})." if found else f"No profile for {email!r}."


# ── Relational callbacks ─────────────────────────────────────────────────────


@callback(
    Output("rel-list", "children"),
    Input("rel-save", "n_clicks"),
    State("rel-profile", "value"),
    State("rel-title", "value"),
    State("rel-body", "value"),
    prevent_initial_call=True,
)
def rel_action(_save: int, profile_id: str, title: str, body: str) -> Any:
    if not (profile_id and title and body):
        return "profile id, title, and body are required."
    _run(_add_note(profile_id, title, body))
    notes = _run(_list_notes(profile_id))
    if not notes:
        return "No notes yet."
    return dbc.ListGroup(
        [
            dbc.ListGroupItem([html.B(note.title), html.Span(f" — {note.body[:60]}")])
            for note in notes
        ],
        flush=True,
    )


# ── Blob callbacks ───────────────────────────────────────────────────────────


@callback(
    Output("blob-status", "children"),
    Output("blob-list", "children"),
    Input("blob-upload", "contents"),
    State("blob-upload", "filename"),
    prevent_initial_call=True,
)
def blob_action(contents: str | None, filename: str | None) -> tuple[Any, Any]:
    if contents is None or filename is None:
        return no_update, no_update
    header, b64 = contents.split(",", 1)
    content_type = header.split(":", 1)[1].split(";", 1)[0] or "application/octet-stream"
    payload = base64.b64decode(b64)
    info = _run(_store_attachment(filename, payload, content_type))
    listing = _run(_list_attachments())
    items = dbc.ListGroup(
        [dbc.ListGroupItem(f"{item['key']} — {item['size']} bytes") for item in listing], flush=True
    )
    return f"Stored {info['key']} ({info['size']} bytes).", items


# ── Vector callbacks ─────────────────────────────────────────────────────────


@callback(
    Output("vec-results", "children"),
    Input("vec-search", "n_clicks"),
    State("vec-query", "value"),
    prevent_initial_call=True,
)
def vec_action(_clicks: int, query: str) -> Any:
    query = (query or "").strip()
    if not query:
        return "Enter a query."
    results = _run(_semantic_search(query))
    if not results:
        return "No semantic matches yet — save a few notes first."
    return dbc.ListGroup(
        [dbc.ListGroupItem([html.B(r.title), html.Span(f" — {r.content[:80]}")]) for r in results],
        flush=True,
    )


# ── Mount Dash inside Skaal ───────────────────────────────────────────────────

app.mount_wsgi(dash_app.server, attribute="dash_app.server")


if __name__ == "__main__":
    from skaal.runtime.local import LocalRuntime

    runtime = LocalRuntime(app, port=8050)
    asyncio.run(runtime.serve())
