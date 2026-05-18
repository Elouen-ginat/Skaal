"""End-to-end GCP synth tests using `pulumi.runtime.set_mocks` (ADR 042).

Each test mocks Pulumi's resource construction so we can assert on the
type and properties of the resources the GCP synth modules emit.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pulumi = pytest.importorskip("pulumi")
pytest.importorskip("pulumi_gcp")
pytest.importorskip("pulumi_docker")

# Importing `skaal.deploy.gcp` registers the GCP target.
import skaal.deploy.gcp  # noqa: E402, F401
from skaal import App, BlobStore, Store, Topic  # noqa: E402
from skaal.binding.model import Environment, LockFile, Target  # noqa: E402
from skaal.deploy import build_artefacts, synthesize_stack  # noqa: E402


class _Mocks(pulumi.runtime.Mocks):
    """Deterministic Pulumi mocks for GCP synth-time assertions."""

    def new_resource(self, args: pulumi.runtime.MockResourceArgs) -> tuple[str, dict[str, Any]]:
        outputs = dict(args.inputs)
        outputs.setdefault("name", args.name)
        outputs.setdefault("project", "test-project")
        outputs.setdefault("repository_id", args.name)
        outputs.setdefault("dataset_id", args.name.replace("-", "_"))
        outputs.setdefault("connection_name", f"test-project:us-central1:{args.name}")
        outputs.setdefault("secret_id", args.name)
        outputs.setdefault("uri", f"https://{args.name}-xyz-a.run.app")
        outputs.setdefault("email", f"{args.name}@test-project.iam.gserviceaccount.com")
        outputs.setdefault("location", "us-central1")
        return args.name + "-id", outputs

    def call(self, args: pulumi.runtime.MockCallArgs) -> dict[str, Any]:
        return {}


@pytest.fixture(autouse=True)
def _mocks() -> None:
    import asyncio

    try:
        asyncio.get_event_loop()
    except DeprecationWarning:
        asyncio.set_event_loop(asyncio.new_event_loop())
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    pulumi.runtime.set_mocks(_Mocks(), preview=False)


def _gcp_env() -> Environment:
    from skaal.binding.model import BackendConfig

    return Environment(
        name="prod",
        target=Target.GCP,
        region="us-central1",
        backends={"gcp": BackendConfig(project="test-project")},
    )


def _build(app: App, bound: Any, env: Environment, tmp_path: Path) -> Path:
    from skaal.deploy import AppSpec

    return build_artefacts(bound, env, AppSpec.for_app(app), out_dir=tmp_path)


def test_synth_stack_function_emits_cloud_run() -> None:
    app = App("svc")

    @app.expose()
    async def greet(name: str) -> dict[str, str]:
        return {"hello": name}

    env = _gcp_env()
    bound = app.plan(env, lock=LockFile())
    # Cloud Run synth needs a build dir even when no artefacts are referenced.
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        build_dir = _build(app, bound, env, Path(tmp))
        results = synthesize_stack(bound, env, build_dir)
    assert results
    [(rid, result)] = list(results.items())
    assert "greet" in rid
    assert result.primary.__class__.__name__ == "Service"


def test_synth_stack_firestore_for_store() -> None:
    from pydantic import BaseModel

    class User(BaseModel):
        name: str

    app = App("svc")

    @app.storage
    class Users(Store[User]):
        pass

    @app.expose()
    async def stub() -> None:
        return None

    env = _gcp_env()
    bound = app.plan(env, lock=LockFile())
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        build_dir = _build(app, bound, env, Path(tmp))
        results = synthesize_stack(bound, env, build_dir)
    firestore_results = [r for r in results.values() if r.primary.__class__.__name__ == "Database"]
    assert firestore_results, "Firestore database resource not emitted"


def test_synth_stack_gcs_for_blob() -> None:
    app = App("svc")

    @app.storage(kind="blob")
    class Photos(BlobStore):
        pass

    @app.expose()
    async def stub() -> None:
        return None

    env = _gcp_env()
    bound = app.plan(env, lock=LockFile())
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        build_dir = _build(app, bound, env, Path(tmp))
        results = synthesize_stack(bound, env, build_dir)
    bucket_results = [r for r in results.values() if r.primary.__class__.__name__ == "Bucket"]
    assert bucket_results, "GCS bucket resource not emitted"


def test_synth_stack_pubsub_for_channel() -> None:
    app = App("svc")

    @app.channel()
    class Events(Topic[dict]):
        pass

    @app.expose()
    async def publish() -> None:
        await Events.send({})

    env = _gcp_env()
    bound = app.plan(env, lock=LockFile())
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        build_dir = _build(app, bound, env, Path(tmp))
        results = synthesize_stack(bound, env, build_dir)
    topic_results = [r for r in results.values() if r.primary.__class__.__name__ == "Topic"]
    assert topic_results, "Pub/Sub topic resource not emitted"


def test_synth_stack_bigquery_for_pinned_table() -> None:
    from sqlmodel import Field

    from skaal.backends.tokens import BigQuery
    from skaal.table import Table

    app = App("svc")

    @app.storage(kind="relational")
    class Sales(Table[BigQuery], table=True):
        __tablename__ = "sales_for_synth"  # type: ignore[assignment]

        id: str = Field(primary_key=True)
        sku: str

    @app.expose()
    async def stub() -> None:
        return None

    env = _gcp_env()
    bound = app.plan(env, lock=LockFile())
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        build_dir = _build(app, bound, env, Path(tmp))
        results = synthesize_stack(bound, env, build_dir)
    dataset_results = [r for r in results.values() if r.primary.__class__.__name__ == "Dataset"]
    assert dataset_results, "BigQuery dataset resource not emitted"
