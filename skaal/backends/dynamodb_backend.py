"""DynamoDB storage backend (boto3 + thread pool for async compatibility)."""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, Callable, List

from skaal.errors import SkaalConflict, SkaalUnavailable
from skaal.storage import (
    _backend_index_fields,
    _cursor_identity,
    _encode_cursor,
    _field_value,
    _get_backend_indexes,
    _lex_sort_token,
    _normalize_limit,
    _validate_cursor,
)
from skaal.types.storage import CursorPayload, Page


class DynamoBackend:
    """
    AWS DynamoDB storage backend.

    Table schema: pk (String, hash key), value (String, JSON-encoded).
    Uses boto3 in asyncio.run_in_executor for async compatibility.
    Requires boto3 installed and AWS credentials configured.

    All methods delegate to synchronous boto3 calls via run_in_executor
    to avoid blocking the event loop.
    """

    def __init__(self, table_name: str, region: str = "us-east-1") -> None:
        self.table_name = table_name
        self.region = region
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import boto3
            except ImportError as exc:
                raise ImportError(
                    "boto3 is required for DynamoBackend. " "Install it with: pip install boto3"
                ) from exc
            self._client = boto3.client("dynamodb", region_name=self.region)
        return self._client

    def _secondary_index_name(self, index_name: str) -> str:
        token = re.sub(r"[^0-9A-Za-z_]+", "_", index_name).strip("_")
        return f"skaal_idx_{token or 'default'}"

    @staticmethod
    def _index_partition_value(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)

    def _project_index_attributes(self, value: Any) -> dict[str, dict[str, str]]:
        projected: dict[str, dict[str, str]] = {}
        if value is None:
            return projected
        for index in _get_backend_indexes(self).values():
            fields = _backend_index_fields(index)
            partition_value = _field_value(value, index.partition_key)
            if partition_value is None:
                continue
            projected[fields.partition_field] = {"S": self._index_partition_value(partition_value)}
            if fields.sort_field is not None and index.sort_key is not None:
                projected[fields.sort_field] = {
                    "S": _lex_sort_token(_field_value(value, index.sort_key))
                }
        return projected

    def _index_resume_key(self, item: dict[str, Any], index: Any) -> dict[str, Any]:
        fields = _backend_index_fields(index)
        resume_key = {"pk": item["pk"]}
        if fields.partition_field in item:
            resume_key[fields.partition_field] = item[fields.partition_field]
        if fields.sort_field is not None and fields.sort_field in item:
            resume_key[fields.sort_field] = item[fields.sort_field]
        return resume_key

    def _ttl_attribute(self, ttl: float | None) -> dict[str, str] | None:
        if ttl is None:
            return None
        return {"N": str(int(time.time() + ttl))}

    def _is_expired_item(self, item: dict[str, Any] | None) -> bool:
        if item is None:
            return False
        expires_at = item.get("expires_at", {}).get("N")
        return expires_at is not None and float(expires_at) <= time.time()

    async def _run(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

    async def get(self, key: str) -> Any | None:
        client = self._get_client()

        def _get() -> Any | None:
            resp = client.get_item(
                TableName=self.table_name,
                Key={"pk": {"S": key}},
            )
            item = resp.get("Item")
            if item is None:
                return None
            if self._is_expired_item(item):
                return None
            return json.loads(item["value"]["S"])

        return await self._run(_get)

    async def set(self, key: str, value: Any, *, ttl: float | None = None) -> None:
        client = self._get_client()

        def _put() -> None:
            item = {
                "pk": {"S": key},
                "kind": {"S": "item"},
                "value": {"S": json.dumps(value)},
            }
            item.update(self._project_index_attributes(value))
            expires_at = self._ttl_attribute(ttl)
            if expires_at is not None:
                item["expires_at"] = expires_at
            client.put_item(TableName=self.table_name, Item=item)

        await self._run(_put)

    async def delete(self, key: str) -> None:
        client = self._get_client()

        def _del() -> None:
            client.delete_item(
                TableName=self.table_name,
                Key={"pk": {"S": key}},
            )

        await self._run(_del)

    async def list(self) -> list[tuple[str, Any]]:
        page = await self.list_page(limit=10_000, cursor=None)
        items = list(page.items)
        while page.has_more:
            page = await self.list_page(limit=10_000, cursor=page.next_cursor)
            items.extend(page.items)
        return items

    async def list_page(self, *, limit: int, cursor: str | None):
        return await self._scan_page_native(prefix=None, limit=limit, cursor=cursor, mode="list")

    async def scan(self, prefix: str = "") -> List[tuple[str, Any]]:
        page = await self.scan_page(prefix=prefix, limit=10_000, cursor=None)
        items = list(page.items)
        while page.has_more:
            page = await self.scan_page(prefix=prefix, limit=10_000, cursor=page.next_cursor)
            items.extend(page.items)
        return items

    async def scan_page(self, prefix: str = "", *, limit: int, cursor: str | None):
        return await self._scan_page_native(
            prefix=prefix,
            limit=limit,
            cursor=cursor,
            mode="scan",
        )

    async def _scan_page_native(
        self,
        *,
        prefix: str | None,
        limit: int,
        cursor: str | None,
        mode: str,
    ) -> Page[tuple[str, Any]]:
        client = self._get_client()
        limit = _normalize_limit(limit)
        extra = {"prefix": prefix or ""} if mode == "scan" else None
        decoded = _validate_cursor(cursor, mode=mode, extra=extra)

        def _page() -> Page[tuple[str, Any]]:
            collected: list[tuple[str, Any]] = []
            last_key = decoded.get("exclusive_start_key") if decoded else None
            while len(collected) < limit + 1:
                kwargs: dict[str, Any] = {
                    "TableName": self.table_name,
                    "Limit": limit + 1 - len(collected),
                    "FilterExpression": "(attribute_not_exists(#kind) OR #kind = :item)"
                    + (" AND begins_with(pk, :pfx)" if prefix else ""),
                    "ExpressionAttributeNames": {"#kind": "kind"},
                    "ExpressionAttributeValues": {":item": {"S": "item"}},
                }
                if prefix:
                    kwargs["ExpressionAttributeValues"][":pfx"] = {"S": prefix}
                if last_key is not None:
                    kwargs["ExclusiveStartKey"] = last_key
                resp = client.scan(**kwargs)
                for item in resp.get("Items", []):
                    if "value" not in item:
                        continue
                    if self._is_expired_item(item):
                        continue
                    collected.append((item["pk"]["S"], json.loads(item["value"]["S"])))
                    if len(collected) >= limit + 1:
                        break
                last_key = resp.get("LastEvaluatedKey")
                if not last_key:
                    break

            page_items = collected[:limit]
            has_more = len(collected) > limit or bool(last_key)
            next_cursor = None
            if has_more and last_key is not None:
                payload = {"mode": mode, "exclusive_start_key": last_key}
                if prefix is not None and mode == "scan":
                    payload["prefix"] = prefix
                next_cursor = _encode_cursor(payload)
            return Page(items=page_items, next_cursor=next_cursor, has_more=has_more)

        return await self._run(_page)

    async def query_index(
        self,
        index_name: str,
        key: Any,
        *,
        limit: int,
        cursor: str | None,
    ):
        client = self._get_client()
        limit = _normalize_limit(limit)
        decoded = _validate_cursor(
            cursor,
            mode="index",
            extra={"index_name": index_name, "key": _cursor_identity(key)},
        )
        indexes = _get_backend_indexes(self)
        index = indexes.get(index_name)
        if index is None:
            raise ValueError(f"No secondary index named {index_name!r}")
        if decoded.get("offset") is not None:
            raise ValueError("Invalid cursor")
        return await self._run(
            self._query_index_native, client, index, index_name, key, limit, decoded
        )

    def _query_index_native(
        self,
        client: Any,
        index: Any,
        index_name: str,
        key: Any,
        limit: int,
        decoded: CursorPayload,
    ) -> Page[Any]:
        collected: list[tuple[dict[str, Any], Any]] = []
        exclusive_start_key = decoded.get("exclusive_start_key") if decoded else None
        fields = _backend_index_fields(index)

        while len(collected) < limit + 1:
            kwargs: dict[str, Any] = {
                "TableName": self.table_name,
                "IndexName": self._secondary_index_name(index_name),
                "KeyConditionExpression": "#idx_pk = :idx_pk",
                "ExpressionAttributeNames": {"#idx_pk": fields.partition_field},
                "ExpressionAttributeValues": {":idx_pk": {"S": self._index_partition_value(key)}},
                "Limit": limit + 1 - len(collected),
                "ScanIndexForward": True,
            }
            if exclusive_start_key is not None:
                kwargs["ExclusiveStartKey"] = exclusive_start_key
            response = client.query(**kwargs)
            raw_items = response.get("Items", [])
            last_evaluated_key = response.get("LastEvaluatedKey")
            for item in raw_items:
                if item.get("kind", {}).get("S") not in (None, "item"):
                    continue
                if "value" not in item or self._is_expired_item(item):
                    continue
                collected.append((item, json.loads(item["value"]["S"])))
                if len(collected) >= limit + 1:
                    break
            if len(collected) >= limit + 1 or last_evaluated_key is None:
                break
            exclusive_start_key = last_evaluated_key

        page_entries = collected[:limit]
        has_more = len(collected) > limit
        next_cursor = None
        if has_more and page_entries:
            next_cursor = _encode_cursor(
                {
                    "backend": "dynamodb",
                    "mode": "index",
                    "index_name": index_name,
                    "key": _cursor_identity(key),
                    "exclusive_start_key": self._index_resume_key(page_entries[-1][0], index),
                }
            )
        return Page(
            items=[item for _, item in page_entries],
            next_cursor=next_cursor,
            has_more=has_more,
        )

    async def ensure_indexes(self) -> None:
        client = self._get_client()
        if not hasattr(client, "describe_table") or not hasattr(client, "update_table"):
            return None

        def _ensure() -> None:
            indexes = _get_backend_indexes(self)
            if not indexes:
                return None
            table = client.describe_table(TableName=self.table_name).get("Table", {})
            existing = {
                gsi.get("IndexName")
                for gsi in table.get("GlobalSecondaryIndexes", [])
                if gsi.get("IndexName")
            }
            defined = {
                attr.get("AttributeName")
                for attr in table.get("AttributeDefinitions", [])
                if attr.get("AttributeName")
            }
            staged = set(defined)
            attribute_definitions: list[dict[str, str]] = []
            pending_updates: list[dict[str, Any]] = []
            for index in indexes.values():
                fields = _backend_index_fields(index)
                native_index_name = self._secondary_index_name(index.name)
                if native_index_name in existing:
                    continue
                for attribute_name in (fields.partition_field, fields.sort_field):
                    if attribute_name is None or attribute_name in staged:
                        continue
                    staged.add(attribute_name)
                    attribute_definitions.append(
                        {"AttributeName": attribute_name, "AttributeType": "S"}
                    )
                key_schema = [{"AttributeName": fields.partition_field, "KeyType": "HASH"}]
                if fields.sort_field is not None:
                    key_schema.append({"AttributeName": fields.sort_field, "KeyType": "RANGE"})
                pending_updates.append(
                    {
                        "Create": {
                            "IndexName": native_index_name,
                            "KeySchema": key_schema,
                            "Projection": {"ProjectionType": "ALL"},
                            "ProvisionedThroughput": {
                                "ReadCapacityUnits": 5,
                                "WriteCapacityUnits": 5,
                            },
                        }
                    }
                )
            if pending_updates:
                client.update_table(
                    TableName=self.table_name,
                    AttributeDefinitions=attribute_definitions,
                    GlobalSecondaryIndexUpdates=pending_updates,
                )

        await self._run(_ensure)

    async def increment_counter(self, key: str, delta: int = 1) -> int:
        """Atomically increment a counter using DynamoDB UpdateItem.

        Uses a single ``UpdateItem`` with ``if_not_exists`` to handle both
        the create-if-missing and increment cases atomically — no separate
        ``put_item`` needed.
        """
        client = self._get_client()

        def _increment() -> int:
            resp = client.update_item(
                TableName=self.table_name,
                Key={"pk": {"S": key}},
                UpdateExpression="SET #v = if_not_exists(#v, :zero) + :d",
                ExpressionAttributeNames={"#v": "counter"},
                ExpressionAttributeValues={
                    ":zero": {"N": "0"},
                    ":d": {"N": str(delta)},
                },
                ReturnValues="ALL_NEW",
            )
            new_val = resp["Attributes"]["counter"]
            if isinstance(new_val, dict) and "N" in new_val:
                return int(new_val["N"])
            return int(new_val)

        return await self._run(_increment)

    async def atomic_update(
        self,
        key: str,
        fn: Callable[[Any], Any],
        *,
        ttl: float | None = None,
        max_retries: int = 8,
    ) -> Any:
        """Atomically read-modify-write using an optimistic ``version`` attribute.

        Each row carries a monotonic ``ver`` number; writes use
        ``ConditionExpression`` to only succeed when the version hasn't
        changed since the read.  After *max_retries* contended attempts a
        :class:`skaal.errors.SkaalConflict` is raised.
        """
        try:
            import botocore.exceptions
        except ImportError as exc:  # pragma: no cover — boto3 always ships botocore
            raise SkaalUnavailable("botocore is required for DynamoBackend") from exc

        client = self._get_client()

        def _once() -> tuple[bool, Any]:
            resp = client.get_item(
                TableName=self.table_name,
                Key={"pk": {"S": key}},
                ConsistentRead=True,
            )
            item = resp.get("Item")
            if item is None:
                current: Any = None
                current_ver = 0
            else:
                current = None if self._is_expired_item(item) else json.loads(item["value"]["S"])
                current_ver = int(item.get("ver", {}).get("N", "0"))

            updated = fn(current)
            next_ver = current_ver + 1
            item_payload = {
                "pk": {"S": key},
                "kind": {"S": "item"},
                "value": {"S": json.dumps(updated)},
                "ver": {"N": str(next_ver)},
            }
            item_payload.update(self._project_index_attributes(updated))
            expires_at = self._ttl_attribute(ttl)
            if expires_at is not None:
                item_payload["expires_at"] = expires_at

            try:
                if item is None:
                    client.put_item(
                        TableName=self.table_name,
                        Item=item_payload,
                        ConditionExpression="attribute_not_exists(pk)",
                    )
                else:
                    client.put_item(
                        TableName=self.table_name,
                        Item=item_payload,
                        ConditionExpression="ver = :cur",
                        ExpressionAttributeValues={":cur": {"N": str(current_ver)}},
                    )
            except botocore.exceptions.ClientError as client_exc:
                code = client_exc.response.get("Error", {}).get("Code", "")
                if code == "ConditionalCheckFailedException":
                    return False, None
                raise
            return True, updated

        async def _loop() -> Any:
            for _ in range(max_retries):
                try:
                    ok, updated = await self._run(_once)
                except botocore.exceptions.EndpointConnectionError as net_exc:
                    raise SkaalUnavailable(f"DynamoDB unreachable: {net_exc}") from net_exc
                if ok:
                    return updated
            raise SkaalConflict(f"atomic_update on {key!r} lost {max_retries} consecutive races")

        return await _loop()

    async def close(self) -> None:
        # boto3 clients don't need explicit closing
        self._client = None

    def __repr__(self) -> str:
        return f"DynamoBackend(table={self.table_name!r}, region={self.region!r})"
