"""SQS-backed channel backend for AWS runtime wiring."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any


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
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("sqs", region_name=self.region)
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

    async def native(self) -> Any:
        return self._get_client()

    def __repr__(self) -> str:
        return f"SqsChannelBackend(queue_url={self.queue_url!r}, region={self.region!r})"
