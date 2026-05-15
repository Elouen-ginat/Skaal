"""Structural tests for the AWS synth dispatch table.

These tests guard the contract between the binding-layer defaults table
and the deploy-layer synth modules: every AWS-targetable backend must
have an entry in `AWS_SYNTH`, and every entry must be a callable. The
actual Pulumi resource emission is covered by `test_aws_synth.py`.

`pulumi_aws` is imported eagerly by `skaal.deploy.aws` so the module
itself requires the optional extra to load.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pulumi_aws")
pytest.importorskip("pulumi_docker")

from skaal.binding.model import Target
from skaal.binding.registry import REGISTRY
from skaal.deploy.aws import AWS_SYNTH


def test_aws_synth_covers_every_aws_backend() -> None:
    """Every backend whose `targets` include `aws` has a synth entry."""
    aws_backends = {
        entry.token.name
        for entry in REGISTRY
        if Target.AWS in entry.targets
    }
    # Phase 4 dispatches storage + compute kinds. SQS is registered as both a
    # CHANNEL backend (`sqs`) and indirectly inside the `sqs-lambda-worker`
    # synth — both names appear in the table.
    missing = aws_backends - set(AWS_SYNTH)
    assert not missing, f"AWS backends without a synth module: {sorted(missing)}"


def test_aws_synth_entries_are_callable() -> None:
    for name, fn in AWS_SYNTH.items():
        assert callable(fn), f"AWS_SYNTH[{name!r}] is not callable"


def test_aws_synth_table_is_immutable() -> None:
    """`AWS_SYNTH` is wrapped in `MappingProxyType`; mutation must raise."""
    with pytest.raises(TypeError):
        AWS_SYNTH["new-backend"] = lambda ctx: None  # type: ignore[index]
