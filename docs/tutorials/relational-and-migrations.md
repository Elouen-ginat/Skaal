# Tutorial 4: Relational Data and Migrations

The mounted todo example in this repository uses more than one storage shape. This tutorial focuses on the relational tier: SQLModel entities, database sessions, and the migration commands that keep schema changes explicit.

## What You Will Learn

- how to declare a relational storage surface with SQLModel
- how to open a Skaal-managed relational session
- how to generate, inspect, and apply schema migrations

## Add a Relational Model

Start from a mounted app and add a SQLModel-backed comments table:

```python
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel, select

from skaal import App, open_relational_session

app = App("todo-comments")


@app.storage(kind="relational", read_latency="< 20ms", durability="persistent")
class Comment(SQLModel, table=True):
    __tablename__ = "todo_comments"

    id: int | None = Field(default=None, primary_key=True)
    todo_id: str = Field(index=True)
    body: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@app.function()
async def add_comment(todo_id: str, body: str) -> dict:
    async with open_relational_session(Comment) as session:
        comment = Comment(todo_id=todo_id, body=body)
        session.add(comment)
        await session.commit()
        await session.refresh(comment)
    return comment.model_dump()


@app.function()
async def list_comments(todo_id: str) -> dict:
    async with open_relational_session(Comment) as session:
        result = await session.exec(
            select(Comment).where(Comment.todo_id == todo_id).order_by(Comment.id)
        )
        return {"comments": [row.model_dump() for row in result.all()]}
```

This mirrors the relational slice of `examples/02_todo_api/app.py` without the rest of the application around it.

## Configure the Project App Reference

The relational migration commands resolve the app from project settings. Make sure `pyproject.toml` contains:

```toml
[tool.skaal]
app = "todo_api:app"
```

If you created the project with `skaal init`, that setting already exists.

## Run Migrations

Generate a revision from the current model set:

```bash
skaal migrate relational autogenerate -m "create todo comments"
```

Apply it:

```bash
skaal migrate relational upgrade
```

Inspect the state:

```bash
skaal migrate relational current
skaal migrate relational history
```

Check for drift after another round of model edits:

```bash
skaal migrate relational check
```

Print the SQL without applying it:

```bash
skaal migrate relational upgrade --dry-run
```

Roll back one revision if you need to:

```bash
skaal migrate relational downgrade -1
```

## Why This Matters

The migration flow keeps schema change explicit. That gives you a real history of the relational tier instead of silently mutating local SQLite state and hoping production will match later.

This is also the place where Skaal's planner model helps: the relational surface stays attached to your app model, but the backing relational backend can still change by target and catalog.

## Compare With the Full Example

The repository todo example combines three storage shapes in one application:

- `Todos` in key-value storage
- `Comments` in the relational tier
- `TodoSearchIndex` in the vector tier

That makes `examples/02_todo_api/app.py` the best next reference once you are comfortable with the migration commands.

## Reference Links

- Read [Python API: Data Surfaces](../reference/python-api-data.md) for `open_relational_session`, relational helpers, and the storage modules around them.
- Read [CLI Configuration](../cli-configuration.md) for the `pyproject.toml` settings that let migration commands resolve your app implicitly.

## Continue

Next: [Tutorial 5: Files and Streaming](files-and-streaming.md).
