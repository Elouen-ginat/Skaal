"""Tests for deploy protocol models and metadata normalization."""

from __future__ import annotations

import pytest

from skaal.backends.tokens import DynamoDB, Redis, RedisChannel
from skaal.binding.registry import lookup_token
from skaal.deploy._protocol import SynthSpec
from skaal.inference.model import ResourceKind


def test_synth_spec_derives_backend_names_and_kinds_from_tokens() -> None:
    spec = SynthSpec(tokens=(Redis, RedisChannel), description="Redis-backed store + channel.")
    redis_entries = tuple(lookup_token(token) for token in (Redis, RedisChannel))

    assert spec.token_classes == (Redis, RedisChannel)
    assert spec.backends == tuple(entry.name for entry in redis_entries)
    assert spec.kinds == frozenset(kind for entry in redis_entries for kind in entry.kinds)


def test_synth_spec_accepts_legacy_backend_names() -> None:
    spec = SynthSpec(backends=("dynamodb",), kinds=frozenset({ResourceKind.STORE}))
    dynamodb = lookup_token(DynamoDB)

    assert spec.token_classes == (DynamoDB,)
    assert spec.backends == (dynamodb.name,)
    assert spec.kinds == frozenset(dynamodb.kinds)


def test_synth_spec_rejects_mismatched_legacy_kinds() -> None:
    with pytest.raises(ValueError, match=r"kinds.*derived.*tokens.*match.*Expected.*Provided"):
        SynthSpec(backends=("dynamodb",), kinds=frozenset({ResourceKind.BLOB}))


def test_synth_spec_rejects_both_tokens_and_backends() -> None:
    with pytest.raises(ValueError, match="only one"):
        SynthSpec(tokens=(DynamoDB,), backends=("dynamodb",))


def test_synth_spec_requires_tokens_or_backends() -> None:
    with pytest.raises(ValueError, match="requires `tokens`"):
        SynthSpec()


def test_synth_spec_rejects_empty_backend_sequences() -> None:
    with pytest.raises(ValueError, match="at least one backend"):
        SynthSpec(tokens=())


def test_synth_spec_rejects_invalid_backend_items() -> None:
    with pytest.raises(TypeError, match="Backend"):
        SynthSpec(tokens=(object(),))
