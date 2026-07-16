"""Operational log DTOs and repositories.

The Python core uses Postgres-backed operational logs as the target persistence model.
Elasticsearch compatibility may be added later as an optional adapter for existing
deployments, but it is intentionally not a dependency of this module.
"""

from nango.logs.models import (
    HttpRequest,
    HttpResponse,
    HttpRetry,
    ListMessagesResult,
    ListOperationsResult,
    LogError,
    MessageLogEntry,
    OperationDescriptor,
    OperationLogEntry,
    PersistResults,
    SearchPeriod,
)
from nango.logs.repository import InMemoryLogsRepository

__all__ = [
    "HttpRequest",
    "HttpResponse",
    "HttpRetry",
    "InMemoryLogsRepository",
    "ListMessagesResult",
    "ListOperationsResult",
    "LogError",
    "MessageLogEntry",
    "OperationDescriptor",
    "OperationLogEntry",
    "PersistResults",
    "SearchPeriod",
]
