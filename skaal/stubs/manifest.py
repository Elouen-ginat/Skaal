"""Pydantic models describing an emitted Skaal stub package (ADR 033 §5.1).

`StubManifest` is the on-disk metadata file (`_manifest.json`) shipped in
every emitted stub package. It carries the source app's identity, the
inferred-plan fingerprint at emission time, and the list of resources the
stubs cover. Consuming projects can validate the manifest, diff
fingerprints, or simply ignore it — the `.pyi` files are self-contained
for type-checking purposes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class StubResourceRef(BaseModel):
    """A single resource described by an emitted stub package.

    Mirrors `skaal.inference.InferredResource`'s identifying fields but
    omits transient details (source-line numbers, schema hashes) — only
    the symbol identity, kind, and origin module are needed for stub
    consumers.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    kind: str
    module: str
    qualname: str


class StubManifest(BaseModel):
    """Metadata file shipped at the root of an emitted stub package.

    The manifest is written to `_manifest.json` in the output directory.
    Consuming projects pin the file in their VCS so a regenerate that
    changes the source-app `app_fingerprint` becomes a visible diff.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    package_name: str
    source_module: str
    source_app: str
    app_fingerprint: str | None = None
    skaal_version: str
    generated_at: datetime
    resources: tuple[StubResourceRef, ...] = ()

    def to_json(self) -> str:
        """Return the manifest's canonical JSON form (`indent=2`, sorted keys)."""
        return self.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, raw: str | bytes) -> StubManifest:
        """Parse a manifest from its on-disk JSON form."""
        return cls.model_validate_json(raw)

    def fingerprint_payload(self) -> dict[str, Any]:
        """Return the byte-stable subset used to compare two manifests.

        Excludes `generated_at` (timestamp drift on regen) and the
        `skaal_version` (cadence of framework bumps is independent of
        the source app's shape).
        """
        return {
            "package_name": self.package_name,
            "source_module": self.source_module,
            "source_app": self.source_app,
            "app_fingerprint": self.app_fingerprint,
            "resources": [res.model_dump() for res in self.resources],
        }
