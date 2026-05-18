"""Internal pydantic models for the build-to-runtime wiring contract."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from skaal.binding.model import Environment, Plan, PlannedResource, Target
from skaal.deploy._naming import resource_slug_key
from skaal.deploy.aws._config import AwsConfig
from skaal.deploy.gcp._config import GcpConfig
from skaal.inference.model import ResourceKind

RuntimeOptionValue = str | int | float | bool


class _ConnectionRefBase(BaseModel):
    """Shared shape for one runtime-bound backend reference."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    backend_name: str
    env_var_keys: tuple[str, ...] = ()
    options: dict[str, RuntimeOptionValue] = Field(default_factory=dict)


class StoreConnectionRef(_ConnectionRefBase):
    """Cold-start contract for one `Store[T, B]` resource."""

    kind: Literal[ResourceKind.STORE] = ResourceKind.STORE


class BlobConnectionRef(_ConnectionRefBase):
    """Cold-start contract for one `BlobStore[B]` resource."""

    kind: Literal[ResourceKind.BLOB] = ResourceKind.BLOB


class RelationalConnectionRef(_ConnectionRefBase):
    """Cold-start contract for one relational resource."""

    kind: Literal[ResourceKind.RELATIONAL] = ResourceKind.RELATIONAL


class ChannelConnectionRef(_ConnectionRefBase):
    """Cold-start contract for one `Topic[T, B]` resource."""

    kind: Literal[ResourceKind.CHANNEL] = ResourceKind.CHANNEL


class SecretConnectionRef(_ConnectionRefBase):
    """Cold-start contract for one declared secret resource."""

    kind: Literal[ResourceKind.SECRET] = ResourceKind.SECRET


BackendConnectionRef = Annotated[
    StoreConnectionRef
    | BlobConnectionRef
    | RelationalConnectionRef
    | ChannelConnectionRef
    | SecretConnectionRef,
    Field(discriminator="kind"),
]


class RuntimeResourceBinding(BaseModel):
    """One row of `runtime_bindings.json`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    resource_id: str
    qualified_class: str
    connection: BackendConnectionRef


class RuntimeBindingManifest(BaseModel):
    """Full runtime binding manifest emitted into Lambda artifacts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int = 1
    app: str
    environment: str
    target: Target
    bindings: tuple[RuntimeResourceBinding, ...] = ()

    @classmethod
    def from_bound_plan(cls, bound: Plan, env: Environment) -> RuntimeBindingManifest:
        """Emit the runtime wiring contract for deploy-managed primitives."""
        connection_fn: Any
        if env.target is Target.AWS:
            config: AwsConfig | GcpConfig = _aws_config_for_env(env)
            connection_fn = _connection_for_aws_resource
        elif env.target is Target.GCP:
            config = _gcp_config_for_env(env)
            connection_fn = _connection_for_gcp_resource
        else:
            msg = (
                "Runtime binding manifests support only `aws` and `gcp` targets; "
                f"got {env.target.value!r}."
            )
            raise ValueError(msg)

        bindings = tuple(
            binding
            for binding in (
                _binding_for_resource(resource, config, connection_fn)
                for resource in sorted(bound.resources, key=lambda item: item.inferred.id)
            )
            if binding is not None
        )
        return cls(
            app=bound.app,
            environment=env.name,
            target=env.target,
            bindings=bindings,
        )

    def to_json(self) -> str:
        """Render the canonical, indented JSON form for on-disk storage."""
        return self.model_dump_json(indent=2) + "\n"


def _aws_config_for_env(env: Environment) -> AwsConfig:
    backend_cfg = env.backends.get(Target.AWS.value)
    if backend_cfg is None or not backend_cfg.options:
        return AwsConfig()
    merged = {
        **AwsConfig().model_dump(),
        **backend_cfg.options,
    }
    return AwsConfig.model_validate(merged)


def _gcp_config_for_env(env: Environment) -> GcpConfig:
    backend_cfg = env.backends.get(Target.GCP.value)
    if backend_cfg is None or not backend_cfg.options:
        return GcpConfig()
    merged = {
        **GcpConfig().model_dump(),
        **backend_cfg.options,
    }
    return GcpConfig.model_validate(merged)


def _binding_for_resource(
    resource: PlannedResource,
    config: AwsConfig | GcpConfig,
    connection_fn: Any,
) -> RuntimeResourceBinding | None:
    if resource.external:
        return None

    connection = connection_fn(resource, config)
    if connection is None:
        return None

    return RuntimeResourceBinding(
        resource_id=resource.inferred.id,
        qualified_class=resource.inferred.id,
        connection=connection,
    )


