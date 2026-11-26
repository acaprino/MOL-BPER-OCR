"""Encrypted edge recovery records, committed to two local SQLite files together."""

from __future__ import annotations

from contextlib import ExitStack, closing
import ctypes
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import threading
from typing import BinaryIO, NamedTuple
import uuid


class RecoveryError(RuntimeError):
    """The recovery store could not safely open, read, or commit the requested data."""


_FORMAT = 1
_DATABASE_ID = 0x42504552  # BPER
_WITNESS_ID = 0x42505754  # BPWT
_UPSERT = "INSERT OR REPLACE INTO {}.records (key, payload, checksum) VALUES (?, ?, ?)"
_CONNECTION_TIMEOUT = 1.0


def _private_directory(path: Path) -> Path:
    path = path.resolve()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        info = path.stat()
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise RecoveryError(f"Recovery requires an owner-only directory: {path}")
    return path


def _lock_directory(path: Path) -> BinaryIO:
    handle = (path / "sessions.lock").open("a+b")
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        handle.close()
        raise
    return handle


def _replace_durably(temporary: Path, destination: Path) -> None:
    if os.name == "nt":
        move = ctypes.WinDLL("kernel32", use_last_error=True).MoveFileExW
        move.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
        move.restype = ctypes.c_int
        if not move(str(temporary), str(destination), 0x1 | 0x8):
            raise ctypes.WinError(ctypes.get_last_error())
    else:
        os.replace(temporary, destination)
        fd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


class _Blob(ctypes.Structure):
    _fields_ = [("size", ctypes.c_uint32), ("data", ctypes.c_void_p)]

    @classmethod
    def from_bytes(cls, value: bytes) -> _Blob:
        return cls(len(value), ctypes.cast(ctypes.c_char_p(value), ctypes.c_void_p))


