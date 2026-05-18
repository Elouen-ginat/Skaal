"""Cloud Run-shaped synth class hierarchy (ADR 042).

The four GCP backends that ship a Cloud Run service — ``cloud-run``
(FUNCTION), ``cloud-run`` (ASGI_SERVICE), ``cloud-scheduler-run`` (SCHEDULE),
``cloud-tasks-run`` (JOB) — share the same Artifact Registry + image +
service-account + Cloud Run scaffold. That common scaffold lives on the
``CloudRunSynth`` base class; each concrete subclass overrides
``_event_source(...)`` (and timeout / memory defaults if it needs to) to
attach the trigger.

Mirrors `skaal.deploy.aws._lambda.LambdaSynth` exactly — the
``_pre_scaffold(ctx)`` hook covers cases like Cloud Tasks where a queue
URL must be in the service's env vars before the service is constructed.
"""

from __future__ import annotations

import hashlib
import os
from abc import ABC
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pulumi
import pulumi_docker as docker
import pulumi_gcp as gcp

from skaal.binding.model import Plan
from skaal.deploy._protocol import SynthContext, SynthModule, SynthResult
from skaal.deploy.gcp._config import GcpConfig
from skaal.inference.model import ResourceKind

_STORAGE_KINDS: frozenset[ResourceKind] = frozenset(
    {
        ResourceKind.STORE,
        ResourceKind.RELATIONAL,
        ResourceKind.BLOB,
        ResourceKind.CHANNEL,
        ResourceKind.SECRET,
    }
)


@dataclass(frozen=True)
class CloudRunScaffold:
    """The Pulumi resources every Cloud Run-shaped synth produces."""

    service: gcp.cloudrunv2.Service
    service_account: gcp.serviceaccount.Account
    image: docker.Image
    repository: gcp.artifactregistry.Repository
    iam_bindings: tuple[Any, ...] = ()

    def as_extras(self) -> tuple[Any, ...]:
        """Return the non-primary scaffolding resources as a tuple."""
        return (self.service_account, self.image, self.repository, *self.iam_bindings)


@dataclass(frozen=True)
class PreScaffold:
    """Resources and env vars produced *before* the Cloud Run scaffold.

    Mirrors `skaal.deploy.aws._lambda.PreScaffold` — used by synths that
    need a resource (Cloud Tasks queue, Pub/Sub subscription, …)
    available at service-construction time.
    """

    resources: tuple[Any, ...] = ()
    env_vars: Mapping[str, Any] = field(default_factory=lambda: cast(Mapping[str, Any], {}))
    payload: Any = None


