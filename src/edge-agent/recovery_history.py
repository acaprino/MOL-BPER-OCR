"""Verified historical copies of encrypted Edge Agent sessions."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import closing
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import threading
import time
import uuid

from recovery_store import (
    RecoveryError, _Protection, _lock_directory, _private_directory, _probe, _replace_durably,
)

_DATABASE = "sessions.sqlite3"
_KEY = "sessions.key"
_KEEP = 3
_INTERVAL = 15 * 60
_NAME = re.compile(r"snapshot-\d{8}T\d{12}Z-[0-9a-f]{32}")
_WARNING = ("Impossibile creare o aggiornare la copia storica. "
            "Verifica lo spazio libero e i permessi nella cartella di backup.")


def _snapshots(history: Path) -> list[Path]:
    return sorted(p for p in history.glob("snapshot-*")
                  if _NAME.fullmatch(p.name) and not p.is_symlink() and p.is_dir())


def _remove_copy(directory: Path) -> None:
    if not os.path.lexists(directory):
        return
    if directory.resolve() != directory.parent.resolve() / directory.name or not directory.is_dir():
        raise RecoveryError(f"Percorso storico inatteso: {directory}")
    entries = list(directory.iterdir())
    expected = {_DATABASE, _KEY, _DATABASE + "-journal", _DATABASE + "-wal", _DATABASE + "-shm"}
    if any(p.name not in expected or p.is_dir() for p in entries):
        raise RecoveryError(f"La cartella contiene file estranei allo storico: {directory}")
    for entry in entries:
        entry.unlink()
    directory.rmdir()


def _copy_verified(source: Path, stage: Path, stop: threading.Event | None = None) -> None:
    """Use SQLite's online backup in short read steps, then verify the independent copy."""
    if not source.is_file():
        raise FileNotFoundError(source)
    database = stage / _DATABASE
    database.touch(mode=0o600, exist_ok=False)

    def check_cancelled() -> None:
        if stop is not None and stop.is_set():
            raise InterruptedError("Snapshot cancelled.")

    def progress(status: int, _remaining: int, _total: int) -> None:
        check_cancelled()
        if status in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
            raise RecoveryError("The recovery database is busy.")

    uri = source.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=0.25)) as reader:
        with closing(sqlite3.connect(database)) as writer:
            reader.backup(writer, pages=32, progress=progress)
    if os.name != "nt":
        # Enforce the source key ownership and mode before copying it.
        _Protection(source.parent, existing=True)
        key = stage / _KEY
        key.touch(mode=0o600, exist_ok=False)
        key.write_bytes((source.parent / _KEY).read_bytes())

    check_cancelled()
    if _probe(database) is None:
        raise RecoveryError("La verifica di integrità della copia storica è fallita.")
    protection = _Protection(stage, existing=True)
    with closing(sqlite3.connect(database)) as db:
        for key_name, payload in db.execute("SELECT key, payload FROM records"):
            check_cancelled()
            protection.open(key_name, payload)

    for path in stage.iterdir():
        with path.open("rb+") as stream:
            os.fsync(stream.fileno())
    if os.name != "nt":
        directory = os.open(stage, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    check_cancelled()


def create_snapshot(primary_path: Path, replica_directory: Path, *,
                    stop: threading.Event | None = None) -> Path:
    """Publish a complete snapshot before rotating the three historical versions."""
    history = _private_directory(replica_directory / "history")
    with _lock_directory(history):
        # The history lock proves any remaining stage was abandoned by a dead writer.
        stage = history / ".incomplete"
        _remove_copy(stage)
        stage.mkdir(mode=0o700)
        try:
            _copy_verified(primary_path, stage, stop)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            final = history / f"snapshot-{timestamp}-{uuid.uuid4().hex}"
            _replace_durably(stage, final)
        finally:
            _remove_copy(stage)
        for old in [p for p in _snapshots(history) if p != final][:-(_KEEP - 1)]:
            _remove_copy(old)
        return final


def restore_snapshot(snapshot: Path, destination: Path) -> None:
    """Validate a history in the current profile and publish it into a new directory."""
    if os.path.lexists(destination):
        raise FileExistsError(destination)
    # Staging beside the destination permits an atomic directory rename.
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix=".restore-") as work:
        stage = Path(work) / "restored"
        stage.mkdir(mode=0o700)
        _copy_verified(snapshot / _DATABASE, stage)
        if os.name == "nt":
            # Windows refuses to replace an existing directory.
            _replace_durably(stage, destination)
        else:
            # POSIX rename can replace an empty directory. Reserve ours exclusively first.
            destination.mkdir(mode=0o700)
            try:
                _replace_durably(stage, destination)
            except BaseException:
                if stage.exists():
                    destination.rmdir()
                raise


class RecoveryHistory:
    """Coalesce committed changes onto one daemon, independent of the live store."""

    def __init__(self, primary_path: Path, replica_directory: Path,
                 on_error: Callable[[str], None] | None = None) -> None:
        self._primary = primary_path
        self._replica_directory = replica_directory
        self._on_error = on_error
        self._dirty = threading.Event()
        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._run, daemon=True, name="recovery-history")
        self._worker.start()

    def request(self) -> None:
        self._dirty.set()

    def close(self) -> None:
        self._stop.set()
        self._dirty.set()

    def _run(self) -> None:
        deadline = 0.0
        while True:
            self._dirty.wait()
            if self._stop.is_set():
                return
            try:
                if deadline == 0:
                    copies = _snapshots(self._replica_directory / "history")
                    if copies:
                        age = max(0.0, time.time() - copies[-1].stat().st_mtime)
                        deadline = time.monotonic() + max(0.0, _INTERVAL - age)
                if self._stop.wait(max(0.0, deadline - time.monotonic())):
                    return
                self._dirty.clear()
                create_snapshot(self._primary, self._replica_directory, stop=self._stop)
            except Exception as exc:
                if self._stop.is_set():
                    return
                logging.getLogger(__name__).warning("%s (%s)", _WARNING, type(exc).__name__)
                if self._on_error is not None:
                    self._on_error(_WARNING)
                self._dirty.set()
            deadline = time.monotonic() + _INTERVAL
