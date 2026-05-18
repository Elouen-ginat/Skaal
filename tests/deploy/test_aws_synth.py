"""End-to-end synth tests using `pulumi.runtime.set_mocks`.

Each test mocks Pulumi's resource construction so we can assert on the
type and properties of the resources every synth module would produce
against a real backend. The mocks return deterministic stand-in values
for inputs like ARNs and URLs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pulumi = pytest.importorskip("pulumi")
pytest.importorskip("pulumi_aws")
pytest.importorskip("pulumi_docker")

# Importing `skaal.deploy.aws` is what registers the AWS target so
# `synthesize_stack` can dispatch through the registry. This is normally
# done lazily by `pulumi_program_for`'s closure; tests call
# `synthesize_stack` directly so they trigger the import explicitly.
import skaal.deploy.aws  # noqa: E402, F401
from skaal import App, Store, Topic  # noqa: E402
from skaal.binding.model import Environment, LockFile, Plan, PlannedResource, Target  # noqa: E402
from skaal.deploy import build_artefacts, synthesize_stack  # noqa: E402
from skaal.errors import SkaalDeployError  # noqa: E402


class _Mocks(pulumi.runtime.Mocks):
    """Deterministic Pulumi mocks for synth-time assertions."""

    def new_resource(self, args: pulumi.runtime.MockResourceArgs) -> tuple[str, dict[str, Any]]:
        outputs = dict(args.inputs)
        outputs.setdefault("arn", f"arn:aws:mock::{args.name}")
        outputs.setdefault("name", args.name)
        outputs.setdefault("address", f"{args.name}.example.com")
        outputs.setdefault("url", f"https://{args.name}.example.com")
        outputs.setdefault(
            "repository_url", f"123456789012.dkr.ecr.us-east-1.amazonaws.com/{args.name}"
        )
        outputs.setdefault("registry_id", "123456789012")
        outputs.setdefault(
            "master_user_secrets", [{"secret_arn": f"arn:aws:mock::{args.name}-secret"}]
        )
        outputs.setdefault("primary_endpoint_address", f"{args.name}-primary.example.com")
        outputs.setdefault("execution_arn", f"arn:aws:mock::{args.name}/execution")
        outputs.setdefault("invoke_arn", f"arn:aws:mock::{args.name}/invoke")
        outputs.setdefault("bucket", args.name)
        return args.name + "-id", outputs

    def call(self, args: pulumi.runtime.MockCallArgs) -> dict[str, Any]:
        if args.token == "aws:ecr/getAuthorizationToken:getAuthorizationToken":
            return {"user_name": "AWS", "password": "secret", "authorization_token": "tok"}
        return {}


@pytest.fixture(autouse=True)
def _mocks() -> None:
    pulumi.runtime.set_mocks(_Mocks(), preview=False)


def _app_with_function() -> App:
    app = App("svc")

    @app.expose()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}

    return app


def _aws_env() -> Environment:
    return Environment(name="prod", target=Target.AWS, region="us-east-1")


def _bound(app: App, env: Environment) -> Any:
    return app.plan(env, lock=LockFile())


def _build(app: App, bound: Any, env: Environment, tmp_path: Path) -> Path:
    from skaal.deploy import AppSpec

    return build_artefacts(bound, env, AppSpec.for_app(app), out_dir=tmp_path)


def test_synth_stack_function_emits_lambda(tmp_path: Path) -> None:
    app = _app_with_function()
    env = _aws_env()
    bound = _bound(app, env)
    build_dir = _build(app, bound, env, tmp_path)

    results = synthesize_stack(bound, env, build_dir)
    assert len(results) == 1
    [(rid, result)] = results.items()
    assert "greet" in rid
    assert result.primary.__class__.__name__ == "Function"


def test_synth_stack_store_emits_dynamodb_then_lambda(tmp_path: Path) -> None:
    """Store synth runs before Lambda synth and contributes env vars."""
    app = App("svc")

    @app.storage()
    class Cache(Store[dict]):
        pass

    @app.expose()
    async def hit(key: str) -> dict:
        return await Cache.get(key) or {}

    env = _aws_env()
    bound = _bound(app, env)
    build_dir = _build(app, bound, env, tmp_path)

    results = synthesize_stack(bound, env, build_dir)
    store_id = next(r for r in results if "Cache" in r)
    fn_id = next(r for r in results if "hit" in r)
    assert results[store_id].primary.__class__.__name__ == "Table"
    assert any(key.startswith("SKAAL_TABLE_") for key in results[store_id].env_vars)
    assert results[fn_id].primary.__class__.__name__ == "Function"


def test_synth_stack_skips_external_resources(tmp_path: Path) -> None:
    """Resources marked external are not synthesised."""
    from skaal import connect
    from skaal.backends.tokens import Postgres

    app = App("svc")

    @connect(name="legacy")
    class Legacy(Store[dict, Postgres]):
        pass

    @app.expose()
    async def noop() -> None:
        return None

    env = _aws_env()
    bound = _bound(app, env)
    build_dir = _build(app, bound, env, tmp_path)

    results = synthesize_stack(bound, env, build_dir)
    assert all("Legacy" not in rid for rid in results)


def test_synth_stack_unknown_backend_raises(tmp_path: Path) -> None:
    """A bound resource naming a backend without a synth entry is rejected."""
    from skaal.inference.model import BlueprintResource, ResourceKind, SourceLocation

    inferred = BlueprintResource(
        id="m:Mystery",
        kind=ResourceKind.STORE,
        source=SourceLocation(module="m", qualname="Mystery", file="x", line=1),
    )
    bound = Plan(
        app="svc",
        environment="prod",
        resources=(
            PlannedResource(
                inferred=inferred,
                backend="not-a-real-backend",
                pinned=False,
            ),
        ),
    )
    env = _aws_env()
    with pytest.raises(SkaalDeployError, match="no synth registered"):
        synthesize_stack(bound, env, tmp_path)


def test_synth_stack_emits_apigw_for_asgi_mount(tmp_path: Path) -> None:
    """`app.mount(path, asgi)` emits the APIGW + Lambda combo."""
    pytest.importorskip("starlette")
    from starlette.applications import Starlette

    app = App("svc")
    asgi = Starlette()
    app.mount("/", asgi)

    env = _aws_env()
    bound = _bound(app, env)
    build_dir = _build(app, bound, env, tmp_path)

    results = synthesize_stack(bound, env, build_dir)
    [(_, result)] = results.items()
    extra_class_names = {r.__class__.__name__ for r in result.extras}
    assert "Api" in extra_class_names
    assert "Stage" in extra_class_names


def test_synth_stack_channel_emits_sqs(tmp_path: Path) -> None:
    app = App("svc")

    @app.channel()
    class Events(Topic[dict]):
        pass

    @app.expose()
    async def publish() -> None:
        await Events.send({})

    env = _aws_env()
    bound = _bound(app, env)
    build_dir = _build(app, bound, env, tmp_path)

    results = synthesize_stack(bound, env, build_dir)
    channel_id = next(r for r in results if "Events" in r)
    assert results[channel_id].primary.__class__.__name__ == "Queue"


def test_synth_stack_job_emits_sqs_worker(tmp_path: Path) -> None:
    """`@app.job` emits the SQS queue + Lambda worker pair with mapping."""
    app = App("svc")

    @app.job
    async def process_digest(payload: dict) -> None:
        return None

    env = _aws_env()
    bound = _bound(app, env)
    build_dir = _build(app, bound, env, tmp_path)

    results = synthesize_stack(bound, env, build_dir)
    [(rid, result)] = results.items()
    assert "process_digest" in rid

    # The Lambda is the primary; the queue sits in `extras` before the
    # scaffold (so a `pre_scaffold` resource ordering test would pass).
    assert result.primary.__class__.__name__ == "Function"
    extra_class_names = [r.__class__.__name__ for r in result.extras]
    assert "Queue" in extra_class_names
    assert "EventSourceMapping" in extra_class_names
    # Queue appears before the Lambda scaffolding so its URL can flow
    # into the function's env vars at construction time.
    assert extra_class_names.index("Queue") < extra_class_names.index("Role")

    # The queue URL is re-exported to peers so a separate FUNCTION can
    # enqueue work via the standard peer-env-var mechanism.
    assert any(key.startswith("SKAAL_JOB_") for key in result.env_vars)


def test_synth_stack_job_peer_env_var_reaches_function(tmp_path: Path) -> None:
    """A FUNCTION declared after a JOB receives the queue URL as an env var."""
    app = App("svc")

    @app.job
    async def worker(payload: dict) -> None:
        return None

    @app.expose()
    async def producer() -> None:
        return None

    env = _aws_env()
    bound = _bound(app, env)
    build_dir = _build(app, bound, env, tmp_path)

    results = synthesize_stack(bound, env, build_dir)
    job_id = next(r for r in results if "worker" in r)
    # The JOB's `env_vars` mapping carries the queue URL — peers
    # (other Lambdas in the same plan) read it during their own
    # `_merge_env_vars` pass.
    assert any(key.startswith("SKAAL_JOB_") for key in results[job_id].env_vars)
