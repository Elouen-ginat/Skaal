from __future__ import annotations

from skaal.deploy.backends._postgres import postgres_kv_plugin, postgres_vector_plugin

postgres_plugin = postgres_kv_plugin(
    "cloud-sql-postgres",
    target="gcp",
    extra_deps=("cloud-sql-python-connector[asyncpg]>=1.9",),
)

pgvector_plugin = postgres_vector_plugin(
    "cloud-sql-pgvector",
    target="gcp",
    extra_deps=(
        "cloud-sql-python-connector[asyncpg]>=1.9",
        "langchain-postgres>=0.0.17",
        "psycopg[binary]>=3.3",
    ),
)
