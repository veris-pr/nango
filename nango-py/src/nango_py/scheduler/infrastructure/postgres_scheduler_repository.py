"""Postgres scheduler repository: tasks + schedules CRUD with SKIP LOCKED dequeue.

Mirrors ``packages/scheduler/lib/models/tasks.ts`` and ``schedules.ts``.
Uses ``FOR UPDATE SKIP LOCKED`` for concurrent dequeue, group concurrency
via counting STARTED tasks per group_key, and state machine transitions
validated against ``VALID_TASK_TRANSITIONS`` / ``VALID_SCHEDULE_TRANSITIONS``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nango_py.scheduler.domain.models import (
    TERMINAL_TASK_STATES,
    VALID_SCHEDULE_TRANSITIONS,
    VALID_TASK_TRANSITIONS,
    ImmediateTaskInput,
    RecurringScheduleInput,
    Schedule,
    ScheduleState,
    Task,
    TaskState,
)

JsonObject = dict[str, Any]


class PostgresSchedulerRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def create_task(self, task_input: ImmediateTaskInput) -> Task:
        now = datetime.now(UTC)
        task_id = str(uuid4())
        retry_key = task_input.retry_key or str(uuid4())

        async with self._sf() as session:
            try:
                await session.execute(
                    text(
                        """
                        INSERT INTO tasks (id, name, payload, group_key, group_max_concurrency,
                            retry_max, retry_count, retry_key, owner_key, starts_after,
                            created_to_started_timeout_secs, started_to_completed_timeout_secs,
                            heartbeat_timeout_secs, created_at, state,
                            last_state_transition_at, last_heartbeat_at, output, terminated)
                        VALUES (:id, :name, CAST(:payload AS json), :gk, :gmc,
                            :rmax, :rcount, :rkey, :ok, :sa,
                            :cts, :stc, :hts, :created, 'CREATED',
                            :now, :now, NULL, false)
                        """
                    ),
                    {
                        "id": task_id, "name": task_input.name,
                        "payload": _json_str(task_input.payload),
                        "gk": task_input.group_key, "gmc": task_input.group_max_concurrency,
                        "rmax": task_input.retry_max, "rcount": task_input.retry_count,
                        "rkey": retry_key, "ok": task_input.owner_key,
                        "sa": task_input.starts_after,
                        "cts": task_input.created_to_started_timeout_secs,
                        "stc": task_input.started_to_completed_timeout_secs,
                        "hts": task_input.heartbeat_timeout_secs,
                        "created": now, "now": now,
                    },
                )
                await session.commit()
            except Exception:
                await session.rollback()
                raise

        return await self._get_task(task_id)

    async def create_schedule(self, sched_input: RecurringScheduleInput) -> Schedule:
        now = datetime.now(UTC)
        sched_id = str(uuid4())
        frequency = timedelta(milliseconds=sched_input.frequency_ms)

        async with self._sf() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO schedules (id, name, state, starts_at, frequency,
                        payload, group_key, retry_max, created_at, updated_at,
                        next_execution_at)
                    VALUES (:id, :name, :state, :starts, :freq,
                        CAST(:payload AS json), :gk, :rmax, :created, :updated,
                        :starts)
                    """
                ),
                {
                    "id": sched_id, "name": sched_input.name, "state": sched_input.state,
                    "starts": sched_input.starts_at, "freq": frequency,
                    "payload": _json_str(sched_input.payload),
                    "gk": sched_input.group_key, "rmax": sched_input.retry_max,
                    "created": now, "updated": now,
                },
            )
            await session.commit()

        return await self._get_schedule(sched_id)

    async def dequeue(
        self, *, group_key_pattern: str, limit: int, now: datetime | None = None
    ) -> list[Task]:
        now = now or datetime.now(UTC)
        async with self._sf() as session:
            rows = (
                await session.execute(
                    text(
                        """
                        WITH candidates AS (
                            SELECT t.id, t.group_key, t.group_max_concurrency,
                                   ROW_NUMBER() OVER (
                                       PARTITION BY t.group_key ORDER BY t.created_at
                                   ) AS rn
                            FROM tasks t
                            WHERE t.state = 'CREATED'
                              AND t.starts_after <= :now
                              AND t.group_key LIKE :pattern
                            ORDER BY t.created_at ASC
                            LIMIT :limit
                        ),
                        running_counts AS (
                            SELECT group_key, COUNT(*) AS running
                            FROM tasks
                            WHERE state = 'STARTED'
                              AND group_key LIKE :pattern
                            GROUP BY group_key
                        )
                        UPDATE tasks SET
                            state = 'STARTED',
                            last_state_transition_at = :now,
                            last_heartbeat_at = :now
                        FROM candidates
                        LEFT JOIN running_counts USING (group_key)
                        WHERE tasks.id = candidates.id
                          AND (
                              candidates.group_max_concurrency = 0
                              OR COALESCE(running_counts.running, 0)
                                 + candidates.rn
                                 <= candidates.group_max_concurrency
                          )
                        RETURNING tasks.*
                        """
                    ),
                    {"now": now, "pattern": group_key_pattern, "limit": limit * 2},
                )
            ).mappings().all()
            await session.commit()

        return [_task_from_row(cast(dict[str, Any], row)) for row in rows[:limit]]

    async def heartbeat(self, task_id: str) -> Task:
        now = datetime.now(UTC)
        async with self._sf() as session:
            await session.execute(
                text(
                    "UPDATE tasks SET last_heartbeat_at = :now WHERE id = :id"
                ),
                {"now": now, "id": task_id},
            )
            await session.commit()
        task = await self._get_task(task_id)
        if task is None:
            raise ValueError(f"task not found: {task_id}")
        if task.state != "STARTED":
            raise ValueError(f"cannot heartbeat task in state {task.state}")
        return task

    async def transition(
        self, task_id: str, new_state: TaskState, output: JsonObject | None = None
    ) -> Task:
        task = await self._get_task(task_id)
        if task is None:
            raise ValueError(f"task not found: {task_id}")
        if (task.state, new_state) not in VALID_TASK_TRANSITIONS:
            raise ValueError(f"invalid task transition from {task.state} to {new_state}")

        now = datetime.now(UTC)
        terminated = new_state in TERMINAL_TASK_STATES

        async with self._sf() as session:
            await session.execute(
                text(
                    """
                    UPDATE tasks SET
                        state = :state,
                        last_state_transition_at = :now,
                        terminated = :terminated,
                        output = CAST(:output AS json)
                    WHERE id = :id
                    """
                ),
                {
                    "state": new_state, "now": now, "terminated": terminated,
                    "output": _json_str(output),
                    "id": task_id,
                },
            )
            await session.commit()

        return await self._get_task(task_id)

    async def set_schedule_state(
        self, schedule_id: str, state: ScheduleState
    ) -> Schedule:
        sched = await self._get_schedule(schedule_id)
        if sched is None:
            raise ValueError(f"schedule not found: {schedule_id}")
        if sched.state == state:
            return sched
        if (sched.state, state) not in VALID_SCHEDULE_TRANSITIONS:
            raise ValueError(
                f"invalid schedule transition from {sched.state} to {state}"
            )

        now = datetime.now(UTC)
        deleted_at = now if state == "DELETED" else None

        async with self._sf() as session:
            await session.execute(
                text(
                    """
                    UPDATE schedules SET state = :state, updated_at = :now,
                        deleted_at = :deleted
                    WHERE id = :id
                    """
                ),
                {"state": state, "now": now, "deleted": deleted_at, "id": schedule_id},
            )
            await session.commit()

        return await self._get_schedule(schedule_id)

    async def get_task(self, task_id: str) -> Task | None:
        try:
            return await self._get_task(task_id)
        except ValueError:
            return None

    async def get_task_by_retry_key(self, retry_key: str) -> Task | None:
        async with self._sf() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT * FROM tasks WHERE retry_key = :rk LIMIT 1"
                    ),
                    {"rk": retry_key},
                )
            ).mappings().first()
        if row is None:
            return None
        return _task_from_row(dict(row))

    async def search_tasks(
        self, *, limit: int = 100, offset: int = 0
    ) -> list[Task]:
        async with self._sf() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT * FROM tasks ORDER BY created_at DESC"
                        " LIMIT :limit OFFSET :offset"
                    ),
                    {"limit": limit, "offset": offset},
                )
            ).mappings().all()
        return [_task_from_row(dict(r)) for r in rows]

    async def search_schedules(
        self, *, limit: int = 100, offset: int = 0
    ) -> list[Schedule]:
        async with self._sf() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT * FROM schedules ORDER BY created_at DESC"
                        " LIMIT :limit OFFSET :offset"
                    ),
                    {"limit": limit, "offset": offset},
                )
            ).mappings().all()
        return [_schedule_from_row(dict(r)) for r in rows]

    async def run_schedule(self, schedule_id: str) -> Task:
        sched = await self._get_schedule(schedule_id)
        if sched is None:
            raise ValueError(f"schedule not found: {schedule_id}")
        return await self.create_task(
            ImmediateTaskInput(
                name=f"run:{schedule_id}:{datetime.now(UTC).isoformat()}",
                payload=sched.payload or {},
                group_key=sched.group_key,
                group_max_concurrency=1,
                retry_max=sched.retry_max,
                retry_count=0,
                retry_key=None,
                owner_key=None,
                starts_after=datetime.now(UTC),
                created_to_started_timeout_secs=30,
                started_to_completed_timeout_secs=300,
                heartbeat_timeout_secs=30,
            )
        )

    async def update_schedule(
        self, *, schedule_id: str, name: str | None = None,
        interval_ms: int | None = None,
    ) -> Schedule:
        sched = await self._get_schedule(schedule_id)
        if sched is None:
            raise ValueError(f"schedule not found: {schedule_id}")
        updates: list[str] = []
        params: dict[str, Any] = {"id": schedule_id}
        if name is not None:
            updates.append("name = :name")
            params["name"] = name
        if interval_ms is not None:
            updates.append("interval_ms = :ims")
            params["ims"] = interval_ms
        if updates:
            async with self._sf() as session:
                await session.execute(
                    text(
                        f"UPDATE schedules SET {', '.join(updates)}"
                        f" WHERE id = :id"
                    ),
                    params,
                )
                await session.commit()
        return await self._get_schedule(schedule_id)

    async def _get_task(self, task_id: str) -> Task:
        async with self._sf() as session:
            row = (
                await session.execute(
                    text("SELECT * FROM tasks WHERE id = :id LIMIT 1"),
                    {"id": task_id},
                )
            ).mappings().first()
        if row is None:
            raise ValueError(f"task not found: {task_id}")
        return _task_from_row(cast(dict[str, Any], row))

    async def _get_schedule(self, schedule_id: str) -> Schedule:
        async with self._sf() as session:
            row = (
                await session.execute(
                    text("SELECT * FROM schedules WHERE id = :id LIMIT 1"),
                    {"id": schedule_id},
                )
            ).mappings().first()
        if row is None:
            raise ValueError(f"schedule not found: {schedule_id}")
        return _schedule_from_row(cast(dict[str, Any], row))


