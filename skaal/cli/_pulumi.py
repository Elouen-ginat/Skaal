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
      ``./.skaal/pulumi-state``. The local backend is selected unless the
      user has *both* an existing Pulumi Cloud login
      (``~/.pulumi/credentials.json``) and a non-empty
      ``PULUMI_ACCESS_TOKEN`` — credentials alone are not a reliable signal
      because ``pulumi/actions@v6`` creates the file even when no token is
      provided, which would otherwise route ``skaal destroy`` to a backend
      it cannot authenticate against. Once a project has any state under
      ``./.skaal/pulumi-state`` we stay on the local backend regardless,
      so destroy always finds the stack that deploy created.

    Both are applied with ``setdefault`` so caller-provided values win.
    """
    if "PULUMI_CONFIG_PASSPHRASE" not in os.environ:
        os.environ["PULUMI_CONFIG_PASSPHRASE"] = ""
    if "PULUMI_BACKEND_URL" not in os.environ:
        state_dir = (Path.cwd() / ".skaal" / "pulumi-state").resolve()
        credentials = Path.home() / ".pulumi" / "credentials.json"
        cloud_token = os.environ.get("PULUMI_ACCESS_TOKEN", "").strip()
        use_local = state_dir.exists() or not (credentials.exists() and cloud_token)
        if use_local:
            state_dir.mkdir(parents=True, exist_ok=True)
            os.environ["PULUMI_BACKEND_URL"] = state_dir.as_uri()
            console.print(
                f"[dim]Pulumi state → {state_dir} (set PULUMI_BACKEND_URL to override).[/dim]"
            )


__all__ = ["apply_pulumi_defaults"]
