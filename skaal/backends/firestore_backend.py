"""Cloud Firestore storage backend (google-cloud-firestore + thread pool for async compatibility)."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, List

from skaal.errors import SkaalBackendError, SkaalConflict, SkaalUnavailable
from skaal.storage import (
    _backend_index_fields,
    _cursor_identity,
    _encode_cursor,
    _field_value,
    _get_backend_indexes,
    _normalize_limit,
    _validate_cursor,
)
from skaal.types.storage import Page


class FirestoreBackend:
    """
    Google Cloud Firestore storage backend.

    Each backend instance maps to a Firestore collection named ``namespace``.
    Documents have the form: {pk: <key>, value: <json-string>}.

    Uses google-cloud-firestore in asyncio.run_in_executor for async
    compatibility (the Firestore SDK is synchronous).

    Requires google-cloud-firestore installed and Application Default
    Credentials configured (e.g. GOOGLE_APPLICATION_CREDENTIALS env var or
    running on GCP with a service account).
    """

    def __init__(
        self,
        collection: str,
        project: str | None = None,
        database: str = "(default)",
    ) -> None:
        self.collection = collection
        self.project = project
        self.database = database
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from google.cloud import firestore
            except ImportError as exc:
                raise ImportError(
                    "google-cloud-firestore is required for FirestoreBackend. "
                    "Install it with: pip install google-cloud-firestore"
                ) from exc
            kwargs: dict[str, Any] = {"database": self.database}
            if self.project is not None:
                kwargs["project"] = self.project
            self._client = firestore.Client(**kwargs)
        return self._client

    def _col(self) -> Any:
        return self._get_client().collection(self.collection)

    def _project_index_fields(self, value: Any) -> dict[str, Any]:
        projected: dict[str, Any] = {}
        if value is None:
            return projected
        for index in _get_backend_indexes(self).values():
            fields = _backend_index_fields(index)
            partition_value = _field_value(value, index.partition_key)
            if partition_value is None:
                continue
            projected[fields.partition_field] = partition_value
            if fields.sort_field is not None and index.sort_key is not None:
                projected[fields.sort_field] = _field_value(value, index.sort_key)
        return projected

    @staticmethod
    def _resume_values(doc: Any, order_fields: list[str]) -> list[Any]:
        data = doc.to_dict() or {}
        values: list[Any] = []
        for field in order_fields:
            values.append(doc.id if field == "pk" else data.get(field))
        return values

    def _bounded_live_query(
        self,
        build_query: Callable[[], Any],
        *,
        order_fields: list[str],
        limit: int,
        start_after: list[Any] | None,
    ) -> tuple[list[tuple[Any, dict[str, Any]]], bool, list[Any] | None]:
        collected: list[tuple[Any, dict[str, Any]]] = []
        current_start_after = start_after

        while len(collected) < limit + 1:
            query = build_query()
            if current_start_after is not None:
                query = query.start_after(current_start_after)
            batch_limit = limit + 1 - len(collected)
            docs = list(query.limit(batch_limit).stream())
            if not docs:
                break
            for doc in docs:
                data = doc.to_dict()
                if data is None or data.get("value") is None or self._is_expired_data(data):
                    continue
                collected.append((doc, data))
                if len(collected) >= limit + 1:
                    break
            if len(docs) < batch_limit or len(collected) >= limit + 1:
                break
            current_start_after = self._resume_values(docs[-1], order_fields)

        page_entries = collected[:limit]
        has_more = len(collected) > limit
        next_start_after = None
        if has_more and page_entries:
            next_start_after = self._resume_values(page_entries[-1][0], order_fields)
        return page_entries, has_more, next_start_after

    def _expiry_deadline(self, ttl: float | None) -> datetime | None:
        if ttl is None:
            return None
        return datetime.now(timezone.utc) + timedelta(seconds=ttl)

    def _is_expired_data(self, data: dict[str, Any] | None) -> bool:
        if not data:
            return False
        expires_at = data.get("expires_at")
        if expires_at is None:
            return False
        return expires_at <= datetime.now(timezone.utc)

    async def _run(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

    async def get(self, key: str) -> Any | None:
        def _get() -> Any | None:
            doc = self._col().document(key).get()
            if not doc.exists:
                return None
            data = doc.to_dict()
            if self._is_expired_data(data):
                return None
            return json.loads(doc.get("value"))

        return await self._run(_get)

    async def set(self, key: str, value: Any, *, ttl: float | None = None) -> None:
        def _set() -> None:
            payload = {
                "pk": key,
                "value": json.dumps(value),
                "expires_at": self._expiry_deadline(ttl),
            }
            payload.update(self._project_index_fields(value))
            self._col().document(key).set(payload)

        await self._run(_set)

    async def delete(self, key: str) -> None:
        def _del() -> None:
            self._col().document(key).delete()

        await self._run(_del)

    async def list(self) -> list[tuple[str, Any]]:
        page = await self.list_page(limit=10_000, cursor=None)
        items = list(page.items)
        while page.has_more:
            page = await self.list_page(limit=10_000, cursor=page.next_cursor)
            items.extend(page.items)
        return items

    async def list_page(self, *, limit: int, cursor: str | None):
        limit = _normalize_limit(limit)
        decoded = _validate_cursor(cursor, mode="list")

        def _list_page() -> Page[tuple[str, Any]]:
            start_after = decoded.get("start_after")
            if start_after is None and decoded.get("last_key") is not None:
                start_after = [decoded["last_key"]]
            page_docs, has_more, next_start_after = self._bounded_live_query(
                lambda: self._col().order_by("pk"),
                order_fields=["pk"],
                limit=limit,
                start_after=start_after,
            )
            items = []
            for doc, data in page_docs:
                if data and "value" in data:
                    items.append((doc.id, json.loads(data["value"])))
            next_cursor = None
            if has_more and page_docs:
                next_cursor = _encode_cursor(
                    {
                        "backend": "firestore",
                        "mode": "list",
                        "last_key": page_docs[-1][0].id,
                        "start_after": next_start_after,
                    }
                )
            return Page(items=items, next_cursor=next_cursor, has_more=has_more)

        return await self._run(_list_page)

    async def scan(self, prefix: str = "") -> List[tuple[str, Any]]:
        page = await self.scan_page(prefix=prefix, limit=10_000, cursor=None)
        items = list(page.items)
        while page.has_more:
            page = await self.scan_page(prefix=prefix, limit=10_000, cursor=page.next_cursor)
            items.extend(page.items)
        return items

    async def scan_page(self, prefix: str = "", *, limit: int, cursor: str | None):
        limit = _normalize_limit(limit)
        decoded = _validate_cursor(cursor, mode="scan", extra={"prefix": prefix})

        def _scan_page() -> Page[tuple[str, Any]]:
            start_after = decoded.get("start_after")
            if start_after is None and decoded.get("last_key") is not None:
                start_after = [decoded["last_key"]]

            def _build_query() -> Any:
                query = self._col().order_by("pk")
                if prefix:
                    query = query.where("pk", ">=", prefix).where("pk", "<", prefix + "\uffff")
                return query

            page_docs, has_more, next_start_after = self._bounded_live_query(
                _build_query,
                order_fields=["pk"],
                limit=limit,
                start_after=start_after,
            )
            items = []
            for doc, data in page_docs:
                if data and "value" in data:
                    items.append((doc.id, json.loads(data["value"])))
            next_cursor = None
            if has_more and page_docs:
                next_cursor = _encode_cursor(
                    {
                        "backend": "firestore",
                        "mode": "scan",
                        "prefix": prefix,
                        "last_key": page_docs[-1][0].id,
                        "start_after": next_start_after,
                    }
                )
            return Page(items=items, next_cursor=next_cursor, has_more=has_more)

        return await self._run(_scan_page)

    async def query_index(
        self,
        index_name: str,
        key: Any,
        *,
        limit: int,
        cursor: str | None,
    ):
        limit = _normalize_limit(limit)
        indexes = _get_backend_indexes(self)
        index = indexes.get(index_name)
        if index is None:
            raise ValueError(f"No secondary index named {index_name!r}")
        decoded = _validate_cursor(
            cursor,
            mode="index",
            extra={"index_name": index_name, "key": _cursor_identity(key)},
        )
        if decoded.get("offset") is not None:
            raise ValueError("Invalid cursor")

        def _query_index() -> Page[Any]:
            fields = _backend_index_fields(index)
            if index.sort_key is None:
                start_after = decoded.get("start_after")
                if start_after is None and decoded.get("last_key") is not None:
                    start_after = [decoded["last_key"]]
                page_docs, has_more, next_start_after = self._bounded_live_query(
                    lambda: self._col().where(fields.partition_field, "==", key).order_by("pk"),
                    order_fields=["pk"],
                    limit=limit,
                    start_after=start_after,
                )
                items = [json.loads(data["value"]) for _, data in page_docs]
                next_cursor = None
                if has_more and page_docs:
                    next_cursor = _encode_cursor(
                        {
                            "backend": "firestore",
                            "mode": "index",
                            "index_name": index_name,
                            "key": _cursor_identity(key),
                            "last_key": page_docs[-1][0].id,
                            "start_after": next_start_after,
                        }
                    )
                return Page(items=items, next_cursor=next_cursor, has_more=has_more)

            start_after = decoded.get("start_after")
            if start_after is None and decoded.get("has_last_sort"):
                start_after = [decoded.get("last_sort"), decoded.get("last_key")]
            sort_field = fields.sort_field
            if sort_field is None:
                raise ValueError(f"Secondary index {index_name!r} requires a sort field")
            try:
                page_docs, has_more, next_start_after = self._bounded_live_query(
                    lambda: self._col()
                    .where(fields.partition_field, "==", key)
                    .order_by(sort_field)
                    .order_by("pk"),
                    order_fields=[sort_field, "pk"],
                    limit=limit,
                    start_after=start_after,
                )
            except Exception as exc:
                if type(exc).__name__ == "FailedPrecondition":
                    raise SkaalBackendError(
                        f"Firestore index required for secondary index {index_name!r}"
                    ) from exc
                raise
            items = [json.loads(data["value"]) for _, data in page_docs]
            next_cursor = None
            if has_more and page_docs:
                next_cursor = _encode_cursor(
                    {
                        "backend": "firestore",
                        "mode": "index",
                        "index_name": index_name,
                        "key": _cursor_identity(key),
                        "has_last_sort": True,
                        "last_sort": page_docs[-1][1].get(sort_field),
                        "last_key": page_docs[-1][0].id,
                        "start_after": next_start_after,
                    }
                )
            return Page(items=items, next_cursor=next_cursor, has_more=has_more)

        return await self._run(_query_index)

    async def ensure_indexes(self) -> None:
        return None

    async def increment_counter(self, key: str, delta: int = 1) -> int:
        """Atomically increment a counter using a Firestore transaction."""

        def _increment() -> int:
            from google.cloud import firestore

            db = self._get_client()
            doc_ref = self._col().document(key)

            @firestore.transactional
            def _update_in_txn(txn: Any) -> int:
                doc = doc_ref.get(transaction=txn)
                current = json.loads(doc.get("value")) if doc.exists else 0
                new_value = int(current) + delta
                txn.set(doc_ref, {"pk": key, "value": json.dumps(new_value)})
                return new_value

            return _update_in_txn(db.transaction())

        return await self._run(_increment)

    async def atomic_update(
        self,
        key: str,
        fn: Callable[[Any], Any],
        *,
        ttl: float | None = None,
    ) -> Any:
        """Atomically read, apply *fn*, and write back inside a Firestore transaction.

        Firestore retries the transaction internally on contention; after the
        configured attempts are exhausted the SDK raises
        ``google.api_core.exceptions.Aborted``, which we surface as
        :class:`skaal.errors.SkaalConflict`.
        """

        def _apply() -> Any:
            try:
                from google.api_core import exceptions as g_exc
                from google.cloud import firestore
            except ImportError as exc:  # pragma: no cover
                raise SkaalUnavailable(
                    "google-cloud-firestore is required for atomic_update"
                ) from exc

            db = self._get_client()
            doc_ref = self._col().document(key)
            previous_value: Any = None

            @firestore.transactional
            def _update_in_txn(txn: Any) -> Any:
                nonlocal previous_value
                doc = doc_ref.get(transaction=txn)
                current_data = doc.to_dict() if doc.exists else None
                current = (
                    None
                    if self._is_expired_data(current_data)
                    else json.loads(doc.get("value"))
                    if doc.exists
                    else None
                )
                previous_value = current
                updated = fn(current)
                txn.set(
                    doc_ref,
                    {
                        "pk": key,
                        "value": json.dumps(updated),
                        "expires_at": self._expiry_deadline(ttl),
                        **self._project_index_fields(updated),
                    },
                )
                return updated

            try:
                updated = _update_in_txn(db.transaction())
                return updated
            except g_exc.Aborted as exc:
                raise SkaalConflict(f"atomic_update on {key!r} lost a race") from exc
            except g_exc.ServiceUnavailable as exc:
                raise SkaalUnavailable(f"Firestore unavailable: {exc}") from exc

        return await self._run(_apply)

    async def close(self) -> None:
        # google-cloud-firestore clients don't require explicit closing
        self._client = None

    def __repr__(self) -> str:
        return (
            f"FirestoreBackend(collection={self.collection!r}, "
            f"project={self.project!r}, database={self.database!r})"
        )
