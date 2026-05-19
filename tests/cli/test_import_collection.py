"""Import-safety regressions for CLI module collection."""

from __future__ import annotations

import builtins
import importlib
import sys
from collections.abc import Callable

import pytest


def _fresh_import(module_name: str) -> object:
    stale = [
        name for name in sys.modules if name == module_name or name.startswith(f"{module_name}.")
    ]
    for name in stale:
        sys.modules.pop(name, None)
    return importlib.import_module(module_name)


@pytest.mark.parametrize(
    ("module_name", "blocked_prefixes"),
    [
        (
            "skaal.cli.build_cmd",
            ("pulumi", "opentelemetry", "pulumi_aws", "pulumi_gcp", "pulumi_docker"),
        ),
        (
            "skaal.cli.deploy_cmd",
            ("pulumi", "opentelemetry", "pulumi_aws", "pulumi_gcp", "pulumi_docker"),
        ),
    ],
)
def test_cli_command_imports_do_not_pull_pulumi_at_collection_time(
    module_name: str,
    blocked_prefixes: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import: Callable[..., object] = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if any(name == prefix or name.startswith(f"{prefix}.") for prefix in blocked_prefixes):
            raise AssertionError(f"unexpected import during collection: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    imported = _fresh_import(module_name)
    assert imported is not None