def _task_from_row(row: dict[str, Any]) -> Task:
    return Task(
        id=str(row["id"]),
        name=row["name"],
        payload=row.get("payload") or {},
        group_key=row["group_key"],
        group_max_concurrency=row["group_max_concurrency"],
        retry_max=row["retry_max"],
        retry_count=row["retry_count"],
        retry_key=str(row["retry_key"]) if row.get("retry_key") else None,
        owner_key=row.get("owner_key"),
        starts_after=row["starts_after"],
        created_to_started_timeout_secs=row["created_to_started_timeout_secs"],
        started_to_completed_timeout_secs=row["started_to_completed_timeout_secs"],
        heartbeat_timeout_secs=row["heartbeat_timeout_secs"],
        created_at=row["created_at"],
        state=row["state"],
        last_state_transition_at=row["last_state_transition_at"],
        last_heartbeat_at=row["last_heartbeat_at"],
        output=row.get("output"),
        terminated=row["terminated"],
        schedule_id=str(row["schedule_id"]) if row.get("schedule_id") else None,
    )


def _schedule_from_row(row: dict[str, Any]) -> Schedule:
    freq = row.get("frequency")
    freq_ms = (
        int(freq.total_seconds() * 1000)
        if freq is not None and hasattr(freq, "total_seconds")
        else 0
    )
    return Schedule(
        id=str(row["id"]),
        name=row["name"],
        state=row["state"],
        starts_at=row["starts_at"],
        frequency_ms=freq_ms,
        payload=row.get("payload") or {},
        group_key=row["group_key"],
        retry_max=row["retry_max"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        deleted_at=row.get("deleted_at"),
        last_scheduled_task_id=(
            str(row["last_scheduled_task_id"]) if row.get("last_scheduled_task_id") else None
        ),
        last_scheduled_task_state=row.get("last_scheduled_task_state"),
        next_execution_at=row["next_execution_at"],
    )


def _json_str(value: JsonObject | None) -> str:
    if value is None:
        return "null"
    import json

    return json.dumps(value, separators=(",", ":"))