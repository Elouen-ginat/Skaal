# Example Apps

The repository examples are the fastest way to see the framework in real application shapes instead of isolated snippets.

<div class="skaal-example-grid">
  <section class="skaal-example-card">
    <div>
      <h3>Hello World</h3>
      <p>The smallest possible app model for learning how <code>App</code>, <code>Store</code>, and the local run loop fit together.</p>
      <div class="skaal-example-links">
        <a href="https://github.com/Elouen-ginat/Skaal/tree/main/examples/hello_world">Browse example</a>
      </div>
    </div>
  </section>
  <section class="skaal-example-card">
    <div>
      <h3>Todo API</h3>
      <p>A mounted FastAPI service with key-value and relational storage.</p>
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
      <h3>Single-file app declarations</h3>
      <p><code>counter.py</code>, <code>session_cache.py</code>, and <code>team_directory.py</code> show compact patterns for counters, Redis-pinned sessions, and secondary-index queries.</p>
      <div class="skaal-example-links">
        <a href="https://github.com/Elouen-ginat/Skaal/tree/main/examples">Browse examples directory</a>
      </div>
    </div>
  </section>
</div>

## Which example to start from

- Start with Hello World if you are learning the model.
- Start with `counter.py` if you want a single file and the generated invoke endpoint.
- Start with `counter_api.py` if you want the smallest mounted HTTP app that still deploys cleanly to AWS.
- Start with Todo API if you want a realistic mounted HTTP service.
- Start with FastAPI Streaming or File Upload API if your workload depends on streaming or multipart behavior.
- Start with Session Cache if you want to see a type-pinned backend.
- Start with Team Directory if you want to see native secondary indexes.

These examples are the best anchors for the tutorial track and the guide pages.
