"""`GcpTarget` — the concrete `DeployTarget` for GCP (ADR 042).

Thin like `AwsTarget`: pins `target = Target.GCP`, names its config schema
(`GcpConfig`), lists the Pulumi optional-extras, and wires `gcp:project`
and `gcp:region` into the Pulumi stack config when the active
`Environment` carries them.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, ClassVar

from skaal.binding.model import Target
from skaal.deploy._base_target import BaseDeployTarget
from skaal.deploy._protocol import TargetConfig
from skaal.deploy.gcp._config import GcpConfig

if TYPE_CHECKING:
    from skaal.binding.model import Environment


class GcpTarget(BaseDeployTarget):
    """The GCP deploy target. Constructed once in `skaal.deploy.gcp.__init__`."""

    target: ClassVar[Target] = Target.GCP
    _config_cls: ClassVar[type[TargetConfig]] = GcpConfig
    _required_extras: ClassVar[tuple[str, ...]] = (
        "pulumi",
        "pulumi_gcp",
        "pulumi_docker",
    )

    def stack_config(self, env: Environment) -> Mapping[str, str]:
        """Wire `gcp:project` / `gcp:region` into the Pulumi stack config."""
        config: dict[str, str] = {}
        gcp_backend = env.backends.get("gcp")
        if gcp_backend is not None and gcp_backend.project:
            config["gcp:project"] = gcp_backend.project
        if env.region:
            config["gcp:region"] = env.region
        return config


__all__ = ["GcpTarget"]
