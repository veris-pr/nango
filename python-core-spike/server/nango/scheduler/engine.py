from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from nango.scheduler.models import (
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
from nango.scheduler.repository import (
    InMemorySchedulerRepository,
    new_task_id,
    schedule_from_input,
)


class SchedulerEngine:
    def __init__(
        self,
        repository: InMemorySchedulerRepository | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository or InMemorySchedulerRepository()
        self._clock = clock or (lambda: datetime.now(UTC))

    def immediate(self, props: ImmediateTaskInput) -> Task:
        now = self._clock()
        task = Task(
            id=new_task_id(),
            name=props.name,
            payload=props.payload,
            groupKey=props.group_key,
            groupMaxConcurrency=props.group_max_concurrency,
            retryMax=props.retry_max,
            retryCount=props.retry_count,
            startsAfter=now,
            createdToStartedTimeoutSecs=props.created_to_started_timeout_secs,
            startedToCompletedTimeoutSecs=props.started_to_completed_timeout_secs,
            heartbeatTimeoutSecs=props.heartbeat_timeout_secs,
            createdAt=now,
            state=TaskState.CREATED,
            lastStateTransitionAt=now,
            lastHeartbeatAt=now,
            output=None,
            terminated=False,
            scheduleId=None,
            retryKey=props.retry_key or str(uuid4()),
            ownerKey=props.owner_key,
        )
        return self.repository.create_task(task)

    def immediate_from_schedule(self, schedule_name: str) -> Task:
        schedule = self.repository.find_schedule_by_name(schedule_name)
        if schedule is None:
            raise ValueError(f"schedule not found: {schedule_name}")

        running = self.repository.tasks_for_schedule(
            schedule.id,
            {TaskState.CREATED, TaskState.STARTED},
        )
        if running:
            raise ValueError(f"task for schedule is already running: {running[0].id}")

        now = self._clock()
        task = Task(
            id=new_task_id(),
            name=f"{schedule.name}:{new_task_id()}",
            payload=schedule.payload,
            groupKey=schedule.group_key,
            groupMaxConcurrency=0,
            retryMax=schedule.retry_max,
            retryCount=0,
            startsAfter=now,
            createdToStartedTimeoutSecs=schedule.created_to_started_timeout_secs,
            startedToCompletedTimeoutSecs=schedule.started_to_completed_timeout_secs,
            heartbeatTimeoutSecs=schedule.heartbeat_timeout_secs,
            createdAt=now,
            state=TaskState.CREATED,
            lastStateTransitionAt=now,
            lastHeartbeatAt=now,
            output=None,
            terminated=False,
            scheduleId=schedule.id,
            retryKey=str(uuid4()),
            ownerKey=None,
        )
        created = self.repository.create_task(task)
        self.repository.update_schedule(
            schedule.model_copy(
                update={
                    "last_scheduled_task_id": created.id,
                    "last_scheduled_task_state": created.state,
                    "updated_at": now,
                }
            )
        )
        return created

    def recurring(self, props: RecurringScheduleInput) -> Schedule:
        return self.repository.create_schedule(schedule_from_input(props, self._clock()))

    def dequeue(self, *, group_key_pattern: str, limit: int) -> list[Task]:
        if limit <= 0:
            return []
        return self.repository.dequeue(
            group_key_pattern=group_key_pattern,
            limit=limit,
            now=self._clock(),
        )

    def heartbeat(self, task_id: str) -> Task:
        task = self.repository.get_task(task_id)
        if task.state != TaskState.STARTED:
            raise ValueError(f"cannot heartbeat task in state {task.state}")
        return self.repository.update_task(
            task.model_copy(update={"last_heartbeat_at": self._clock()})
        )

    def complete(self, task_id: str, output: object | None = None) -> Task:
        return self._transition(task_id, TaskState.SUCCEEDED, output)

    def succeed(self, task_id: str, output: object | None = None) -> Task:
        return self.complete(task_id, output)

    def fail(self, task_id: str, error: object | None = None) -> Task:
        return self._transition(task_id, TaskState.FAILED, error)

    def cancel(self, task_id: str, reason: object | None = None) -> Task:
        return self._transition(task_id, TaskState.CANCELLED, {"reason": reason})

    def expire(self, task_id: str, reason: object | None = None) -> Task:
        return self._transition(task_id, TaskState.EXPIRED, {"reason": reason})

    def groups_with_backpressure(self, *, limit: int) -> list[tuple[str, int]]:
        return self.repository.groups_with_backpressure(limit=limit)

    def expire_timed_out_tasks(self) -> list[Task]:
        return self.repository.expire_timed_out_tasks(now=self._clock())

    def set_schedule_state(self, schedule_id: str, state: ScheduleState) -> Schedule:
        schedule = self.repository.get_schedule(schedule_id)
        if schedule.state == state:
            return schedule
        if (schedule.state, state) not in VALID_SCHEDULE_TRANSITIONS:
            raise ValueError(f"invalid schedule transition from {schedule.state} to {state}")

        now = self._clock()
        return self.repository.update_schedule(
            schedule.model_copy(
                update={
                    "state": state,
                    "updated_at": now,
                    "deleted_at": now if state == ScheduleState.DELETED else schedule.deleted_at,
                }
            )
        )

    def _transition(self, task_id: str, new_state: TaskState, output: object | None) -> Task:
        task = self.repository.get_task(task_id)
        if (task.state, new_state) not in VALID_TASK_TRANSITIONS:
            raise ValueError(f"invalid task transition from {task.state} to {new_state}")

        now = self._clock()
        updated = task.model_copy(
            update={
                "state": new_state,
                "last_state_transition_at": now,
                "terminated": new_state in TERMINAL_TASK_STATES,
                "output": output,
            }
        )
        saved = self.repository.update_task(updated)
        self._update_schedule_after_terminal_task(saved, now)
        return saved

    def _update_schedule_after_terminal_task(self, task: Task, now: datetime) -> None:
        if task.schedule_id is None or task.state not in TERMINAL_TASK_STATES:
            return

        schedule = self.repository.get_schedule(task.schedule_id)
        next_execution_at = schedule.starts_at
        if schedule.frequency_ms > 0:
            elapsed_ms = max((now - schedule.starts_at) / timedelta(milliseconds=1), 0)
            periods = int(elapsed_ms // schedule.frequency_ms) + 1
            next_execution_at = schedule.starts_at + timedelta(
                milliseconds=periods * schedule.frequency_ms
            )

        self.repository.update_schedule(
            schedule.model_copy(
                update={
                    "last_scheduled_task_state": task.state,
                    "next_execution_at": next_execution_at,
                    "updated_at": now,
                }
            )
        )
