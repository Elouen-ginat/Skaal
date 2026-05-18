"""Tests for the runtime target registry."""

from __future__ import annotations

import pytest

from skaal.errors import RuntimeWiringError, SkaalConfigError
from skaal.inference.model import ResourceKind
from skaal.runtime._registry import (
    RuntimeBackendFactoryContext,
    RuntimeTargetRegistration,
    get_runtime_target,
    register_runtime_target,
)


def test_builtin_runtime_targets_are_registered() -> None:
    local = get_runtime_target("local")
    aws = get_runtime_target("aws")

    assert callable(local.adapter_for(ResourceKind.STORE))
    assert callable(aws.binding_wirer_for(ResourceKind.STORE))


def test_unknown_runtime_target_raises_clear_error() -> None:
    with pytest.raises(SkaalConfigError, match="No runtime target registered"):
        get_runtime_target("missing-runtime")


def test_runtime_target_backend_factory_lookup_is_scoped_by_kind() -> None:
    target = RuntimeTargetRegistration(name="test-runtime")
    register_runtime_target(target)

    with pytest.raises(RuntimeWiringError, match="No runtime backend factory registered"):
        target.build_backend(
            RuntimeBackendFactoryContext(
                target_name="test-runtime",
                resource_kind=ResourceKind.STORE,
                backend_name="sqlite",
                target=object(),
            )
        )