def _connection_for_aws_resource(
    resource: PlannedResource,
    config: AwsConfig,
) -> BackendConnectionRef | None:
    slug_key = resource_slug_key(resource)
    options = _normalize_options(resource.options)
    backend = resource.backend
    kind = resource.inferred.kind

    if kind is ResourceKind.STORE:
        if backend == "dynamodb":
            return StoreConnectionRef(
                backend_name=backend,
                env_var_keys=(f"{config.dynamodb.env_var_prefix}{slug_key}",),
                options=options,
            )
        if backend == "redis":
            return StoreConnectionRef(
                backend_name=backend,
                env_var_keys=(
                    f"{config.redis.env_var_prefix}{slug_key}{config.redis.env_var_suffix}",
                ),
                options=options,
            )
        raise ValueError(f"Unsupported AWS runtime store backend {backend!r}.")

    if kind is ResourceKind.BLOB:
        if backend == "s3":
            return BlobConnectionRef(
                backend_name=backend,
                env_var_keys=(f"{config.s3.env_var_prefix}{slug_key}",),
                options=options,
            )
        raise ValueError(f"Unsupported AWS runtime blob backend {backend!r}.")

    if kind is ResourceKind.RELATIONAL:
        if backend == "postgres":
            return RelationalConnectionRef(
                backend_name=backend,
                env_var_keys=(
                    f"{config.postgres.env_var_prefix}{slug_key}_HOST",
                    f"{config.postgres.env_var_prefix}{slug_key}_SECRET_ARN",
                ),
                options=options,
            )
        raise ValueError(f"Unsupported AWS runtime relational backend {backend!r}.")

    if kind is ResourceKind.CHANNEL:
        if backend == "sqs":
            return ChannelConnectionRef(
                backend_name=backend,
                env_var_keys=(f"{config.sqs.env_var_prefix}{slug_key}{config.sqs.env_var_suffix}",),
                options=options,
            )
        if backend == "redis-channel":
            return ChannelConnectionRef(
                backend_name=backend,
                env_var_keys=(
                    f"{config.redis.env_var_prefix}{slug_key}{config.redis.env_var_suffix}",
                ),
                options=options,
            )
        raise ValueError(f"Unsupported AWS runtime channel backend {backend!r}.")

    if kind is ResourceKind.SECRET:
        if backend == "aws-secrets-manager":
            return SecretConnectionRef(
                backend_name=backend,
                env_var_keys=(
                    f"{config.secrets.env_var_prefix}{slug_key}{config.secrets.env_var_suffix}",
                ),
                options=options,
            )
        raise ValueError(f"Unsupported AWS runtime secret backend {backend!r}.")

    return None


def _connection_for_gcp_resource(
    resource: PlannedResource,
    config: GcpConfig,
) -> BackendConnectionRef | None:
    slug_key = resource_slug_key(resource)
    options = _normalize_options(resource.options)
    backend = resource.backend
    kind = resource.inferred.kind

    if kind is ResourceKind.STORE:
        if backend == "firestore":
            return StoreConnectionRef(
                backend_name=backend,
                env_var_keys=(f"{config.firestore.env_var_prefix}{slug_key}",),
                options=options,
            )
        if backend == "redis":
            # Reuse the AWS Redis env-var convention so the same factory works.
            return StoreConnectionRef(
                backend_name=backend,
                env_var_keys=(f"SKAAL_REDIS_{slug_key}_URL",),
                options=options,
            )
        raise ValueError(f"Unsupported GCP runtime store backend {backend!r}.")

    if kind is ResourceKind.BLOB:
        if backend == "gcs":
            return BlobConnectionRef(
                backend_name=backend,
                env_var_keys=(f"{config.gcs.env_var_prefix}{slug_key}",),
                options=options,
            )
        raise ValueError(f"Unsupported GCP runtime blob backend {backend!r}.")

    if kind is ResourceKind.RELATIONAL:
        if backend == "postgres":
            return RelationalConnectionRef(
                backend_name=backend,
                env_var_keys=(
                    f"{config.postgres.env_var_prefix}{slug_key}{config.postgres.env_var_conn_suffix}",
                    f"{config.postgres.env_var_prefix}{slug_key}{config.postgres.env_var_secret_suffix}",
                ),
                options=options,
            )
        if backend == "bigquery":
            return RelationalConnectionRef(
                backend_name=backend,
                env_var_keys=(
                    f"{config.bigquery.env_var_prefix}{slug_key}{config.bigquery.env_var_dataset_suffix}",
                    f"{config.bigquery.env_var_prefix}{slug_key}{config.bigquery.env_var_project_suffix}",
                ),
                options=options,
            )
        raise ValueError(f"Unsupported GCP runtime relational backend {backend!r}.")

    if kind is ResourceKind.CHANNEL:
        if backend == "pubsub":
            return ChannelConnectionRef(
                backend_name=backend,
                env_var_keys=(
                    f"{config.pubsub.env_var_prefix}{slug_key}{config.pubsub.env_var_suffix}",
                ),
                options=options,
            )
        if backend == "redis-channel":
            return ChannelConnectionRef(
                backend_name=backend,
                env_var_keys=(f"SKAAL_REDIS_{slug_key}_URL",),
                options=options,
            )
        raise ValueError(f"Unsupported GCP runtime channel backend {backend!r}.")

    if kind is ResourceKind.SECRET:
        if backend == "gcp-secret-manager":
            return SecretConnectionRef(
                backend_name=backend,
                env_var_keys=(
                    f"{config.secrets.env_var_prefix}{slug_key}{config.secrets.env_var_suffix}",
                ),
                options=options,
            )
        raise ValueError(f"Unsupported GCP runtime secret backend {backend!r}.")

    return None


def _normalize_options(options: dict[str, str]) -> dict[str, RuntimeOptionValue]:
    normalized: dict[str, RuntimeOptionValue] = {}
    for key, value in options.items():
        lowered = value.lower()
        if lowered == "true":
            normalized[key] = True
            continue
        if lowered == "false":
            normalized[key] = False
            continue
        try:
            normalized[key] = int(value)
            continue
        except ValueError:
            pass
        try:
            normalized[key] = float(value)
            continue
        except ValueError:
            pass
        normalized[key] = value
    return normalized


__all__ = ["RuntimeBindingManifest", "RuntimeResourceBinding"]
