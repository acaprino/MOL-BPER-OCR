"""Durability contracts for the edge agent's two independently readable copies."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

import pytest

from recovery_store import RecoveryError, RecoveryStore


PRIMARY = "sessions.sqlite3"
BACKUP = "sessions-backup.sqlite3"
WITNESS = "sessions-state.sqlite3"
EDGE = Path(__file__).resolve().parents[1] / "src" / "edge-agent"
PAYLOAD = b"PRIVATE SYNTHETIC CUSTOMER - pending frame\x00\xff"


def _child(directory: Path, code: str) -> subprocess.CompletedProcess[str]:
    setup = (
        "import os, sys\nfrom pathlib import Path\n"
        f"sys.path.insert(0, {str(EDGE)!r})\n"
        "from recovery_store import RecoveryStore, RecoveryError\n"
        f"directory = Path({str(directory)!r})\n"
    )
    return subprocess.run([sys.executable, "-c", setup + code], capture_output=True,
                          text=True, timeout=30, check=False)


def test_acknowledged_generation_survives_abrupt_process_exit(tmp_path: Path) -> None:
    result = _child(tmp_path, f"""store = RecoveryStore(directory)
store.put("frame", b"old")
store.put("frame", {PAYLOAD!r})
store.put("gone", b"obsolete")
store.delete("gone")
os._exit(19)
""")
    assert result.returncode == 19, result.stderr
    with closing(RecoveryStore(tmp_path)) as store:
        assert store.keys() == ["frame"]
        assert store.read("frame") == PAYLOAD


@pytest.mark.parametrize("damage", ["removed", "overwritten", "truncated"])
def test_backup_recovers_a_damaged_primary(tmp_path: Path, damage: str) -> None:
    primary, backup = tmp_path / "work", tmp_path / "copy"
    with closing(RecoveryStore(primary, backup_directory=backup)) as store:
        store.put("frame", PAYLOAD)
    assert (backup / BACKUP).is_file()
    if damage == "removed":
        (primary / PRIMARY).unlink()
    else:
        (primary / PRIMARY).write_bytes(b"" if damage == "truncated" else b"bad database")
    with closing(RecoveryStore(primary, backup_directory=backup)) as restored:
        assert restored.recovered_from_backup
        assert restored.read("frame") == PAYLOAD
    (backup / BACKUP).unlink()
    with closing(RecoveryStore(primary, backup_directory=backup)) as rebuilt:
        assert not rebuilt.recovered_from_backup
        assert rebuilt.read("frame") == PAYLOAD
    assert (backup / BACKUP).is_file()


def test_an_old_backup_cannot_resurrect_a_deleted_entry(tmp_path: Path) -> None:
    with closing(RecoveryStore(tmp_path)) as store:
        store.put("discarded", PAYLOAD)
    old = (tmp_path / BACKUP).read_bytes()
    with closing(RecoveryStore(tmp_path)) as store:
        store.delete("discarded")
    (tmp_path / BACKUP).write_bytes(old)
    (tmp_path / PRIMARY).unlink()
    with pytest.raises(RecoveryError):
        RecoveryStore(tmp_path)
    assert (tmp_path / BACKUP).read_bytes() == old


def test_stale_primary_is_replaced_from_current_backup(tmp_path: Path) -> None:
    with closing(RecoveryStore(tmp_path)) as store:
        store.put("frame", b"before")
    old = (tmp_path / PRIMARY).read_bytes()
    with closing(RecoveryStore(tmp_path)) as store:
        store.put("frame", PAYLOAD)
    (tmp_path / PRIMARY).write_bytes(old)
    with closing(RecoveryStore(tmp_path)) as store:
        assert store.recovered_from_backup
        assert store.read("frame") == PAYLOAD


def test_newer_copy_is_preserved_when_witness_and_backup_are_stale(tmp_path: Path) -> None:
    with closing(RecoveryStore(tmp_path)) as store:
        store.put("frame", b"old")
    old = {name: (tmp_path / name).read_bytes() for name in (WITNESS, BACKUP)}
    with closing(RecoveryStore(tmp_path)) as store:
        store.put("frame", PAYLOAD)
    current = (tmp_path / PRIMARY).read_bytes()
    for name, content in old.items():
        (tmp_path / name).write_bytes(content)
    with pytest.raises(RecoveryError):
        RecoveryStore(tmp_path)
    assert (tmp_path / PRIMARY).read_bytes() == current


def test_store_publishes_paths_for_online_snapshots(tmp_path: Path) -> None:
    backup = tmp_path / "backup"
    with closing(RecoveryStore(tmp_path, backup_directory=backup)) as store:
        assert store.primary_path == tmp_path / PRIMARY
        assert store.replica_directory == backup


def test_empty_binary_value_is_distinct_from_an_absent_record(tmp_path: Path) -> None:
    with closing(RecoveryStore(tmp_path)) as store:
        store.put("empty", b"")
        assert store.read("empty") == b""
        store.delete("empty")
        with pytest.raises(KeyError):
            store.read("empty")


def test_existing_backup_of_another_store_is_preserved(tmp_path: Path) -> None:
    original, other = tmp_path / "original", tmp_path / "other"
    with closing(RecoveryStore(original)) as store:
        store.put("original", PAYLOAD)
    with closing(RecoveryStore(other)) as store:
        store.put("other", b"belongs to another recovery directory")
    before = (other / BACKUP).read_bytes()
    with pytest.raises(RecoveryError):
        RecoveryStore(original, backup_directory=other)
    assert (other / BACKUP).read_bytes() == before


def test_divergent_copies_without_a_witness_are_preserved(tmp_path: Path) -> None:
    with closing(RecoveryStore(tmp_path)) as store:
        store.put("frame", b"before")
    old = (tmp_path / BACKUP).read_bytes()
    with closing(RecoveryStore(tmp_path)) as store:
        store.put("frame", PAYLOAD)
    (tmp_path / BACKUP).write_bytes(old)
    (tmp_path / WITNESS).unlink()
    with pytest.raises(RecoveryError):
        RecoveryStore(tmp_path)
    assert (tmp_path / BACKUP).read_bytes() == old


def test_unrecoverable_databases_are_preserved(tmp_path: Path) -> None:
    with closing(RecoveryStore(tmp_path)) as store:
        store.put("frame", PAYLOAD)
    for name in (PRIMARY, BACKUP):
        (tmp_path / name).write_bytes(b"damaged")
    with pytest.raises(RecoveryError):
        RecoveryStore(tmp_path)
    assert (tmp_path / PRIMARY).read_bytes() == b"damaged"
    assert (tmp_path / BACKUP).read_bytes() == b"damaged"


def test_new_owner_can_open_the_independent_backup(tmp_path: Path) -> None:
    original, relocated = tmp_path / "original", tmp_path / "relocated"
    with closing(RecoveryStore(original)) as store:
        store.put("frame", PAYLOAD)
    relocated.mkdir(mode=0o700)
    shutil.copy2(original / BACKUP, relocated / BACKUP)
    if os.name != "nt":
        shutil.copy2(original / "sessions.key", relocated / "sessions.key")
    with closing(RecoveryStore(relocated)) as store:
        assert store.recovered_from_backup
        assert store.read("frame") == PAYLOAD


def test_live_owner_excludes_another_process(tmp_path: Path) -> None:
    with closing(RecoveryStore(tmp_path)):
        result = _child(tmp_path, """try:
    RecoveryStore(directory)
