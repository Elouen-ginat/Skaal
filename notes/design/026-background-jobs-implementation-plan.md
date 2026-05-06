# ADR 026 — Background Jobs via RQ in LocalRuntime

**Status:** Implemented
**Date:** 2026-05-05
**Related:** [user_gaps.md §B.6](../user_gaps.md#b6-compute--functions), [skaal/module.py](../../skaal/module.py), [skaal/runtime/local.py](../../skaal/runtime/local.py), [skaal/runtime/jobs.py](../../skaal/runtime/jobs.py), [skaal/types/job.py](../../skaal/types/job.py)

## Goal

Add a first-class jobs surface to Skaal so applications can register background handlers and enqueue immediate or delayed work without building `Channel` plus worker plumbing by hand.

The public shape is:

```python
app = skaal.App("mailer")

@app.job(retry=RetryPolicy(max_attempts=3, base_delay_ms=100, max_delay_ms=1000))
async def send_email(user_id: str) -> None:
    ...

runtime = LocalRuntime(app)
await app.enqueue("send_email", "u1")
await app.enqueue(send_email, "u2", delay="5m")
```

This closes the P0 jobs gap in `user_gaps.md` without changing the HTTP invoke seam or the recurring schedule system.

## Decision

Skaal keeps a Skaal-native public jobs API and uses RQ as the execution substrate inside `LocalRuntime`.

The earlier custom KV-backed queue design was discarded. RQ already provides the hard parts Skaal would otherwise reimplement poorly:

1. queue persistence
2. retry orchestration
3. delayed scheduling primitives
4. worker lifecycle and failure registries

The local runtime still owns the Skaal-specific parts:

1. job registration and qualified-name resolution
2. JSON payload validation
3. idempotency key semantics
4. marshaling execution back onto Skaal's main asyncio loop
5. readiness reporting and local developer ergonomics

## Target support

The jobs API is runtime-native, but deploy-target support is not uniform because the targets do not share the same execution model.

Currently supported deploy targets:

1. `local` Docker artifacts
2. `gcp-cloudrun`
3. `aws-lambda` with a dedicated jobs worker Lambda

Why the split exists:

1. Local Docker and Cloud Run host a long-lived process, so `LocalRuntime` can keep the RQ worker loop alive in-process.
2. The generated AWS request Lambda is still request-scoped, so AWS support uses a second Lambda as the jobs worker instead of pretending the request handler itself can host background work.

Skaal therefore wires Redis-backed jobs automatically for each supported target, but the concrete deploy shape differs:

1. local Docker: Redis sidecar plus in-process worker thread
2. Cloud Run: Memorystore Redis plus in-process worker loop inside the service container
3. AWS Lambda: ElastiCache Redis plus a dedicated worker Lambda, with the request Lambda asynchronously nudging the worker after immediate enqueue and an EventBridge one-minute tick covering delayed jobs

## Public API and types

### New public types

The jobs API adds [skaal/types/job.py](../../skaal/types/job.py) and re-exports these from both [skaal/types/__init__.py](../../skaal/types/__init__.py) and [skaal/__init__.py](../../skaal/__init__.py):

1. `JobSpec`

```python
@dataclass(frozen=True)
class JobSpec:
    name: str
    retry: RetryPolicy | None = None
```

Stored on handlers as `__skaal_job__` metadata.

2. `JobHandle`

```python
@dataclass(frozen=True)
class JobHandle:
    job_id: str
    job_name: str
    scheduled_for: datetime
```

Returned from `enqueue(...)` so callers can correlate queued work.

3. `JobStatus`

```python
class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
```

Reserved for future job-introspection APIs.

4. `JobResult`

```python
@dataclass(frozen=True)
class JobResult:
    job_id: str
    status: JobStatus
    attempts: int
    last_error: str | None = None
    completed_at: datetime | None = None
```

Reserved for future result and inspection APIs.

### Existing public types reused

The implementation deliberately reuses existing types instead of inventing jobs-specific copies:

1. `RetryPolicy` from [skaal/types/compute.py](../../skaal/types/compute.py)
2. `Duration` from [skaal/types/duration.py](../../skaal/types/duration.py)

### Module and app surface

[skaal/module.py](../../skaal/module.py) now owns jobs as a separate resource family.

Added members:

1. `self._jobs: dict[str, Any]`
2. `job(...)`
3. `enqueue(...)`
4. `_resolve_job(...)`
5. `_collect_jobs()`

`_collect_jobs()` is intentionally separate from `_collect_all()`. Jobs should resolve across mounted submodules even when those submodules are not exported as public HTTP surfaces.

`enqueue(...)` resolves either a callable or a qualified-name string and delegates to the bound runtime. Like `app.invoke(...)`, it raises when no runtime is active.

## LocalRuntime design

### Runtime-owned state

[skaal/runtime/local.py](../../skaal/runtime/local.py) owns the execution bridge from the public API to RQ.

Key state:

1. `_job_handlers: dict[str, tuple[str, Any]]`
2. `_job_connection: Any | None`
3. `_job_queue: rq.Queue | None`
4. `_job_task: asyncio.Task[None] | None`
5. `_job_stop: asyncio.Event`
6. `_job_loop: asyncio.AbstractEventLoop | None`
7. `_job_runtime_token: str`
8. `_job_telemetry: JobWorkerTelemetry`
9. `_autostart_task: asyncio.Task[None] | None`

The runtime token is stable per app name: `skaal-runtime:<app_name>`. That is required so delayed jobs queued before a runtime restart can route into the restarted runtime instance.

### Internal helper types and functions

[skaal/runtime/jobs.py](../../skaal/runtime/jobs.py) now contains the runtime-only adapter layer. The important pieces are:

1. `JobWorkerTelemetry`

```python
@dataclass
class JobWorkerTelemetry:
    queued: int = 0
    running: int = 0
    succeeded: int = 0
    failed: int = 0
    last_tick_at: datetime | None = None
```

2. `WindowsSimpleWorker(SimpleWorker)`

Uses `TimerDeathPenalty` and disables signal installation so burst workers can run safely from a background thread on Windows.

3. `default_job_connection(app_name: str) -> Any`

Resolution order:

1. use `SKAAL_JOBS_REDIS_URL` when set
2. otherwise use a per-app shared `fakeredis.FakeStrictRedis`

The fake Redis server is keyed by app name so delayed jobs survive runtime-object restarts in the same Python process.

4. `build_rq_retry(policy: RetryPolicy | None) -> rq.Retry | None`

Maps Skaal retry policy onto RQ retry intervals.

5. `unique_job_id(job_name: str, idempotency_key: str) -> str`

Builds a deterministic SHA-1-backed job ID so idempotent enqueue calls resolve to the same RQ job.

6. `register_runtime(token: str, runtime: Any) -> None`
7. `unregister_runtime(token: str) -> None`
8. `execute_registered_job(runtime_token: str, job_name: str, args: list[Any] | None, kwargs: dict[str, Any] | None) -> Any`

RQ never executes nested or local handler functions directly. Instead, Skaal queues the top-level helper `skaal.runtime.jobs.execute_registered_job`, then uses the runtime token plus qualified job name to marshal real handler execution back onto the runtime's main asyncio loop with `asyncio.run_coroutine_threadsafe(...)`.

9. `promote_scheduled_jobs(queue: Any, connection: Any) -> int`

This directly drains `ScheduledJobRegistry` and re-enqueues due jobs. Skaal intentionally does not rely on `RQScheduler` in the local runtime loop because that API assumes scheduler locks and an external scheduler process model that does not fit the in-process Windows-safe runtime.

### Queueing semantics

`LocalRuntime.enqueue_job(...)` performs these steps:

1. call `ensure_started()`
2. resolve the job through `_job_handlers`
3. read `JobSpec` from `__skaal_job__`
4. normalize `delay` / `run_at` through `normalize_scheduled_for(...)`
5. validate that `args` and `kwargs` are JSON-serializable through `ensure_json_payload(...)`
6. derive an RQ retry policy through `build_rq_retry(...)`
7. if `idempotency_key` is present, derive a deterministic job ID with `unique_job_id(...)` and return the existing RQ job when present
8. enqueue immediate work with `Queue.enqueue(...)` or delayed work with `Queue.enqueue_at(...)`
9. store Skaal metadata in `job.meta["scheduled_for"]` and `job.meta["skaal_job_name"]`
10. return a `JobHandle` built from the RQ job record

### Worker loop

`_job_worker_loop()` is intentionally small and polls on a short interval:

1. promote due scheduled jobs from `ScheduledJobRegistry`
2. update readiness telemetry
3. if the live queue has ready jobs, run a single burst worker in a thread
4. sleep briefly unless shutdown has been requested

This keeps the runtime simple, avoids a long-running separate worker process, and remains safe on Windows.

### Restart behavior

When a new `LocalRuntime` is constructed inside an active asyncio loop, it now autostarts only if queued or scheduled jobs already exist. That behavior is targeted at recovery, not eager startup.

That choice matters for two reasons:

1. it lets delayed jobs resume after a runtime-object restart without requiring a manual `ensure_started()` call
2. it avoids racing a fresh worker on runtimes that have no background work yet

For WSGI / gunicorn-based local artifacts, `LocalRuntime.start_background_jobs()` now mirrors `start_background_scheduler()` so delayed jobs can resume in Docker deployments that do not call `serve()`.

## Persistence and durability

The implemented design no longer uses Skaal's KV storage abstraction for job persistence.

Instead:

1. jobs live in Redis-compatible RQ structures
2. delayed jobs live in RQ's `ScheduledJobRegistry`
3. failed jobs are counted from `FailedJobRegistry`

Durability depends on the selected connection:

1. default `fakeredis` preserves jobs across runtime-object restarts inside the same Python process
2. configured Redis via `SKAAL_JOBS_REDIS_URL` preserves jobs across full process restarts

This is a deliberate tradeoff. The local default is dependency-light and test-friendly. Real durability is available when the user points Skaal at Redis.

Deploy wiring now uses that same environment variable:

1. local Docker stacks provision a Redis sidecar and set `SKAAL_JOBS_REDIS_URL`
2. GCP Cloud Run stacks provision a dedicated Memorystore Redis instance and set `SKAAL_JOBS_REDIS_URL`
3. AWS Lambda stacks provision a dedicated ElastiCache Redis instance, set `SKAAL_JOBS_REDIS_URL`, and add `SKAAL_JOBS_WORKER_FUNCTION` so the request Lambda can nudge the worker Lambda

## Guarantees and limitations

Current guarantees:

1. at-least-once execution
2. delayed one-shot jobs
3. retry semantics reused from `RetryPolicy`
4. idempotent enqueue semantics through deterministic job IDs
5. mounted-module qualified-name resolution

Current non-goals:

1. result retrieval APIs
2. cancellation APIs
3. solver-level queue selection
4. exactly-once guarantees
5. per-job AWS native queue selection
6. arbitrary Python-object payload codecs

Only JSON-serializable arguments are accepted in the local runtime. That validation happens at enqueue time.

## Files changed

| File | Change |
|---|---|
| [skaal/types/job.py](../../skaal/types/job.py) | New public job types: `JobSpec`, `JobHandle`, `JobStatus`, `JobResult`. |
| [skaal/types/__init__.py](../../skaal/types/__init__.py) | Re-export job types. |
| [skaal/__init__.py](../../skaal/__init__.py) | Top-level job exports. |
| [skaal/module.py](../../skaal/module.py) | Add jobs registry, decorator, enqueue helper, qualified resolution, and recursive job collection. |
| [skaal/runtime/jobs.py](../../skaal/runtime/jobs.py) | New RQ adapter helpers, runtime registry bridge, retry conversion, delayed promotion, and Windows-safe worker subclass. |
| [skaal/runtime/local.py](../../skaal/runtime/local.py) | Integrate RQ queueing, worker lifecycle, delayed promotion, recovery autostart, and readiness telemetry. |
| [skaal/deploy/builders/local.py](../../skaal/deploy/builders/local.py) | Provision a Redis sidecar and `SKAAL_JOBS_REDIS_URL` when the app declares jobs. |
| [skaal/deploy/builders/gcp.py](../../skaal/deploy/builders/gcp.py) | Provision a dedicated Memorystore Redis instance and wire `SKAAL_JOBS_REDIS_URL` for jobs-enabled apps. |
| [skaal/deploy/builders/aws.py](../../skaal/deploy/builders/aws.py) | Provision ElastiCache Redis, a worker Lambda, and the worker-tick EventBridge rule for jobs-enabled apps. |
| [skaal/deploy/targets/aws.py](../../skaal/deploy/targets/aws.py) | Render a dedicated `worker.py` Lambda entrypoint for jobs-enabled artifacts. |
| [skaal/deploy/templates/aws/worker.py](../../skaal/deploy/templates/aws/worker.py) | Drain due jobs in bounded bursts inside the worker Lambda. |
| [skaal/deploy/templates/local/main_wsgi.py](../../skaal/deploy/templates/local/main_wsgi.py) | Start the background jobs worker thread for WSGI / gunicorn local artifacts. |
| [skaal/deploy/packaging/lambda_pkg.py](../../skaal/deploy/packaging/lambda_pkg.py) | Include `worker.py` in packaged Lambda artifacts when present. |
| [pyproject.toml](../../pyproject.toml) | Add `rq` and `fakeredis` to runtime and test dependencies. |
| [tests/api/test_jobs.py](../../tests/api/test_jobs.py) | Add jobs API registration coverage. |
| [tests/runtime/test_jobs.py](../../tests/runtime/test_jobs.py) | Add execution, delay, retry, idempotency, restart, and mounted-module coverage. |
| [tests/deploy/test_jobs_targets.py](../../tests/deploy/test_jobs_targets.py) | Add deploy-target coverage for local Docker, Cloud Run, and AWS Lambda rejection. |

## Validation

Focused validation command:

```bash
pytest tests/deploy/test_jobs_targets.py tests/deploy/test_local_stack.py tests/deploy/test_aws_apigw.py tests/cli/test_stack_profiles.py tests/api/test_jobs.py tests/runtime/test_jobs.py -q
```

Current result:

```text
48 passed in 4.47s
```

## Migration / compatibility

No backward-compatibility shim is provided.

This is a new API surface and the implementation deliberately chose RQ instead of the earlier custom queue plan. Existing `@app.function()` and `@app.schedule()` behavior is unchanged.

## Follow-up work

Natural next steps after this implementation are:

1. expose a `get_job(job_id)` read API that returns `JobResult`
2. document `SKAAL_JOBS_REDIS_URL` in user-facing docs for real durability and override behaviour
3. tighten the AWS delayed-job SLA if one-minute EventBridge cadence is too coarse for some workloads
