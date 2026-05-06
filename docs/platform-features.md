# Platform Features

Skaal is not only a solver wrapper. It gives you one application model across typed data surfaces, compute, local runtime behavior, and generated deployment artifacts.

<div class="skaal-feature-grid">
  <section class="skaal-feature-card">
    <img src="../design_system/illustrations/stack-cubes.svg" alt="Illustration of stacked infrastructure layers." />
    <div>
      <h3>Typed data surfaces</h3>
      <ul>
        <li><code>Map[K, V]</code> and <code>Collection[T]</code> for application storage</li>
        <li><code>BlobStore</code> for files and object workflows</li>
        <li>relational and vector tiers for SQL and embedding use cases</li>
        <li>backend selection driven by catalogs for local, AWS, and GCP</li>
      </ul>
    </div>
  </section>
  <section class="skaal-feature-card">
    <img src="../design_system/illustrations/analytics-screen.svg" alt="Dashboard illustration for runtime and observability capabilities." />
    <div>
      <h3>Runtime and execution model</h3>
      <ul>
        <li>async-first runtime design</li>
        <li>resilience policies on compute functions</li>
        <li>schedules, channels, and background work support</li>
        <li>local serving, hot reload, and mounted ASGI or WSGI apps</li>
      </ul>
    </div>
  </section>
  <section class="skaal-feature-card">
    <img src="../design_system/illustrations/cloud-route.svg" alt="Cloud route illustration showing movement from local to cloud targets." />
    <div>
      <h3>Deployment without handwritten glue</h3>
      <ul>
        <li>generated Dockerfiles and runtime entry points</li>
        <li>Pulumi programs and stack metadata</li>
        <li>local target for Docker-backed development deployment</li>
        <li>AWS and GCP packaging flows from the same app definition</li>
      </ul>
    </div>
  </section>
  <section class="skaal-feature-card">
    <img src="../design_system/illustrations/code-console.svg" alt="Code console illustration for framework integration and developer workflow." />
    <div>
      <h3>Framework and product integration</h3>
      <ul>
        <li>FastAPI, Starlette, and Dash fit the mounted-app model well</li>
        <li>plugin discovery for backends, channels, and catalogs</li>
        <li>example apps for APIs, streaming, uploads, dashboards, and mesh flows</li>
        <li>Python API equivalents of the CLI for orchestration and testing</li>
      </ul>
    </div>
  </section>
</div>

## Capability areas

### Planning and selection

Skaal plans against TOML catalogs using a Z3-backed solver. That lets the app express required behavior while the catalog controls what is allowed in a given environment.

### Data and storage

The framework can reason about more than one storage shape. You can keep a simple typed key-value surface, move to blob workflows, or use relational and vector tiers when the workload needs them, without discarding the broader planning model.

### Runtime composition

`Module` and `App` let you build composable Skaal systems. HTTP is intentionally handled through mounted frameworks instead of forcing everything through a framework-specific abstraction. That keeps the runtime close to normal Python service architecture.

### Deployment outputs

The deployment pipeline produces real artifacts instead of asking you to hand-maintain the glue around them. That is the practical value of planning: once the route is selected, Skaal has enough information to generate the target-specific output.

## Where to drill deeper

- [How Skaal Works](how-it-works.md) for the lifecycle from constraints to artifacts
- [Catalogs](catalogs.md) for the environment model and overrides
- [CLI](cli.md) for operational commands
- [Python API](reference/python-api.md) for in-process planning and deployment
