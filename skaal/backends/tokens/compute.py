"""Function and service backend tokens."""

from skaal.backends._base import Backend


class Asyncio(Backend[object]):
    name = "asyncio"
    kinds = frozenset({"function", "job"})


class Lambda(Backend[object]):
    name = "lambda"
    kinds = frozenset({"function"})


class CloudRun(Backend[object]):
    name = "cloud-run"
    kinds = frozenset({"function", "asgi_service"})


class Uvicorn(Backend[object]):
    name = "uvicorn"
    kinds = frozenset({"asgi_service"})


class ApigwLambda(Backend[object]):
    name = "apigw-lambda"
    kinds = frozenset({"asgi_service"})


__all__ = ["ApigwLambda", "Asyncio", "CloudRun", "Lambda", "Uvicorn"]
