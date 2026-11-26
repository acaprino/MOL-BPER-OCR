"""Operator-visible state of accepted screenshots, guarded by the client lock."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, replace


RECENT_LIMIT = 100


@dataclass(frozen=True, slots=True)
class QueueRow:
    session: str
    sequence: int
    page: str
    state: str


@dataclass(frozen=True, slots=True)
class QueueSnapshot:
    revision: int
    limit: int
    pid: int | None
    rows: tuple[QueueRow, ...]


class WorkQueue:
    def __init__(self) -> None:
        self.revision = 0
        self._active: dict[tuple[str, int], QueueRow] = {}
        self._recent: OrderedDict[tuple[str, int], QueueRow] = OrderedDict()

    def accept(self, job: str, sequence: int, label: str, page: str) -> None:
        self._active[job, sequence] = QueueRow(label, sequence, page, "queued")
        self.revision += 1

    def update(self, job: str, sequence: int, state: str) -> None:
        key = job, sequence
        row = replace(self._active[key], state=state)
        if state in {"done", "failed", "uncertain", "timed_out", "unassigned"}:
            del self._active[key]
            self._recent[key] = row
            if len(self._recent) > RECENT_LIMIT:
                self._recent.popitem(last=False)
        else:
            self._active[key] = row
        self.revision += 1

    def mark_assigned(self, job: str, sequence: int, state: str) -> None:
        key = job, sequence
        if key in self._recent:
            self._recent[key] = replace(self._recent[key], state=state)
            self.revision += 1

    def rows(self) -> tuple[QueueRow, ...]:
        return (*self._active.values(), *reversed(self._recent.values()))
