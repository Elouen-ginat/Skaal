"""`BaseDeployTarget` — shared scaffolding for every concrete `DeployTarget`.

Each cloud target subclasses `BaseDeployTarget`, declares its
`TargetConfig` subclass, and uses `BaseDeployTarget.from_modules(...)` to
build itself from a tuple of synth-module objects. The factory walks each
module's `SPEC: SynthSpec` and `synthesize: SynthFn` and assembles the
dispatch table — the per-target `__init__.py` lists modules, not
backend-name → function entries.

Subclasses override:

- `target` — the `Target` enum value
- `_config_cls` — the `TargetConfig` subclass for this target
- `_required_extras` — importable module names the target depends on
- `stack_name(bound, env)` — usually overrideable for naming conventions
- `stack_config(env)` — for region / project / … config wiring
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar, Protocol

from skaal.deploy._protocol import (
    DeployTarget,
    SynthFn,
    SynthSpec,
    TargetConfig,
)
from skaal.errors import SkaalDeployError

if TYPE_CHECKING:
    from skaal.binding.model import BoundPlan, Environment, Target


class _SynthModule(Protocol):
    """Duck-typed view of a synth module: `SPEC` + `synthesize`.

    Each synth module declares `SPEC: SynthSpec` listing the backend
    names it covers, plus a `synthesize` function matching `SynthFn`.
    The factory in `BaseDeployTarget.from_modules` reads only these two
    attributes; nothing else in the module participates in dispatch.
    """

    SPEC: SynthSpec
    synthesize: SynthFn


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
        synth: Mapping[str, SynthFn],
        *,
        default_config: TargetConfig | None = None,
    ) -> None:
        self._synth: Mapping[str, SynthFn] = MappingProxyType(dict(synth))
        self._default_config: TargetConfig = (
            default_config if default_config is not None else self._config_cls()
        )

    @classmethod
    def from_modules(
        cls,
        modules: Iterable[Any],
        *,
        default_config: TargetConfig | None = None,
    ) -> BaseDeployTarget:
        """Build a target from a tuple of synth modules.

        Each module must satisfy the `_SynthModule` protocol (a
        `SPEC: SynthSpec` attribute plus a `synthesize: SynthFn`
        callable). The `Iterable[Any]` parameter type accepts plain
        Python modules — mypy cannot see module attributes
        structurally, so the duck-type check happens at runtime.

        Raises:
            SkaalDeployError: If two modules declare the same backend
                name in `SPEC.backends`, or a module is missing its
                `SPEC` / `synthesize` attribute.
        """
        dispatch: dict[str, SynthFn] = {}
        for module in modules:
            if not hasattr(module, "SPEC") or not hasattr(module, "synthesize"):
                raise SkaalDeployError(
                    f"Module {getattr(module, '__name__', module)!r} is not "
                    "a synth module: missing `SPEC` or `synthesize`."
                )
            spec = module.SPEC
            for backend in spec.backends:
                if backend in dispatch:
                    raise SkaalDeployError(
                        f"Duplicate synth registration for backend "
                        f"{backend!r}. Each backend name maps to exactly "
                        "one synth module."
                    )
                dispatch[backend] = module.synthesize
        return cls(dispatch, default_config=default_config)

    def lookup_synth(self, backend_name: str) -> SynthFn | None:
        return self._synth.get(backend_name)

    def supported_backends(self) -> frozenset[str]:
        return frozenset(self._synth)

    def default_config(self) -> TargetConfig:
        return self._default_config

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


__all__ = ["BaseDeployTarget"]
