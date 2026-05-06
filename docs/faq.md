# FAQ

Honest answers to the questions a new user usually has before adopting Skaal.

## Scope and maturity

### How mature is Skaal?

Alpha (0.3.1). The constraint model, Z3 solver, plan format, and generated deployment artifacts are stable in shape — but the API surface still moves. Breaking changes go through ADRs in [`docs/design/`](design/001-infrastructure-as-constraints.md).

The most exercised path is **local + AWS Lambda + DynamoDB / Postgres / S3**. GCP (Cloud Run, Firestore, GCS), the vector tier (Chroma, pgvector), and the Rust `mesh/` runtime are in active development.

### What does "Infrastructure as Constraints" actually mean in practice?

You declare what a resource must *do* — its read latency budget, durability class, throughput floor, residency, access pattern — and Skaal selects a concrete backend from a TOML catalog that satisfies all of those at the lowest declared cost. The choice is recorded in `plan.skaal.lock`, including rejected candidates and the reason each was rejected.

You change the backend by changing the catalog, not the application code.

### Is the solver overkill for small apps?

For a single `Map` and a single backend, yes — but the cost is negligible (Z3 returns in milliseconds for typical app graphs). The payoff is when the catalog has more than one viable backend per resource, when you have a development catalog and a production catalog, or when prices change and you re-solve instead of refactor.

## Lock-in and ejection

### Can I stop using Skaal and keep my deployment?

Yes. `skaal build` writes a complete Pulumi program plus Dockerfile, handler entrypoint, and stack metadata under `artifacts/`. Those files are normal Pulumi — you can commit them, run `pulumi up` directly, and never invoke Skaal again. The eject path is "stop running `skaal build`."

What you'd lose by ejecting:

- Re-solving when the catalog changes.
- The `plan.skaal.lock` audit trail.
- Decorator-driven regeneration of handlers.

What you'd keep:

- All generated infrastructure code.
- Your application code (`skaal` is an import; remove the decorators by inlining the chosen backend client).

### Does Skaal hide the Pulumi code?

No. `artifacts/` is meant to be readable. The generated Pulumi program uses standard `pulumi_aws` / `pulumi_gcp` resource types; there is no proprietary runtime.

## License

### Can I use Skaal in a closed-source SaaS?

Skaal is **GPL-3.0-or-later**. Running a GPL-licensed framework as part of a network service does not, on its own, force you to publish your service code — that obligation belongs to the **AGPL**, not GPL. However:

- Distributing a binary or container that bundles Skaal does trigger GPL source-availability obligations.
- We are not lawyers. If you ship product, ask yours.

The **generated artifacts** (your Pulumi program, your Dockerfile, your application code) are not derivative works of the framework in the GPL sense — they are configuration and your own code emitted from templates.

### Why GPL and not MIT / Apache?

To keep downstream forks of the framework itself open. The generated output is permissively usable; the planner and runtime are copyleft. If this is a blocker, [open an issue](https://github.com/Elouen-ginat/Skaal/issues) — relicensing can be discussed.

## Solver behavior

### What happens if no backend in the catalog satisfies my constraints?

`skaal plan` returns `UnsatisfiableConstraintsError` with the offending constraint and the closest candidates. Common causes:

- Latency budget tighter than any catalog entry advertises.
- Residency requirement not present on any backend in the active target.
- Conflicting durability + throughput pairs that no single backend covers.

Run `skaal plan --explain` to see candidate-by-candidate rejection reasons.

### Can I pin a backend instead of letting the solver choose?

Yes — declare a constraint that only one catalog entry satisfies (e.g. `backend="postgres"` in your storage decorator), or remove competing entries from the catalog with the `remove` overlay key. Pinning is supported but defeats the point; we prefer overlays.

### How fast is the solver?

Sub-second for application graphs we've tested (dozens of resources). Z3 caches between runs are not yet shared; this is on the roadmap.

## Operational concerns

### How are secrets handled?

Generated artifacts never embed secrets. Skaal references environment variables and the configured secrets backend (`skaal[secrets-aws]` or `skaal[secrets-gcp]`). Catalog files may contain non-sensitive deployment hints (region, table class) but not credentials.

### Does Skaal manage migrations?

Relational tier yes — SQLModel-backed entities use Alembic via `skaal migrate` (autogenerate, upgrade, downgrade, drift, dry-run SQL). Other tiers (DynamoDB, Firestore, blob, vector) follow the 6-stage migration engine where applicable; see [`skaal/migrate/`](https://github.com/Elouen-ginat/Skaal/tree/main/skaal/migrate).

### How do I observe a deployed Skaal app?

Runtime hooks expose OpenTelemetry traces and metrics when `skaal[runtime]` is installed. The runtime emits per-handler spans, per-storage-call spans, and solver decisions are tagged on the deployed stack. There is no proprietary collector — ship to whatever OTEL backend you already use.

## Comparison

### How does Skaal compare to Encore, SST, Wing, Modal, or plain Pulumi?

See the dedicated [comparison page](comparison.md).

### Why not just use `pulumi` directly?

You can. Skaal exists for the case where you want **one application file** to target multiple environments and let cost or capability differences pick the backend, without maintaining N parallel Pulumi programs by hand. If you have one target and one backend choice per resource, plain Pulumi is simpler.

## Contributing

### How do I propose a new backend or constraint type?

Open an issue first; significant changes go through an ADR under [`docs/design/`](design/001-infrastructure-as-constraints.md). For a backend, the checklist is in [`CONTRIBUTING.md`](https://github.com/Elouen-ginat/Skaal/blob/main/CONTRIBUTING.md): implementation under `skaal/backends/`, entry-point registration, catalog entry, contract test, doc update.

### Where do design discussions happen?

GitHub issues and pull requests, plus ADRs in `docs/design/`. There is no Discord or Slack yet — open an issue if you'd find one useful.
