"""Parity test conftest — re-exports the integration DB fixtures.

The DB fixtures (postgres testcontainer, migrated schema, session factory, clean_db)
are defined in ``tests/integration/conftest.py``. This file makes them available
to parity tests in ``tests/parity/``.
"""

from tests.integration.conftest import (  # noqa: F401
    clean_db,
    db_engine,
    db_session_factory,
    migrated_url,
    pg_container,
)