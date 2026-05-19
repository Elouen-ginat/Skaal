"""`AwsTarget` — the concrete `DeployTarget` for AWS.

The class is thin: it pins `target = Target.AWS`, names its config
schema (`AwsConfig`), and lists the optional-extras the Pulumi automation
path needs. Everything else (synth dispatch, stack name, region wiring)
inherits from `BaseDeployTarget`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, ClassVar

from skaal.binding.model import Target
from skaal.deploy._base_target import BaseDeployTarget
from skaal.deploy._protocol import TargetConfig
from skaal.deploy.aws._config import AwsConfig

if TYPE_CHECKING:
    from skaal.binding.model import Environment


class AwsTarget(BaseDeployTarget):
    """The AWS deploy target. Constructed once in `skaal.deploy.aws.__init__`."""

    target: ClassVar[Target] = Target.AWS
    _config_cls: ClassVar[type[TargetConfig]] = AwsConfig
    _required_extras: ClassVar[tuple[str, ...]] = (
        "pulumi",
        "pulumi_aws",
        "pulumi_docker",
        "pulumi_random",
    )

    def stack_config(self, env: Environment) -> Mapping[str, str]:
        """Wire `aws:region` into the Pulumi stack config when present."""
        if env.region:
            return {"aws:region": env.region}
        return {}


__all__ = ["AwsTarget"]
