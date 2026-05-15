"""Tests for `AppSpec` and `LoadedPlan` value types in `skaal.cli._load`."""

from __future__ import annotations

import pytest

from skaal import App
from skaal.cli._load import AppSpec, LoadedPlan


def test_app_spec_parse_canonical_form() -> None:
    spec = AppSpec.parse("examples.todo_api:app")
    assert spec.module == "examples.todo_api"
    assert spec.attribute == "app"
    assert spec.reference == "examples.todo_api:app"
    assert spec.top_package == "examples"


def test_app_spec_parse_top_level_module() -> None:
    spec = AppSpec.parse("counter:app")
    assert spec.module == "counter"
    assert spec.top_package == "counter"


def test_app_spec_parse_rejects_missing_colon() -> None:
    with pytest.raises(ValueError, match="not a `module:attribute`"):
        AppSpec.parse("examples.todo_api")


def test_app_spec_parse_handles_extra_colons_in_attribute() -> None:
    """A second colon stays inside the attribute side (`split(maxsplit=1)`)."""
    spec = AppSpec.parse("pkg.mod:Outer:inner")
    assert spec.module == "pkg.mod"
    assert spec.attribute == "Outer:inner"


def test_app_spec_for_app_uses_live_module() -> None:
    app = App("svc")
    spec = AppSpec.for_app(app)
    assert spec.attribute == "app"
    assert spec.module  # whatever the test module's name is, it's non-empty
    assert spec.reference == f"{spec.module}:app"


def test_app_spec_for_app_custom_attribute() -> None:
    app = App("svc")
    spec = AppSpec.for_app(app, attribute="my_app_var")
    assert spec.attribute == "my_app_var"


def test_app_spec_is_hashable_and_frozen() -> None:
    a = AppSpec(module="x.y", attribute="app")
    b = AppSpec(module="x.y", attribute="app")
    assert a == b
    assert hash(a) == hash(b)
    with pytest.raises(Exception):
        a.module = "z"  # type: ignore[misc]


def test_loaded_plan_carries_bound_and_env() -> None:
    """Constructing a `LoadedPlan` shape works without going through `load_plan`."""
    from skaal.binding import bind
    from skaal.binding.model import Environment, LockFile, Target

    app = App("svc")
    env = Environment(name="local", target=Target.LOCAL)
    bound = bind(app.infer(), env, LockFile())
    loaded = LoadedPlan(bound=bound, env=env)
    assert loaded.bound is bound
    assert loaded.env is env
