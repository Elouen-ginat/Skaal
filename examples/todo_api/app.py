"""
Todo API — FastAPI mounted over Skaal compute, KV, and relational storage.

Run locally:

    uv sync --extra runtime --extra deploy --extra serve --extra examples
    skaal run examples.todo_api:app

Deploy to AWS Lambda + DynamoDB:

    skaal plan examples.todo_api:app --env prod
    skaal build examples.todo_api:app --env prod
    skaal deploy examples.todo_api:app --env prod

Try it:

    curl -s localhost:8000/todos \\
        -X POST \\
        -H "Content-Type: application/json" \\
        -d '{"id":"t1","title":"Buy groceries","description":"Milk eggs bread","tags":["home","errands"]}' | jq

    curl -s localhost:8000/todos | jq
    curl -s localhost:8000/todos/t1 | jq
    curl -s localhost:8000/todos/t1/comments \\
        -X POST \\
        -H "Content-Type: application/json" \\
        -d '{"author":"alex","body":"Remember oat milk too"}' | jq
    curl -s localhost:8000/todos/t1 -X DELETE | jq
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel
from pydantic import Field as PydanticField
from sqlmodel import Field, select

from skaal import App, Store, Table

# ── Domain models ──────────────────────────────────────────────────────────────


class Attachment(BaseModel):
    url: str
    name: str
    mime_type: str = "application/octet-stream"


class Todo(BaseModel):
    id: str
    title: str
    description: str = ""
    done: bool = False
    tags: list[str] = PydanticField(default_factory=list[str])
    attachments: list[Attachment] = PydanticField(default_factory=list[Attachment])
    created_at: str = PydanticField(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str | None = None


Todo.model_rebuild()


class CreateTodoRequest(BaseModel):
    id: str
    title: str
    description: str = ""
    tags: list[str] = PydanticField(default_factory=list[str])
    attachments: list[Attachment] = PydanticField(default_factory=list[Attachment])


class CommentRequest(BaseModel):
    author: str
    body: str


# ── App declaration ────────────────────────────────────────────────────────────

app = App("todos")
api = FastAPI(title="Skaal Todo API")


@app.storage
class Todos(Store[Todo]):
    """Persistent todo items keyed by id."""


@app.storage(kind="relational")
class Comments(Table, table=True):
    """Structured todo comments stored in the relational tier."""

    __tablename__ = "todo_comments"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    todo_id: str = Field(index=True)
    author: str
    body: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


async def _comment_rows(todo_id: str) -> list[Comments]:
    async with Comments.session() as session:
        statement = (
            select(Comments).where(Comments.todo_id == todo_id).order_by(Comments.id)  # type: ignore[arg-type]
        )
        result = await session.exec(statement)
        return list(result.all())


# ── Functions ──────────────────────────────────────────────────────────────────


@app.expose()
async def create_todo(
    id: str,
    title: str,
    description: str = "",
    tags: list[str] | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a new todo. Returns error if id already exists."""
    if await Todos.get(id) is not None:
        return {"error": f"Todo {id!r} already exists"}
    todo = Todo(
        id=id,
        title=title,
        description=description,
        tags=tags or [],
        attachments=[Attachment(**a) for a in (attachments or [])],
    )
    await Todos.set(id, todo)
    return todo.model_dump()


@app.expose()
async def get_todo(id: str) -> dict[str, Any]:
    """Fetch a single todo by id."""
    todo = await Todos.get(id)
    return todo.model_dump() if todo else {"error": f"Todo {id!r} not found"}


@app.expose()
async def complete_todo(id: str) -> dict[str, Any]:
    """Mark a todo as done."""
    todo = await Todos.get(id)
    if todo is None:
        return {"error": f"Todo {id!r} not found"}
    todo.done = True
    todo.completed_at = datetime.now(timezone.utc).isoformat()
    await Todos.set(id, todo)
    return todo.model_dump()


@app.expose()
async def add_attachment(
    id: str, url: str, name: str, mime_type: str = "application/octet-stream"
) -> dict[str, Any]:
    """Attach a file to a todo. Demonstrates nested model mutation."""
    todo = await Todos.get(id)
    if todo is None:
        return {"error": f"Todo {id!r} not found"}
    todo.attachments.append(Attachment(url=url, name=name, mime_type=mime_type))
    await Todos.set(id, todo)
    return todo.model_dump()


@app.expose()
async def add_comment(todo_id: str, author: str, body: str) -> dict[str, Any]:
    """Insert a structured comment for a todo using relational storage."""
    if await Todos.get(todo_id) is None:
        return {"error": f"Todo {todo_id!r} not found"}

    async with Comments.session() as session:
        comment = Comments(todo_id=todo_id, author=author, body=body)
        session.add(comment)
        await session.commit()
        await session.refresh(comment)
    return comment.model_dump()


@app.expose()
async def list_comments(todo_id: str) -> dict[str, Any]:
    """List structured comments for a todo from the relational store."""
    comments = await _comment_rows(todo_id)
    return {"comments": [comment.model_dump() for comment in comments], "count": len(comments)}


@app.expose()
async def list_todos(done: bool | None = None) -> dict[str, Any]:
    """List all todos, optionally filtered by done status."""
    entries = await Todos.list()
    todos = [v for _, v in entries]
    if done is not None:
        todos = [t for t in todos if t.done == done]
    return {"todos": [t.model_dump() for t in todos], "count": len(todos)}


@app.expose()
async def delete_todo(id: str) -> dict[str, Any]:
    """Delete a todo by id."""
    await Todos.delete(id)
    return {"ok": True, "deleted": id}


def _raise_for_error(
    result: dict[str, Any], *, not_found: bool = False, conflict: bool = False
) -> dict[str, Any]:
    if "error" not in result:
        return result
    if conflict:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=result["error"])
    if not_found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])


@api.get("/todos")
async def http_list_todos(done: bool | None = Query(default=None)) -> dict[str, Any]:
    return await list_todos(done=done)


@api.get("/todos/{todo_id}")
async def http_get_todo(todo_id: str) -> dict[str, Any]:
    result = await get_todo(id=todo_id)
    return _raise_for_error(result, not_found=True)


@api.post("/todos", status_code=status.HTTP_201_CREATED)
async def http_create_todo(payload: CreateTodoRequest) -> dict[str, Any]:
    result = await create_todo(**payload.model_dump(mode="json"))
    return _raise_for_error(result, conflict=True)


@api.delete("/todos/{todo_id}")
async def http_delete_todo(todo_id: str) -> dict[str, Any]:
    return await delete_todo(id=todo_id)


@api.post("/todos/{todo_id}/comments", status_code=status.HTTP_201_CREATED)
async def http_add_comment(todo_id: str, payload: CommentRequest) -> dict[str, Any]:
    result = await add_comment(todo_id=todo_id, **payload.model_dump())
    return _raise_for_error(result, not_found=True)


@api.get("/todos/{todo_id}/comments")
async def http_list_comments(todo_id: str) -> dict[str, Any]:
    return await list_comments(todo_id=todo_id)


app.mount("/", api)
