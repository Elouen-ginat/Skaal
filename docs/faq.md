# FAQ

Honest answers to the questions a new user usually has before adopting Skaal.

## Scope and maturity

### How mature is Skaal?

Alpha (`0.4.0a0`). The code-first primitives, environment binding, lock file, and deploy pipeline are in place. Some command groups are still catching up to that model. Breaking changes still go through ADRs in `notes/design/`.

The most exercised path today is local plus AWS-focused deployment. GCP and some CLI polish are still moving.

## Lock-in and ejection

### Can I stop using Skaal and keep my deployment?

Yes. `skaal build` writes a complete render tree under `.skaal/build/<env>/` by default. Those files are normal deploy artifacts: Dockerfiles, entrypoints, Pulumi program files, and stack metadata. The eject path is simple: stop regenerating them.

What you'd lose by ejecting:

- The environment-to-plan bind step.
- The `skaal.lock` pinning flow.
- The ability to regenerate the deploy output from the app graph.

What you'd keep:

- All generated infrastructure code.
- Your application code.

### Does Skaal hide the Pulumi code?

No. The render tree is meant to be readable. Skaal is opinionated about how it gets there, not about hiding the result.

## License

### Can I use Skaal in a closed-source SaaS?

Skaal is **GPL-3.0-or-later**. Running a GPL-licensed framework as part of a network service does not, on its own, force you to publish your service code — that obligation belongs to the **AGPL**, not GPL. However:

- Distributing a binary or container that bundles Skaal does trigger GPL source-availability obligations.
- We are not lawyers. If you ship product, ask yours.

The **generated artifacts** (your Pulumi program, your Dockerfile, your application code) are not derivative works of the framework in the GPL sense — they are configuration and your own code emitted from templates.

### Why GPL and not MIT / Apache?

To keep downstream forks of the framework itself open. The generated output is permissively usable; the planner and runtime are copyleft. If this is a blocker, [open an issue](https://github.com/Elouen-ginat/Skaal/issues) — relicensing can be discussed.

## Adoption

### When should I not use Skaal?

Do not use Skaal if any of these are true:

- You already know you want one cloud, one backend choice per resource, and handwritten Pulumi is fine.
- Your team wants a hosted platform instead of generated infrastructure you own.
- You need a stable project scaffolder and fully surfaced migrations in the CLI today.

Read [When to use Skaal](when-to-use.md) for the decision table.

### Is there a migration path from 0.3.x?

No. The current line is a new product surface. If you need the earlier release, pin `skaal==0.3.1`.

## Operational concerns

### How are secrets handled?

Generated artifacts should not embed secrets. Skaal references environment variables and the configured secrets backend. `skaal.toml` is for environment shape and backend options, not credentials.

### Does Skaal manage migrations?

The relational layer and migration engine exist in the codebase. The public migration CLI is still being wired into the current alpha command surface, so the docs call that out where it matters.

### How do I observe a deployed Skaal app?

Runtime hooks expose OpenTelemetry traces and metrics when `skaal[runtime]` is installed. The runtime emits per-handler spans, per-storage-call spans, and solver decisions are tagged on the deployed stack. There is no proprietary collector — ship to whatever OTEL backend you already use.

## Comparison

### How does Skaal compare to Encore, SST, Wing, Modal, or plain Pulumi?

See the dedicated [comparison page](comparison.md).

### Why not just use `pulumi` directly?

You can. Skaal exists for the case where you want one app graph to target more than one environment without hand-maintaining parallel Pulumi programs. If that is not your problem, plain Pulumi is simpler.

## Contributing

### How do I propose a new backend or primitive change?

Open an issue first; significant changes go through an ADR under [`notes/design/`](https://github.com/Elouen-ginat/Skaal/tree/main/notes/design). For a backend, the checklist is in [`CONTRIBUTING.md`](https://github.com/Elouen-ginat/Skaal/blob/main/CONTRIBUTING.md).

### Where do design discussions happen?

GitHub issues and pull requests, plus ADRs in `notes/design/`. There is no Discord or Slack yet — open an issue if you'd find one useful.
