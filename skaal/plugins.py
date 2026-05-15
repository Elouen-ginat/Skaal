"""Skaal plugin protocol — entry-point-driven extension of the deploy + binding registries.

External libraries contribute to Skaal by declaring one or more
`SkaalPlugin` subclasses and exposing them via a ``skaal.plugins``
Python entry point. A plugin's `register(plugin_registry)` method can:

- Add a new `DeployTarget` (so a plugin can introduce an entirely new
  cloud like Azure or DigitalOcean).
- Add one or more synth modules to an existing target (so a plugin can
  introduce e.g. an Aurora RDS backend on AWS).
- Add `BackendEntry` rows to the binding registry so the binder
  recognises the new backend at `bind()` time.

Discovery is **lazy**: the first call to `get_target(...)` (deploy) or
`lookup(...)` / `tokens_for(...)` (binding) walks
``importlib.metadata.entry_points(group="skaal.plugins")`` exactly once
per interpreter, instantiates each plugin class, and runs
`plugin.register(plugin_registry)`. The flag is reset only by
`_reset_for_tests()`.

Plugin authors:

```toml
# pyproject.toml of `skaal-aws-aurora`
[project.entry-points."skaal.plugins"]
aurora = "skaal_aws_aurora:AuroraPlugin"
```

```python
# skaal_aws_aurora/__init__.py
from skaal import Backend, Target
from skaal.binding.registry import BackendEntry
from skaal.deploy import SynthContext, SynthResult, SynthSpec
from skaal.plugins import PluginRegistry, SkaalPlugin

class Aurora(Backend[object]):
    name = "aurora"
    kinds = frozenset({"relational"})

SPEC = SynthSpec(backends=("aurora",), kinds=frozenset({ResourceKind.RELATIONAL}))

def synthesize(ctx: SynthContext) -> SynthResult: ...

class AuroraPlugin(SkaalPlugin):
    name = "aurora"
    def register(self, registry: PluginRegistry) -> None:
        registry.add_backend(
            BackendEntry(token=Aurora, targets=frozenset({Target.AWS}))
        )
        # Hand any object exposing `SPEC: SynthSpec` + `synthesize: SynthFn`.
        registry.add_synth(Target.AWS, __import__(__name__))
```
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from threading import Lock
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, runtime_checkable

if TYPE_CHECKING:
    from skaal.binding.model import Target
    from skaal.binding.registry import BackendEntry
    from skaal.deploy._protocol import DeployTarget


_LOG = logging.getLogger("skaal.plugins")
_LOAD_LOCK = Lock()
_PLUGINS_LOADED = False


@runtime_checkable
class SkaalPlugin(Protocol):
    """A skaal plugin contributes infrastructure modules.

    Implementations declare a `name` class variable (used for logging
    and de-duplication) and a `register(plugin_registry)` method that
    invokes `add_target` / `add_synth` / `add_backend` to wire its
    contributions into the live registries.

    Plugins are instantiated once per interpreter via the
    ``skaal.plugins`` entry-point group; their `register(...)` method
    is called immediately after instantiation. Implementations must not
    perform deploy-time work in `register(...)` — that runs at every
    first lookup, including read-only ones like `skaal plan`.
    """

    name: ClassVar[str]

    def register(self, registry: PluginRegistry) -> None: ...


class PluginRegistry:
    """The contribution surface a plugin sees inside its `register(...)` call.

    Wraps the deploy and binding registries so a plugin has a single
    object to call methods on without reaching into private internals.
    The wrapper validates each contribution before delegating: bad
    contributions raise `SkaalDeployError` / `SkaalConfigError` with a
    clear message naming the offending plugin.
    """

    def __init__(self, plugin_name: str) -> None:
        self._plugin_name = plugin_name

    @property
    def plugin_name(self) -> str:
        return self._plugin_name

    def add_target(self, target: DeployTarget) -> None:
        """Register a new `DeployTarget` (a whole new cloud).

        Equivalent to `skaal.deploy.register_target(target)` but tagged
        with the contributing plugin's name for diagnostics.
        """
        from skaal.deploy._registry import register_target

        _LOG.debug(
            "plugin %r adding deploy target %r", self._plugin_name, target.target.value
        )
        register_target(target)

    def add_synth(self, target: Target, module: Any) -> None:
        """Add a synth module (must expose `SPEC` + `synthesize`) to a target.

        Raises:
            SkaalDeployError: If the target hasn't been registered yet,
                or `module` isn't a valid synth module.
        """
        from skaal.deploy._registry import get_target

        deploy_target = get_target(target)
        if not hasattr(deploy_target, "register_synth"):
            from skaal.errors import SkaalDeployError

            raise SkaalDeployError(
                f"Plugin {self._plugin_name!r} cannot add a synth to "
                f"target {target.value!r}: the target does not support "
                "late synth registration."
            )
        _LOG.debug(
            "plugin %r adding synth module %r to target %r",
            self._plugin_name,
            getattr(module, "__name__", module),
            target.value,
        )
        deploy_target.register_synth(module)

    def add_backend(self, entry: BackendEntry) -> None:
        """Register a `BackendEntry` in the binding registry."""
        from skaal.binding.registry import register_backend

        _LOG.debug(
            "plugin %r adding backend %r", self._plugin_name, entry.token.name
        )
        register_backend(entry)


def load_plugins(*, force: bool = False) -> None:
    """Walk ``skaal.plugins`` entry points and invoke each plugin's `register(...)`.

    Called lazily on first `get_target(...)` / `lookup(...)` /
    `tokens_for(...)`. Subsequent calls short-circuit; pass ``force=True``
    to bypass the load-once guard (used by the test reset helper).

    Each plugin's failure is contained: a broken plugin logs a warning
    and is skipped, but does not prevent other plugins (or the rest of
    Skaal) from loading.
    """
    global _PLUGINS_LOADED
    if _PLUGINS_LOADED and not force:
        return
    with _LOAD_LOCK:
        if _PLUGINS_LOADED and not force:
            return
        _PLUGINS_LOADED = True
        for plugin_cls in _discover_plugin_classes():
            _safe_register(plugin_cls)


def _discover_plugin_classes() -> Iterable[type[SkaalPlugin]]:
    """Iterate over plugin classes declared on the ``skaal.plugins`` group."""
    try:
        from importlib.metadata import entry_points
    except ImportError:  # pragma: no cover - stdlib since 3.8
        return ()

    discovered: list[type[SkaalPlugin]] = []
    try:
        eps: Any = entry_points(group="skaal.plugins")
    except TypeError:
        # Older importlib.metadata returns a dict-like object.
        eps = entry_points().get("skaal.plugins", ())

    for entry in eps:
        try:
            obj = entry.load()
        except Exception as exc:  # pragma: no cover - exercised in plugin tests
            _LOG.warning("failed to load plugin entry point %r: %s", entry.name, exc)
            continue
        if isinstance(obj, type) and isinstance(getattr(obj, "name", None), str):
            discovered.append(obj)
        else:
            _LOG.warning(
                "entry point %r did not point at a SkaalPlugin subclass: %r",
                entry.name,
                obj,
            )
    return discovered


def _safe_register(plugin_cls: type[SkaalPlugin]) -> None:
    """Instantiate `plugin_cls` and call `register(...)`, isolating failures."""
    name = getattr(plugin_cls, "name", plugin_cls.__name__)
    try:
        instance = plugin_cls()
        registry = PluginRegistry(name)
        instance.register(registry)
        _LOG.debug("plugin %r registered", name)
    except Exception as exc:  # pragma: no cover - exercised in plugin tests
        _LOG.warning("plugin %r failed to register: %s", name, exc)


def _reset_for_tests() -> None:
    """Clear the load-once flag so the next lookup re-walks entry points."""
    global _PLUGINS_LOADED
    with _LOAD_LOCK:
        _PLUGINS_LOADED = False


__all__ = [
    "PluginRegistry",
    "SkaalPlugin",
    "load_plugins",
]
