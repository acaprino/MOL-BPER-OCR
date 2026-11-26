"""The source and portable launchers keep backups beside the application."""

from contextlib import closing
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile

import pytest

import app_paths
from recovery_store import RecoveryStore


def test_source_uses_the_entry_script_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("EDGE_AGENT_BACKUP_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    assert app_paths.backup_dir() == Path(app_paths.__file__).resolve().parent / "backup"


@pytest.mark.parametrize("setting", [None, "", "backup", "archivi/copie", "absolute"])
def test_portable_resolves_the_backup_from_the_installed_exe(
    setting: str | None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    install = tmp_path / "Edge Agent"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(install / "EdgeAgent.exe"))
    monkeypatch.setattr(sys, "_MEIPASS", str(install / "_internal"), raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EDGE_AGENT_BACKUP_DIR", raising=False)
    value = str(tmp_path / "secondo disco") if setting == "absolute" else setting
    if value is not None:
        monkeypatch.setenv("EDGE_AGENT_BACKUP_DIR", value)
    assert app_paths.backup_dir() == install / (value or "backup")


def test_new_location_recovers_the_only_remaining_legacy_replica(tmp_path: Path) -> None:
    primary = tmp_path / "profile"
    target = tmp_path / "portable" / "backup"
    with closing(RecoveryStore(primary)) as previous:
        previous.put("frame/old", b"synthetic capture")
    (primary / "sessions.sqlite3").unlink()
    with closing(RecoveryStore(primary, target, create=False)) as upgraded:
        assert upgraded.recovered_from_backup
        assert upgraded.read("frame/old") == b"synthetic capture"
        upgraded.put("frame/new", b"after upgrade")
    (primary / "sessions.sqlite3").unlink()
    with closing(RecoveryStore(primary, target)) as reopened:
        assert reopened.read("frame/new") == b"after upgrade"


def test_desktop_and_offline_snapshot_use_the_same_installation_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import edge_agent
    from local_extraction_client import LocalExtractionClient

    install, primary = tmp_path / "portable", tmp_path / "profile"
    install.mkdir()
    monkeypatch.setattr(app_paths, "app_dir", lambda: install)
    monkeypatch.setenv("EDGE_AGENT_RECOVERY_DIR", str(primary))
    monkeypatch.delenv("EDGE_AGENT_BACKUP_DIR", raising=False)
    client = LocalExtractionClient(pipeline=object(), recovery_dir=primary)
    client.shutdown()
    assert (install / "backup" / "sessions-backup.sqlite3").is_file()
    assert edge_agent._recovery_command(["--recovery-snapshot"]) == 0
    assert len(list((install / "backup" / "history").glob("snapshot-*"))) == 1


def test_release_zip_ships_the_empty_backup_folder_and_excludes_its_contents(tmp_path: Path) -> None:
    tool = Path(__file__).resolve().parents[1] / "tools" / "package_portable.py"
    dist = tmp_path / "EdgeAgent"
    history = dist / "backup" / "history"
    history.mkdir(parents=True)
    (history / "private.sqlite3").write_bytes(b"synthetic")
    (dist / "EdgeAgent.exe").write_bytes(b"fixture")
    (dist / ".env").write_text("EDGE_AGENT_BACKUP_DIR=backup", encoding="utf8")
    package = tmp_path / "release.zip"
    subprocess.run([sys.executable, str(tool), str(dist), str(package)], check=True)
    with ZipFile(package) as archive:
        assert archive.getinfo("EdgeAgent/backup/").is_dir()
        assert archive.read("EdgeAgent/.env") == b"EDGE_AGENT_BACKUP_DIR=backup"
        assert archive.read("EdgeAgent/EdgeAgent.exe") == b"fixture"
        assert all(name == "EdgeAgent/backup/" or not name.startswith("EdgeAgent/backup/")
                   for name in archive.namelist())
