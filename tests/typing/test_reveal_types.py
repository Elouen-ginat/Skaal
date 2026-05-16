"""`pyright` `reveal_type` assertions for the §6.13.3 contract rows.

The test runs `pyright --outputjson` against a temp file containing
representative `reveal_type(...)` calls, parses the JSON, and asserts
that each line reveals the expected type. Skipped when `pyright` is not
on the `PATH` so contributors who only have `mypy` still get a green
suite; CI installs `pyright` in the `typecheck` dependency group so the
assertions run there.

Phase 5a covers the rows that do not depend on `.native()` typing:

- Decorator preserves signatures (call sites preserve `(user: User)
  -> CoroutineType[Any, Any, User]`)
- Pydantic models round-trip through `model_validate_json`
- `ResourceOverrides.backend` reveals `str | None`, not `Any`

Phase 5b extends the table to `.native()` typing once each `Backend`
token has its `NativeClient: type[ConcreteSDK]` declaration in place.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import textwrap

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("pyright") is None,
    reason="pyright not installed",
)


_PROBE = textwrap.dedent(
    """
    from __future__ import annotations

    from typing import cast

    from pydantic import BaseModel

    from skaal import App, Store
    from skaal.backends.redis import Redis
    from skaal.inference.model import InferredPlan, ResourceOverrides


    class User(BaseModel):
        id: str
        name: str


    a = App("probe")


    @a.storage
    class Users(Store[User]):
        pass


    @a.storage
    class Cache(Store[User, Redis]):
        pass


    @a.function()
    async def signup(user: User) -> User:
        return user


    plan = cast(InferredPlan, None)
    overrides = cast(ResourceOverrides, None)

    reveal_type(signup)
    reveal_type(signup(User(id="u1", name="Alice")))
    reveal_type(plan.model_validate_json("{}"))
    reveal_type(overrides.backend)
    """
).strip()


@pytest.fixture(scope="module")
def pyright_diagnostics(tmp_path_factory: pytest.TempPathFactory) -> list[dict]:
    tmp = tmp_path_factory.mktemp("reveal_types")
    probe = tmp / "probe.py"
    probe.write_text(_PROBE, encoding="utf-8")
    proc = subprocess.run(
        ["pyright", "--outputjson", str(probe)],
        check=False,
        capture_output=True,
        text=True,
    )
    payload = json.loads(proc.stdout or "{}")
    diags = payload.get("generalDiagnostics", [])
    return [d for d in diags if d.get("severity") == "information"]


def _messages(diags: list[dict]) -> list[str]:
    return [d.get("message", "") for d in diags]


def test_function_decorator_preserves_signature(pyright_diagnostics: list[dict]) -> None:
    """`signup`'s call signature survives the decoration.

    Per ADR 028 §6.13.3 the load-bearing property is that callers
    continue to see `(user: User)` after decoration. `Module.function`'s
    `F`-preserving overloads ensure the IDE sees the original callable
    shape; the call result is `Coroutine[..., User]` so `await signup(u)`
    still reveals `User` downstream.
    """
    messages = _messages(pyright_diagnostics)
    signup_msg = next((m for m in messages if 'Type of "signup"' in m), "")
    assert "user: User" in signup_msg, messages
    assert "User" in signup_msg, messages


def test_call_site_returns_coroutine_of_user(pyright_diagnostics: list[dict]) -> None:
    """`signup(User(...))` reveals a coroutine whose result is `User`."""
    messages = _messages(pyright_diagnostics)
    assert any(
        ("Coroutine" in msg or "CoroutineType" in msg) and "User" in msg for msg in messages
    ), messages


def test_inferred_plan_roundtrip_returns_inferred_plan(
    pyright_diagnostics: list[dict],
) -> None:
    """`InferredPlan.model_validate_json(...)` is typed as `InferredPlan`."""
    messages = _messages(pyright_diagnostics)
    plan_msg = next((m for m in messages if "plan.model_validate_json" in m), "")
    assert "InferredPlan" in plan_msg, messages


def test_resource_overrides_backend_is_str_or_none(
    pyright_diagnostics: list[dict],
) -> None:
    """`ResourceOverrides.backend` reveals `str | None`, not `Any`."""
    messages = _messages(pyright_diagnostics)
    backend_msg = next((m for m in messages if "overrides.backend" in m), "")
    assert "str" in backend_msg and "None" in backend_msg, messages