class _Protection:
    """Windows binds each payload to the user with DPAPI. POSIX uses a private AES key."""

    def __init__(self, directory: Path, existing: bool) -> None:
        if os.name == "nt":
            self._crypto = ctypes.WinDLL("crypt32", use_last_error=True)
            for function in (self._crypto.CryptProtectData, self._crypto.CryptUnprotectData):
                function.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.POINTER(_Blob),
                                     ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
                                     ctypes.POINTER(_Blob)]
                function.restype = ctypes.c_int
            self._free = ctypes.WinDLL("kernel32", use_last_error=True).LocalFree
            self._free.argtypes = [ctypes.c_void_p]
            self._free.restype = ctypes.c_void_p
        else:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            path = directory / "sessions.key"
            if not path.exists():
                if existing:
                    raise RecoveryError("The private recovery key is missing.")
                fd, filename = tempfile.mkstemp(dir=directory, prefix=".new-key-")
                temporary = Path(filename)
                try:
                    with os.fdopen(fd, "wb") as output:
                        output.write(AESGCM.generate_key(bit_length=256))
                        output.flush()
                        os.fsync(output.fileno())
                    _replace_durably(temporary, path)
                finally:
                    temporary.unlink(missing_ok=True)
            info = path.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) & 0o077):
                raise RecoveryError("The private recovery key has unsafe permissions.")
            self._cipher = AESGCM(path.read_bytes())

    def _dpapi(self, key: bytes, value: bytes, decrypt: bool) -> bytes:
        source, entropy, result = _Blob.from_bytes(value), _Blob.from_bytes(key), _Blob()
        function = self._crypto.CryptUnprotectData if decrypt else self._crypto.CryptProtectData
        # CRYPTPROTECT_UI_FORBIDDEN, current user scope. The logical key binds the blob to its row.
        if not function(ctypes.byref(source), None, ctypes.byref(entropy), None, None, 1,
                        ctypes.byref(result)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return ctypes.string_at(result.data, result.size)
        finally:
            self._free(result.data)

    def seal(self, key: str, payload: bytes) -> bytes:
        associated = key.encode("utf-8")
        if os.name == "nt":
            return self._dpapi(associated, payload, False)
        nonce = os.urandom(12)
        return nonce + self._cipher.encrypt(nonce, payload, associated)

    def open(self, key: str, payload: bytes) -> bytes:
        associated = key.encode("utf-8")
        if os.name == "nt":
            return self._dpapi(associated, payload, True)
        return self._cipher.decrypt(payload[:12], payload[12:], associated)


def _connect(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path, timeout=_CONNECTION_TIMEOUT, check_same_thread=False,
                           isolation_level=None)


class _Generation(NamedTuple):
    identity: str
    revision: str
    number: int


class _Snapshot(NamedTuple):
    generation: _Generation
    fingerprint: bytes


def _probe(path: Path, *, witness: bool = False) -> _Snapshot | None:
    """Read-write open lets SQLite finish any hot rollback journal before inspecting a copy."""
    if not path.is_file():
        if path.exists():
            raise RecoveryError(f"Expected a recovery database file: {path}")
        return None
    if path.stat().st_size == 0:
        return None
    try:
        with closing(_connect(path)) as db:
            if db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                return None
            expected = _WITNESS_ID if witness else _DATABASE_ID
            if (db.execute("PRAGMA application_id").fetchone()[0] != expected
                    or db.execute("PRAGMA user_version").fetchone()[0] != _FORMAT):
                raise RecoveryError(f"Unrecognized recovery database format: {path}")
            rows = db.execute("SELECT identity, revision, number FROM state").fetchall()
            if len(rows) != 1:
                return None
            generation = _Generation(*rows[0])
            if (not isinstance(generation.number, int) or generation.number < 0
                    or any(not isinstance(token, str) or len(token) != 32
                           for token in (generation.identity, generation.revision))):
                return None
            fingerprint = hashlib.sha256()
            if not witness:
                for key, payload, checksum in db.execute(
                    "SELECT key, payload, checksum FROM records ORDER BY key"
                ):
                    if (not isinstance(key, str) or not isinstance(payload, bytes)
                            or hashlib.sha256(payload).digest() != checksum):
                        return None
                    fingerprint.update(hashlib.sha256(key.encode("utf-8")).digest())
                    fingerprint.update(checksum)
            return _Snapshot(generation, fingerprint.digest())
    except sqlite3.DatabaseError as exc:
        if getattr(exc, "sqlite_errorcode", 0) & 0xFF in (sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB):
            return None
        raise


def _install_database(path: Path, generation: _Generation, *, source: Path | None = None,
                      witness: bool = False) -> None:
    fd, filename = tempfile.mkstemp(dir=path.parent, prefix=".new-db-")
    os.close(fd)
    temporary = Path(filename)
    try:
        with closing(_connect(temporary)) as target:
            if source is not None:
                with closing(_connect(source)) as original:
                    original.backup(target)
            else:
                with target:
                    target.execute("BEGIN")
                    target.execute(f"PRAGMA application_id={_WITNESS_ID if witness else _DATABASE_ID}")
                    target.execute(f"PRAGMA user_version={_FORMAT}")
                    target.execute("CREATE TABLE state (identity TEXT NOT NULL, revision TEXT NOT NULL, "
                                   "number INTEGER NOT NULL)")
                    target.execute("INSERT INTO state VALUES (?, ?, ?)", generation)
                    if not witness:
                        target.execute("CREATE TABLE records (key TEXT PRIMARY KEY, "
                                       "payload BLOB NOT NULL, checksum BLOB NOT NULL)")
        # A restored database must never inherit a torn database's old journal.
        for suffix in ("-journal", "-wal", "-shm"):
            Path(str(path) + suffix).unlink(missing_ok=True)
        _replace_durably(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class RecoveryStore:
    """Single-owner, thread-safe storage. A successful mutation includes its backup."""

    def __init__(self, directory: Path, backup_directory: Path | None = None, *,
                 create: bool = True) -> None:
        self._mutex = threading.RLock()
        self._handles = ExitStack()
        self._db: sqlite3.Connection | None = None
        self.recovered_from_backup = False
        try:
            directory = directory.resolve()
            backup = (backup_directory or directory).resolve()
            self.primary_path = directory / "sessions.sqlite3"
            self.replica_directory = backup
            primary = self.primary_path
            replica = backup / "sessions-backup.sqlite3"
            witness = directory / "sessions-state.sqlite3"
            previous_replica = directory / replica.name
            copies = (primary, replica, witness, previous_replica)
            if not create and not any(path.exists() for path in copies):
                raise RecoveryError("Nessun archivio di recupero nella cartella indicata.")
            for location in sorted({directory, backup}):
                _private_directory(location)
                self._handles.enter_context(_lock_directory(location))
            existing = not create or any(path.exists() for path in copies)
            self._protection = _Protection(directory, existing)
            source_replica = replica if replica.exists() or not previous_replica.exists() else previous_replica
            self._restore(primary, replica, witness, existing, source_replica)
            db = self._handles.enter_context(closing(_connect(primary)))
            db.execute("ATTACH DATABASE ? AS replica", (str(replica),))
            db.execute("ATTACH DATABASE ? AS witness", (str(witness),))
            # The disk-backed main database and rollback journals enable SQLite's
            # super-journal, which commits (or rolls back) all three files together.
            for schema in ("main", "replica", "witness"):
                if db.execute(f"PRAGMA {schema}.journal_mode=DELETE").fetchone()[0] != "delete":
                    raise RecoveryError("Recovery needs SQLite rollback journals.")
                db.execute(f"PRAGMA {schema}.synchronous=EXTRA")
                db.execute(f"PRAGMA {schema}.secure_delete=ON")
            self._db = db
        except Exception as exc:
            self._handles.close()
            if isinstance(exc, RecoveryError):
                raise
            raise RecoveryError(f"Could not open local recovery: {exc}") from exc

    def _restore(self, primary: Path, replica: Path, witness: Path, existing: bool,
                 source_replica: Path) -> None:
        if not existing:
            _install_database(primary, _Generation(uuid.uuid4().hex, uuid.uuid4().hex, 0))
        first, second = _probe(primary), _probe(source_replica)
        marker = _probe(witness, witness=True)
        if len({copy.generation.identity for copy in (first, second, marker) if copy}) > 1:
            raise RecoveryError("Recovery files belong to different stores; all copies have been preserved.")
        if marker:
            for copy in (first, second):
                if (copy and copy.generation != marker.generation
                        and copy.generation.number >= marker.generation.number):
                    raise RecoveryError("Conflicting recovery generations; all copies have been preserved.")
            if first and first.generation != marker.generation:
                first = None
            if second and second.generation != marker.generation:
                second = None
        if not first and not second:
            raise RecoveryError("Neither recovery copy matches the last committed session.")
        if first and second and first != second:
            raise RecoveryError("The recovery copies disagree; both have been preserved.")
        selected, source = (first, primary) if first else (second, source_replica)
        assert selected is not None
        # Refuse an incompatible user profile/key before replacing any copies or adding frames.
        with closing(_connect(source)) as db:
            sample = db.execute("SELECT key, payload FROM records LIMIT 1").fetchone()
            if sample is not None:
                self._protection.open(*sample)
        if not second or source_replica != replica:
            _install_database(replica, selected.generation, source=source)
        if not first:
            _install_database(primary, selected.generation, source=source)
            self.recovered_from_backup = True
        if marker is None:
            _install_database(witness, selected.generation, witness=True)

    def _connection(self) -> sqlite3.Connection:
        if self._db is None:
            raise RecoveryError("The recovery store is closed.")
        return self._db

    def _write(self, key: str, payload: bytes | None) -> None:
        with self._mutex:
            db = self._connection()
            try:
                sealed = self._protection.seal(key, payload) if payload is not None else None
                checksum = hashlib.sha256(sealed).digest() if sealed is not None else None
                revision = uuid.uuid4().hex
                with db:
                    db.execute("BEGIN IMMEDIATE")
                    for schema in ("main", "replica"):
                        if sealed is None:
                            db.execute(f"DELETE FROM {schema}.records WHERE key=?", (key,))
                        else:
                            db.execute(_UPSERT.format(schema), (key, sealed, checksum))
                    for schema in ("main", "replica", "witness"):
                        db.execute(f"UPDATE {schema}.state SET revision=?, number=number+1", (revision,))
            except Exception as exc:
                raise RecoveryError(f"Could not commit local recovery: {exc}") from exc

    def put(self, key: str, payload: bytes) -> None:
        self._write(key, payload)

    def delete(self, key: str) -> None:
        self._write(key, None)

    def keys(self) -> list[str]:
        with self._mutex:
            try:
                return [row[0] for row in self._connection().execute("SELECT key FROM records ORDER BY key")]
            except sqlite3.Error as exc:
                raise RecoveryError(f"Could not enumerate recovery records: {exc}") from exc

    def read(self, key: str) -> bytes:
        with self._mutex:
            db = self._connection()
            try:
                row = db.execute("SELECT payload, checksum FROM records WHERE key=?", (key,)).fetchone()
                if row is not None:
                    if hashlib.sha256(row[0]).digest() != row[1]:
                        raise RecoveryError("The recovery record failed its checksum.")
                    return self._protection.open(key, row[0])
            except Exception as exc:
                raise RecoveryError(f"Could not read the protected recovery record: {exc}") from exc
            raise KeyError(key)

    def close(self) -> None:
        with self._mutex:
            self._db = None
            self._handles.close()
