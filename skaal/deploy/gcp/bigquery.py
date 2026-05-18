"""BigQuery synth — `gcp.bigquery.Dataset` + `gcp.bigquery.Table` per `RELATIONAL`.

Configuration tunables live in `GcpConfig.bigquery`; override via
``[env.<name>.backends.gcp.options.bigquery]`` in `skaal.toml`.

BigQuery is a non-default backend for `(relational, gcp)` — `Postgres`
(Cloud SQL) remains the default. Users opt in via type pin:

    class Sales(Table[BigQuery], table=True):
        ...

The synth emits the dataset and one table per `RELATIONAL[BigQuery]`
resource; the runtime adapter constructs `BigQueryBackend(project, dataset)`
from the env vars exposed below.
"""

from __future__ import annotations

from typing import ClassVar

import pulumi_gcp as gcp

from skaal.backends.tokens import BigQuery
from skaal.deploy._protocol import (
    SynthContext,
    SynthModule,
    SynthResult,
    SynthSpec,
    WherePreference,
    WhereSpec,
)
from skaal.deploy.gcp._config import GcpConfig
from skaal.deploy.gcp._where import (
    GCP_BIGQUERY_DATASET,
    GCP_BIGQUERY_TABLE,
    WHERE_FALLBACK,
    WHERE_PRIMARY,
    bigquery_dataset_console_url,
    bigquery_table_console_url,
)
from skaal.inference.model import ResourceKind


class BigQuerySynth(SynthModule[GcpConfig]):
    """`gcp.bigquery.Dataset` + `Table` for `Table[BigQuery]` analytics tables."""

    SPEC: ClassVar[SynthSpec] = SynthSpec(
        tokens=(BigQuery,),
        description="BigQuery dataset + table for analytics relational data.",
        where=WhereSpec(
            preferences=(
                WherePreference(
                    kind=ResourceKind.RELATIONAL,
                    provider_type=GCP_BIGQUERY_DATASET,
                    priority=WHERE_PRIMARY,
                ),
                WherePreference(
                    kind=ResourceKind.RELATIONAL,
                    provider_type=GCP_BIGQUERY_TABLE,
                    priority=WHERE_FALLBACK,
                ),
            ),
            console_url_resolvers={
                GCP_BIGQUERY_DATASET: bigquery_dataset_console_url,
                GCP_BIGQUERY_TABLE: bigquery_table_console_url,
            },
        ),
    )

    def synthesize(self, ctx: SynthContext[GcpConfig]) -> SynthResult:
        cfg = ctx.config.bigquery
        dataset_id = ctx.resource_slug.replace("-", "_")
        dataset = gcp.bigquery.Dataset(
            ctx.pulumi_name,
            dataset_id=dataset_id,
            location=cfg.location,
            delete_contents_on_destroy=cfg.delete_contents_on_destroy,
            labels=ctx.tags,
        )
        # The actual table schema is materialised by the runtime adapter
        # (`BigQueryBackend.ensure_relational_schema`) since it walks the
        # SQLModel metadata at startup. Pulumi just provisions the dataset
        # container — the runtime creates tables idempotently inside it.
        dataset_env = f"{cfg.env_var_prefix}{ctx.slug_key}{cfg.env_var_dataset_suffix}"
        project_env = f"{cfg.env_var_prefix}{ctx.slug_key}{cfg.env_var_project_suffix}"
        return SynthResult(
            resource_id=ctx.resource_id,
            primary=dataset,
            env_vars={
                dataset_env: dataset.dataset_id,
                project_env: dataset.project,
            },
        )


__all__ = ["BigQuerySynth"]
