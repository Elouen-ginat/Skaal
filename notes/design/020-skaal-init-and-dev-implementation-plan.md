# ADR 020 — `skaal init` and `skaal dev` Implementation Plan

**Status:** Superseded
**Date:** 2026-05-01
**Related:** [user_gaps.md §A.1](../user_gaps.md#a1-cli-zero-config-and-dev-loop), [skaal/cli/init_cmd.py](../../skaal/cli/init_cmd.py), [skaal/cli/run_cmd.py](../../skaal/cli/run_cmd.py), [skaal/cli/_reload.py](../../skaal/cli/_reload.py)

## Outcome

This ADR is historical only.

The original proposal was to add a dedicated `skaal dev` command as the friendly hot-reload entry point. That is no longer the intended product shape.

The shipped local-development workflow is:

- `skaal init` scaffolds a starter project
- `skaal run` is the local runtime and dev entry point
- hot reload is controlled through `skaal run --reload/--no-reload`
- reload defaults to auto mode, which turns on for interactive local development

## Guidance

Do not reopen this ADR as a missing-command implementation target.

If the local dev loop needs more work, frame it as one of these instead:

- documentation/help discoverability for the existing `skaal run` workflow
- CLI help polish around reload defaults, `--reload-dir`, or `[tool.skaal].app`
- a new product-shape ADR that explicitly replaces the `skaal run` model

Unless one of those conditions changes, the canonical dev-loop surface remains `skaal init` followed by `skaal run`.
