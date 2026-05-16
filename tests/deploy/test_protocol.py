"""Tests for deploy protocol models and metadata normalization."""

from __future__ import annotations

import pytest

from skaal.backends._tokens import DynamoDB, Redis, RedisChannel
from skaal.deploy._protocol import SynthSpec
from skaal.inference.model import ResourceKind


def test_synth_spec_derives_backend_names_and_kinds_from_tokens() -> None:
    spec = SynthSpec(tokens=(Redis, RedisChannel), description="Redis-backed store + channel.")

    assert spec.token_classes == (Redis, RedisChannel)
    assert spec.backends == ("redis", "redis-channel")
    assert spec.kinds == frozenset({ResourceKind.STORE, ResourceKind.CHANNEL})


def test_synth_spec_accepts_legacy_backend_names() -> None:
    spec = SynthSpec(backends=("dynamodb",), kinds=frozenset({ResourceKind.STORE}))

    assert spec.token_classes == (DynamoDB,)
    assert spec.backends == ("dynamodb",)
    assert spec.kinds == frozenset({ResourceKind.STORE})


def test_synth_spec_rejects_mismatched_legacy_kinds() -> None:
    with pytest.raises(ValueError, match="derived"):
        SynthSpec(backends=("dynamodb",), kinds=frozenset({ResourceKind.BLOB}))
