"""Incremental Python port of the persist API over in-memory repositories.

This module mirrors the TypeScript persist route concepts without production DB
adapters, billing, telemetry, large-body limits, Elasticsearch, or daemon loops.
"""

from typing import Any

__all__ = ["PERSIST_V1_PREFIX", "PersistService", "create_persist_router"]


def __getattr__(name: str) -> Any:
    if name == "PersistService":
        from nango.persist.service import PersistService

        return PersistService
    if name in {"PERSIST_V1_PREFIX", "create_persist_router"}:
        from nango.persist.router import PERSIST_V1_PREFIX, create_persist_router

        exports = {
            "PERSIST_V1_PREFIX": PERSIST_V1_PREFIX,
            "create_persist_router": create_persist_router,
        }
        return exports[name]
    raise AttributeError(name)
