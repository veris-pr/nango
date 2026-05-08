from datetime import UTC, datetime, timedelta

from nango.logs import (
    InMemoryLogsRepository,
    MessageLogEntry,
    OperationLogEntry,
    SearchPeriod,
)

BASE_TIME = datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC)


def operation_entry(
    operation_id: str,
    *,
    seconds: int = 0,
    state: str = "waiting",
    integration_name: str = "github-demo",
) -> OperationLogEntry:
    created_at = BASE_TIME + timedelta(seconds=seconds)
    return OperationLogEntry.model_validate(
        {
            "id": operation_id,
            "message": "Sync executed",
            "operation": {"type": "sync", "action": "run"},
            "state": state,
            "accountId": 1,
            "accountName": "Acme",
            "environmentId": 10,
            "environmentName": "dev",
            "integrationName": integration_name,
            "connectionName": "primary",
            "syncConfigName": "contacts",
            "createdAt": created_at,
            "updatedAt": created_at,
            "startedAt": None,
            "endedAt": None,
            "expiresAt": None,
            "meta": {"job": operation_id},
        }
    )


def message_entry(
    message_id: str, parent_id: str, *, seconds: int, message: str
) -> MessageLogEntry:
    return MessageLogEntry.model_validate(
        {
            "id": message_id,
            "parentId": parent_id,
            "accountId": 1,
            "message": message,
            "level": "info",
            "type": "log",
            "createdAt": BASE_TIME + timedelta(seconds=seconds),
            "meta": {"step": message_id},
        }
    )


def test_create_and_list_operations_with_filters() -> None:
    repository = InMemoryLogsRepository()
    repository.create_operation(operation_entry("op-old", seconds=1, state="success"))
    repository.create_operation(operation_entry("op-new", seconds=2, state="failed"))
    repository.create_operation(
        operation_entry("op-other", seconds=3, integration_name="slack-demo")
    )

    result = repository.list_operations(
        account_id=1,
        environment_id=10,
        limit=10,
        states=["failed"],
        integrations=["github-demo"],
    )

    assert [item.id for item in result.items] == ["op-new"]
    assert result.count == 1


def test_operation_search_matches_serialized_fields() -> None:
    repository = InMemoryLogsRepository()
    repository.create_operation(operation_entry("op-sync", integration_name="github-demo"))

    result = repository.list_operations(account_id=1, limit=10, search="github")

    assert [item.id for item in result.items] == ["op-sync"]


def test_operation_cursor_pages_deterministically() -> None:
    repository = InMemoryLogsRepository()
    repository.create_operation(operation_entry("op-1", seconds=1))
    repository.create_operation(operation_entry("op-2", seconds=2))
    repository.create_operation(operation_entry("op-3", seconds=3))

    first_page = repository.list_operations(account_id=1, limit=2)
    second_page = repository.list_operations(account_id=1, limit=2, cursor=first_page.cursor)

    assert [item.id for item in first_page.items] == ["op-3", "op-2"]
    assert [item.id for item in second_page.items] == ["op-1"]
    assert second_page.cursor is None


def test_create_list_and_search_messages() -> None:
    repository = InMemoryLogsRepository()
    repository.create_message(message_entry("msg-1", "op-1", seconds=1, message="started sync"))
    repository.create_message(message_entry("msg-2", "op-1", seconds=2, message="provider failed"))
    repository.create_message(message_entry("msg-3", "op-2", seconds=3, message="provider failed"))

    result = repository.list_messages(parent_id="op-1", limit=10, search="failed")

    assert [item.id for item in result.items] == ["msg-2"]
    assert result.count == 1


def test_message_cursors_page_after_and_before() -> None:
    repository = InMemoryLogsRepository()
    repository.create_message(message_entry("msg-1", "op-1", seconds=1, message="one"))
    repository.create_message(message_entry("msg-2", "op-1", seconds=2, message="two"))
    repository.create_message(message_entry("msg-3", "op-1", seconds=3, message="three"))

    first_page = repository.list_messages(parent_id="op-1", limit=2)
    older_page = repository.list_messages(
        parent_id="op-1", limit=2, cursor_after=first_page.cursor_after
    )
    newer_page = repository.list_messages(
        parent_id="op-1", limit=2, cursor_before=older_page.cursor_before
    )

    assert [item.id for item in first_page.items] == ["msg-3", "msg-2"]
    assert [item.id for item in older_page.items] == ["msg-1"]
    assert [item.id for item in newer_page.items] == ["msg-3", "msg-2"]


def test_period_filter_and_message_operation_search() -> None:
    repository = InMemoryLogsRepository()
    repository.create_operation(operation_entry("op-1", seconds=1))
    repository.create_operation(operation_entry("op-2", seconds=5))
    repository.create_message(message_entry("msg-1", "op-1", seconds=1, message="token refreshed"))
    repository.create_message(message_entry("msg-2", "op-2", seconds=5, message="sync skipped"))

    result = repository.list_operations(
        account_id=1,
        limit=10,
        period=SearchPeriod.model_validate(
            {"from": BASE_TIME, "to": BASE_TIME + timedelta(seconds=2)}
        ),
    )

    assert [item.id for item in result.items] == ["op-1"]
    assert repository.search_message_operation_ids(
        search="token", operation_ids=["op-1", "op-2"]
    ) == ["op-1"]


def test_log_entries_serialize_typescript_field_names() -> None:
    operation = operation_entry("op-serialize")
    message = message_entry("msg-serialize", "op-serialize", seconds=1, message="ready")

    assert operation.model_dump(mode="json", by_alias=True, exclude_none=True)["accountId"] == 1
    assert message.model_dump(mode="json", by_alias=True, exclude_none=True) == {
        "id": "msg-serialize",
        "source": "internal",
        "level": "info",
        "type": "log",
        "message": "ready",
        "parentId": "op-serialize",
        "accountId": 1,
        "meta": {"step": "msg-serialize"},
        "createdAt": "2025-01-02T03:04:06Z",
    }
