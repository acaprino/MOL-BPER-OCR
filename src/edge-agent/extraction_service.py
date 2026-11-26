"""Bounded parallel image extraction in a reusable child process, without Qt."""

from __future__ import annotations

import multiprocessing as mp
import os
import threading
from collections.abc import Callable
from multiprocessing.connection import Connection
from typing import Protocol

from PIL import Image


class ImageReader(Protocol):
    def extract_from_image(self, img: Image.Image, screen_id: str) -> dict: ...


def live_pipeline() -> ImageReader:
    from extraction.config import LLM_MODEL, LLM_MODEL_ANCHOR, LLM_PROVIDER
    from extraction.llm_factory import create_chat_model
    from extraction.pipeline import ExtractionPipeline

    return ExtractionPipeline(
        main_model=create_chat_model(LLM_PROVIDER, model=LLM_MODEL),
        anchor_model=create_chat_model(LLM_PROVIDER, model=LLM_MODEL_ANCHOR),
        main_model_name=LLM_MODEL, anchor_model_name=LLM_MODEL_ANCHOR,
    )


def worker_limit(fallback: int) -> int:
    setting = os.getenv("EDGE_AGENT_MAX_JOBS", "").strip().lower()
    if not setting:
        return max(1, fallback)
    if setting == "auto":
        cpu_count = getattr(os, "process_cpu_count", os.cpu_count)() or 1
        return max(1, min(4, cpu_count - 1))
    if not setting.isascii() or not setting.isdecimal() or int(setting) < 1:
        raise ValueError("EDGE_AGENT_MAX_JOBS richiede un intero positivo oppure auto.")
    return int(setting)


def _serve(channel: Connection, pipeline: ImageReader | None, startup_error: str) -> None:
    with channel:
        try:
            while True:
                image, screen_id = channel.recv()
                try:
                    if pipeline is None:
                        raise RuntimeError(startup_error)
                    result = pipeline.extract_from_image(image, screen_id)
                except Exception as exc:
                    channel.send((False, str(exc)))
                else:
                    channel.send((True, result))
                finally:
                    del image
        except (EOFError, OSError):
            return


def _exit_with_parent() -> None:
    parent = mp.parent_process()
    if parent is not None:
        parent.join()
        os._exit(0)


def _run(channels: list[Connection], factory: Callable[[], ImageReader]) -> None:
    threading.Thread(target=_exit_with_parent, daemon=True).start()
    startup_error = ""
    try:
        pipeline = factory()
    except Exception as exc:
        pipeline, startup_error = None, str(exc)
    workers = [threading.Thread(target=_serve, args=(channel, pipeline, startup_error))
               for channel in channels]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()


class _ModelProcess:
    """Idle channels belong here. Each active channel belongs to one caller."""

    def __init__(self, limit: int, factory: Callable[[], ImageReader]) -> None:
        context = mp.get_context("spawn")
        self.idle: list[Connection] = []
        children: list[Connection] = []
        try:
            for _ in range(limit):
                parent, child = context.Pipe()
                self.idle.append(parent)
                children.append(child)
            self.process = context.Process(target=_run, args=(children, factory), daemon=True)
            self.process.start()
        except BaseException:
            for channel in self.idle:
                channel.close()
            raise
        finally:
            for child in children:
                child.close()

    def stop(self) -> None:
        if self.process.is_alive():
            self.process.terminate()
        for channel in self.idle:
            channel.close()
        self.idle.clear()


class _ProcessInterrupted(RuntimeError):
    """The model process was lost before this channel returned a result."""


class ExtractionService:
    """One shared model, one exclusive pipe per simultaneous screenshot."""

    def __init__(self, max_jobs: int, factory: Callable[[], ImageReader] = live_pipeline) -> None:
        self._limit = max_jobs
        self._factory = factory
        self._slots = threading.BoundedSemaphore(max_jobs)
        self._lock = threading.Lock()
        self._active: _ModelProcess | None = None
        self._closed = False

    def extract_from_image(self, img: Image.Image, screen_id: str) -> dict:
        try:
            return self._extract_once(img, screen_id)
        except _ProcessInterrupted:
            # Retry the original capture once, without accepting another slot.
            return self._extract_once(img, screen_id)

    def _extract_once(self, img: Image.Image, screen_id: str) -> dict:
        with self._slots:
            with self._lock:
                if self._closed:
                    raise RuntimeError("Servizio di estrazione chiuso.")
                if self._active is not None and not self._active.process.is_alive():
                    self._active.stop()
                    self._active = None
                if self._active is None:
                    self._active = _ModelProcess(self._limit, self._factory)
                service = self._active
                channel = service.idle.pop()
            try:
                channel.send((img, screen_id))
                success, result = channel.recv()
                if not success:
                    raise RuntimeError(result)
                return result
            except (EOFError, OSError) as exc:
                with self._lock:
                    if self._active is service:
                        service.stop()
                        self._active = None
                raise _ProcessInterrupted("Il processo di estrazione si è interrotto.") from exc
            finally:
                with self._lock:
                    if self._active is service:
                        service.idle.append(channel)
                    else:
                        channel.close()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            if self._active is not None:
                self._active.stop()
                self._active = None
