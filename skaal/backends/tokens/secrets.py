"""Secret backend tokens."""

from skaal.backends._base import Backend


class DotenvSecret(Backend[object]):
    name = "dotenv"
    kinds = frozenset({"secret"})


class AwsSecretsManager(Backend[object]):
    name = "aws-secrets-manager"
    kinds = frozenset({"secret"})


class GcpSecretManager(Backend[object]):
    name = "gcp-secret-manager"
    kinds = frozenset({"secret"})


__all__ = ["AwsSecretsManager", "DotenvSecret", "GcpSecretManager"]
