# Tutorial 2: Add a FastAPI Surface

The first tutorial used Skaal's generated local HTTP endpoints directly. That is useful for learning, but real applications usually want a proper public HTTP framework for routing, validation, auth, and OpenAPI generation. Skaal's job is to execute the application work behind those routes.

## What You Will Learn

- how to mount FastAPI on top of a Skaal app
- when to call `app.invoke(...)` instead of the decorated function directly
- how storage and compute stay inside Skaal while your public routes stay inside FastAPI

## Install FastAPI Support

```bash
pip install "skaal[serve,fastapi]"
```

## Mount FastAPI

Create `todo_api.py` with a simple todo store and a mounted FastAPI app:

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from skaal import App, Store

app = App("todo-api")
api = FastAPI(title="Tutorial Todo API")


class Todo(BaseModel):
    id: str
    title: str
    done: bool = False


class CreateTodoRequest(BaseModel):
    id: str
    title: str


@app.storage(read_latency="< 10ms", durability="persistent")
class Todos(Store[Todo]):
    pass


@app.function()
async def create_todo(id: str, title: str) -> dict:
    if await Todos.get(id) is not None:
        return {"error": f"Todo {id!r} already exists"}
    todo = Todo(id=id, title=title)
    await Todos.set(id, todo)
    return todo.model_dump()


@app.function()
async def list_todos() -> dict:
    entries = await Todos.list()
    return {"todos": [todo.model_dump() for _, todo in entries]}


@api.get("/todos")
async def http_list_todos() -> dict:
    return await app.invoke(list_todos)


@api.post("/todos", status_code=201)
async def http_create_todo(payload: CreateTodoRequest) -> dict:
    result = await app.invoke(create_todo, **payload.model_dump())
    if "error" in result:
        raise HTTPException(status_code=409, detail=result["error"])
    return result


app.mount_asgi(api, attribute="api")
```

Two boundaries matter here:

- FastAPI owns the public routes.
- Skaal owns the application work and storage surfaces.

## Run the API

```bash
skaal run todo_api:app --persist
```

Using `--persist` here is helpful because the todo list survives restarts while you iterate.

## Call the Public Routes

Create a todo through FastAPI:

```bash
curl -s http://127.0.0.1:8000/todos \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"id": "t1", "title": "Write docs"}'
```

List the collection:

```bash
curl -s http://127.0.0.1:8000/todos
```

## Why `app.invoke(...)` Matters

`app.invoke(...)` routes the call through Skaal's runtime boundary. That means the same call site can later pick up retry policies, circuit breakers, bulkheads, or rate limits without rewriting the FastAPI handler.

Calling the decorated function directly can still be valid for in-process code, but `app.invoke(...)` is the safer default at the HTTP boundary.

Skaal also reserves `/_skaal/*` for internal runtime traffic. Your mounted ASGI app owns the public paths outside that namespace.

## Compare With the Full Example

The repository version at `examples/02_todo_api/app.py` grows this pattern into a more complete application:

- key-value storage for todo items
- relational storage for comments
- vector search for semantic lookup
- FastAPI routes that call Skaal compute

That is the example this tutorial sequence builds toward.

## Reference Links

- Read [Python API: Core and Decorators](../reference/python-api-core.md) for `App`, `Module`, and the decorator surface.
- Read [Python API: Data Surfaces](../reference/python-api-data.md) for `Store` and the related storage APIs.
- Read [HTTP Integration](../http.md) for the higher-level mounted ASGI model.

## Continue

Next: [Tutorial 3: Plan, Build, and Deploy](planning-and-deployment.md).