except RecoveryError:
    sys.exit(23)
""")
        assert result.returncode == 23, result.stderr


def test_two_primaries_cannot_share_a_live_backup(tmp_path: Path) -> None:
    backup = tmp_path / "backup"
    with closing(RecoveryStore(tmp_path / "one", backup_directory=backup)):
        with pytest.raises(RecoveryError):
            RecoveryStore(tmp_path / "two", backup_directory=backup)


def test_failed_write_keeps_last_acknowledged_value_in_both_copies(tmp_path: Path) -> None:
    with closing(RecoveryStore(tmp_path)) as store:
        store.put("frame", PAYLOAD)
        with closing(sqlite3.connect(tmp_path / BACKUP)) as blocked:
            blocked.execute("BEGIN IMMEDIATE")
            with pytest.raises(RecoveryError):
                store.put("frame", b"unacknowledged")
            with pytest.raises(RecoveryError):
                store.delete("frame")
        assert store.read("frame") == PAYLOAD
    (tmp_path / PRIMARY).unlink()
    with closing(RecoveryStore(tmp_path)) as store:
        assert store.read("frame") == PAYLOAD


def test_kill_during_a_mirrored_transaction_preserves_acknowledged_work(tmp_path: Path) -> None:
    with closing(RecoveryStore(tmp_path)) as store:
        store.put("frame", PAYLOAD)
    program = f"""
import sys
from pathlib import Path
sys.path.insert(0, {str(EDGE)!r})
from recovery_store import RecoveryStore
directory = Path({str(tmp_path)!r})
store = RecoveryStore(directory)
print("READY", flush=True)
sys.stdin.readline()
store.put("frame", b"interrupt me" * 65536)
"""
    with subprocess.Popen([sys.executable, "-c", program], stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, text=True) as child:
        assert child.stdin and child.stdout
        try:
            assert child.stdout.readline().strip() == "READY"
            with closing(sqlite3.connect(tmp_path / PRIMARY)) as reader:
                reader.execute("BEGIN")
                reader.execute("SELECT * FROM sqlite_master").fetchall()
                # The real reader holds the writer before commit. Kill only after a rollback
                # journal exists, so the interrupted child is inside a database transaction.
                child.stdin.write("start\n")
                child.stdin.flush()
                deadline = time.monotonic() + 10
                while not (tmp_path / (PRIMARY + "-journal")).exists():
                    assert child.poll() is None and time.monotonic() < deadline
                    time.sleep(0.005)
                child.kill()
                child.wait(timeout=10)
        finally:
            if child.poll() is None:
                child.kill()
    with closing(RecoveryStore(tmp_path)) as store:
        assert store.read("frame") == PAYLOAD
    (tmp_path / PRIMARY).unlink()
    with closing(RecoveryStore(tmp_path)) as backup:
        assert backup.read("frame") == PAYLOAD


def test_concurrent_frame_writes_can_be_recovered(tmp_path: Path) -> None:
    with closing(RecoveryStore(tmp_path)) as store:
        keys = [f"frame/{i:03}" for i in range(24)]
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(store.put, keys, [key.encode() for key in keys]))
    (tmp_path / PRIMARY).unlink()
    with closing(RecoveryStore(tmp_path)) as store:
        assert store.keys() == keys
        assert all(store.read(key) == key.encode() for key in keys)


def test_private_payload_never_appears_in_recovery_files(tmp_path: Path) -> None:
    with closing(RecoveryStore(tmp_path)) as store:
        store.put("frame", PAYLOAD)
    for path in tmp_path.iterdir():
        assert PAYLOAD not in path.read_bytes()


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_missing_protection_key_preserves_existing_data(tmp_path: Path) -> None:
    with closing(RecoveryStore(tmp_path)) as store:
        store.put("frame", PAYLOAD)
    key = tmp_path / "sessions.key"
    key.unlink()
    with pytest.raises(RecoveryError):
        RecoveryStore(tmp_path)
    assert not key.exists()
