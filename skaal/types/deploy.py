"""Typed deploy resource shapes shared by Pulumi-based generators."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, NamedTuple, Protocol, TypeAlias

from pydantic import BaseModel
from typing_extensions import Required, TypedDict

TargetName: TypeAlias = Literal[
    "aws",
    "aws-lambda",
    "gcp",
    "gcp-cloudrun",
    "local",
    "local-docker",
]

ComponentKind: TypeAlias = Literal[
    "proxy",
    "api-gateway",
    "schedule-trigger",
    "external-storage",
    "external-queue",
    "external-observability",
    "app-ref",
]

ConfigOverrides: TypeAlias = dict[str, str]
StackOutputs: TypeAlias = dict[str, str]


class StackProfile(TypedDict, total=False):
    env: dict[str, str]
    invokers: list[str]
    labels: dict[str, str]
    enable_mesh: bool


class DeployMeta(TypedDict, total=False):
    target: Required[TargetName]
    source_module: Required[str]
    app_name: Required[str]
    lambda_architecture: str
    lambda_runtime: str


class RouteSpec(BaseModel):
    path: str
    target: str
    methods: list[str]
    strip_prefix: bool = False
    timeout_ms: int | None = None
    rewrite: str | None = None


class AuthConfig(BaseModel):
    provider: str
    issuer: str | None = None
    audience: str | None = None
    header: str = "Authorization"
    required: bool = True


class RateLimitConfig(BaseModel):
    requests_per_second: float | int
    burst: int | None = None
    scope: str | None = None


class GatewayConfig(BaseModel):
    routes: list[RouteSpec]
    auth: AuthConfig | None = None
    rate_limit: RateLimitConfig | None = None
    cors_origins: list[str] | None = None
    tls: bool | None = None
    latency_ms: float | None = None
    health_check_path: str | None = None
    implementation: str | None = None


class CronTriggerConfig(BaseModel):
    expression: str


class EveryTriggerConfig(BaseModel):
    interval: str


class ScheduleTriggerConfig(BaseModel):
    trigger: CronTriggerConfig | EveryTriggerConfig
    trigger_type: Literal["cron", "every"]
    target_function: str
    timezone: str = "UTC"
    emit_to: str | None = None


class ExternalComponentConfig(BaseModel):
    external: bool = True
    secret_name: str | None = None
    latency_ms: float | None = None
    region: str | None = None


class ExternalStorageConfig(ExternalComponentConfig):
    access_pattern: str
    durability: str


class ExternalQueueConfig(ExternalComponentConfig):
    throughput: str | None = None


class ExternalObservabilityConfig(ExternalComponentConfig):
    provider: str


class AppRefConfig(ExternalComponentConfig):
    timeout_ms: int


ComponentConfig: TypeAlias = (
    GatewayConfig
    | ScheduleTriggerConfig
    | ExternalStorageConfig
    | ExternalQueueConfig
    | ExternalObservabilityConfig
    | AppRefConfig
)


class CloudRunSecretKeyRef(TypedDict):
    name: str
    key: str


class CloudRunEnvValueSource(TypedDict):
    secretKeyRef: CloudRunSecretKeyRef


class CloudRunEnvVar(TypedDict, total=False):
    name: Required[str]
    value: str
    valueFrom: CloudRunEnvValueSource


class AppLike(Protocol):
    name: str
    _mounts: dict[str, str]
    _wsgi_attribute: str


class BackendWiring(NamedTuple):
    imports: str
    overrides: str


class DockerBuildConfig(TypedDict, total=False):
    context: str
    dockerfile: str
    platform: str


class DockerHealthcheck(TypedDict, total=False):
    interval: str
    retries: int
    startPeriod: str
    tests: list[str]
    timeout: str


class DockerLabel(TypedDict):
    label: str
    value: str


class DockerNetworkAttachment(TypedDict, total=False):
    aliases: list[str]
    name: str


class DockerPortBinding(TypedDict, total=False):
    external: int
    internal: int
    ip: str
    protocol: str


class DockerVolumeMount(TypedDict, total=False):
    containerPath: str
    hostPath: str
    readOnly: bool
    volumeName: str


class DockerImageProperties(TypedDict, total=False):
    build: DockerBuildConfig
    imageName: str
    skipPush: bool


class DockerContainerProperties(TypedDict, total=False):
    command: list[str]
    envs: list[str]
    healthcheck: DockerHealthcheck
    image: str
    labels: list[DockerLabel]
    name: str
    networkMode: str
    networksAdvanced: list[DockerNetworkAttachment]
    ports: list[DockerPortBinding]
    restart: str
    volumes: list[DockerVolumeMount]
    wait: bool
    waitTimeout: int
    workingDir: str


class LocalServiceSpec(TypedDict, total=False):
    command: list[str]
    envs: list[str]
    healthcheck: DockerHealthcheck
    image: str
    labels: list[DockerLabel]
    ports: list[DockerPortBinding]
    volumes: list[DockerVolumeMount]


class PulumiProviderPlugin(TypedDict):
    name: str
    version: str


class PulumiPlugins(TypedDict):
    providers: Required[list[PulumiProviderPlugin]]


class PulumiResourceOptions(TypedDict, total=False):
    dependsOn: list[str]


class PulumiResource(TypedDict, total=False):
    properties: Required[Mapping[str, Any]]
    type: Required[str]
    options: PulumiResourceOptions


class PulumiStack(TypedDict, total=False):
    config: Required[dict[str, Any]]
    name: Required[str]
    outputs: Required[dict[str, Any]]
    plugins: PulumiPlugins
    resources: Required[dict[str, PulumiResource]]
    runtime: Required[str]
    variables: dict[str, Any]
