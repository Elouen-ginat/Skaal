"""External components — references to pre-existing infrastructure.

Provisioned components (`Proxy`, `APIGateway`, `Route`, `AuthConfig`,
`ScheduleTrigger`, `AppRef`) and the `ExternalObservability` reference have
been removed per ADR 028 / ADR 029 Phase 1. `ExternalStorage` and
`ExternalQueue` survive in this slimmed-down form and will be reshaped into
the `@app.external` decorator family in Phase 2.
"""

from __future__ import annotations

from typing import Any, ClassVar

from skaal.types import SecretRef

# ── Base classes ──────────────────────────────────────────────────────────


class ComponentBase:
    """Abstract base for all Skaal components.

    Subclasses set `_skaal_component_kind` as a class variable. On
    instantiation they populate `__skaal_component__` — the metadata dict
    consumed by the inference layer.
    """

    _skaal_component_kind: ClassVar[str] = "base"

    def __init__(self, name: str) -> None:
        self.name = name
        self.__skaal_component__: dict[str, Any] = {
            "kind": self._skaal_component_kind,
            "name": name,
        }

    def describe(self) -> dict[str, Any]:
        return dict(self.__skaal_component__)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(name={self.name!r})"


class ExternalComponent(ComponentBase):
    """A pre-existing infrastructure component that Skaal did NOT provision.

    Connection info is supplied either through `connection_string` (literal,
    not recommended for production) or `secret` (a typed `SecretRef`
    declaring the provider that holds the DSN at deploy time).
    """

    def __init__(
        self,
        name: str,
        *,
        connection_string: str | None = None,
        secret: SecretRef | None = None,
        region: str | None = None,
    ) -> None:
        super().__init__(name)
        self.connection_string = connection_string
        self.secret = secret
        self.region = region
        self.__skaal_component__.update(
            {
                "external": True,
                "secret_name": secret.name if secret else None,
                "region": region,
            }
        )


# ── External components ───────────────────────────────────────────────────


class ExternalStorage(ExternalComponent):
    """Reference to a pre-existing database or object store.

    Examples:

        legacy_db = ExternalStorage(
            "legacy-postgres",
            secret=Secret("LEGACY_DATABASE_URL", provider="aws-secrets-manager"),
        )
        app.attach(legacy_db)
    """

    _skaal_component_kind = "external-storage"


class ExternalQueue(ExternalComponent):
    """Reference to a pre-existing message broker or queue (Kafka, RabbitMQ, …)."""

    _skaal_component_kind = "external-queue"
