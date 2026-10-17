"""Daemon-thread pool for background extraction jobs (no Qt)."""

from __future__ import annotations

import queue
import threading
import traceback
from typing import Any, Callable

_SENTINEL: Any = object()


class DaemonThreadPool:
    """Runs callables on N daemon threads.

    Daemon threads do not block interpreter exit: closing the window while
    extractions are in flight terminates the process immediately. This is why
    concurrent.futures.ThreadPoolExecutor is not used here (its non-daemon
    threads are joined at interpreter shutdown, keeping the process alive
    until in-flight LLM calls time out).
    """

    def __init__(self, max_workers: int, name_prefix: str = "extract") -> None:
        self._queue: "queue.Queue[Any]" = queue.Queue()
        self._stopped: bool = False
        self._threads = [
            threading.Thread(target=self._run, name=f"{name_prefix}-{i}", daemon=True)
            for i in range(max(1, int(max_workers)))
        ]
        for thread in self._threads:
            thread.start()

    def submit(self, fn: Callable[..., Any], *args: Any) -> bool:
        """Enqueue a task; returns False if the pool has been stopped."""
        if self._stopped:
            return False
        self._queue.put((fn, args))
        return True

    def pending(self) -> int:
        """Approximate number of tasks not yet started."""
        return self._queue.qsize()

    def stop(self) -> None:
        """Discard queued tasks and unblock workers; running tasks finish alone."""
        self._stopped = True
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass
        for _ in self._threads:
            self._queue.put(_SENTINEL)

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is _SENTINEL:
                return
            fn, args = item
            try:
                fn(*args)
            except Exception:  # noqa: BLE001
                traceback.print_exc()
