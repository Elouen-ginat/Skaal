"""Channel and queue backend tokens."""

from skaal.backends._base import Backend
from skaal.backends._native_types import RedisNativeClient, SqsClientProtocol


class InProcessChannel(Backend[object]):
    name = "in-process"
    kinds = frozenset({"channel"})


class RedisChannel(Backend[RedisNativeClient]):
    name = "redis-channel"
    kinds = frozenset({"channel"})
    NativeClient = RedisNativeClient


class Sqs(Backend[SqsClientProtocol]):
    name = "sqs"
    kinds = frozenset({"channel"})
    NativeClient = SqsClientProtocol


class Pubsub(Backend[object]):
    name = "pubsub"
    kinds = frozenset({"channel"})


__all__ = ["InProcessChannel", "Pubsub", "RedisChannel", "Sqs"]
