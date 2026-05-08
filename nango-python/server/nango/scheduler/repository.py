from __future__ import annotations

from datetime import UTC, datetime
from fnmatch import fnmatchcase
from uuid import uuid4

from nango.scheduler.models import (
    RecurringScheduleInput,
    Schedule,
    Task,
    TaskState,
)


class InMemorySchedulerRepository:
    """In-memory repository that mirrors scheduler persistence semantics for tests.

    The production Postgres repository should keep the existing Knex migrations as the
    schema authority and replace this class with row locking, SKIP LOCKED dequeue,
    expiry, and backpressure queries.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}
        self._schedules: dict[str, Schedule] = {}

    def create_task(self, task: Task) -> Task:
        if any(existing.name == task.name for existing in self._tasks.values()):
            raise ValueError(f"task name already exists: {task.name}")
        self._tasks[task.id] = task
        return task

    def create_schedule(self, schedule: Schedule) -> Schedule:
        if any(existing.name == schedule.name for existing in self._schedules.values()):
            raise ValueError(f"schedule name already exists: {schedule.name}")
        self._schedules[schedule.id] = schedule
        return schedule

    def get_task(self, task_id: str) -> Task:
        try:
            return self._tasks[task_id]
        except KeyError as exc:
            raise ValueError(f"task not found: {task_id}") from exc

    def get_schedule(self, schedule_id: str) -> Schedule:
        try:
            return self._schedules[schedule_id]
        except KeyError as exc:
            raise ValueError(f"schedule not found: {schedule_id}") from exc

    def find_schedule_by_name(self, name: str) -> Schedule | None:
        return next(
            (schedule for schedule in self._schedules.values() if schedule.name == name),
            None,
        )

    def tasks_for_schedule(self, schedule_id: str, states: set[TaskState]) -> list[Task]:
        return [
            task
            for task in self._tasks.values()
            if task.schedule_id == schedule_id and task.state in states
        ]

    def update_task(self, task: Task) -> Task:
        self.get_task(task.id)
        self._tasks[task.id] = task
        return task

    def update_schedule(self, schedule: Schedule) -> Schedule:
        self.get_schedule(schedule.id)
        self._schedules[schedule.id] = schedule
        return schedule

    def dequeue(self, *, group_key_pattern: str, limit: int, now: datetime) -> list[Task]:
        matches = [
            task
            for task in self._tasks.values()
            if task.state == TaskState.CREATED
            and task.starts_after <= now
            and fnmatchcase(task.group_key, group_key_pattern)
        ]
        candidates = sorted(matches, key=lambda task: (task.created_at, task.id))
        running_by_group = self._running_counts(group_key_pattern)

        selected: list[Task] = []
        selected_by_group: dict[str, int] = {}
        for task in candidates:
            if len(selected) >= limit:
                break
            running = running_by_group.get(task.group_key, 0)
            selected_count = selected_by_group.get(task.group_key, 0)
            if self._can_start(task, running + selected_count + 1):
                selected.append(task)
                selected_by_group[task.group_key] = selected_count + 1

        return [self.update_task(_mark_started(task, now)) for task in selected]

    def queue_sizes(self) -> dict[str, int]:
        sizes: dict[str, int] = {}
        for task in self._tasks.values():
            if task.state == TaskState.CREATED:
                sizes[task.group_key] = sizes.get(task.group_key, 0) + 1
        return sizes

    def groups_with_backpressure(self, *, limit: int) -> list[tuple[str, int]]:
        """Placeholder for the future Postgres backpressure query.

        It returns groups where queued CREATED tasks exceed the configured group
        concurrency. Production should calculate this in SQL using authoritative
        scheduler tables and indexes.
        """

        groups: dict[str, tuple[int, int]] = {}
        for task in self._tasks.values():
            if task.state == TaskState.CREATED and task.group_max_concurrency > 0:
                queued, max_concurrency = groups.get(
                    task.group_key, (0, task.group_max_concurrency)
                )
                groups[task.group_key] = (queued + 1, max_concurrency)

        pressured = [
            (group_key, queued)
            for group_key, (queued, max_concurrency) in groups.items()
            if queued > max_concurrency
        ]
        return sorted(pressured, key=lambda item: item[1], reverse=True)[:limit]

    def expire_timed_out_tasks(self, *, now: datetime | None = None) -> list[Task]:
        """Placeholder for expiry semantics owned by the future Postgres engine.

        The TypeScript scheduler expires CREATED and STARTED tasks based on their
        timeout columns. This foundation deliberately keeps expiry explicit and
        side-effect-free until a real DB scheduler can perform locked batch updates.
        """

        _ = now or datetime.now(UTC)
        return []

    def _running_counts(self, group_key_pattern: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for task in self._tasks.values():
            if task.state == TaskState.STARTED and fnmatchcase(task.group_key, group_key_pattern):
                counts[task.group_key] = counts.get(task.group_key, 0) + 1
        return counts

    def _can_start(self, task: Task, concurrent_count: int) -> bool:
        return task.group_max_concurrency == 0 or concurrent_count <= task.group_max_concurrency


def new_task_id() -> str:
    return str(uuid4())


def new_schedule_id() -> str:
    return str(uuid4())


def schedule_from_input(props: RecurringScheduleInput, now: datetime) -> Schedule:
    return Schedule(
        id=new_schedule_id(),
        name=props.name,
        state=props.state,
        startsAt=props.starts_at,
        frequencyMs=props.frequency_ms,
        payload=props.payload,
        groupKey=props.group_key,
        retryMax=props.retry_max,
        createdToStartedTimeoutSecs=props.created_to_started_timeout_secs,
        startedToCompletedTimeoutSecs=props.started_to_completed_timeout_secs,
        heartbeatTimeoutSecs=props.heartbeat_timeout_secs,
        createdAt=now,
        updatedAt=now,
        deletedAt=None,
        lastScheduledTaskId=None,
        lastScheduledTaskState=None,
        nextExecutionAt=props.starts_at,
    )


def _mark_started(task: Task, now: datetime) -> Task:
    return task.model_copy(
        update={
            "state": TaskState.STARTED,
            "last_state_transition_at": now,
            "last_heartbeat_at": now,
        }
    )
