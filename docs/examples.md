# Example Apps

Four end-to-end examples cover the surface Skaal is meant to support in
practice. Each one is small, ships with a Dash interface so you can poke
it from a browser, and lives in its own folder under `examples/`.

<div class="skaal-example-grid">
  <section class="skaal-example-card">
    <div>
      <h3>01 — Quickstart</h3>
      <p>The smallest end-to-end Skaal app. A Dash UI exercises a single
      <code>Store[int]</code> behind <code>@app.function</code>s. Start here if
      you have never seen Skaal before.</p>
      <div class="skaal-example-links">
        <a href="https://github.com/Elouen-ginat/Skaal/tree/main/examples/01_quickstart">Browse example</a>
      </div>
    </div>
  </section>
  <section class="skaal-example-card">
    <div>
      <h3>02 — Storage tour</h3>
      <p>One Dash page, four storage tiers: KV with secondary index,
      relational SQLModel rows, blob uploads, and vector semantic search.
      All declared with the same <code>@app.storage</code> decorator.</p>
      <div class="skaal-example-links">
        <a href="https://github.com/Elouen-ginat/Skaal/tree/main/examples/02_storage_tour">Browse example</a>
      </div>
    </div>
  </section>
  <section class="skaal-example-card">
    <div>
      <h3>03 — Agents and jobs</h3>
      <p>Virtual actors (<code>@app.agent</code>), background jobs
      (<code>@app.job</code> + <code>app.enqueue</code>), scheduled tasks
      (<code>@app.schedule(Every(...))</code>), and resilient functions with
      <code>RetryPolicy</code>, all wired into one Dash UI.</p>
      <div class="skaal-example-links">
        <a href="https://github.com/Elouen-ginat/Skaal/tree/main/examples/03_agents_and_jobs">Browse example</a>
      </div>
    </div>
  </section>
  <section class="skaal-example-card">
    <div>
      <h3>04 — Fullstack split</h3>
      <p>Two Skaal apps in one repo. A backend with
      <code>Store[Task]</code> and <code>@app.function</code>s; a frontend
      that holds no storage but declares an <code>AppRef</code> to the
      backend and mounts a Dash UI. Includes a Makefile that chains both
      <code>skaal deploy</code> runs.</p>
      <div class="skaal-example-links">
        <a href="https://github.com/Elouen-ginat/Skaal/tree/main/examples/04_fullstack_split">Browse example</a>
      </div>
    </div>
  </section>
</div>

## Which example to start from

- **01 — Quickstart** if you are learning the application model.
- **02 — Storage tour** if you want to see the storage tier breadth in one
  place.
- **03 — Agents and jobs** if you want to inspect the dynamic, time-driven
  surface (actors, jobs, schedules, retries).
- **04 — Fullstack split** if you are sketching a real split deployment
  with two Skaal apps (one backend, one frontend) calling each other via
  `AppRef`.

Each example folder has its own `README.md` with the exact commands. The
short version is: install `skaal[serve,examples]` (plus extras the example
mentions), then run `python examples/<name>/app.py` and open
[http://localhost:8050](http://localhost:8050). For example 04 you start
the FastAPI backend on port 8000 first, then the Dash frontend on port
8050 in a second terminal.

## Going further — custom backends

The decorators in these examples are the user-facing surface, but every
backend selected by the solver is just a class implementing the
`StorageBackend` (or `BlobBackend`, channel) Protocol. See
[Extending Skaal — Custom Backends](custom-backends.md) for a walkthrough
that adds a new key-value backend, registers it via entry points, and
plugs it into a catalog so the solver can pick it.
