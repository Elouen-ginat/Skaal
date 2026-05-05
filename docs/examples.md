# Example Apps

The repository includes example apps that cover the shapes Skaal is meant to support in practice: simple services, mounted HTTP APIs, streaming responses, dashboards, uploads, and mesh-oriented patterns.

<div class="skaal-example-grid">
  <section class="skaal-example-card">
    <div markdown="1">

### Hello World

The smallest end-to-end app model for learning how `App`, typed storage, and the local run loop fit together.

[Browse example](https://github.com/Elouen-ginat/Skaal/tree/main/examples/01_hello_world)

    </div>
  </section>
  <section class="skaal-example-card">
    <div markdown="1">

### Todo API

A practical CRUD API shape that shows Skaal alongside a mounted HTTP framework.

[Browse example](https://github.com/Elouen-ginat/Skaal/tree/main/examples/02_todo_api)

    </div>
  </section>
  <section class="skaal-example-card">
    <div markdown="1">

### Dash App and Task Dashboard

UI-oriented examples that show Skaal as the application and data layer underneath a dashboard surface.

[Dash app](https://github.com/Elouen-ginat/Skaal/tree/main/examples/03_dash_app)

[Task dashboard](https://github.com/Elouen-ginat/Skaal/tree/main/examples/05_task_dashboard)

    </div>
  </section>
  <section class="skaal-example-card">
    <div markdown="1">

### FastAPI Streaming and Uploads

Examples for streaming responses and multipart workflows using the mounted-ASGI model.

[Streaming](https://github.com/Elouen-ginat/Skaal/tree/main/examples/06_fastapi_streaming)

[File uploads](https://github.com/Elouen-ginat/Skaal/tree/main/examples/07_file_upload_api)

    </div>
  </section>
  <section class="skaal-example-card">
    <div markdown="1">

### Mesh Counter

An example focused on the optional distributed mesh runtime surface and actor-style composition.

[Browse example](https://github.com/Elouen-ginat/Skaal/tree/main/examples/04_mesh_counter)

    </div>
  </section>
  <section class="skaal-example-card">
    <div markdown="1">

### Team Directory and top-level app examples

The repository also includes simpler top-level examples like `team_directory.py`, `todo_api.py`, `fastapi_streaming.py`, and `file_upload_api.py` for direct entry-point inspection.

[Browse examples directory](https://github.com/Elouen-ginat/Skaal/tree/main/examples)

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
