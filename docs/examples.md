# Example Apps

The repository includes example apps that cover the shapes Skaal is meant to support in practice: simple services, mounted HTTP APIs, streaming responses, and uploads.

<div class="skaal-example-grid">
  <section class="skaal-example-card">
    <div>
      <h3>Hello World</h3>
      <p>The smallest end-to-end app model for learning how <code>App</code>, typed storage, and the local run loop fit together.</p>
      <div class="skaal-example-links">
        <a href="https://github.com/Elouen-ginat/Skaal/tree/main/examples/hello_world">Browse example</a>
      </div>
    </div>
  </section>
  <section class="skaal-example-card">
    <div>
      <h3>Todo API</h3>
      <p>A practical CRUD API shape that shows Skaal alongside a mounted HTTP framework.</p>
      <div class="skaal-example-links">
        <a href="https://github.com/Elouen-ginat/Skaal/tree/main/examples/todo_api">Browse example</a>
      </div>
    </div>
  </section>
  <section class="skaal-example-card">
    <div>
      <h3>FastAPI Streaming and Uploads</h3>
      <p>Examples for streaming responses and multipart workflows using the mounted-ASGI model.</p>
      <div class="skaal-example-links">
        <a href="https://github.com/Elouen-ginat/Skaal/tree/main/examples/fastapi_streaming">Streaming</a>
        <a href="https://github.com/Elouen-ginat/Skaal/tree/main/examples/file_upload_api">File uploads</a>
      </div>
    </div>
  </section>
  <section class="skaal-example-card">
    <div>
      <h3>Top-level single-file examples</h3>
      <p>Smaller single-module examples — <code>counter.py</code>, <code>session_cache.py</code>, and <code>team_directory.py</code> — sit at the top of <code>examples/</code> for direct entry-point inspection.</p>
      <div class="skaal-example-links">
        <a href="https://github.com/Elouen-ginat/Skaal/tree/main/examples">Browse examples directory</a>
      </div>
    </div>
  </section>
</div>

## Which example to start from

- Start with Hello World if you are learning the application model.
- Start with Todo API if you want a real HTTP service shape.
- Start with FastAPI Streaming or File Upload API if your workload depends on streaming or multipart behavior.

These examples are the fastest way to see how Skaal behaves outside a stripped-down API reference.
