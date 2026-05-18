# Tutorial 4: Relational data

The mounted todo example uses more than one storage shape. This tutorial focuses on the relational tier: SQLModel entities, sessions, and how that model fits into the same app graph as `Store` and `BlobStore`.

## What You Will Learn

- how to declare a relational storage surface with SQLModel
- how to open a Skaal-managed relational session
- how the relational layer fits into the current alpha surface

## Add a Relational Model

Start from a mounted app and add a SQLModel-backed comments table:

```python
from datetime import datetime, timezone

from sqlmodel import Field, select

from skaal import App, Table

app = App("todo-comments")


@app.storage(kind="relational")
class Comment(Table, table=True):
    __tablename__ = "todo_comments"

    id: int | None = Field(default=None, primary_key=True)
    todo_id: str = Field(index=True)
    body: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@app.expose()
async def add_comment(todo_id: str, body: str) -> dict:
    async with Comment.session() as session:
        comment = Comment(todo_id=todo_id, body=body)
        session.add(comment)
        await session.commit()
        await session.refresh(comment)
    return comment.model_dump()


@app.expose()
async def list_comments(todo_id: str) -> dict:
    async with Comment.session() as session:
        result = await session.exec(
            select(Comment).where(Comment.todo_id == todo_id).order_by(Comment.id)
        )
        return {"comments": [row.model_dump() for row in result.all()]}
```

This mirrors the relational slice of `examples/todo_api/app.py` without the rest of the application around it.

## Run the app shape through Skaal

Add a minimal `skaal.toml` if you do not have one yet:

```toml
[env.local]
target = "local"
```

Then inspect the bound shape:

```bash
skaal plan todo_api:app --env local
skaal map todo_api:app --env local
```

## Migration status

!!! note "Current alpha"

    The relational model and migration engine exist in the codebase, but the public `skaal migrate` command group is not exposed in the current alpha CLI yet. This tutorial covers the declaration and session pattern that command group will operate on.

## Why this matters

`Table` keeps relational data in the same app model as the rest of your Skaal primitives. The app still declares one coherent graph even when one part of it needs SQL sessions and schema discipline.

What this gives you now:

- typed SQLModel entities
- a Skaal-managed async session boundary
- one app graph that can still be bound and rendered by environment

## Compare with the full example

The repository todo example combines two concrete storage shapes in one app:

- `Todos` in key-value storage
- `Comments` in the relational tier

That makes `examples/todo_api/app.py` the best next reference once you are comfortable with `Table.session()`.

## What this does not cover

- the public migration CLI
- advanced relational backend tuning
- deploy-time SQL operations

## Reference Links

- Read [Python API: Data Surfaces](../reference/python-api-data.md) for `Table.session()`, migration helpers, and the storage modules around them.
- Read [Configuring your environments](../cli-configuration.md) for the current environment model.

## Continue

Next: [Tutorial 5: Files and Streaming](files-and-streaming.md).
