"""Deploy-target registry.

Each `skaal.deploy.<target>` package constructs a `DeployTarget` instance
and calls `register_target(...)` at import time. The `program` driver
looks up the right target via `get_target(env.target)`.

The registry lives in module-level state because `Environment.target` is
a fixed enum and there is exactly one canonical target per enum value
inside a given Python interpreter. Tests that need a custom target
should register it (re-registration silently overwrites) and reset via
`_reset_for_tests()` to clean up.
"""

from __future__ import annotations

from collections.abc import Mapping
from threading import Lock
from typing import TYPE_CHECKING

from skaal.errors import SkaalDeployError

if TYPE_CHECKING:
    from skaal.binding.model import Target
    from skaal.deploy._protocol import DeployTarget


_TARGETS: dict[Target, DeployTarget] = {}
_LOCK = Lock()


def register_target(target: DeployTarget) -> None:
    """Register a deploy target. Re-registration overwrites silently.

    Idempotency matters because target modules are typically imported
    once per process, but tests may import them through multiple paths
    (e.g. via `skaal.deploy` re-exports). A silent overwrite keeps
    that case painless; the singleton invariant is preserved by the
    fact that `target` is keyed by the `Target` enum.
    """
    with _LOCK:
        _TARGETS[target.target] = target


def get_target(target: Target) -> DeployTarget:
    """Return the registered target for `target` or raise.

    Raises:
        SkaalDeployError: If no target has been registered for `target`
            (typically because the target's module has not been imported,
            or the optional extras are missing).
    """
    deploy_target = _TARGETS.get(target)
    if deploy_target is None:
        registered = ", ".join(sorted(t.value for t in _TARGETS)) or "(none)"
        raise SkaalDeployError(
            f"No deploy target registered for {target.value!r}. "
            f"Registered targets: {registered}. Import the target's "
            "module (e.g. `import skaal.deploy.aws`) before invoking "
            "the program callable."
        )
    return deploy_target


def registered_targets() -> Mapping[Target, DeployTarget]:
    """Return a snapshot of every currently-registered target."""
    with _LOCK:
        return dict(_TARGETS)


def _reset_for_tests() -> None:
    """Clear the registry — exclusively for use by the test suite."""
    with _LOCK:
        _TARGETS.clear()


__all__ = [
    "get_target",
    "register_target",
    "registered_targets",
]
