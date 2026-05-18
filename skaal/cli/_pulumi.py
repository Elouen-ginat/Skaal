"""Shared Pulumi setup used by `skaal deploy` and `skaal destroy`."""

from __future__ import annotations

import os
from pathlib import Path

from rich.console import Console


def apply_pulumi_defaults(console: Console) -> None:
    """Set sensible Pulumi defaults so first-time deploys work out of the box.

    - ``PULUMI_CONFIG_PASSPHRASE``: defaults to an empty string. Pulumi
      refuses to create or open a stack without one when using a passphrase-
      encrypted backend; the empty string is the conventional "no encryption"
      value for local state.
    - ``PULUMI_BACKEND_URL``: defaults to a project-local file backend at
      ``./.skaal/pulumi-state`` when the user has neither set the env var
      nor run ``pulumi login`` (no ``~/.pulumi/credentials.json``). Users
      who already configured Pulumi keep their existing backend.

    Both are applied with ``setdefault`` so caller-provided values win.
    """
    if "PULUMI_CONFIG_PASSPHRASE" not in os.environ:
        os.environ["PULUMI_CONFIG_PASSPHRASE"] = ""
    if "PULUMI_BACKEND_URL" not in os.environ:
        credentials = Path.home() / ".pulumi" / "credentials.json"
        if not credentials.exists():
            state_dir = (Path.cwd() / ".skaal" / "pulumi-state").resolve()
            state_dir.mkdir(parents=True, exist_ok=True)
            os.environ["PULUMI_BACKEND_URL"] = state_dir.as_uri()
            console.print(
                f"[dim]Pulumi state → {state_dir} (set PULUMI_BACKEND_URL to override).[/dim]"
            )


__all__ = ["apply_pulumi_defaults"]
