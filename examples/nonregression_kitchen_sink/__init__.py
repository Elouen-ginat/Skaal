"""Kitchen-sink Skaal example used by the non-regression deploy suite.

The app exists purely to exercise every public decorator on `App` / `Module`
during the post-merge deploy/destroy lifecycle. It is **not** intended as a
tutorial example — see `examples/todo_api/` and `examples/counter.py` for
those. The shape is intentionally maximal: KV + blob + relational storage,
a sub-module, a typed channel, functions with every resilience policy, a
background job, and both `Every` and `Cron` schedules.
"""
