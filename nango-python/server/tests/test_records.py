from __future__ import annotations

from datetime import UTC, datetime, timedelta

from nango.records import InMemoryRecordsRepository, RecordInput

BASE_TIME = datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.offset = 0

    def __call__(self) -> datetime:
        value = BASE_TIME + timedelta(seconds=self.offset)
        self.offset += 1
        return value


def record_input(
    external_id: str,
    *,
    data: dict[str, object] | None = None,
    metadata: dict[str, object] | None = None,
) -> RecordInput:
    return RecordInput(
        id=f"record-{external_id}",
        external_id=external_id,
        connection_id=10,
        model="Contact",
        data=data or {"id": external_id, "name": external_id},
        metadata=metadata or {},
    )


def test_upsert_is_idempotent_for_same_payload() -> None:
    repository = InMemoryRecordsRepository(clock=Clock())
    first = repository.upsert_records([record_input("a")])[0]
    second = repository.upsert_records([record_input("a")])[0]

    assert second == first


def test_upsert_replaces_existing_payload_and_preserves_created_at() -> None:
    repository = InMemoryRecordsRepository(clock=Clock())
    first = repository.upsert_records([record_input("a", data={"name": "old"})])[0]
    updated = repository.upsert_records([record_input("a", data={"name": "new"})])[0]

    assert updated.data == {"name": "new"}
    assert updated.created_at == first.created_at
    assert updated.updated_at > first.updated_at
    assert updated.record_metadata.last_action == "UPDATED"


def test_update_merges_existing_payload() -> None:
    repository = InMemoryRecordsRepository(clock=Clock())
    repository.upsert_records([record_input("a", data={"name": "Ada", "city": "Paris"})])
    updated = repository.update_records([record_input("a", data={"city": "Berlin"})])[0]

    assert updated.data == {"name": "Ada", "city": "Berlin"}


def test_list_records_pages_by_cursor_in_updated_at_id_order() -> None:
    repository = InMemoryRecordsRepository(clock=Clock())
    repository.upsert_records(
        [
            record_input("a"),
            record_input("b"),
            record_input("c"),
        ]
    )

    first_page = repository.list_records(connection_id=10, model="Contact", limit=2)
    second_page = repository.list_records(
        connection_id=10,
        model="Contact",
        limit=2,
        cursor=first_page.next_cursor,
    )

    assert [record.external_id for record in first_page.records] == ["a", "b"]
    assert [record.external_id for record in second_page.records] == ["c"]
    assert second_page.next_cursor is None


def test_delete_marks_records_deleted_and_count_ignores_deleted_records() -> None:
    repository = InMemoryRecordsRepository(clock=Clock())
    repository.upsert_records([record_input("a"), record_input("b")])

    deleted = repository.delete_records(connection_id=10, model="Contact", external_ids=["a"])
    result = repository.list_records(
        connection_id=10,
        model="Contact",
        include_deleted=False,
    )

    assert deleted == 1
    assert [record.external_id for record in result.records] == ["b"]
    assert repository.count_records(connection_id=10, model="Contact").count == 1


def test_metadata_is_preserved_on_upsert_and_list() -> None:
    repository = InMemoryRecordsRepository(clock=Clock())
    repository.upsert_records(
        [record_input("a", metadata={"syncId": "sync-1", "source": {"page": 1}})]
    )

    listed = repository.list_records(connection_id=10, model="Contact").records[0]

    assert listed.metadata == {"syncId": "sync-1", "source": {"page": 1}}


def test_checkpoint_metadata_can_be_saved_and_loaded() -> None:
    repository = InMemoryRecordsRepository(clock=Clock())
    page = repository.list_records(connection_id=10, model="Contact")
    checkpoint = repository.save_checkpoint(
        connection_id=10,
        model="Contact",
        name="sync",
        cursor=page.next_cursor,
    )

    assert repository.get_checkpoint(connection_id=10, model="Contact", name="sync") == checkpoint
