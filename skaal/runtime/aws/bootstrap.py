"""AWS cold-start bootstrap helpers for the runtime target."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Mapping
from typing import TYPE_CHECKING, Any, Protocol, cast

from skaal.app import App
from skaal.errors import RuntimeWiringError, SecretMissingError
from skaal.inference.model import BlueprintResource
from skaal.runtime._registry import RuntimeBackendFactoryContext, get_runtime_target
from skaal.runtime.aws.backends import aws_region
from skaal.runtime.aws.target import AWS_RUNTIME_TARGET_NAME
from skaal.runtime.models import RuntimeBindingManifest, RuntimeResourceBinding
from skaal.secrets import SecretRegistry
from skaal.types.secret import ResolvedSecret, SecretProvider, SecretResolver, SecretSpec


class AwsSecretsManagerClient(Protocol):
    def get_secret_value(self, *, SecretId: str) -> dict[str, Any]: ...


if TYPE_CHECKING:

    def _secretsmanager_client(region: str | None) -> AwsSecretsManagerClient: ...
else:

    def _secretsmanager_client(region: str | None) -> AwsSecretsManagerClient:
        import boto3

        return cast(AwsSecretsManagerClient, boto3.client("secretsmanager", region_name=region))


def wire_app_from_environment(
    app: App,
    *,
    manifest: RuntimeBindingManifest,
    env: Mapping[str, str] | None = None,
) -> None:
    actual_env = env if env is not None else os.environ
    aws_target = get_runtime_target(AWS_RUNTIME_TARGET_NAME)
    app._autodiscover_declarations()
    wire_declared_secrets(app, actual_env)

    resource_index = resource_index_for_app(app)
    for binding in manifest.bindings:
        target = resolve_target(binding, resource_index)
        aws_target.wire_binding(
            RuntimeBackendFactoryContext(
                target_name=AWS_RUNTIME_TARGET_NAME,
                resource_kind=binding.connection.kind,
                backend_name=binding.connection.backend_name,
                target=target,
                binding=binding,
                env=actual_env,
            )
        )


def resource_index_for_app(app: App) -> dict[str, Any]:
    index: dict[str, Any] = {}
    for registry in (app._storage, app._channels):
        for obj in registry.values():
            inferred = getattr(obj, "__skaal_inferred__", None)
            if isinstance(inferred, BlueprintResource):
                index[inferred.id] = obj
    return index


def resolve_target(binding: RuntimeResourceBinding, index: dict[str, Any]) -> Any:
    target = index.get(binding.resource_id)
    if target is not None:
        return target
    available = ", ".join(sorted(index)) if index else "(none)"
    raise RuntimeWiringError(
        f"Runtime binding {binding.resource_id!r} does not match any live app resource. "
        f"Available resource ids: {available}."
    )


def wire_declared_secrets(app: App, env: Mapping[str, str]) -> None:
    refs = app._collect_secrets()
    if not refs:
        return

    resolvers: dict[SecretProvider, SecretResolver] = {
        "env": cast(SecretResolver, EnvMappingResolver("env", env)),
        "pulumi-config": cast(SecretResolver, EnvMappingResolver("pulumi-config", env)),
        "aws-secrets-manager": cast(SecretResolver, AwsRuntimeSecretResolver(env)),
    }
    registry = SecretRegistry(
        {name: ref.to_spec() for name, ref in refs.items()},
        resolvers=resolvers,
    )
    run_blocking(registry.warmup(), context="warm declared secrets")
    app._set_secret_registry(registry)


class EnvMappingResolver:
    def __init__(self, provider: SecretProvider, env: Mapping[str, str]) -> None:
        self.provider = provider
        self._env = env

    async def resolve(self, spec: SecretSpec) -> ResolvedSecret:
        raw = self._env.get(spec.env)
        if raw is None and spec.source != spec.env:
            raw = self._env.get(spec.source)
        return ResolvedSecret(
            name=spec.name, value=raw, provider=cast(SecretProvider, self.provider)
        )

    async def close(self) -> None:
        return None


class AwsRuntimeSecretResolver:
    provider: SecretProvider = "aws-secrets-manager"

    def __init__(self, env: Mapping[str, str]) -> None:
        self._env = env
        self._region = aws_region(env)

    async def resolve(self, spec: SecretSpec) -> ResolvedSecret:
        secret_id = self._env.get(spec.env) or spec.source
        if not secret_id:
            return ResolvedSecret(name=spec.name, value=None, provider=self.provider)

        try:
            client = _secretsmanager_client(self._region)
        except ImportError as exc:
            raise SecretMissingError(
                spec.name,
                self.provider,
                detail="boto3 is required for AWS cold-start secret wiring",
            ) from exc
        try:
            response = cast(
                dict[str, Any],
                await asyncio.to_thread(client.get_secret_value, SecretId=secret_id),
            )
        except Exception as exc:
            raise SecretMissingError(
                spec.name,
                self.provider,
                detail=f"GetSecretValue failed: {exc}",
            ) from exc

        value = cast(str | None, response.get("SecretString"))
        secret_binary = response.get("SecretBinary")
        if value is None and isinstance(secret_binary, bytes):
            value = secret_binary.decode("utf-8")
        return ResolvedSecret(
            name=spec.name,
            value=value,
            provider=cast(SecretProvider, self.provider),
        )

    async def close(self) -> None:
        return None


def run_blocking(awaitable: Awaitable[object], *, context: str) -> None:
    async def _runner() -> object:
        return await awaitable

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        try:
            asyncio.run(_runner())
        except Exception as exc:
            raise RuntimeWiringError(f"Failed to {context}: {exc}") from exc
        return
    raise RuntimeWiringError(f"Cannot {context} while an event loop is already running.")


__all__ = ["wire_app_from_environment"]
