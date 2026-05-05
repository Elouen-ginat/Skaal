from __future__ import annotations

from pathlib import Path

from skaal import App
from skaal.deploy.builders.aws import build_pulumi_stack as build_aws_stack
from skaal.deploy.builders.gcp import build_pulumi_stack as build_gcp_stack
from skaal.deploy.builders.local import build_pulumi_stack as build_local_stack
from skaal.deploy.targets.aws import generate_artifacts as generate_aws_artifacts
from skaal.plan import PlanFile


def _make_jobs_app(name: str = "jobs-targets") -> App:
    app = App(name)

    @app.job()
    async def send_email(user_id: str) -> None:
        del user_id

    return app


def test_local_stack_provisions_jobs_redis_when_app_has_jobs(tmp_path: Path) -> None:
    app = _make_jobs_app("jobs-local")
    stack = build_local_stack(
        app,
        PlanFile(app_name="jobs-local", deploy_target="local", deploy_config={"port": 8123}),
        output_dir=tmp_path / "artifacts",
        source_module="examples.counter",
    )

    resources = stack["resources"]
    assert resources["redis"]["type"] == "docker:Container"
    app_envs = resources["app"]["properties"]["envs"]
    assert any(env.startswith("SKAAL_JOBS_REDIS_URL=redis://") for env in app_envs)
    app_options = resources["app"].get("options") or {}
    assert "${redis}" in (app_options.get("dependsOn") or [])


def test_gcp_stack_provisions_jobs_redis_when_app_has_jobs() -> None:
    app = _make_jobs_app("jobs-gcp")
    stack = build_gcp_stack(
        app,
        PlanFile(app_name="jobs-gcp", deploy_target="gcp"),
        region="us-central1",
    )

    assert stack["config"]["jobsRedisSizeGb"] == {"type": "integer", "default": 1}
    resources = stack["resources"]
    assert resources["jobs-redis"]["type"] == "gcp:redis:Instance"
    assert resources["vpc-connector"]["type"] == "gcp:vpcaccess:Connector"

    envs = resources["cloud-run-service"]["properties"]["template"]["spec"]["containers"][0]["envs"]
    env_map = {entry["name"]: entry["value"] for entry in envs if "value" in entry}
    assert env_map["SKAAL_JOBS_REDIS_URL"] == "redis://${jobs-redis.host}:6379"


def test_aws_stack_provisions_jobs_worker_and_redis_when_app_has_jobs() -> None:
    app = _make_jobs_app("jobs-aws")
    stack = build_aws_stack(
        app, PlanFile(app_name="jobs-aws", deploy_target="aws"), region="us-east-1"
    )

    config = stack["config"]
    assert config["jobsWorkerMaxBursts"] == {"type": "integer", "default": 5}
    assert config["jobsWorkerMaxJobs"] == {"type": "integer", "default": 10}
    assert config["jobsRedisNodeType"] == {"type": "string", "default": "cache.t4g.micro"}

    resources = stack["resources"]
    assert resources["jobs-redis"]["type"] == "aws:elasticache:ReplicationGroup"
    assert resources["jobs-worker-fn"]["type"] == "aws:lambda:Function"
    assert resources["jobs-worker-rule"]["type"] == "aws:events:Rule"
    assert resources["jobs-worker-target"]["properties"]["arn"] == "${jobs-worker-fn.arn}"

    lambda_env = resources["lambda-fn"]["properties"]["environment"]["variables"]
    assert lambda_env["SKAAL_JOBS_REDIS_URL"] == "redis://${jobs-redis.primaryEndpointAddress}:6379"
    assert lambda_env["SKAAL_JOBS_WORKER_FUNCTION"] == "${jobs-worker-fn.name}"

    worker_env = resources["jobs-worker-fn"]["properties"]["environment"]["variables"]
    assert worker_env["SKAAL_JOBS_REDIS_URL"] == "redis://${jobs-redis.primaryEndpointAddress}:6379"
    assert worker_env["SKAAL_JOBS_WORKER_MAX_BURSTS"] == "${jobsWorkerMaxBursts}"
    assert worker_env["SKAAL_JOBS_WORKER_MAX_JOBS"] == "${jobsWorkerMaxJobs}"
    assert stack["outputs"]["jobsWorkerArn"] == "${jobs-worker-fn.arn}"


def test_aws_generate_artifacts_writes_worker_for_jobs(tmp_path: Path) -> None:
    output_dir = tmp_path / "artifacts"
    src_pkg = tmp_path / "examples"
    src_pkg.mkdir()
    (src_pkg / "__init__.py").write_text("", encoding="utf-8")

    generated = generate_aws_artifacts(
        _make_jobs_app("jobs-aws-artifacts"),
        PlanFile(app_name="jobs-aws-artifacts", deploy_target="aws"),
        output_dir=output_dir,
        source_module="examples.counter",
    )

    worker_path = output_dir / "worker.py"
    assert worker_path in generated
    assert worker_path.read_text(encoding="utf-8").strip().startswith('"""')
