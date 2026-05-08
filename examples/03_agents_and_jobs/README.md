# 03 — Agents, Jobs, and Schedules

A single Dash UI that exercises Skaal's dynamic surface:

| Card | Feature | Decorator |
| --- | --- | --- |
| ChatRoom — virtual actor | Persistent identity, single-threaded per id | `@app.agent(persistent=True)` |
| Background job | Worker-executed, retried on failure | `@app.job(retry=...)` + `app.enqueue(...)` |
| Resilient function | Auto-retries flaky upstreams | `@app.function(retry=RetryPolicy(...))` |
| Scheduled task | Periodic tick every 5 seconds | `@app.schedule(trigger=Every("5s"))` |

The UI also tails the job log and the most recent heartbeat so you can
watch the runtime actually fire timers and run retries.

## Run

```bash
pip install "skaal[serve,examples]" dash dash-bootstrap-components
python examples/03_agents_and_jobs/app.py
```

Then open [http://localhost:8050](http://localhost:8050).

## What to try

1. Bump the same room id a few times — the actor's `message_count` keeps
   incrementing because state is persisted. Restart the runtime; the count
   survives.
2. Enqueue a few `index_message` jobs. About one in three fails on the
   first try and is retried by the runtime worker.
3. Click "Invoke" on the resilient function. Half the calls fail
   internally; `RetryPolicy` smooths it over so the UI rarely sees an
   error.
4. Watch the heartbeat panel update on its own — that is `@app.schedule`
   firing every five seconds.
