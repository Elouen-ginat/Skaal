"""Counter API — minimal FastAPI + Store app for the cloud deploy tutorials.

Run locally:

    skaal run examples.counter_api:app --env local

Deploy to AWS:

    skaal deploy examples.counter_api:app --env prod --yes

Deploy to GCP:

    skaal deploy examples.counter_api:app --env prod --yes
"""

from fastapi import FastAPI

from skaal import App, Store

app = App("counter-api")
api = FastAPI(title="Skaal Counter API")


@app.storage
class Counts(Store[int]):
    """Simple named counters."""


@app.expose()
async def increment(name: str = "world") -> dict[str, str | int]:
    """Increment the greeting count for one name and return the new total."""
    count = (await Counts.get(name) or 0) + 1
    await Counts.set(name, count)
    return {"message": f"hello {name}", "count": count}


@api.get("/")
async def home(name: str = "world") -> dict[str, str | int]:
    """Public HTTP route that forwards to the Skaal-exposed function."""
    return await increment(name=name)


app.mount("/", api)