class CloudRunSynth(SynthModule[GcpConfig], ABC):
    """Abstract base for every Cloud Run-shaped GCP synth.

    Subclasses override ``_event_source(ctx, scaffold, pre)`` to attach a
    trigger (Cloud Scheduler, Cloud Tasks). ``_timeout_s(ctx)``,
    ``_memory(ctx)``, and ``_max_instances(ctx)`` are overrideable so the
    ASGI / JOB variants can pick their own defaults from ``GcpConfig``.
    """

    # No `SPEC` here — `CloudRunSynth` is abstract.

    def synthesize(self, ctx: SynthContext[GcpConfig]) -> SynthResult:
        pre = self._pre_scaffold(ctx)
        scaffold = self._build_scaffold(ctx, extra_env=pre.env_vars)
        event_resources = self._event_source(ctx, scaffold, pre)
        outputs = (
            {"public_url": scaffold.service.uri}
            if ctx.resource.inferred.kind is ResourceKind.ASGI_SERVICE
            else {}
        )
        return SynthResult(
            resource_id=ctx.resource_id,
            primary=scaffold.service,
            extras=(*pre.resources, *scaffold.as_extras(), *event_resources),
            env_vars=self._env_vars(ctx, scaffold, pre),
            outputs=outputs,
        )

    def _build_scaffold(
        self,
        ctx: SynthContext[GcpConfig],
        *,
        extra_env: Mapping[str, Any] | None = None,
    ) -> CloudRunScaffold:
        cfg = ctx.config
        repository = self._build_repository(ctx, cfg)
        image = self._build_image(ctx, cfg, repository)
        service_account = self._build_service_account(ctx, cfg)
        iam_bindings = self._build_iam_bindings(ctx, cfg, service_account)
        service = self._build_service(
            ctx,
            cfg,
            image=image,
            service_account=service_account,
            extra_env=extra_env,
        )
        invoker_bindings = self._build_invoker_bindings(ctx, service)
        return CloudRunScaffold(
            service=service,
            service_account=service_account,
            image=image,
            repository=repository,
            iam_bindings=(*iam_bindings, *invoker_bindings),
        )

    def _build_invoker_bindings(
        self,
        ctx: SynthContext[GcpConfig],
        service: gcp.cloudrunv2.Service,
    ) -> tuple[Any, ...]:
        """Grant the Cloud Run service's public-invocation policy.

        ASGI services mounted by user code are public by default
        (``allUsers`` ``roles/run.invoker``) so the printed ``public_url``
        works without manual IAM steps. Other Cloud Run-shaped resources
        (function HTTP endpoints, Cloud-Tasks workers) stay private and
        rely on their dedicated callers granting access.
        """
        if ctx.resource.inferred.kind is not ResourceKind.ASGI_SERVICE:
            return ()
        binding = gcp.cloudrunv2.ServiceIamMember(
            f"{ctx.pulumi_name}-public",
            location=service.location,
            name=service.name,
            role="roles/run.invoker",
            member="allUsers",
        )
        return (binding,)

    # -- Overridable knobs ----------------------------------------------------

    def _timeout_s(self, ctx: SynthContext[GcpConfig]) -> int:
        overrides = ctx.resource.inferred.overrides
        if overrides.timeout_s:
            return int(overrides.timeout_s)
        return ctx.config.cloud_run_defaults.timeout_s

    def _memory(self, ctx: SynthContext[GcpConfig]) -> str:
        # `memory_mb` overrides are honoured by converting to Mi.
        overrides = ctx.resource.inferred.overrides
        if overrides.memory_mb:
            return f"{overrides.memory_mb}Mi"
        return ctx.config.cloud_run_defaults.memory

    def _cpu(self, ctx: SynthContext[GcpConfig]) -> str:
        return ctx.config.cloud_run_defaults.cpu

    def _max_instances(self, ctx: SynthContext[GcpConfig]) -> int:
        return ctx.config.cloud_run_defaults.max_instances

    def _min_instances(self, ctx: SynthContext[GcpConfig]) -> int:
        return ctx.config.cloud_run_defaults.min_instances

    def _ingress(self, ctx: SynthContext[GcpConfig]) -> str:
        return ctx.config.cloud_run_defaults.ingress

    def _port(self, ctx: SynthContext[GcpConfig]) -> int:
        return ctx.config.cloud_run_defaults.port

    def _pre_scaffold(self, ctx: SynthContext[GcpConfig]) -> PreScaffold:
        """Default: no pre-scaffold resources or env vars."""
        return PreScaffold()

    def _event_source(
        self,
        ctx: SynthContext[GcpConfig],
        scaffold: CloudRunScaffold,
        pre: PreScaffold,
    ) -> tuple[Any, ...]:
        """Default: no event source attached."""
        return ()

    def _env_vars(
        self,
        ctx: SynthContext[GcpConfig],
        scaffold: CloudRunScaffold,
        pre: PreScaffold,
    ) -> Mapping[str, Any]:
        """Default: re-export the pre-scaffold env vars to downstream peers."""
        return dict(pre.env_vars)

    # -- Internal Pulumi resource builders ------------------------------------

    def _build_repository(
        self,
        ctx: SynthContext[GcpConfig],
        cfg: GcpConfig,
    ) -> gcp.artifactregistry.Repository:
        return gcp.artifactregistry.Repository(
            f"{ctx.pulumi_name}-repo",
            location=_artifact_registry_location(ctx, cfg),
            repository_id=_repository_id(ctx.pulumi_name),
            format=cfg.artifact_registry.format,
            labels=ctx.tags,
        )

    def _build_image(
        self,
        ctx: SynthContext[GcpConfig],
        cfg: GcpConfig,
        repository: gcp.artifactregistry.Repository,
    ) -> docker.Image:
        image_tag = _artifact_tag_for_dir(ctx.build_dir / ctx.resource_slug)
        image_name = pulumi.Output.concat(
            _artifact_registry_location(ctx, cfg),
            "-docker.pkg.dev/",
            repository.project,
            "/",
            repository.repository_id,
            "/",
            ctx.resource_slug,
            ":",
            image_tag,
        )
        return docker.Image(
            f"{ctx.pulumi_name}-image",
            image_name=image_name,
            build=docker.DockerBuildArgs(
                context=str(ctx.build_dir / ctx.resource_slug),
                dockerfile=str(ctx.build_dir / ctx.resource_slug / "Dockerfile"),
                platform="linux/amd64",
            ),
        )

    def _build_service_account(
        self,
        ctx: SynthContext[GcpConfig],
        cfg: GcpConfig,
    ) -> gcp.serviceaccount.Account:
        return gcp.serviceaccount.Account(
            f"{ctx.pulumi_name}-sa",
            account_id=_service_account_id(ctx.pulumi_name),
            display_name=cfg.iam.service_account_display_name,
        )

    def _build_iam_bindings(
        self,
        ctx: SynthContext[GcpConfig],
        cfg: GcpConfig,
        service_account: gcp.serviceaccount.Account,
    ) -> tuple[Any, ...]:
        member = pulumi.Output.concat("serviceAccount:", service_account.email)
        roles: list[str] = list(cfg.iam.base_roles)
        roles.extend(
            cfg.iam.storage_roles[backend_name]
            for backend_name in self._storage_backend_names(ctx.bound, cfg.iam.storage_roles)
        )
        bindings: list[Any] = []
        gcp_backend = ctx.env.backends.get("gcp")
        project = (gcp_backend.project if gcp_backend else None) or ""
        for index, role in enumerate(roles):
            bindings.append(
                gcp.projects.IAMMember(
                    f"{ctx.pulumi_name}-role-{index}",
                    project=project,
                    role=role,
                    member=member,
                )
            )
        return tuple(bindings)

    def _build_service(
        self,
        ctx: SynthContext[GcpConfig],
        cfg: GcpConfig,
        *,
        image: docker.Image,
        service_account: gcp.serviceaccount.Account,
        extra_env: Mapping[str, Any] | None,
    ) -> gcp.cloudrunv2.Service:
        env = self._merge_env_vars(ctx, extra_env)
        env_list = [
            gcp.cloudrunv2.ServiceTemplateContainerEnvArgs(name=key, value=value)
            for key, value in env.items()
        ]
        return gcp.cloudrunv2.Service(
            ctx.pulumi_name,
            location=ctx.env.region or "us-central1",
            ingress=self._ingress(ctx),
            deletion_protection=False,
            template=gcp.cloudrunv2.ServiceTemplateArgs(
                service_account=service_account.email,
                timeout=f"{self._timeout_s(ctx)}s",
                scaling=gcp.cloudrunv2.ServiceTemplateScalingArgs(
                    min_instance_count=self._min_instances(ctx),
                    max_instance_count=self._max_instances(ctx),
                ),
                containers=[
                    gcp.cloudrunv2.ServiceTemplateContainerArgs(
                        image=image.image_name,
                        envs=env_list,
                        ports=gcp.cloudrunv2.ServiceTemplateContainerPortsArgs(
                            container_port=self._port(ctx),
                        ),
                        resources=gcp.cloudrunv2.ServiceTemplateContainerResourcesArgs(
                            limits={"cpu": self._cpu(ctx), "memory": self._memory(ctx)},
                        ),
                    )
                ],
            ),
            labels=ctx.tags,
        )

    @staticmethod
    def _storage_backend_names(bound: Plan, roles: Mapping[str, str]) -> tuple[str, ...]:
        """Return unique storage backend names present in `bound` that map to a role."""
        seen: set[str] = set()
        for resource in bound.resources:
            if resource.external:
                continue
            if resource.inferred.kind in _STORAGE_KINDS and resource.backend in roles:
                seen.add(resource.backend)
        return tuple(sorted(seen))

    @staticmethod
    def _merge_env_vars(
        ctx: SynthContext[GcpConfig], extra: Mapping[str, Any] | None
    ) -> dict[str, Any]:
        """Merge baseline env, storage-peer env vars, and per-call overrides."""
        merged: dict[str, Any] = {
            "SKAAL_APP": ctx.bound.app,
            "SKAAL_ENV": ctx.env.name,
            "SKAAL_RESOURCE_ID": ctx.resource_id,
            "SKAAL_FINGERPRINT": ctx.bound.bound_fingerprint,
            # ``PORT`` is reserved by Cloud Run — the platform injects it
            # automatically and rejects user-set values. Container code
            # should read ``$PORT`` from the runtime, not from this map.
        }
        merged.update(
            {key: value for peer in ctx.peers.values() for key, value in peer.env_vars.items()}
        )
        runtime_wire = os.environ.get("SKAAL_RUNTIME_WIRE")
        merged["SKAAL_RUNTIME_WIRE"] = "1" if runtime_wire is None else runtime_wire
        if extra:
            merged.update(extra)
        return merged


