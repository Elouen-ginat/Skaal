"""Drift-detection tests for ``skaal migrate relational check``."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlmodel import Field, SQLModel

from skaal import App, api
from skaal.runtime.local import LocalRuntime


def _model_suffix(tmp_path: Path, variant: str) -> str:
    return f"{tmp_path.name}_{variant}".replace("-", "_")


def _build_user_model(tmp_path: Path, *, with_extra_column: bool) -> type[SQLModel]:
    suffix = _model_suffix(tmp_path, "extra" if with_extra_column else "base")
    fields: dict[str, object] = {
        "__module__": __name__,
        "__tablename__": f"users_{tmp_path.name}",
        "id": Field(default=None, primary_key=True),
        "email": Field(default=""),
        "__annotations__": {"id": int | None, "email": str},
    }
    if with_extra_column:
        fields["nickname"] = Field(default="")
        fields["__annotations__"] = {"id": int | None, "email": str, "nickname": str}

    return type(f"User_{suffix}", (SQLModel,), fields, table=True)


def _build_app(tmp_path: Path, with_extra_column: bool) -> App:
    app = App(name="check-app")
    User = _build_user_model(tmp_path, with_extra_column=with_extra_column)
    app.storage(kind="relational", read_latency="< 20ms", durability="persistent")(User)

    LocalRuntime.from_sqlite(app, db_path=tmp_path / "drift.db")
    return app


@pytest.mark.asyncio
async def test_check_at_head_is_empty(isolated_cwd: Path) -> None:
    app = _build_app(isolated_cwd, with_extra_column=False)
    await api.relational_autogenerate(app, message="initial")
    await api.relational_upgrade(app)

    plans = await api.relational_check(app)
    assert plans["sqlite"].is_empty


@pytest.mark.asyncio
async def test_check_detects_drift_when_model_adds_column(
    isolated_cwd: Path,
) -> None:
    # Initial deploy: model has only id+email.
    app = _build_app(isolated_cwd, with_extra_column=False)
    await api.relational_autogenerate(app, message="initial")
    await api.relational_upgrade(app)

    # New process: same DB, but the model now declares an extra column.
    SQLModel.metadata.clear()
    app2 = _build_app(isolated_cwd, with_extra_column=True)

    plans = await api.relational_check(app2)
    plan = plans["sqlite"]
    assert not plan.is_empty
    assert any(step.op.value == "add_column" for step in plan.steps)


@pytest.mark.asyncio
async def test_check_ignores_unregistered_tables(isolated_cwd: Path) -> None:
    """Tables outside the app's SQLModels (e.g. the KV facade) must not
    appear as ``drop_table`` in drift output."""
    app = _build_app(isolated_cwd, with_extra_column=False)
    await api.relational_autogenerate(app, message="initial")
    await api.relational_upgrade(app)

    # Sneak in an unregistered table via raw SQL.
    sync_url = f"sqlite:///{(isolated_cwd / 'drift.db').as_posix()}"
    engine = create_engine(sync_url)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE skaal_kv (ns TEXT, key TEXT, value TEXT)"))
    engine.dispose()

    plans = await api.relational_check(app)
    plan = plans["sqlite"]
    # No step should reference skaal_kv — include_object filters it out.
    assert not any(step.table == "skaal_kv" for step in plan.steps)
