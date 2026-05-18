"""Root test configuration for pytest."""

from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def reset_migration_registry() -> Iterator[None]:
    """Ensure the migration registry is clean before each test."""
    from skaal.types.schema import _MIGRATIONS

    snapshot = dict(_MIGRATIONS)
    yield
    _MIGRATIONS.clear()
    _MIGRATIONS.update(snapshot)


@pytest.fixture(autouse=True)
def reset_skaal_settings_state() -> Iterator[None]:
    """Ensure cached Skaal settings never leak across tests."""
    from skaal.settings import reset_settings_cache

    reset_settings_cache()
    yield
    reset_settings_cache()
