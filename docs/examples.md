# Example Apps

The repository includes example apps that cover the shapes Skaal is meant to support in practice: simple services, mounted HTTP APIs, streaming responses, dashboards, uploads, and mesh-oriented patterns.

<div class="skaal-example-grid">
  <section class="skaal-example-card">
    <div>
      <h3>Hello World</h3>
      <p>The smallest end-to-end app model for learning how <code>App</code>, typed storage, and the local run loop fit together.</p>
      <div class="skaal-example-links">
        <a href="https://github.com/Elouen-ginat/Skaal/tree/main/examples/01_hello_world">Browse example</a>
      </div>
    </div>
  </section>
  <section class="skaal-example-card">
    <div>
      <h3>Todo API</h3>
      <p>A practical CRUD API shape that shows Skaal alongside a mounted HTTP framework.</p>
      <div class="skaal-example-links">
        <a href="https://github.com/Elouen-ginat/Skaal/tree/main/examples/02_todo_api">Browse example</a>
      </div>
    </div>
  </section>
  <section class="skaal-example-card">
    <div>
      <h3>Dash App and Task Dashboard</h3>
      <p>UI-oriented examples that show Skaal as the application and data layer underneath a dashboard surface.</p>
      <div class="skaal-example-links">
        <a href="https://github.com/Elouen-ginat/Skaal/tree/main/examples/03_dash_app">Dash app</a>
        <a href="https://github.com/Elouen-ginat/Skaal/tree/main/examples/05_task_dashboard">Task dashboard</a>
      </div>
    </div>
  </section>
  <section class="skaal-example-card">
    <div>
      <h3>FastAPI Streaming and Uploads</h3>
      <p>Examples for streaming responses and multipart workflows using the mounted-ASGI model.</p>
      <div class="skaal-example-links">
        <a href="https://github.com/Elouen-ginat/Skaal/tree/main/examples/06_fastapi_streaming">Streaming</a>
        <a href="https://github.com/Elouen-ginat/Skaal/tree/main/examples/07_file_upload_api">File uploads</a>
      </div>
    </div>
  </section>
  <section class="skaal-example-card">
    <div>
      <h3>Mesh Counter</h3>
      <p>An example focused on the optional distributed mesh runtime surface and actor-style composition.</p>
      <div class="skaal-example-links">
        <a href="https://github.com/Elouen-ginat/Skaal/tree/main/examples/04_mesh_counter">Browse example</a>
      </div>
    </div>
  </section>
  <section class="skaal-example-card">
    <div>
      <h3>Team Directory and top-level app examples</h3>
      <p>The repository also includes simpler top-level examples like <code>team_directory.py</code>, <code>todo_api.py</code>, <code>fastapi_streaming.py</code>, and <code>file_upload_api.py</code> for direct entry-point inspection.</p>
      <div class="skaal-example-links">
        <a href="https://github.com/Elouen-ginat/Skaal/tree/main/examples">Browse examples directory</a>
      </div>
    </div>
  </section>
</div>

## Which example to start from

- Start with Hello World if you are learning the application model.
- Start with Todo API if you want a real HTTP service shape.
- Start with Dash or Task Dashboard if you want a UI-first example.
- Start with FastAPI Streaming or File Upload API if your workload depends on streaming or multipart behavior.
- Start with Mesh Counter if you want to inspect the distributed runtime direction.

These examples are the fastest way to see how Skaal behaves outside a stripped-down API reference.
