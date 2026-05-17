# 02 — Storage Tour

A single Dash UI that exercises the four storage tiers Skaal supports:

| Card | Tier | Decorator | Class |
| --- | --- | --- | --- |
| Profiles | KV with secondary index | `@app.storage(...)` | `Store[Profile]` |
| Notes | Relational (SQLModel rows) | `@app.storage(kind="relational")` | `SQLModel` |
| Attachments | Blob (arbitrary bytes) | `@app.storage(kind="blob")` | `BlobStore` |
| Note semantic search | Vector (embeddings) | `@app.storage(kind="vector")` | `VectorStore[NoteDocument]` |

All four are declared with the same `@app.storage` decorator and routed
through the Skaal solver. Switching catalogs swaps the concrete backend
(SQLite ↔ Postgres, local files ↔ S3, Chroma ↔ pgvector) without touching
the function bodies.

## Run

```bash
pip install "skaal[serve,examples,vector]" dash dash-bootstrap-components
python examples/02_storage_tour/app.py
```

Then open [http://localhost:8050](http://localhost:8050).

## What to try

1. Save a `Profiles` row, then look it up by email — that hits the unique
   secondary index.
2. Add notes for a profile and watch them appear; they are persisted to the
   relational tier and indexed in the vector tier in the same call.
3. Upload a file and see it appear in the listing under the `attachments/`
   blob prefix.
4. Search for a note by topic — the vector store finds it even when the
   query does not match the title verbatim.
