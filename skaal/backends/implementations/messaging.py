"""Channel and queue backend implementations."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, cast

from skaal.backends._native_types import RedisNativeClient, SqsClientProtocol

if TYPE_CHECKING:

    def _sqs_client(region: str | None) -> SqsClientProtocol: ...
else:

    def _sqs_client(region: str | None) -> SqsClientProtocol:
        import boto3

        return cast(SqsClientProtocol, boto3.client("sqs", region_name=region))


class RedisStreamChannel:
    """
    Distributed pub/sub channel backed by Redis Streams.

    Each topic is a Redis Stream keyed as ``skaal:ch:{namespace}:{topic}``.
    Subscribers use ``XREADGROUP`` with consumer groups for at-least-once
    delivery. A ``subscribe()`` call auto-creates the consumer group on
    first use.
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379",
        namespace: str = "default",
    ) -> None:
        self.url = url
        self.namespace = namespace
        self._client: Any = None

    def _stream_key(self, topic: str) -> str:
        return f"skaal:ch:{self.namespace}:{topic}"

    async def connect(self) -> None:
        import redis.asyncio as aioredis

        self._client = aioredis.from_url(  # type: ignore[no-untyped-call]
            self.url, decode_responses=True
        )

    async def _ensure_connected(self) -> None:
        if self._client is None:
            await self.connect()

    async def publish(self, topic: str, message: Any) -> str:
        await self._ensure_connected()
        key = self._stream_key(topic)
        payload = json.dumps(message) if not isinstance(message, str) else message
        msg_id: str = await self._client.xadd(key, {"data": payload})
        return msg_id

    async def subscribe(
        self,
        topic: str,
        *,
        group: str = "default",
        consumer: str = "worker-0",
        from_beginning: bool = False,
        poll_interval_ms: int = 100,
        batch_size: int = 10,
    ) -> AsyncIterator[dict[str, Any]]:
        await self._ensure_connected()
        key = self._stream_key(topic)

        start_id = "0" if from_beginning else "$"
        try:
            await self._client.xgroup_create(key, group, id=start_id, mkstream=True)
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise

        while True:
            entries = await self._client.xreadgroup(
                groupname=group,
                consumername=consumer,
                streams={key: ">"},
                count=batch_size,
                block=poll_interval_ms,
            )
            if not entries:
                continue
            for _stream_name, messages in entries:
                for msg_id, fields in messages:
                    raw = fields.get("data", "{}")
                    try:
                        payload = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        payload = {"data": raw}

                    if isinstance(payload, dict):
                        payload["_id"] = msg_id
                    else:
                        payload = {"data": payload, "_id": msg_id}

                    yield payload

    async def ack(self, topic: str, group: str, message_id: str) -> None:
        await self._ensure_connected()
        await self._client.xack(self._stream_key(topic), group, message_id)

    async def pending(self, topic: str, group: str) -> int:
        await self._ensure_connected()
        info: Any = await self._client.xpending(self._stream_key(topic), group)
        if isinstance(info, dict):
            mapping = cast(dict[str, Any], info)
            return int(mapping.get("pending", 0))
        if isinstance(info, (list, tuple)):
            seq = cast(list[Any], list(cast(Any, info)))
            if seq:
                return int(seq[0])
        return 0

    async def stream_length(self, topic: str) -> int:
        await self._ensure_connected()
        return await self._client.xlen(self._stream_key(topic))

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def native(self) -> RedisNativeClient:
        await self._ensure_connected()
        return cast(RedisNativeClient, self._client)

    def __repr__(self) -> str:
        return f"RedisStreamChannel(url={self.url!r}, namespace={self.namespace!r})"


class SqsChannelBackend:
    """Thin async wrapper over one SQS queue used as a Skaal channel."""

    def __init__(
        self,
        queue_url: str,
        *,
        region: str | None = None,
        wait_time_seconds: int = 10,
    ) -> None:
        self.queue_url = queue_url
        self.region = region
        self.wait_time_seconds = wait_time_seconds
        self._client: SqsClientProtocol | None = None

    def _get_client(self) -> SqsClientProtocol:
        if self._client is None:
            self._client = _sqs_client(self.region)
        return self._client

    async def _run(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        return await asyncio.to_thread(fn, *args, **kwargs)

    async def send(self, item: Any) -> None:
        client = self._get_client()
        body = item if isinstance(item, str) else json.dumps(item)
        await self._run(client.send_message, QueueUrl=self.queue_url, MessageBody=body)

    async def receive(self) -> AsyncIterator[Any]:
        client = self._get_client()
        while True:
            response = await self._run(
                client.receive_message,
                QueueUrl=self.queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=self.wait_time_seconds,
            )
            messages = response.get("Messages", [])
            if not messages:
                continue

            for message in messages:
                body = message.get("Body", "")
                try:
                    payload: Any = json.loads(body)
                except json.JSONDecodeError:
                    payload = body
                yield payload
                receipt_handle = message.get("ReceiptHandle")
                if receipt_handle:
                    await self._run(
                        client.delete_message,
                        QueueUrl=self.queue_url,
                        ReceiptHandle=receipt_handle,
                    )

    async def native(self) -> SqsClientProtocol:
        return self._get_client()

    def __repr__(self) -> str:
        return f"SqsChannelBackend(queue_url={self.queue_url!r}, region={self.region!r})"


__all__ = ["RedisStreamChannel", "SqsChannelBackend"]
