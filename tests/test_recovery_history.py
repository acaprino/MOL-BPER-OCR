"""Historical snapshots survive later edits and restore only into new stores."""

import os
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time

import pytest

from recovery_history import RecoveryHistory, create_snapshot, restore_snapshot
from recovery_store import RecoveryError, RecoveryStore


VALUE = b"synthetic-private-edited-value-079123"


def test_snapshot_restores_the_historical_version_after_a_later_edit(tmp_path: Path) -> None:
    live, backup = tmp_path / "live", tmp_path / "backup"
    with closing(RecoveryStore(live, backup)) as store:
        store.put("edits/a", VALUE)
        snapshot = create_snapshot(store.primary_path, store.replica_directory)
        store.put("edits/a", b"newer")
    assert snapshot.parent == backup / "history"
    assert all(VALUE not in p.read_bytes() for p in snapshot.iterdir())
    if os.name != "nt":
        assert (snapshot / "sessions.key").stat().st_mode & 0o077 == 0
    restored = tmp_path / "restored"
    restore_snapshot(snapshot, restored)
    with closing(RecoveryStore(restored)) as recovered:
        assert recovered.read("edits/a") == VALUE
    with closing(RecoveryStore(live, backup)) as current:
        assert current.read("edits/a") == b"newer"


def test_pruning_keeps_three_successful_versions(tmp_path: Path) -> None:
    with closing(RecoveryStore(tmp_path / "live")) as store:
        copies = []
        for index in range(4):
            store.put("frame/a", bytes([index]))
            copies.append(create_snapshot(store.primary_path, store.replica_directory))
    assert not copies[0].exists()
    assert all(copy.is_dir() for copy in copies[1:])


@pytest.mark.parametrize("populated", [False, True])
def test_restore_refuses_an_existing_destination(tmp_path: Path, populated: bool) -> None:
    with closing(RecoveryStore(tmp_path / "live")) as store:
        store.put("frame/a", VALUE)
        snapshot = create_snapshot(store.primary_path, store.replica_directory)
    destination = tmp_path / "existing"
    destination.mkdir()
    if populated:
        (destination / "untouched").write_bytes(b"keep")
    before = list(destination.iterdir())
    with pytest.raises(FileExistsError):
        restore_snapshot(snapshot, destination)
    assert list(destination.iterdir()) == before


def test_corrupt_snapshot_does_not_publish_a_restore_directory(tmp_path: Path) -> None:
    with closing(RecoveryStore(tmp_path / "live")) as store:
        store.put("frame/a", VALUE)
        snapshot = create_snapshot(store.primary_path, store.replica_directory)
    with closing(sqlite3.connect(snapshot / "sessions.sqlite3")) as db:
        with db:
            db.execute("UPDATE records SET payload=?", (b"damaged",))
    destination = tmp_path / "restored"
    with pytest.raises(RecoveryError):
        restore_snapshot(snapshot, destination)
    assert not destination.exists()


def test_failed_snapshot_preserves_previous_histories_and_replica(tmp_path: Path) -> None:
    with closing(RecoveryStore(tmp_path / "live")) as store:
        store.put("frame/a", VALUE)
        snapshot = create_snapshot(store.primary_path, store.replica_directory)
        replica = store.replica_directory / "sessions-backup.sqlite3"
        earlier = replica.read_bytes()
        with pytest.raises((RecoveryError, OSError, sqlite3.Error)):
            create_snapshot(tmp_path / "missing.sqlite3", store.replica_directory)
        assert snapshot.is_dir()
        assert replica.read_bytes() == earlier


def test_next_snapshot_reclaims_staging_left_by_a_killed_writer(tmp_path: Path) -> None:
    with closing(RecoveryStore(tmp_path / "live")) as store:
        store.put("frame/a", VALUE)
        snapshot = create_snapshot(store.primary_path, store.replica_directory)
        interrupted = snapshot.parent / ".incomplete"
        interrupted.mkdir()
        (interrupted / "sessions.sqlite3").write_bytes(b"partial")
        (interrupted / "sessions.sqlite3-journal").write_bytes(b"journal")
        newer = create_snapshot(store.primary_path, store.replica_directory)
        assert newer.is_dir() and snapshot.is_dir()
        assert not interrupted.exists()


def test_background_requests_coalesce_during_a_burst(tmp_path: Path) -> None:
    with closing(RecoveryStore(tmp_path / "live")) as store:
        store.put("edits/a", VALUE)
        with closing(RecoveryHistory(store.primary_path, store.replica_directory)) as history:
            for _ in range(30):
                history.request()
            folder = store.replica_directory / "history"
            deadline = time.monotonic() + 5
            while not list(folder.glob("snapshot-*")) and time.monotonic() < deadline:
                time.sleep(0.01)
            assert len(list(folder.glob("snapshot-*"))) == 1
        assert store.read("edits/a") == VALUE


def test_background_failure_reports_a_history_warning_without_stopping_the_live_store(
    tmp_path: Path,
) -> None:
    notice = threading.Event()
    warnings: list[str] = []

    def warn(message: str) -> None:
        warnings.append(message)
        notice.set()

    with closing(RecoveryStore(tmp_path / "live")) as store:
        (store.replica_directory / "history").write_bytes(b"occupied")
        with closing(RecoveryHistory(store.primary_path, store.replica_directory, on_error=warn)) as history:
            store.put("frame", VALUE)
            history.request()
            assert notice.wait(5)
        assert "storic" in warnings[0].lower()
        assert VALUE.decode() not in warnings[0]
        assert store.read("frame") == VALUE


def test_packaged_entry_arguments_run_offline_without_preflight(tmp_path: Path) -> None:
    live, dest = tmp_path / "live", tmp_path / "restored"
    with closing(RecoveryStore(live)) as store:
        store.put("edits/a", VALUE)
    entry = Path(__file__).resolve().parents[1] / "src" / "edge-agent" / "edge_agent.py"
    env = {**os.environ, "EDGE_AGENT_RECOVERY_DIR": str(live), "EDGE_AGENT_BACKUP_DIR": str(live)}
    for args in (["--recovery-snapshot"], ["--recovery-restore", "SNAPSHOT", str(dest)]):
        if "SNAPSHOT" in args:
            args[1] = str(next((live / "history").glob("snapshot-*")))
        result = subprocess.run([sys.executable, str(entry), *args], env=env, capture_output=True,
                                text=True, timeout=20)
        assert result.returncode == 0, result.stderr
    with closing(RecoveryStore(dest)) as recovered:
        assert recovered.read("edits/a") == VALUE
