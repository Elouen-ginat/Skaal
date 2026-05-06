# How Skaal Works

Skaal keeps the application model stable and treats infrastructure selection as a planning problem. You do not rewrite the app when you move from local development to a cloud target. You change the catalog, the target, and the environment-specific secrets. Skaal handles the rest.

<div class="skaal-flow-grid">
  <section class="skaal-flow-card">
    <img src="../design_system/components/constraint-tokens.svg" alt="Constraint tokens showing latency, durability, and throughput specifications." />
    <div>
      <h3>1. Declare the behavior you need</h3>
      <p>Use typed surfaces like <code>Map</code>, <code>Collection</code>, <code>BlobStore</code>, or <code>VectorStore</code>, then attach constraints with decorators such as <code>@storage</code>, <code>@function</code>, <code>@schedule</code>, and <code>@channel</code>.</p>
      <p>The app code describes required behavior, not vendor-specific infrastructure.</p>
    </div>
  </section>
  <section class="skaal-flow-card">
    <img src="../design_system/components/backend-card.svg" alt="Backend evaluation card showing a viable infrastructure option." />
    <div>
      <h3>2. Load the environment catalog</h3>
      <p>Catalogs describe the backend options available for a target environment. A local catalog might expose SQLite and filesystem storage. An AWS catalog might expose DynamoDB, S3, Lambda, and EventBridge.</p>
      <p>That gives the solver a bounded search space grounded in real infrastructure capabilities.</p>
    </div>
  </section>
  <section class="skaal-flow-card">
    <img src="../design_system/components/plan-graph-example.svg" alt="Plan graph showing a selected route through infrastructure options." />
    <div>
      <h3>3. Solve for the cheapest viable path</h3>
      <p>The Z3-backed planner evaluates the declared constraints against the catalog and selects a backend mix that satisfies them. The output is a plan, not a guess: the chosen route is explicit, explainable, and target-aware.</p>
      <p>This is the core Skaal trade. The solver owns infrastructure selection so your app code does not have to.</p>
    </div>
  </section>
  <section class="skaal-flow-card">
    <img src="../design_system/components/pulumi-output.svg" alt="Generated Pulumi output and deployment artifacts panel." />
    <div>
      <h3>4. Generate artifacts and run them</h3>
      <p>Once a plan exists, Skaal generates the runnable surface for the chosen target: Dockerfiles, runtime entry points, Pulumi programs, stack metadata, and local deployment outputs.</p>
      <p>You can run locally, or deploy the same application model to AWS or GCP.</p>
    </div>
  </section>
</div>

## The command loop

```bash
skaal plan --app myapp:app --catalog catalogs/local.toml
skaal build --app myapp:app --target local --catalog catalogs/local.toml
skaal deploy --app myapp:app --target local --catalog catalogs/local.toml
```

The same shape applies to cloud targets. You swap the target and catalog, not the business logic.

## What stays stable

<div class="skaal-split-callout">
  <div>
    <h3>Stable across environments</h3>
    <ul>
      <li>Your <code>App</code> and <code>Module</code> definitions</li>
      <li>Your typed storage and compute surfaces</li>
      <li>Your mounted HTTP framework shape</li>
      <li>Your public application logic</li>
    </ul>
  </div>
  <div>
    <h3>Environment-specific inputs</h3>
    <ul>
      <li>The catalog file</li>
      <li>The deployment target</li>
      <li>Region, project, and stack settings</li>
      <li>Secrets and external connection details</li>
    </ul>
  </div>
</div>

## Why this matters

Most frameworks make you commit to infrastructure in the same place you are still deciding application behavior. Skaal separates those concerns. The result is a cleaner development loop locally, and a clearer deployment story when the app needs to move.

Next steps:

- Read [Platform Features](platform-features.md) for the major capabilities across data, runtime, and deployment.
- Read [HTTP Integration](http.md) for the recommended ASGI mounting model.
- Read [Python API](reference/python-api.md) if you want to drive plan, build, or deploy flows directly from Python.
