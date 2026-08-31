"""Adaptive Subagent Scheduler and Concurrency Controller.

Manages dynamic concurrency slot allocations, pipelined verification,
and disjoint write ownership validation:
- 6 total active subagent slots (BOSS is outside this limit)
- Max parallel scouts: 2
- Max parallel standard workers: 4
- Max parallel deep workers: 2
- Reviewers and Premium Second Opinion consume standard subagent slots
- Immediate pipelined verification: Reviewers start as soon as a worker finishes without waiting for the full wave
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from core.model_discovery import derive_model_family
from core.runtime_routing_policy import ConcurrencyConfig, RuntimePolicy


class TaskState(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ScheduledTask:
    task_id: str
    role: str  # "SCOUT" | "STANDARD_WORKER" | "DEEP_WORKER" | "VERIFIER" | "PREMIUM_SECOND_OPINION"
    owned_files: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()  # task_ids that must finish before this task starts
    implementer_task_id: Optional[str] = None  # for VERIFIER / PSO
    is_high_risk: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConcurrencySnapshot:
    peak_active_subagents: int
    max_active_limit: int
    scouts_spawned: int
    standard_workers_spawned: int
    deep_workers_spawned: int
    reviewers_spawned: int
    premium_reviews_spawned: int
    parallel_waves: int
    parallelism_used: bool
    events_log: tuple[Mapping[str, Any], ...] = ()


class AdaptiveScheduler:
    """Dynamic, event-driven scheduler enforcing concurrency slots and ownership rules."""

    def __init__(self, policy: RuntimePolicy):
        self.policy = policy
        self.cfg: ConcurrencyConfig = policy.concurrency
        self.active_tasks: dict[str, ScheduledTask] = {}
        self.completed_tasks: dict[str, ScheduledTask] = {}
        self.failed_tasks: dict[str, ScheduledTask] = {}
        
        # Concurrency counters
        self.scouts_count = 0
        self.std_workers_count = 0
        self.deep_workers_count = 0
        self.reviewers_count = 0
        self.premium_count = 0
        self.peak_active = 0
        self.parallel_waves = 0
        self.events: list[dict[str, Any]] = []

    @property
    def current_active_count(self) -> int:
        return len(self.active_tasks)

    def _role_active_count(self, role: str) -> int:
        return sum(1 for t in self.active_tasks.values() if t.role == role)

    def can_dispatch(self, task: ScheduledTask) -> tuple[bool, str]:
        """Check if a task can be dispatched immediately under concurrency and dependency constraints."""
        # 1. Check overall slot capacity
        if self.current_active_count >= self.cfg.max_active_subagents:
            return False, f"GLOBAL_CAPACITY_EXHAUSTED: {self.current_active_count}/{self.cfg.max_active_subagents} slots active"

        # 2. Check role-specific concurrency caps
        if task.role == "SCOUT":
            if self._role_active_count("SCOUT") >= self.cfg.max_parallel_scouts:
                return False, f"SCOUT_CAPACITY_REACHED: max {self.cfg.max_parallel_scouts} parallel scouts"
        elif task.role == "STANDARD_WORKER":
            if self._role_active_count("STANDARD_WORKER") >= self.cfg.max_parallel_standard_workers:
                return False, f"WORKER_CAPACITY_REACHED: max {self.cfg.max_parallel_standard_workers} parallel standard workers"
        elif task.role == "DEEP_WORKER":
            if self._role_active_count("DEEP_WORKER") >= self.cfg.max_parallel_deep_workers:
                return False, f"DEEP_WORKER_CAPACITY_REACHED: max {self.cfg.max_parallel_deep_workers} parallel deep workers"

        # 3. Check explicit dependencies
        for dep in task.dependencies:
            if dep not in self.completed_tasks:
                return False, f"DEPENDENCY_UNRESOLVED: waiting for {dep}"

        # 4. Check disjoint write ownership against currently active write workers
        if task.owned_files:
            task_files = set(task.owned_files)
            for active_id, active_t in self.active_tasks.items():
                if active_t.owned_files:
                    overlap = task_files.intersection(set(active_t.owned_files))
                    if overlap:
                        return False, f"OWNERSHIP_OVERLAP: conflicts on {sorted(overlap)} with active task {active_id}"

        # 5. Pipelined verification check: Verifiers must have their implementer completed
        if task.role in ("VERIFIER", "PREMIUM_SECOND_OPINION") and task.implementer_task_id:
            if task.implementer_task_id not in self.completed_tasks:
                return False, f"IMPLEMENTER_INCOMPLETE: waiting for implementer {task.implementer_task_id}"

        return True, "READY"

    def dispatch(self, task: ScheduledTask, timestamp_utc: Optional[str] = None) -> bool:
        """Dispatch task into an active execution slot."""
        can_run, reason = self.can_dispatch(task)
        ts = timestamp_utc or datetime.now(timezone.utc).isoformat()

        if not can_run:
            self.events.append({
                "timestamp_utc": ts,
                "event": "DISPATCH_BLOCKED",
                "task_id": task.task_id,
                "role": task.role,
                "active_slots": self.current_active_count,
                "reason": reason,
            })
            return False

        self.active_tasks[task.task_id] = task
        active_now = len(self.active_tasks)
        if active_now > self.peak_active:
            self.peak_active = active_now
        if active_now > 1:
            self.parallel_waves += 1

        if task.role == "SCOUT":
            self.scouts_count += 1
        elif task.role == "STANDARD_WORKER":
            self.std_workers_count += 1
        elif task.role == "DEEP_WORKER":
            self.deep_workers_count += 1
        elif task.role == "VERIFIER":
            self.reviewers_count += 1
        elif task.role == "PREMIUM_SECOND_OPINION":
            self.premium_count += 1

        self.events.append({
            "timestamp_utc": ts,
            "event": "TASK_SPAWNED",
            "task_id": task.task_id,
            "role": task.role,
            "active_slots": active_now,
            "parallel_active": active_now > 1,
            "owned_files": list(task.owned_files),
        })
        return True

    def finish_task(self, task_id: str, success: bool = True, timestamp_utc: Optional[str] = None) -> None:
        """Complete an active task, releasing its slot immediately for waiting workers or verifiers."""
        if task_id not in self.active_tasks:
            return

        task = self.active_tasks.pop(task_id)
        ts = timestamp_utc or datetime.now(timezone.utc).isoformat()

        if success:
            self.completed_tasks[task_id] = task
            status_str = "COMPLETED"
        else:
            self.failed_tasks[task_id] = task
            status_str = "FAILED"

        self.events.append({
            "timestamp_utc": ts,
            "event": "TASK_FINISHED",
            "task_id": task_id,
            "role": task.role,
            "status": status_str,
            "active_slots_remaining": len(self.active_tasks),
        })

    def snapshot(self) -> ConcurrencySnapshot:
        """Generate read-only concurrency and scheduling metrics snapshot."""
        return ConcurrencySnapshot(
            peak_active_subagents=self.peak_active,
            max_active_limit=self.cfg.max_active_subagents,
            scouts_spawned=self.scouts_count,
            standard_workers_spawned=self.std_workers_count,
            deep_workers_spawned=self.deep_workers_count,
            reviewers_spawned=self.reviewers_count,
            premium_reviews_spawned=self.premium_count,
            parallel_waves=self.parallel_waves,
            parallelism_used=self.peak_active > 1,
            events_log=tuple(self.events),
        )


def format_concurrency_table(snapshot: ConcurrencySnapshot) -> str:
    """Format Auto Team Concurrency table for end-of-run summary."""
    lines = [
        "⚙ Auto Team Concurrency",
        "",
        f"Peak Active Subagents: {snapshot.peak_active_subagents} / {snapshot.max_active_limit}",
        f"Scouts Spawned:        {snapshot.scouts_spawned}",
        f"Workers Spawned:       {snapshot.standard_workers_spawned}",
        f"Deep Workers Spawned:  {snapshot.deep_workers_spawned}",
        f"Reviewers Spawned:     {snapshot.reviewers_spawned}",
        f"Premium Reviews:       {snapshot.premium_reviews_spawned}",
        f"Parallel Waves:        {snapshot.parallel_waves}",
        f"Parallelism Used:      {'YES' if snapshot.parallelism_used else 'NO'}",
    ]
    return "\n".join(lines)
