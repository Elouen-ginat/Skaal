"""Component constraint encoding and resolution for the Z3 solver.

Resolves :class:`~skaal.components.ProvisionedComponent` instances to concrete
implementations and passes :class:`~skaal.components.ExternalComponent`
instances through as-is.  Both are written into ``PlanFile.components`` so the
deploy engine can provision or configure them.

Adding support for a new component kind
----------------------------------------
1. Add a ``"<kind>": { ... }`` entry to :data:`_COMPONENT_DEFAULTS` mapping
   each :class:`~skaal.solver.targets.TargetFamily` value to a default
   implementation name.
2. Add a fallback string to :data:`_COMPONENT_FALLBACKS`.
No other changes are required.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any, Literal, cast

from skaal.solver.targets import TargetFamily, resolve_family
from skaal.types.deploy import (
    AppRefConfig,
    AuthConfig,
    ComponentConfig,
    CronTriggerConfig,
    EveryTriggerConfig,
    ExternalComponentConfig,
    ExternalObservabilityConfig,
    ExternalQueueConfig,
    ExternalStorageConfig,
    GatewayConfig,
    RateLimitConfig,
    RouteSpec,
    ScheduleTriggerConfig,
)

if TYPE_CHECKING:
    from skaal.components import ComponentBase
    from skaal.plan import ComponentSpec


# ── Implementation selection tables ──────────────────────────────────────────
#
# Keyed by component kind → target family value → default implementation.
# Family values (TargetFamily.value) are used as keys so the table is readable
# without importing the enum at every call site.

_COMPONENT_DEFAULTS: dict[str, dict[str, str]] = {
    "proxy": {
        TargetFamily.AWS.value: "api-gateway",
        TargetFamily.GCP.value: "cloud-endpoints",
        TargetFamily.LOCAL.value: "traefik",
        TargetFamily.GENERIC.value: "traefik",
        # Container-orchestration overrides within GENERIC family
        "k8s": "traefik",
        "ecs": "alb",
    },
    "api-gateway": {
        TargetFamily.AWS.value: "api-gateway",
        TargetFamily.GCP.value: "cloud-endpoints",
        TargetFamily.LOCAL.value: "kong",
        TargetFamily.GENERIC.value: "kong",
        "k8s": "kong",
        "ecs": "api-gateway",
    },
    "schedule-trigger": {
        TargetFamily.AWS.value: "eventbridge",
        TargetFamily.GCP.value: "cloud-scheduler",
        TargetFamily.LOCAL.value: "apscheduler",
        TargetFamily.GENERIC.value: "apscheduler",
        "k8s": "apscheduler",
        "ecs": "eventbridge",
    },
}

#: Fallback implementation when neither the target nor its family has an entry.
_COMPONENT_FALLBACKS: dict[str, str] = {
    "proxy": "traefik",
    "api-gateway": "kong",
    "schedule-trigger": "apscheduler",
}


# ── Resolution logic ──────────────────────────────────────────────────────────


def _resolve_provisioned_impl(
    name: str,
    kind: str,
    component: Any,
    target: str,
    catalog: dict[str, Any],
) -> tuple[str, str]:
    """Return ``(implementation, reason)`` for a :class:`ProvisionedComponent`.

    Resolution order:
    1. Explicit ``implementation`` pin on the component instance.
    2. Exact target match in :data:`_COMPONENT_DEFAULTS` (e.g. ``"ecs"``).
    3. Target-family match in :data:`_COMPONENT_DEFAULTS` (e.g. ``"aws"``).
    4. Catalog ``[components.<name>]`` entry.
    5. The *kind* string itself as a last resort.
    """
    # 1. Explicit pin takes absolute precedence
    if hasattr(component, "implementation"):
        pinned = component.implementation
    else:
        pinned = None
    if pinned:
        return pinned, f"{kind} implementation={pinned!r} (explicitly pinned)"

    defaults = _COMPONENT_DEFAULTS.get(kind)
    if defaults is not None:
        # 2. Exact target string (handles special cases like "ecs" inside GENERIC)
        impl = defaults.get(target)
        if impl is not None:
            return impl, f"{kind} implementation={impl!r} for target={target!r}"

        # 3. Target family
        family_key = resolve_family(target).value
        impl = defaults.get(family_key, _COMPONENT_FALLBACKS.get(kind, kind))
        return impl, f"{kind} implementation={impl!r} for target={target!r}"

    # 4. Catalog lookup for unknown / custom kinds
    comp_catalog = catalog.get("components", {})
    if name in comp_catalog:
        impl = comp_catalog[name].get("implementation") or kind
        return impl, f"implementation {impl!r} from catalog for {kind}"

    # 5. Bare kind name — the deploy engine is expected to recognise it
    return kind, f"default implementation for kind={kind!r}"


def _serialize_component_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    return value


def _base_external_config(comp_meta: dict[str, Any]) -> ExternalComponentConfig:
    return ExternalComponentConfig(
        external=True,
        secret_name=cast(str | None, comp_meta["secret_name"]),
        latency_ms=cast(float | None, comp_meta["latency_ms"]),
        region=cast(str | None, comp_meta["region"]),
    )


def _normalize_routes(raw_routes: list[dict[str, Any]]) -> list[RouteSpec]:
    return [
        RouteSpec(
            path=str(route["path"]),
            target=str(route["target"]),
            methods=[str(method) for method in route["methods"]],
            strip_prefix=bool(route.get("strip_prefix", False)),
            timeout_ms=int(timeout_ms)
            if isinstance(timeout_ms := route.get("timeout_ms"), int)
            else None,
            rewrite=str(rewrite) if isinstance(rewrite := route.get("rewrite"), str) else None,
        )
        for route in raw_routes
    ]


def _normalize_auth_config(raw_auth: dict[str, Any] | None) -> AuthConfig | None:
    if raw_auth is None:
        return None
    return AuthConfig(
        provider=cast(str, raw_auth["provider"]),
        issuer=cast(str | None, raw_auth["issuer"]),
        audience=cast(str | None, raw_auth["audience"]),
        header=cast(str, raw_auth["header"]),
        required=cast(bool, raw_auth["required"]),
    )


def _normalize_rate_limit(raw_rate_limit: dict[str, Any] | None) -> RateLimitConfig | None:
    if raw_rate_limit is None:
        return None
    return RateLimitConfig(
        requests_per_second=cast(float | int, raw_rate_limit["requests_per_second"]),
        burst=cast(int | None, raw_rate_limit["burst"]),
        scope=cast(str | None, raw_rate_limit["scope"]),
    )


def _encode_component_config(kind: str, comp_meta: dict[str, Any]) -> ComponentConfig:
    if kind in {"proxy", "api-gateway"}:
        return GatewayConfig(
            routes=_normalize_routes(cast(list[dict[str, Any]], comp_meta["routes"])),
            auth=_normalize_auth_config(
                cast(dict[str, Any] | None, comp_meta["auth"]) if "auth" in comp_meta else None
            ),
            rate_limit=_normalize_rate_limit(
                cast(dict[str, Any] | None, comp_meta["rate_limit"])
                if "rate_limit" in comp_meta
                else None
            ),
            cors_origins=cast(list[str] | None, comp_meta["cors_origins"])
            if "cors_origins" in comp_meta
            else None,
            tls=cast(bool | None, comp_meta["tls"]) if "tls" in comp_meta else None,
            latency_ms=cast(float | None, comp_meta["latency_ms"])
            if "latency_ms" in comp_meta
            else None,
            health_check_path=cast(str | None, comp_meta["health_check_path"])
            if "health_check_path" in comp_meta
            else None,
            implementation=cast(str | None, comp_meta["implementation"]),
        )

    if kind == "schedule-trigger":
        trigger_type = cast(str, comp_meta["trigger_type"])
        raw_trigger = cast(dict[str, Any], comp_meta["trigger"])
        trigger: CronTriggerConfig | EveryTriggerConfig
        if trigger_type == "cron":
            trigger = CronTriggerConfig(expression=cast(str, raw_trigger["expression"]))
        else:
            trigger = EveryTriggerConfig(interval=cast(str, raw_trigger["interval"]))
        return ScheduleTriggerConfig(
            trigger=trigger,
            trigger_type=cast("Literal['cron', 'every']", trigger_type),
            target_function=cast(str, comp_meta["target_function"]),
            timezone=cast(str, comp_meta["timezone"]),
            emit_to=cast(str | None, comp_meta["emit_to"]),
        )

    if kind == "external-storage":
        base = _base_external_config(comp_meta)
        return ExternalStorageConfig(
            external=base.external,
            secret_name=base.secret_name,
            latency_ms=base.latency_ms,
            region=base.region,
            access_pattern=cast(str, _serialize_component_value(comp_meta["access_pattern"])),
            durability=cast(str, _serialize_component_value(comp_meta["durability"])),
        )

    if kind == "external-queue":
        base = _base_external_config(comp_meta)
        return ExternalQueueConfig(
            external=base.external,
            secret_name=base.secret_name,
            latency_ms=base.latency_ms,
            region=base.region,
            throughput=cast(str | None, comp_meta["throughput"]),
        )

    if kind == "external-observability":
        base = _base_external_config(comp_meta)
        return ExternalObservabilityConfig(
            external=base.external,
            secret_name=base.secret_name,
            latency_ms=base.latency_ms,
            region=base.region,
            provider=cast(str, comp_meta["provider"]),
        )

    if kind == "app-ref":
        base = _base_external_config(comp_meta)
        return AppRefConfig(
            external=base.external,
            secret_name=base.secret_name,
            latency_ms=base.latency_ms,
            region=base.region,
            timeout_ms=cast(int, comp_meta["timeout_ms"]),
        )

    raise ValueError(f"Unsupported component kind {kind!r}")


# ── Main entry point ──────────────────────────────────────────────────────────


def encode_component(
    name: str,
    component: ComponentBase,
    catalog: dict[str, Any],
    target: str = "generic",
) -> ComponentSpec:
    """Resolve a component to a concrete :class:`~skaal.plan.ComponentSpec`.

    - **ProvisionedComponent** (Proxy, APIGateway, ScheduleTrigger): selects
      an implementation via :func:`_resolve_provisioned_impl` and returns a
      spec with ``provisioned=True``.
    - **ExternalComponent**: returns a pass-through spec with
      ``provisioned=False`` and the ``secret_name`` (if any) referencing an
      entry in :attr:`PlanFile.secrets`.

    Args:
        name:      The component's ``.name`` attribute.
        component: The :class:`~skaal.components.ComponentBase` instance.
        catalog:   Parsed TOML catalog dict (may include ``[components]``).
        target:    Deploy target, e.g. ``"generic"`` | ``"aws"`` | ``"k8s"``.

    Returns:
        A resolved :class:`~skaal.plan.ComponentSpec`.
    """
    from skaal.components import ExternalComponent
    from skaal.plan import ComponentSpec

    kind = component._skaal_component_kind
    comp_meta = component.__skaal_component__
    config = _encode_component_config(kind, comp_meta)

    if isinstance(component, ExternalComponent):
        return ComponentSpec(
            component_name=name,
            kind=kind,
            implementation=None,
            provisioned=False,
            secret_name=cast(str | None, comp_meta["secret_name"]),
            config=config,
            reason="external component — not provisioned by Skaal",
        )

    impl, reason = _resolve_provisioned_impl(name, kind, component, target, catalog)
    return ComponentSpec(
        component_name=name,
        kind=kind,
        implementation=impl,
        provisioned=True,
        secret_name=None,
        config=config,
        reason=reason,
    )