def _artifact_registry_location(ctx: SynthContext[GcpConfig], cfg: GcpConfig) -> str:
    """Return the Artifact Registry location for one synth context.

    Prefers the active environment's region so the image lives next to the
    Cloud Run service (fast pulls, no cross-region egress). Falls back to
    ``GcpConfig.artifact_registry.location`` when ``env.region`` is unset.
    """
    return ctx.env.region or cfg.artifact_registry.location


def _artifact_tag_for_dir(resource_dir: Path) -> str:
    """Return a stable image tag derived from one rendered Cloud Run artifact dir."""
    digest = hashlib.sha256()
    for path in sorted(candidate for candidate in resource_dir.rglob("*") if candidate.is_file()):
        relative = path.relative_to(resource_dir).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:16]


def _repository_id(name: str) -> str:
    """Return an Artifact Registry-compatible repository id."""
    sanitized = "".join(char if char.isalnum() else "-" for char in name.lower())
    collapsed = "-".join(part for part in sanitized.split("-") if part)
    return collapsed or "skaal"


def _service_account_id(name: str) -> str:
    """Return a GCP service-account id (must be 6-30 chars, lowercase alphanumeric+hyphens)."""
    sanitized = "".join(char if char.isalnum() else "-" for char in name.lower())
    collapsed = "-".join(part for part in sanitized.split("-") if part) or "skaal"
    # SA ids must be ≤30 chars; hash the tail if it overflows.
    if len(collapsed) <= 30:
        return collapsed
    digest = hashlib.sha1(collapsed.encode("utf-8"), usedforsecurity=False).hexdigest()[:6]
    head = collapsed[:23]
    return f"{head}-{digest}"


__all__ = ["CloudRunScaffold", "CloudRunSynth", "PreScaffold"]
