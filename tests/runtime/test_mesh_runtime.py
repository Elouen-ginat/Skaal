"""Tests for MeshRuntime and the skaal_mesh native extension.

All tests skip when the ``skaal_mesh`` extension is not installed so the CI
suite remains green on machines without a Rust toolchain.
"""

from __future__ import annotations

import json

import pytest

try:
    import skaal_mesh  # type: ignore[import-untyped]

    HAS_MESH = True
except ImportError:
    HAS_MESH = False

pytestmark = pytest.mark.skipif(not HAS_MESH, reason="skaal_mesh extension not installed")


# ── Low-level Rust extension tests ──────────────────────────────────────────


class TestSkaalMeshExtension:
    def test_create_and_health(self) -> None:
        m = skaal_mesh.SkaalMesh("test-app", "{}")
        h = json.loads(m.health_snapshot())
        assert h["app"] == "test-app"
        assert h["status"] == "ok"
        assert h["nodes"] == 1

    def test_register_node_and_list(self) -> None:
        m = skaal_mesh.SkaalMesh("test-app", "{}")
        m.register_node("node-1", "http://localhost:9001", ["fn_a"])
        nodes = sorted(m.list_nodes())
        assert nodes == ["node-0", "node-1"]

    def test_route_invoke_local(self) -> None:
        plan = json.dumps({"compute": {"add": {}}})
        m = skaal_mesh.SkaalMesh("test-app", plan)
        node_id, result = m.route_invoke("add", "{}")
        assert node_id == "node-0"
        assert result is None

    def test_route_invoke_remote(self) -> None:
        m = skaal_mesh.SkaalMesh("test-app", "{}")
        m.register_node("node-1", "http://remote:8000", ["remote_fn"])
        node_id, _ = m.route_invoke("remote_fn", "{}")
        assert node_id == "node-1"

    def test_route_invoke_unknown_raises(self) -> None:
        m = skaal_mesh.SkaalMesh("test-app", "{}")
        with pytest.raises(KeyError, match="no mesh node serves function"):
            m.route_invoke("does_not_exist", "{}")

    def test_agent_placement_round_robin(self) -> None:
        m = skaal_mesh.SkaalMesh("test-app", "{}")
        m.register_node("node-1", "http://n1:8000")

        n1 = m.route_agent_call("User", "u1", "greet", "{}")
        n2 = m.route_agent_call("User", "u2", "greet", "{}")
        # Two nodes → two agents should go to different nodes.
        assert {n1, n2} == {"node-0", "node-1"}

        # Same agent id re-routes to the same node (sticky).
        assert m.route_agent_call("User", "u1", "greet", "{}") == n1

    def test_channel_publish_consume(self) -> None:
        m = skaal_mesh.SkaalMesh("test-app", "{}")
        m.channel_publish("events", '{"type":"click"}')
        m.channel_publish("events", '{"type":"scroll"}')
        msgs = m.channel_consume("events")
        assert len(msgs) == 2
        # Second consume returns empty — messages were drained.
        assert m.channel_consume("events") == []

    def test_custom_node_id(self) -> None:
        m = skaal_mesh.SkaalMesh("app", "{}", "worker-7")
        h = json.loads(m.health_snapshot())
        assert h["node_id"] == "worker-7"


# ── MeshRuntime integration tests ───────────────────────────────────────────


class TestMeshRuntime:
    @pytest.mark.asyncio
    async def test_dispatch_and_health(self) -> None:
        from skaal import App
        from skaal.runtime.mesh_runtime import MeshRuntime

        app = App("mesh-test")

        @app.function
        async def greet(name: str = "world") -> dict:
            return {"hello": name}

        rt = MeshRuntime(app, plan_json=json.dumps({"compute": {"greet": {}}}))

        # Health endpoint includes mesh info.
        result, status = await rt._dispatch("GET", "/health", b"")
        assert status == 200
        assert result["status"] == "ok"
        assert "mesh" in result

        # Function invocation through the dispatch path.
        result, status = await rt._dispatch("POST", "/greet", json.dumps({"name": "mesh"}).encode())
        assert status == 200
        assert result == {"hello": "mesh"}

        await rt.shutdown()

    @pytest.mark.asyncio
    async def test_mesh_bridge_methods(self) -> None:
        from skaal import App
        from skaal.runtime.mesh_runtime import MeshRuntime

        app = App("bridge-test")

        @app.function
        async def noop() -> dict:
            return {}

        rt = MeshRuntime(app)

        rt.register_node("node-1", "http://n1:8000", ["noop"])
        h = rt.health()
        assert h["nodes"] == 2

        rt.channel_publish("t", {"x": 1})
        msgs = rt.channel_consume("t")
        assert msgs == [{"x": 1}]

        node = rt.route_agent("Agent", "a1", "method", {})
        assert node in ("node-0", "node-1")

        await rt.shutdown()
