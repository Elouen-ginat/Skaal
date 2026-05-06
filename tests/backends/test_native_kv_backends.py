from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Any

import pytest

from skaal.backends.dynamodb_backend import DynamoBackend
from skaal.backends.firestore_backend import FirestoreBackend
from skaal.backends.redis_backend import RedisBackend
from skaal.storage import _decode_cursor
from skaal.types.storage import SecondaryIndex


async def _immediate_run(fn: Any, *args: Any, **kwargs: Any) -> Any:
    return fn(*args, **kwargs)


class FakeRedisPipeline:
    def __init__(self, client: FakeRedis) -> None:
        self.client = client
        self._ops: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    async def __aenter__(self) -> FakeRedisPipeline:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    async def watch(self, *_: Any) -> None:
        return None

    async def get(self, key: str) -> Any:
        return await self.client.get(key)

    def multi(self) -> None:
        return None

    def set(self, key: str, value: str, **kwargs: Any) -> None:
        self._ops.append(("set", (key, value), kwargs))

    def delete(self, key: str) -> None:
        self._ops.append(("delete", (key,), {}))

    def zadd(self, key: str, mapping: dict[str, float]) -> None:
        self._ops.append(("zadd", (key, mapping), {}))

    def zrem(self, key: str, member: str) -> None:
        self._ops.append(("zrem", (key, member), {}))

    def rpush(self, key: str, *values: str) -> None:
        self._ops.append(("rpush", (key, *values), {}))

    async def execute(self) -> list[Any]:
        results = []
        for name, args, kwargs in self._ops:
            results.append(await getattr(self.client, name)(*args, **kwargs))
        self._ops.clear()
        return results


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.zsets: dict[str, set[str]] = {}
        self.lists: dict[str, list[str]] = {}
        self.expiry: dict[str, float] = {}
        self.lrange_calls: list[tuple[str, int, int]] = []

    def _purge(self, key: str | None = None) -> None:
        now = time.time()
        keys = [key] if key is not None else list(self.expiry)
        for candidate in keys:
            if candidate is None:
                continue
            deadline = self.expiry.get(candidate)
            if deadline is not None and deadline <= now:
                self.values.pop(candidate, None)
                self.expiry.pop(candidate, None)

    def pipeline(self, transaction: bool = True) -> FakeRedisPipeline:
        return FakeRedisPipeline(self)

    async def get(self, key: str) -> str | None:
        self._purge(key)
        return self.values.get(key)

    async def set(self, key: str, value: str, px: int | None = None) -> None:
        self.values[key] = value
        if px is None:
            self.expiry.pop(key, None)
        else:
            self.expiry[key] = time.time() + (px / 1000)

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)
        self.lists.pop(key, None)
        self.expiry.pop(key, None)

    async def zadd(self, key: str, mapping: dict[str, float]) -> None:
        self.zsets.setdefault(key, set()).update(mapping.keys())

    async def zrem(self, key: str, member: str) -> None:
        self.zsets.setdefault(key, set()).discard(member)

    async def zcard(self, key: str) -> int:
        return len(self.zsets.get(key, set()))

    async def zrange(self, key: str, start: int, end: int) -> list[str]:
        members = sorted(self.zsets.get(key, set()))
        if end == -1:
            return members[start:]
        return members[start : end + 1]

    async def zrangebylex(
        self,
        key: str,
        min_value: str,
        max_value: str,
        *,
        start: int = 0,
        num: int | None = None,
    ) -> list[str]:
        def _lower(candidate: str) -> bool:
            if min_value == "-":
                return True
            inclusive = min_value.startswith("[")
            boundary = min_value[1:]
            return candidate >= boundary if inclusive else candidate > boundary

        def _upper(candidate: str) -> bool:
            if max_value == "+":
                return True
            inclusive = max_value.startswith("[")
            boundary = max_value[1:]
            return candidate <= boundary if inclusive else candidate < boundary

        members = [m for m in sorted(self.zsets.get(key, set())) if _lower(m) and _upper(m)]
        if num is None:
            return members[start:]
        return members[start : start + num]

    async def mget(self, *keys: str) -> list[str | None]:
        for key in keys:
            self._purge(key)
        return [self.values.get(key) for key in keys]

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        self.lrange_calls.append((key, start, end))
        values = self.lists.get(key, [])
        if end == -1:
            return values[start:]
        return values[start : end + 1]

    async def rpush(self, key: str, *values: str) -> None:
        self.lists.setdefault(key, []).extend(values)

    async def incrby(self, key: str, delta: int) -> int:
        current = int(self.values.get(key, "0"))
        current += delta
        self.values[key] = str(current)
        return current

    async def aclose(self) -> None:
        return None

    async def scan_iter(self, match: str):
        for key in sorted(self.values):
            if fnmatch(key, match):
                yield key


