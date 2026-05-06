from __future__ import annotations

from typing import TYPE_CHECKING

from skaal.deploy.backends.handler import BackendHandler, get_handler
from skaal.types import BackendWiring

if TYPE_CHECKING:
    from skaal.plan import PlanFile


def _uses_namespace(handler: BackendHandler, *, kind: str) -> bool:
    # SQLite KV stores frequently share one file in local deploys, so each
    # store still needs its own namespace even if a catalog forgets to declare
    # that flag in [wire].
    return handler.uses_namespace or (handler.class_name == "SqliteBackend" and kind == "kv")


def _make_constructor(handler: BackendHandler, class_name: str, env_var: str, *, kind: str) -> str:
    uses_namespace = _uses_namespace(handler, kind=kind)
    if handler.env_prefix is None:
        if handler.path_default and uses_namespace:
            return f'{handler.class_name}("{handler.path_default}", namespace="{class_name}")'
        if handler.path_default:
            return f'{handler.class_name}("{handler.path_default}")'
        return f"{handler.class_name}()"
    if uses_namespace:
        return f'{handler.class_name}(os.environ["{env_var}"], namespace="{class_name}")'
    return f'{handler.class_name}(os.environ["{env_var}"])'


def build_wiring(plan: PlanFile, *, local: bool = False) -> BackendWiring:
    seen: set[str] = set()
    import_lines: list[str] = []
    override_lines: list[str] = []

    for qualified_name, spec in plan.storage.items():
        class_name = qualified_name.split(".")[-1]
        handler = get_handler(spec, local=local)
        env_var = f"{handler.env_prefix}_{class_name.upper()}" if handler.env_prefix else ""

        if handler.import_stmt not in seen:
            seen.add(handler.import_stmt)
            import_lines.append(handler.import_stmt)

        constructor = _make_constructor(handler, class_name, env_var, kind=spec.kind)
        override_lines.append(f'        "{class_name}": {constructor},')

    return BackendWiring("\n".join(import_lines), "\n".join(override_lines))


def build_wiring_aws(plan: PlanFile) -> BackendWiring:
    return build_wiring(plan, local=False)
