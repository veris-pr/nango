from __future__ import annotations

import base64
import json
from collections.abc import Iterable
from datetime import datetime
from typing import Literal

from nango.logs.models import (
    ListMessagesResult,
    ListOperationsResult,
    MessageLogEntry,
    OperationLogEntry,
    SearchPeriod,
)

CursorDirection = Literal["before", "after"]


class InMemoryLogsRepository:
    """Deterministic logs repository for tests and future Postgres parity work."""

    def __init__(self) -> None:
        self._operations: dict[str, OperationLogEntry] = {}
        self._messages: list[MessageLogEntry] = []

    def create_operation(self, entry: OperationLogEntry) -> OperationLogEntry:
        self._operations[entry.id] = entry
        return entry

    def create_message(self, entry: MessageLogEntry) -> MessageLogEntry:
        self._messages.append(entry)
        return entry

    def list_operations(
        self,
        *,
        account_id: int,
        limit: int,
        environment_id: int | None = None,
        states: list[str] | None = None,
        types: list[str] | None = None,
        integrations: list[str] | None = None,
        connections: list[str] | None = None,
        syncs: list[str] | None = None,
        period: SearchPeriod | None = None,
        search: str | None = None,
        cursor: str | None = None,
    ) -> ListOperationsResult:
        items = self._sort_operations(self._operations.values())
        items = [
            item
            for item in items
            if item.account_id == account_id
            and self._matches_optional_value(item.environment_id, environment_id)
            and self._matches_any(item.state, states)
            and self._matches_operation_type(item, types)
            and self._matches_any(item.integration_name, integrations)
            and self._matches_any(item.connection_name, connections)
            and self._matches_any(item.sync_config_name, syncs)
            and self._matches_period(item.created_at, period)
            and self._matches_search(item, search)
        ]
        page_with_extra = self._page_after(items, limit + 1, cursor)
        page = page_with_extra[:limit]
        next_cursor = self._cursor_for(page[-1]) if len(page_with_extra) > limit else None

        return ListOperationsResult(count=len(items), items=page, cursor=next_cursor)

    def list_messages(
        self,
        *,
        parent_id: str,
        limit: int,
        search: str | None = None,
        cursor_before: str | None = None,
        cursor_after: str | None = None,
        period: SearchPeriod | None = None,
    ) -> ListMessagesResult:
        items = [
            item
            for item in self._sort_messages(self._messages)
            if item.parent_id == parent_id
            and self._matches_period(item.created_at, period)
            and self._matches_search(item, search)
        ]

        if cursor_before:
            page = self._page_before(items, limit, cursor_before)
        else:
            page = self._page_after(items, limit, cursor_after)

        return ListMessagesResult(
            count=len(items),
            items=page,
            cursorBefore=self._cursor_for(page[0]) if page else None,
            cursorAfter=self._cursor_for(page[-1]) if page else None,
        )

    def search_message_operation_ids(self, *, search: str, operation_ids: list[str]) -> list[str]:
        allowed_ids = set(operation_ids)
        parent_ids = {
            item.parent_id
            for item in self._messages
            if item.parent_id in allowed_ids and self._matches_search(item, search)
        }
        return [operation_id for operation_id in operation_ids if operation_id in parent_ids]

    def _page_after[T](
        self, items: list[T], limit: int, cursor: str | None
    ) -> list[T]:
        start = self._cursor_index(items, cursor)
        return items[start : start + limit]

    def _page_before[T](self, items: list[T], limit: int, cursor: str) -> list[T]:
        end = max(self._cursor_index(items, cursor) - 1, 0)
        start = max(end - limit, 0)
        return items[start:end]

    def _cursor_index[T](self, items: list[T], cursor: str | None) -> int:
        if cursor is None:
            return 0

        sort_key = self._decode_cursor(cursor)
        for index, item in enumerate(items):
            if self._sort_key(item) == sort_key:
                return index + 1
        return 0

    def _cursor_for(self, item: OperationLogEntry | MessageLogEntry) -> str:
        payload = [item.created_at.isoformat(), item.id]
        return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()

    def _decode_cursor(self, cursor: str) -> tuple[str, str]:
        value = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        if not isinstance(value, list) or len(value) != 2:
            raise ValueError("invalid log cursor")
        return (str(value[0]), str(value[1]))

    def _sort_operations(self, items: Iterable[OperationLogEntry]) -> list[OperationLogEntry]:
        return sorted(items, key=lambda item: (item.created_at, item.id), reverse=True)

    def _sort_messages(self, items: Iterable[MessageLogEntry]) -> list[MessageLogEntry]:
        return sorted(items, key=lambda item: (item.created_at, item.id), reverse=True)

    def _sort_key(self, item: object) -> tuple[str, str]:
        if not isinstance(item, OperationLogEntry | MessageLogEntry):
            raise TypeError("log cursor item must be an operation or message")
        return (item.created_at.isoformat(), item.id)

    def _matches_optional_value(self, value: int | None, expected: int | None) -> bool:
        return expected is None or value == expected

    def _matches_any(self, value: object, candidates: list[str] | None) -> bool:
        if candidates is None or candidates == ["all"]:
            return True
        return str(value) in candidates

    def _matches_operation_type(self, item: OperationLogEntry, types: list[str] | None) -> bool:
        if types is None or types == ["all"]:
            return True

        operation_type = item.operation.type
        operation_action = item.operation.action
        return operation_type in types or f"{operation_type}:{operation_action}" in types

    def _matches_period(self, created_at: datetime, period: SearchPeriod | None) -> bool:
        return period is None or period.from_ <= created_at <= period.to

    def _matches_search(
        self, item: OperationLogEntry | MessageLogEntry, search: str | None
    ) -> bool:
        if not search:
            return True
        haystack = item.model_dump_json(by_alias=True, exclude_none=True).lower()
        return search.lower() in haystack
