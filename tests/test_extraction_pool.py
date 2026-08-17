"""Tests for edge-agent/extraction_pool.py (daemon worker pool)."""

import threading
import time

from extraction_pool import DaemonThreadPool


def test_submitted_tasks_execute_with_args() -> None:
    pool = DaemonThreadPool(2)
    done = threading.Event()
    results = []
    pool.submit(lambda a, b: (results.append(a + b), done.set()), 1, 2)
    assert done.wait(2.0)
    assert results == [3]


def test_threads_are_daemon() -> None:
    pool = DaemonThreadPool(3)
    assert len(pool._threads) == 3
    assert all(t.daemon for t in pool._threads)


def test_exception_does_not_kill_worker() -> None:
    pool = DaemonThreadPool(1)
    done = threading.Event()

    def boom() -> None:
        raise RuntimeError("task failure")

    pool.submit(boom)
    pool.submit(done.set)
    assert done.wait(2.0)


def test_concurrency_is_bounded_by_max_workers() -> None:
    pool = DaemonThreadPool(2)
    gate = threading.Event()
    active = []
    peak = []
    lock = threading.Lock()

    def task() -> None:
        with lock:
            active.append(1)
            peak.append(len(active))
        gate.wait(2.0)
        with lock:
            active.pop()

    for _ in range(4):
        pool.submit(task)
    time.sleep(0.3)
    gate.set()
    time.sleep(0.3)
    assert max(peak) <= 2


def test_stop_discards_queued_tasks_and_rejects_new_ones() -> None:
    pool = DaemonThreadPool(1)
    gate = threading.Event()
    ran = []
    pool.submit(lambda: (ran.append("first"), gate.wait(2.0)))
    for i in range(5):
        pool.submit(lambda i=i: ran.append(f"queued-{i}"))
    time.sleep(0.2)          # let the first task start and hold the only worker
    pool.stop()              # queued tasks must be discarded
    gate.set()
    time.sleep(0.3)
    assert ran == ["first"]
    assert pool.submit(lambda: ran.append("late")) is False
    assert pool.pending() == 0
