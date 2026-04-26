"""Deploy registries and orchestration for Skaal artifact build and deploy."""

from __future__ import annotations

from typing import Any


def build_artifacts(*args: Any, **kwargs: Any) -> Any:
    from skaal.deploy.pipeline import build_artifacts as _build_artifacts

    return _build_artifacts(*args, **kwargs)


def deploy_artifacts(*args: Any, **kwargs: Any) -> Any:
    from skaal.deploy.pipeline import deploy_artifacts as _deploy_artifacts

    return _deploy_artifacts(*args, **kwargs)


def __getattr__(name: str) -> object:
    if name in {
        "BackendPlugin",
        "backend_registry",
        "get_backend_plugin",
        "get_target",
        "register_backend_plugin",
        "register_target",
        "resolve_backend_plugin",
        "target_registry",
        "Target",
    }:
        from skaal.deploy.plugin import BackendPlugin
        from skaal.deploy.registry import (
            backend_registry,
            get_backend_plugin,
            get_target,
            register_backend_plugin,
            register_target,
            resolve_backend_plugin,
            target_registry,
        )
        from skaal.deploy.targets.base import Target

        exports: dict[str, object] = {
            "BackendPlugin": BackendPlugin,
            "backend_registry": backend_registry,
            "get_backend_plugin": get_backend_plugin,
            "get_target": get_target,
            "register_backend_plugin": register_backend_plugin,
            "register_target": register_target,
            "resolve_backend_plugin": resolve_backend_plugin,
            "target_registry": target_registry,
            "Target": Target,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "BackendPlugin",
    "Target",
    "backend_registry",
    "build_artifacts",
    "deploy_artifacts",
    "get_backend_plugin",
    "get_target",
    "register_backend_plugin",
    "register_target",
    "resolve_backend_plugin",
    "target_registry",
]
