"""Cloud SQL Postgres synth — one `gcp.sql.DatabaseInstance` per `RELATIONAL`.

Configuration tunables live in `GcpConfig.postgres`; override via
``[env.<name>.backends.gcp.options.postgres]`` in `skaal.toml`.

The synth emits an instance, a database, a user, and a Secret Manager
secret carrying the generated password. The runtime adapter reads the
connection string from the secret + the instance's connection-name
env var.
"""

from __future__ import annotations

import secrets as _python_secrets
from typing import ClassVar

import pulumi
import pulumi_gcp as gcp

from skaal.backends.tokens import Postgres
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
    GCP_SECRETMANAGER_SECRET,
    GCP_SQL_INSTANCE,
    WHERE_FALLBACK,
    WHERE_PRIMARY,
    cloud_sql_console_url,
    secret_console_url,
)
from skaal.inference.model import ResourceKind


class CloudSqlPostgresSynth(SynthModule[GcpConfig]):
    """Cloud SQL Postgres instance for `Relational` resources bound to `postgres`."""

    SPEC: ClassVar[SynthSpec] = SynthSpec(
        tokens=(Postgres,),
        description="Cloud SQL Postgres instance + database + user + secret.",
        where=WhereSpec(
            preferences=(
                WherePreference(
                    kind=ResourceKind.RELATIONAL,
                    provider_type=GCP_SQL_INSTANCE,
                    priority=WHERE_PRIMARY,
                ),
                WherePreference(
                    kind=ResourceKind.RELATIONAL,
                    provider_type=GCP_SECRETMANAGER_SECRET,
                    priority=WHERE_FALLBACK,
                ),
            ),
            console_url_resolvers={
                GCP_SQL_INSTANCE: cloud_sql_console_url,
                GCP_SECRETMANAGER_SECRET: secret_console_url,
            },
        ),
    )

    def synthesize(self, ctx: SynthContext[GcpConfig]) -> SynthResult:
        cfg = ctx.config.postgres
        password = _python_secrets.token_urlsafe(24)
        instance = gcp.sql.DatabaseInstance(
            ctx.pulumi_name,
            database_version=cfg.database_version,
            region=ctx.env.region or "us-central1",
            deletion_protection=cfg.deletion_protection,
            settings=gcp.sql.DatabaseInstanceSettingsArgs(tier=cfg.tier),
        )
        database = gcp.sql.Database(
            f"{ctx.pulumi_name}-db",
            instance=instance.name,
            name=cfg.db_name,
        )
        user = gcp.sql.User(
            f"{ctx.pulumi_name}-user",
            instance=instance.name,
            name=cfg.username,
            password=password,
        )
        secret = gcp.secretmanager.Secret(
            f"{ctx.pulumi_name}-secret",
            secret_id=f"{ctx.resource_slug}-conn",
            replication=gcp.secretmanager.SecretReplicationArgs(
                auto=gcp.secretmanager.SecretReplicationAutoArgs()
            ),
            labels=ctx.tags,
        )
        secret_value = pulumi.Output.json_dumps(
            {
                "username": user.name,
                "password": password,
                "dbname": database.name,
                "instance_connection_name": instance.connection_name,
            }
        )
        secret_version = gcp.secretmanager.SecretVersion(
            f"{ctx.pulumi_name}-secret-version",
            secret=secret.id,
            secret_data=secret_value,
        )
        conn_env = f"{cfg.env_var_prefix}{ctx.slug_key}{cfg.env_var_conn_suffix}"
        secret_env = f"{cfg.env_var_prefix}{ctx.slug_key}{cfg.env_var_secret_suffix}"
        return SynthResult(
            resource_id=ctx.resource_id,
            primary=instance,
            extras=(database, user, secret, secret_version),
            env_vars={
                conn_env: instance.connection_name,
                secret_env: secret.secret_id,
            },
        )


__all__ = ["CloudSqlPostgresSynth"]