class FakeDynamoClient:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}
        self.global_secondary_indexes: dict[str, dict[str, Any]] = {}
        self.attribute_definitions: dict[str, str] = {"pk": "S"}

    def get_item(self, *, TableName: str, Key: dict[str, Any], **_: Any) -> dict[str, Any]:
        pk = Key["pk"]["S"]
        item = self.items.get(pk)
        return {"Item": item} if item is not None else {}

    def put_item(self, *, TableName: str, Item: dict[str, Any], **_: Any) -> None:
        self.items[Item["pk"]["S"]] = Item

    def delete_item(self, *, TableName: str, Key: dict[str, Any], **_: Any) -> None:
        self.items.pop(Key["pk"]["S"], None)

    def batch_get_item(self, *, RequestItems: dict[str, Any]) -> dict[str, Any]:
        table_name, request = next(iter(RequestItems.items()))
        rows = []
        for key in request["Keys"]:
            item = self.items.get(key["pk"]["S"])
            if item is not None:
                rows.append(item)
        return {"Responses": {table_name: rows}}

    def scan(
        self,
        *,
        TableName: str,
        Limit: int,
        ExclusiveStartKey: dict[str, Any] | None = None,
        ExpressionAttributeValues: dict[str, Any] | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        prefix = None
        if ExpressionAttributeValues and ":pfx" in ExpressionAttributeValues:
            prefix = ExpressionAttributeValues[":pfx"]["S"]

        keys = sorted(self.items)
        if ExclusiveStartKey is not None:
            start_pk = ExclusiveStartKey["pk"]["S"]
            keys = [key for key in keys if key > start_pk]

        rows = []
        for key in keys:
            item = self.items[key]
            kind = item.get("kind", {}).get("S")
            if kind not in (None, "item"):
                continue
            if prefix is not None and not key.startswith(prefix):
                continue
            rows.append(item)

        page = rows[:Limit]
        response: dict[str, Any] = {"Items": page}
        if len(rows) > Limit:
            response["LastEvaluatedKey"] = {"pk": {"S": page[-1]["pk"]["S"]}}
        return response

    def describe_table(self, *, TableName: str) -> dict[str, Any]:
        return {
            "Table": {
                "AttributeDefinitions": [
                    {"AttributeName": name, "AttributeType": attr_type}
                    for name, attr_type in self.attribute_definitions.items()
                ],
                "GlobalSecondaryIndexes": list(self.global_secondary_indexes.values()),
            }
        }

    def update_table(
        self,
        *,
        TableName: str,
        AttributeDefinitions: list[dict[str, Any]],
        GlobalSecondaryIndexUpdates: list[dict[str, Any]],
    ) -> None:
        for definition in AttributeDefinitions:
            self.attribute_definitions[definition["AttributeName"]] = definition["AttributeType"]
        for update in GlobalSecondaryIndexUpdates:
            created = update["Create"]
            self.global_secondary_indexes[created["IndexName"]] = created

    def query(
        self,
        *,
        TableName: str,
        IndexName: str,
        Limit: int,
        ExpressionAttributeNames: dict[str, str],
        ExpressionAttributeValues: dict[str, Any],
        ExclusiveStartKey: dict[str, Any] | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        partition_attr = ExpressionAttributeNames["#idx_pk"]
        partition_value = ExpressionAttributeValues[":idx_pk"]["S"]
        matching = [
            item
            for item in self.items.values()
            if item.get(partition_attr, {}).get("S") == partition_value
            and item.get("kind", {}).get("S") == "item"
        ]
        sort_attr = None
        for item in matching:
            sort_attr = next((name for name in item if name.endswith("_sk")), None)
            if sort_attr is not None:
                break
        matching.sort(
            key=lambda item: (
                item.get(sort_attr, {}).get("S") if sort_attr is not None else item["pk"]["S"],
                item["pk"]["S"],
            )
        )
        if ExclusiveStartKey is not None:
            start_token = (
                ExclusiveStartKey.get(sort_attr, {}).get("S")
                if sort_attr is not None
                else ExclusiveStartKey["pk"]["S"],
                ExclusiveStartKey["pk"]["S"],
            )
            matching = [
                item
                for item in matching
                if (
                    item.get(sort_attr, {}).get("S") if sort_attr is not None else item["pk"]["S"],
                    item["pk"]["S"],
                )
                > start_token
            ]
        page = matching[:Limit]
        response: dict[str, Any] = {"Items": page}
        if len(matching) > Limit:
            last = page[-1]
            resume = {"pk": {"S": last["pk"]["S"]}}
            if partition_attr in last:
                resume[partition_attr] = last[partition_attr]
            if sort_attr is not None and sort_attr in last:
                resume[sort_attr] = last[sort_attr]
            response["LastEvaluatedKey"] = resume
        return response


@dataclass
class FakeFirestoreDoc:
    id: str
    data: dict[str, Any] | None

    @property
    def exists(self) -> bool:
        return self.data is not None

    def get(self, field: str) -> Any:
        if self.data is None:
            return None
        return self.data.get(field)

    def to_dict(self) -> dict[str, Any] | None:
        return self.data


class FakeFirestoreDocRef:
    def __init__(self, collection: FakeFirestoreCollection, doc_id: str) -> None:
        self.collection = collection
        self.doc_id = doc_id

    def get(self, transaction: Any = None) -> FakeFirestoreDoc:
        return FakeFirestoreDoc(self.doc_id, self.collection.docs.get(self.doc_id))

    def set(self, data: dict[str, Any]) -> None:
        self.collection.docs[self.doc_id] = data

    def delete(self) -> None:
        self.collection.docs.pop(self.doc_id, None)


class FakeFirestoreQuery:
    def __init__(
        self, collection: FakeFirestoreCollection, docs: list[tuple[str, dict[str, Any]]]
    ) -> None:
        self.collection = collection
        self.docs = docs
        self._order_fields: list[str] = []
        self._limit: int | None = None
        self._start_after: list[Any] | None = None

    def where(self, field: str, op: str, value: Any) -> FakeFirestoreQuery:
        def _match(doc: dict[str, Any]) -> bool:
            current = doc.get(field)
            if op == "==":
                return current == value
            if op == ">":
                return current > value
            if op == ">=":
                return current >= value
            if op == "<":
                return current < value
            raise AssertionError(f"Unsupported operator: {op}")

        return FakeFirestoreQuery(
            self.collection,
            [(doc_id, data) for doc_id, data in self.docs if _match(data)],
        )._clone(order_fields=self._order_fields, limit=self._limit, start_after=self._start_after)

    def order_by(self, field: str) -> FakeFirestoreQuery:
        return self._clone(
            order_fields=[*self._order_fields, field],
            limit=self._limit,
            start_after=self._start_after,
        )

    def limit(self, count: int) -> FakeFirestoreQuery:
        self.collection.query_limits.append(count)
        return self._clone(
            order_fields=self._order_fields,
            limit=count,
            start_after=self._start_after,
        )

    def start_after(self, values: list[Any]) -> FakeFirestoreQuery:
        return self._clone(
            order_fields=self._order_fields,
            limit=self._limit,
            start_after=list(values),
        )

    def _clone(
        self,
        *,
        order_fields: list[str],
        limit: int | None,
        start_after: list[Any] | None,
    ) -> FakeFirestoreQuery:
        clone = FakeFirestoreQuery(self.collection, list(self.docs))
        clone._order_fields = list(order_fields)
        clone._limit = limit
        clone._start_after = list(start_after) if start_after is not None else None
        return clone

    def stream(self):
        docs = list(self.docs)
        if self._order_fields:
            docs.sort(
                key=lambda item: tuple(
                    item[0] if field == "pk" else item[1].get(field) for field in self._order_fields
                )
            )
        if self._start_after is not None:
            docs = [
                item
                for item in docs
                if tuple(
                    item[0] if field == "pk" else item[1].get(field) for field in self._order_fields
                )
                > tuple(self._start_after)
            ]
        if self._limit is not None:
            docs = docs[: self._limit]
        for doc_id, data in docs:
            yield FakeFirestoreDoc(doc_id, data)


class FakeFirestoreCollection:
    def __init__(self) -> None:
        self.docs: dict[str, dict[str, Any]] = {}
        self.query_limits: list[int] = []

    def document(self, doc_id: str) -> FakeFirestoreDocRef:
        return FakeFirestoreDocRef(self, doc_id)

    def order_by(self, field: str) -> FakeFirestoreQuery:
        return FakeFirestoreQuery(self, list(self.docs.items())).order_by(field)

    def where(self, field: str, op: str, value: Any) -> FakeFirestoreQuery:
        return FakeFirestoreQuery(self, list(self.docs.items())).where(field, op, value)

    def stream(self):
        for doc_id, data in self.docs.items():
            yield FakeFirestoreDoc(doc_id, data)


class FakeFirestoreClient:
    def __init__(self) -> None:
        self.collections: dict[str, FakeFirestoreCollection] = {}

    def collection(self, name: str) -> FakeFirestoreCollection:
        return self.collections.setdefault(name, FakeFirestoreCollection())


@pytest.mark.asyncio
async def test_redis_backend_native_pages_and_indexes() -> None:
    backend = RedisBackend(namespace="test")
    client = FakeRedis()

    async def _fake_connected() -> FakeRedis:
        return client

    backend._ensure_connected = _fake_connected  # type: ignore[method-assign]
    setattr(
        backend,
        "_skaal_secondary_indexes",
        {"by_team": SecondaryIndex(name="by_team", partition_key="team", sort_key="score")},
    )

    await backend.set("m1", {"team": "alpha", "score": 10})
    await backend.set("m2", {"team": "alpha", "score": 2})
    await backend.set("m3", {"team": "alpha", "score": 30})
    client.lrange_calls.clear()

    first_page = await backend.list_page(limit=2, cursor=None)
    assert [key for key, _ in first_page.items] == ["m1", "m2"]
    assert first_page.has_more is True

    first_index_page = await backend.query_index("by_team", "alpha", limit=2, cursor=None)
    assert [item["score"] for item in first_index_page.items] == [2, 10]
    assert first_index_page.has_more is True
    first_index_cursor = _decode_cursor(first_index_page.next_cursor)
    assert first_index_cursor.get("last_member") is not None
    assert "offset" not in first_index_cursor

    second_index_page = await backend.query_index(
        "by_team",
        "alpha",
        limit=2,
        cursor=first_index_page.next_cursor,
    )
    assert [item["score"] for item in second_index_page.items] == [30]
    assert client.lrange_calls == []


@pytest.mark.asyncio
async def test_redis_backend_hides_expired_keys_from_pages() -> None:
    backend = RedisBackend(namespace="test")
    client = FakeRedis()

    async def _fake_connected() -> FakeRedis:
        return client

    backend._ensure_connected = _fake_connected  # type: ignore[method-assign]

    await backend.set("ephemeral", {"value": 1}, ttl=0.02)
    await backend.set("stable", {"value": 2})
    await asyncio.sleep(0.05)

    page = await backend.list_page(limit=10, cursor=None)
    assert [key for key, _ in page.items] == ["stable"]


@pytest.mark.asyncio
async def test_dynamo_backend_native_pages_and_indexes() -> None:
    backend = DynamoBackend("test-table")
    backend._client = FakeDynamoClient()
    backend._run = _immediate_run  # type: ignore[method-assign]
    setattr(
        backend,
        "_skaal_secondary_indexes",
        {"by_team": SecondaryIndex(name="by_team", partition_key="team", sort_key="score")},
    )

    await backend.set("m1", {"team": "alpha", "score": 10})
    await backend.set("m2", {"team": "alpha", "score": 2})
    await backend.set("m3", {"team": "beta", "score": 5})
    await backend.set("m4", {"team": "alpha", "score": 30})

    list_page = await backend.list_page(limit=2, cursor=None)
    assert [key for key, _ in list_page.items] == ["m1", "m2"]
    assert list_page.has_more is True

    scan_page = await backend.scan_page("m", limit=2, cursor=None)
    assert [key for key, _ in scan_page.items] == ["m1", "m2"]
    assert scan_page.has_more is True

    index_page = await backend.query_index("by_team", "alpha", limit=2, cursor=None)
    assert [item["score"] for item in index_page.items] == [2, 10]
    assert index_page.has_more is True
    index_cursor = _decode_cursor(index_page.next_cursor)
    assert index_cursor.get("exclusive_start_key") is not None
    assert "offset" not in index_cursor

    next_index_page = await backend.query_index(
        "by_team",
        "alpha",
        limit=2,
        cursor=index_page.next_cursor,
    )
    assert [item["score"] for item in next_index_page.items] == [30]


@pytest.mark.asyncio
async def test_dynamo_backend_filters_expired_items() -> None:
    backend = DynamoBackend("test-table")
    backend._client = FakeDynamoClient()
    backend._run = _immediate_run  # type: ignore[method-assign]

    await backend.set("ephemeral", {"value": 1}, ttl=0.02)
    await backend.set("stable", {"value": 2})
    await asyncio.sleep(0.05)

    assert await backend.get("ephemeral") is None
    page = await backend.list_page(limit=10, cursor=None)
    assert [key for key, _ in page.items] == ["stable"]


@pytest.mark.asyncio
async def test_firestore_backend_native_pages_and_indexes() -> None:
    backend = FirestoreBackend("tasks")
    backend._client = FakeFirestoreClient()
    backend._run = _immediate_run  # type: ignore[method-assign]
    setattr(
        backend,
        "_skaal_secondary_indexes",
        {"by_team": SecondaryIndex(name="by_team", partition_key="team", sort_key="score")},
    )

    await backend.set("m1", {"team": "alpha", "score": 10})
    await backend.set("m2", {"team": "alpha", "score": 2})
    await backend.set("m3", {"team": "alpha", "score": 30})
    backend._col().query_limits.clear()

    list_page = await backend.list_page(limit=2, cursor=None)
    assert [key for key, _ in list_page.items] == ["m1", "m2"]
    assert list_page.has_more is True

    scan_page = await backend.scan_page("m", limit=2, cursor=None)
    assert [key for key, _ in scan_page.items] == ["m1", "m2"]
    assert scan_page.has_more is True

    first_index_page = await backend.query_index("by_team", "alpha", limit=2, cursor=None)
    assert [item["score"] for item in first_index_page.items] == [2, 10]
    assert first_index_page.has_more is True
    assert backend._col().query_limits.count(3) >= 3

    second_index_page = await backend.query_index(
        "by_team",
        "alpha",
        limit=2,
        cursor=first_index_page.next_cursor,
    )
    assert [item["score"] for item in second_index_page.items] == [30]
    assert second_index_page.has_more is False


@pytest.mark.asyncio
async def test_firestore_backend_filters_expired_items() -> None:
    backend = FirestoreBackend("tasks")
    backend._client = FakeFirestoreClient()
    backend._run = _immediate_run  # type: ignore[method-assign]

    await backend.set("ephemeral", {"value": 1}, ttl=0.02)
    await backend.set("stable", {"value": 2})
    await asyncio.sleep(0.05)

    assert await backend.get("ephemeral") is None
    page = await backend.list_page(limit=10, cursor=None)
    assert [key for key, _ in page.items] == ["stable"]
