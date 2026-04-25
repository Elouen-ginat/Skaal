from __future__ import annotations

from skaal.deploy.backends._postgres import postgres_kv_plugin, postgres_vector_plugin

postgres_plugin = postgres_kv_plugin(
    "rds-postgres",
    target="aws",
    extra_deps=("asyncpg>=0.29",),
)

pgvector_plugin = postgres_vector_plugin(
    "rds-pgvector",
    target="aws",
    extra_deps=("langchain-postgres>=0.0.17", "psycopg[binary]>=3.3"),
)
