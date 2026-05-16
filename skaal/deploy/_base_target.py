"""`BaseDeployTarget` — shared scaffolding for every concrete `DeployTarget`.

Each cloud target subclasses `BaseDeployTarget`, declares its
`TargetConfig` subclass, and uses `BaseDeployTarget.from_classes(...)` to
build itself from a tuple of `SynthModule` subclasses. The factory
instantiates each class once, reads its `SPEC: ClassVar[SynthSpec]`, and
binds the instance's `synthesize` method into the dispatch table — the
per-target `__init__.py` lists classes, not backend-name → function
entries.

Subclasses override:

- `target` — the `Target` enum value
- `_config_cls` — the `TargetConfig` subclass for this target
- `_required_extras` — importable module names the target depends on
- `stack_name(bound, env)` — overrideable for naming conventions
- `stack_config(env)` — for region / project / … config wiring
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from threading import Lock
from typing import TYPE_CHECKING, Any, ClassVar

from skaal.deploy._protocol import (
    ConsoleUrlResolver,
    DeployTarget,
    SynthFn,
    SynthModule,
    TargetConfig,
    WherePreference,
    WhereSpec,
)
from skaal.errors import SkaalDeployError
from skaal.inference.model import ResourceKind

if TYPE_CHECKING:
    from skaal.binding.model import BoundPlan, Environment, Target


class BaseDeployTarget(DeployTarget):
    """Shared `DeployTarget` implementation; concrete targets subclass.

    The class-level `target` and `_config_cls` ClassVars must be set by
    every subclass. The remaining methods (`stack_name`, `stack_config`,
    `required_extras`) have sensible defaults that most targets can
    override or leave alone.
    """

    target: ClassVar[Target]
    _config_cls: ClassVar[type[TargetConfig]]
    _required_extras: ClassVar[tuple[str, ...]] = ()

    def __init__(
        self,
        synths: Iterable[SynthModule[Any]] = (),
        *,
        default_config: TargetConfig | None = None,
    ) -> None:
        # Mutable storage so plugins can call `register_synth(...)` after
        # the target is built. Public accessors return snapshots so the
        # outside world sees read-only views.
        self._synth: dict[str, SynthFn] = {}
        self._synth_instances: dict[str, SynthModule[Any]] = {}
        self._where_console_url_resolvers: dict[str, ConsoleUrlResolver] = {}
        self._where_preferences: dict[ResourceKind, list[WherePreference]] = {}
        self._synth_lock: Lock = Lock()
        self._default_config: TargetConfig = (
            default_config if default_config is not None else self._config_cls()
        )
        for synth in synths:
            self._register_locked(synth)

    @classmethod
    def from_classes(
        cls,
        synth_classes: Iterable[type[SynthModule[Any]]],
        *,
        default_config: TargetConfig | None = None,
    ) -> BaseDeployTarget:
        """Build a target by instantiating each `SynthModule` subclass.

        Each class must declare `SPEC: ClassVar[SynthSpec]` and implement
        `synthesize(ctx)`. Instances are constructed with no arguments;
        synth classes that need parameters should accept them via class
        attributes or override `__init__` with safe defaults.

        Raises:
            SkaalDeployError: If two classes declare the same backend
                name in their `SPEC.backends`, or a class is missing
                `SPEC`.
        """
        instances: list[SynthModule[Any]] = []
        for synth_cls in synth_classes:
            if not hasattr(synth_cls, "SPEC"):
                raise SkaalDeployError(
                    f"{synth_cls.__name__!r} is not a valid SynthModule "
                    "subclass: missing `SPEC` class variable."
                )
            instances.append(synth_cls())
        return cls(instances, default_config=default_config)

    def register_synth(self, synth: SynthModule[Any]) -> None:
        """Add a plugin-contributed synth to this target.

        Re-registering the exact same instance is a silent no-op
        (idempotent for plugin double-loads). A different instance
        claiming the same backend name raises.

        Raises:
            SkaalDeployError: If `synth` lacks `SPEC`, or a different
                synth is already registered for one of its backend
                names.
        """
        with self._synth_lock:
            self._register_locked(synth)

    def _register_locked(self, synth: SynthModule[Any]) -> None:
        """Inner registration helper — caller must hold `_synth_lock`."""
        spec = getattr(synth, "SPEC", None)
        if spec is None or not hasattr(synth, "synthesize"):
            raise SkaalDeployError(
                f"{synth!r} is not a valid SynthModule: missing `SPEC` or `synthesize`."
            )
        synthesize = synth.synthesize
        for backend in spec.backends:
            existing_instance = self._synth_instances.get(backend)
            if existing_instance is synth:
                continue
            if existing_instance is not None:
                raise SkaalDeployError(
                    f"Backend {backend!r} on target "
                    f"{self.target.value!r} is already wired to "
                    f"{type(existing_instance).__name__!r}; a plugin "
                    f"tried to override it with "
                    f"{type(synth).__name__!r}."
                )
            self._synth[backend] = synthesize
            self._synth_instances[backend] = synth
        if spec.where is not None:
            self._register_where_locked(spec.where, owner=type(synth).__name__)

    def lookup_synth(self, backend_name: str) -> SynthFn | None:
        with self._synth_lock:
            return self._synth.get(backend_name)

    def supported_backends(self) -> frozenset[str]:
        with self._synth_lock:
            return frozenset(self._synth)

    def default_config(self) -> TargetConfig:
        return self._default_config

    def where_console_url_resolvers(self) -> Mapping[str, ConsoleUrlResolver]:
        with self._synth_lock:
            return dict(self._where_console_url_resolvers)

    def where_resource_type_preferences(self) -> Mapping[ResourceKind, tuple[str, ...]]:
        with self._synth_lock:
            return {
                kind: tuple(
                    preference.provider_type
                    for preference in sorted(preferences, key=lambda pref: -pref.priority)
                )
                for kind, preferences in self._where_preferences.items()
            }

    def config_for(self, env: Environment) -> TargetConfig:
        """Overlay any TOML overrides from `env.backends[<target>]`.

        Targets that need richer loading (multi-section overlays, secret
        refs, …) override this. The default reads
        `env.backends[<target.value>].options` and validates it against
        the target's `TargetConfig` schema.
        """
        backend_cfg = env.backends.get(self.target.value)
        if backend_cfg is None or not backend_cfg.options:
            return self._default_config
        merged = {
            **self._default_config.model_dump(),
            **backend_cfg.options,
        }
        return self._config_cls.model_validate(merged)

    def stack_name(self, bound: BoundPlan, env: Environment) -> str:
        return f"{bound.app}-{env.name}"

    def stack_config(self, env: Environment) -> Mapping[str, str]:
        return {}

    def required_extras(self) -> tuple[str, ...]:
        return self._required_extras

    def _register_where_locked(self, where: WhereSpec, *, owner: str) -> None:
        """Merge one synth's built-in `skaal where` metadata into the target.

        If two preferences name the same `(kind, provider_type)`, the
        higher priority wins. Equal priorities keep the earlier
        registration, which makes synth registration order the tie-breaker.
        """
        for provider_type, resolver in where.console_url_resolvers.items():
            existing = self._where_console_url_resolvers.get(provider_type)
            if existing is not None and existing is not resolver:
                raise SkaalDeployError(
                    f"Provider type {provider_type!r} on target {self.target.value!r} "
                    f"already has a `where` resolver; {owner!r} tried to replace it."
                )
            self._where_console_url_resolvers[provider_type] = resolver

        for preference in where.preferences:
            current = self._where_preferences.setdefault(preference.kind, [])
            for index, existing_preference in enumerate(current):
                if existing_preference.provider_type != preference.provider_type:
                    continue
                if existing_preference.priority < preference.priority:
                    current[index] = preference
                break
            else:
                current.append(preference)


__all__ = ["BaseDeployTarget"]
