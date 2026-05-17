"""
Counter — a simple Skaal app demonstrating storage and functions.

Run locally:

    skaal run examples.counter:app

Then try:

    curl -s http://localhost:8000/ | jq
    curl -s http://localhost:8000/increment -d '{"name": "hits"}' | jq
    curl -s http://localhost:8000/increment -d '{"name": "hits", "by": 5}' | jq
    curl -s http://localhost:8000/get_count -d '{"name": "hits"}' | jq
    curl -s http://localhost:8000/list_counts | jq
    curl -s http://localhost:8000/reset -d '{"name": "hits"}' | jq
"""

from typing import Any

from skaal import App, Store

app = App("counter")


@app.storage
class Counts(Store[int]):
    """Named integer counters. Backed by SQLite locally."""


@app.expose()
async def increment(name: str, by: int = 1) -> dict[str, Any]:
    """Increment counter ``name`` by ``by`` (default 1). Returns new value."""
    current = await Counts.get(name) or 0
    new_value = current + by
    await Counts.set(name, new_value)
    return {"name": name, "value": new_value}


@app.expose()
async def get_count(name: str) -> dict[str, Any]:
    """Return the current value of counter ``name``."""
    value = await Counts.get(name) or 0
    return {"name": name, "value": value}


@app.expose()
async def reset(name: str) -> dict[str, Any]:
    """Reset counter ``name`` to zero."""
    await Counts.delete(name)
    return {"name": name, "value": 0}


@app.expose()
async def list_counts() -> dict[str, Any]:
    """Return all counters and their values."""
    entries = await Counts.list()
    return {"counts": dict(entries)}
