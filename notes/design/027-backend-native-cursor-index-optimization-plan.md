# ADR 027 — Backend-native Cursor and Index Optimization Plan

**Status:** Proposed
**Date:** 2026-05-05
**Related:** [user_gaps.md §B.2](../user_gaps.md#b2-kv-store-and-storage-tiers), [ADR 015](015-store-surface-implementation-plan.md), [ADR 025](025-per-row-ttl-implementation-plan.md)

## Goal

Keep the `Store[T]` API from ADR 015 unchanged, but make the hot paging and secondary-index paths use backend-native resume and indexing primitives wherever the backend can support them.

Today the public surface is good enough:

1. `list_page(...)`
2. `scan_page(prefix=...)`
3. `query_index(index_name, key, ...)`

The remaining gap is implementation quality, not API shape. Several backends still compute pages by loading too much state into the runtime before slicing, and the SQL backends still answer declared secondary-index queries without provisioning matching native indexes. That makes the surface correct but leaves obvious performance cliffs once datasets stop being toy-sized.

This pass closes the P1 scalability gap in [user_gaps.md §B.2](../user_gaps.md#b2-kv-store-and-storage-tiers) without reopening the broader storage API design.

## Why this is next

Most of the earlier storage/runtime top-list work is now landed:

1. ADR 015 added the `Store[T]` page and secondary-index surface.
2. ADR 016 added blob storage.
3. ADR 025 added TTL-aware read and write behaviour.

That means the next storage pass should not add another user-visible abstraction. It should harden the one already shipped.

This work is a good next slice because it is:

1. narrow enough to implement without changing the public API
2. directly user-visible on larger datasets
3. a prerequisite for saying the built-in backends scale similarly instead of only offering feature parity

## Scope

This pass includes:

1. backend-native resume tokens for the remaining non-native page paths
2. backend-native secondary-index lookup where the backend has a first-class index primitive
3. native SQL index provisioning for declared `SecondaryIndex` metadata
4. compatibility fallbacks so existing data remains readable during rollout
5. tests that enforce bounded page reads instead of full materialization

This pass does **not** include:

1. changes to the public `Store[T]` API
2. range predicates or richer query DSL on `query_index(...)`
3. full-text search, hybrid search, or relational read replicas
4. changes to the solver's backend selection semantics
5. removal of the generic in-memory helper path for `LocalMap`

## Current facts

The current backend state is mixed, not uniformly bad.

### Already reasonably native

1. `SqliteBackend.list_page(...)` and `scan_page(...)` use ordered SQL with `LIMIT` and a key resume token.
2. `PostgresBackend.list_page(...)` and `scan_page(...)` do the same with ordered SQL and cursor state.
3. `DynamoBackend.list_page(...)` and `scan_page(...)` already use `scan(..., ExclusiveStartKey=...)` and carry the native resume token in Skaal's opaque cursor.

### Still materializing too much

1. `RedisBackend.query_index(...)` reads the full index bucket with `LRANGE 0 -1`, then `MGET`s all referenced payloads, removes stale keys, and only then slices the page.
2. `DynamoBackend.query_index(...)` reads the whole bucket record set, performs a batch get for all members, and paginates with an in-memory offset.
3. `FirestoreBackend.list_page(...)` and `scan_page(...)` stream the query, build a full Python list, and then slice.
4. `FirestoreBackend.query_index(...)` reads the whole bucket, loads referenced documents one by one, and paginates with an in-memory offset.

### Correct but not yet native-indexed

1. `SqliteBackend.query_index(...)` executes JSON-expression queries against the KV table, but the declared `SecondaryIndex` metadata is not turned into matching SQLite indexes.
2. `PostgresBackend.query_index(...)` does the same against `jsonb`, again without provisioning matching SQL indexes from the declaration.

The result is that the same user code can be cheap on one backend and unexpectedly expensive on another.

## Decision

Keep one Skaal cursor format and one Skaal index declaration surface, but let each backend encode native resume state inside that opaque cursor and use native indexing where available.

The design rules are:

1. user-facing `Page` and `SecondaryIndex` stay unchanged
2. cursors remain opaque base64 JSON owned by Skaal
3. backends may store native resume state inside that JSON
4. native query/index paths should be the default when the backend can support them
5. the generic bucket-materialization path remains only as a compatibility fallback or for `LocalMap`

## Target backend outcomes

| Backend | `list_page` / `scan_page` target | `query_index` target |
|---|---|---|
| `LocalMap` | keep current in-memory helper | keep current in-memory helper |
| `SqliteBackend` | keep ordered SQL path | add SQLite expression indexes for each declared `SecondaryIndex` |
| `PostgresBackend` | keep ordered SQL path | add Postgres expression indexes for each declared `SecondaryIndex` |
| `RedisBackend` | tighten sorted-key traversal to bounded fetch loops | replace full-bucket list scans with native sorted-set or lex-range pagination |
| `DynamoBackend` | keep native `ExclusiveStartKey` scan path | move from bucket materialization to native GSI query + native resume token |
| `FirestoreBackend` | move from stream-then-slice to query `limit` + `start_after` | move from bucket materialization to native field query + cursor resume |

## Cursor contract

The public cursor remains opaque, but the payload becomes more explicit about backend-native state.

Example payloads:

```json
{
  "backend": "dynamodb",
  "mode": "index",
  "index_name": "by_org",
  "key": "org_123",
  "exclusive_start_key": {"pk": {"S": "..."}, "gsi1pk": {"S": "..."}}
}
```

```json
{
  "backend": "firestore",
  "mode": "scan",
  "prefix": "user_",
  "start_after": ["user_0042"]
}
```

```json
{
  "backend": "redis",
  "mode": "index",
  "index_name": "by_org_created",
  "key": "org_123",
  "last_member": "2026-05-05T10:00:00Z|user_0042"
}
```

The cursor codec in `skaal/backends/base.py` already owns encode/decode helpers. This pass extends the payload shapes but does not change the user contract.

## Backend designs

### SQLite

The read-page path is already acceptable. The missing piece is native support for declared secondary indexes.

Plan:

1. Keep `query_index(...)` SQL semantics and cursor shape.
2. On backend wire/connect, inspect declared `SecondaryIndex` metadata.
3. Create SQLite expression indexes such as:

```sql
CREATE INDEX IF NOT EXISTS skaal_kv_idx_<ns>_<name>
ON kv (
  ns,
  json_extract(value, '$.<partition_key>'),
  json_extract(value, '$.<sort_key>'),
  key
)
```

4. For partition-only indexes, omit the sort expression and index `(ns, json_extract(...), key)`.
5. Keep TTL filtering in the query predicate; do not attempt a time-dependent partial index.

This preserves current semantics while making the common query path use native SQLite indexing instead of JSON scans.

### Postgres

The read-page path is already acceptable. The missing piece is again native SQL indexes for declared `SecondaryIndex` metadata.

Plan:

1. Keep the current ordered SQL query shape and cursor logic.
2. Provision expression indexes on the JSONB value payload, for example:

```sql
CREATE INDEX IF NOT EXISTS skaal_kv_idx_<name>
ON skaal_kv (
  ns,
  (value #>> '{org_id}'),
  (value #>> '{created_at}'),
  key
)
```

3. Use deterministic naming so repeated runtime startup is idempotent.
4. Continue to filter expired rows in the query, not in the index definition.

This gives Postgres the same declared-index ergonomics as today, but without forcing sequential JSONB evaluation at query time.

### Redis

The main key listing path already uses a sorted key index, but `query_index(...)` still loads an entire logical bucket before slicing.

Plan:

1. Replace per-bucket list storage with native sorted sets for declared indexes.
2. For partition-only indexes, use a lexicographically ordered member encoding over primary key.
3. For partition+sort indexes, encode members as `<sortable>|<pk>` and page by `ZRANGEBYLEX` or score/member resume depending on the normalized type.
4. Keep the current bucket list writer as a temporary compatibility read path during rollout.
5. On read, prefer the sorted-set path; if absent, fall back to the old list bucket and opportunistically migrate.

This removes the `LRANGE 0 -1` + full `MGET` pattern from hot index queries.

### DynamoDB

`list_page(...)` and `scan_page(...)` already carry the native resume token, but `query_index(...)` still behaves like a bucket lookup layered on top of DynamoDB rather than a DynamoDB query.

Plan:

1. For each declared `SecondaryIndex`, project synthetic attributes onto item rows, for example `idx_<name>_pk` and `idx_<name>_sk`.
2. Provision matching GSIs when the backend initializes a table.
3. Switch `query_index(...)` to `Query` against that GSI with `LastEvaluatedKey` carried in the Skaal cursor.
4. Keep the existing bucket records readable during migration, but stop using them for new queries once the GSI exists.
5. Add a lightweight backfill helper for existing rows in test/dev environments; document that production backfill is an operator step.

This aligns DynamoDB with the query model it already provides natively.

### Firestore

Firestore is the furthest from the desired end state today.

Plan:

1. Stop using `query.stream()` followed by full Python slicing for `list_page(...)` and `scan_page(...)`.
2. Use `order_by("pk")`, `limit(limit + 1)`, and `start_after(...)` in the underlying query instead.
3. For declared `SecondaryIndex` metadata, dual-write extracted index fields onto the main document, for example `idx_<name>_pk` and `idx_<name>_sk`.
4. Switch `query_index(...)` to native Firestore field queries with `where(...)`, `order_by(...)`, `limit(...)`, and `start_after(...)`.
5. If a required composite Firestore index is missing, raise a Skaal-shaped error that names the declared `SecondaryIndex` and the missing Firestore index requirement.

This removes the full-materialization behaviour and lets Firestore page like a document store instead of like a local Python collection.

## Metadata and wiring changes

This pass needs one small piece of shared backend metadata: every backend already receives declared `SecondaryIndex` information through wiring, but the SQL and document backends need an explicit "index provisioning done" phase.

Add a backend hook in `skaal/backends/base.py`:

```python
async def ensure_indexes(self) -> None: ...
```

Rules:

1. default no-op for backends that do not provision anything
2. called once from `Store.wire(...)` or backend connect/startup path
3. safe to call repeatedly

This keeps index provisioning close to the backend instead of smearing it across solver or deploy code.

## Compatibility and rollout

The rollout should be incremental rather than all-at-once.

### Phase 1

1. Firestore native page queries
2. SQLite/Postgres expression-index provisioning
3. tests proving current API behaviour is unchanged

### Phase 2

1. Redis native sorted-set index path with compatibility fallback
2. DynamoDB GSI-backed query path with cursor resume

### Phase 3

1. optional cleanup helpers to remove legacy bucket records once migration is complete
2. docs/examples showing index-heavy access patterns on multiple backends

This order lands the smallest high-value wins first and keeps the higher-risk Redis/Dynamo migration work isolated.

## Testing

Add focused coverage under `tests/storage/`.

Required tests:

1. `query_index(...)` on Redis does not issue a full-bucket scan for page 2 and beyond.
2. `query_index(...)` on DynamoDB carries a native resume token instead of an in-memory offset.
3. `list_page(...)` and `scan_page(...)` on Firestore request bounded documents with `limit + 1` semantics.
4. SQLite and Postgres create deterministic native indexes for declared `SecondaryIndex` metadata.
5. TTL-filtered rows do not leak back into the optimized paths.
6. Old cursor payloads remain readable during the transition where practical; otherwise Skaal raises a clear invalid-cursor error rather than silently mispaging.

Where the test backend is mocked rather than fully live, assert on backend method inputs and the encoded cursor payload, not just on returned items.

## Files touched

Expected implementation footprint:

1. `skaal/backends/base.py`
2. `skaal/backends/sqlite_backend.py`
3. `skaal/backends/postgres_backend.py`
4. `skaal/backends/redis_backend.py`
5. `skaal/backends/dynamodb_backend.py`
6. `skaal/backends/firestore_backend.py`
7. `skaal/storage.py`
8. `tests/storage/`
9. `docs/user_gaps.md`
10. at least one example app using declared secondary indexes across more than a trivial dataset

## Success criteria

This ADR is complete when all of the following are true:

1. `Store[T]` user code does not change.
2. Firestore and Redis no longer materialize entire logical result sets just to serve one page.
3. DynamoDB index queries use native GSI query semantics and native resume state.
4. SQLite and Postgres provision native indexes from declared `SecondaryIndex` metadata.
5. Benchmarks or focused instrumentation show bounded per-page work instead of dataset-sized work on the optimized paths.
