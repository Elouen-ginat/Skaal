"""Pydantic models for the deploy layer.

Every build-time data structure has a typed representation here, so the
deploy code never round-trips through bare ``dict[str, Any]``. Concretely:

- `SkaalTags` — the canonical `skaal:*` tag set applied to every cloud
  resource (ADR 028 §6.11). Constructed with
  `SkaalTags.for_resource(resource, env, fingerprint)`; the on-the-wire
  form for Pulumi `tags=` kwargs is `tags.as_mapping()`.
- `BuildContext` — the strict Jinja2 render context for one resource's
  per-Lambda templates. Every variable referenced by a template lives
  here as a typed field.
- `ManifestResourceEntry` and `BuildManifest` — the pydantic shape of
  ``.skaal/build/<env>/manifest.json``. Reading the manifest back is one
  ``BuildManifest.model_validate_json(...)`` call.
- `BuildPyProject` — the in-memory shape of the `pyproject.toml` we
  render alongside each Lambda artefact. The TOML serialisation lives in
  the Jinja2 template, but the model documents the contract.

Enum fields (`ResourceKind`, `Target`) carry through as enum values into
JSON / template contexts via ``model_dump(mode="json")``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from skaal.binding.model import Target
from skaal.inference.model import ResourceKind

if TYPE_CHECKING:
    from skaal.binding.model import Environment, PlannedResource


class SkaalTags(BaseModel):
    """The canonical `skaal:*` tag set applied to every cloud resource.

    Pulumi resource constructors take ``tags`` as a ``dict[str, str]``;
    callers wire that through with ``**tags.as_mapping()``. The pydantic
    surface itself documents the schema and validates at construction.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    app: str
    resource_id: str
    source: str
    source_line: str
    kind: ResourceKind
    env: str
    target: Target
    backend: str
    fingerprint: str

    @classmethod
    def for_resource(
        cls,
        resource: PlannedResource,
        env: Environment,
        fingerprint: str,
    ) -> SkaalTags:
        """Build the tag set for one bound resource."""
        inferred = resource.inferred
        # AWS tag values reject backslashes (regex `[\p{L}\p{Z}\p{N}_.:/=+\-@]*`),
        # so source paths captured on Windows are normalised to forward slashes.
        portable_file = inferred.source.file.replace("\\", "/")
        return cls(
            app=inferred.source.top_package,
            resource_id=inferred.id,
            source=f"{inferred.source.module}:{inferred.source.qualname}",
            source_line=f"{portable_file}:{inferred.source.line}",
            kind=inferred.kind,
            env=env.name,
            target=env.target,
            backend=resource.backend,
            fingerprint=fingerprint,
        )

    def as_mapping(self, target: Target | None = None) -> dict[str, str]:
        """Return the prefixed ``skaal:*`` mapping for Pulumi `tags=`.

        Args:
            target: When ``Target.GCP``, returns a GCP-label-safe shape:
                keys use ``skaal_*`` separators (GCP rejects ``:`` in
                keys) and values are lowercased to ``[a-z0-9_-]`` (GCP
                rejects uppercase and most punctuation in label values).
                Any other value (including ``None``) returns the
                AWS-shape used historically.
        """
        if target is Target.GCP:
            return {
                "skaal_app": _gcp_label_value(self.app),
                "skaal_resource_id": _gcp_label_value(self.resource_id),
                "skaal_source": _gcp_label_value(self.source),
                "skaal_source_line": _gcp_label_value(self.source_line),
                "skaal_kind": _gcp_label_value(self.kind.value),
                "skaal_env": _gcp_label_value(self.env),
                "skaal_target": _gcp_label_value(self.target.value),
                "skaal_backend": _gcp_label_value(self.backend),
                "skaal_fingerprint": _gcp_label_value(self.fingerprint),
            }
        return {
            "skaal:app": _sanitize_tag_value(self.app),
            "skaal:resource_id": _sanitize_tag_value(self.resource_id),
            "skaal:source": _sanitize_tag_value(self.source),
            "skaal:source_line": _sanitize_tag_value(self.source_line),
            "skaal:kind": _sanitize_tag_value(self.kind.value),
            "skaal:env": _sanitize_tag_value(self.env),
            "skaal:target": _sanitize_tag_value(self.target.value),
            "skaal:backend": _sanitize_tag_value(self.backend),
            "skaal:fingerprint": _sanitize_tag_value(self.fingerprint),
        }


def _sanitize_tag_value(value: str) -> str:
    """Return an AWS-safe tag value while preserving readable provenance."""
    sanitized = "".join(
        char if (char.isalnum() or char.isspace() or char in "_.:/=+-@") else "_" for char in value
    )
    return sanitized[:256]


_GCP_LABEL_VALID_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-_")


def _gcp_label_value(value: str) -> str:
    """Return a GCP-label-safe value: lowercased, ``[a-z0-9_-]``, max 63 chars."""
    lowered = value.lower()
    sanitized = "".join(c if c in _GCP_LABEL_VALID_CHARS else "_" for c in lowered)
    return sanitized[:63]


class BuildContext(BaseModel):
    """The Jinja2 render context for one resource's per-Lambda templates.

    With ``StrictUndefined`` on the Jinja2 environment, every variable a
    template references must appear here — fields cannot drift between
    the template tree and the code that drives it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    app_name: str
    env_name: str
    target: Target
    user_package: str
    app_target: str
    python_version: str
    resource_id: str
    resource_kind: ResourceKind
    resource_bare_name: str
    backend: str
    bound_fingerprint: str
    app_fingerprint: str
    requirements: tuple[str, ...]
    dev_skaal_source: bool = False


class ManifestResourceEntry(BaseModel):
    """One row of `manifest.json` — a built resource's identity + slug."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    kind: ResourceKind
    backend: str
    slug: str
    external: bool

    @classmethod
    def for_resource(cls, resource: PlannedResource, *, slug: str) -> ManifestResourceEntry:
        """Build an entry from a bound resource and its rendered slug."""
        return cls(
            id=resource.inferred.id,
            kind=resource.inferred.kind,
            backend=resource.backend,
            slug=slug,
            external=resource.external,
        )


class BuildManifest(BaseModel):
    """The full `manifest.json` written next to each build's artefacts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int = 1
    app: str
    environment: str
    target: Target
    app_fingerprint: str
    bound_fingerprint: str
    resources: tuple[ManifestResourceEntry, ...] = ()

    def to_json(self) -> str:
        """Render the canonical, indented JSON form for on-disk storage."""
        return self.model_dump_json(indent=2) + "\n"


class BuildPyProject(BaseModel):
    """The contents of the `pyproject.toml` rendered alongside each Lambda.

    The TOML emission is left to the Jinja2 template (it is the natural
    rendering layer); this model documents the contract and gives callers
    a typed view if they want to introspect what the build will emit.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    version: str = "0.0.0"
    requires_python: str = Field(default=">=3.11", alias="requires-python")
    dependencies: tuple[str, ...] = ()
