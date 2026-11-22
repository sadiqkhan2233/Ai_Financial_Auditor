"""Backup and restore of the built-in SQLite database."""
import shutil
import sqlite3
import tempfile
from pathlib import Path

from models.database import get_engine, init_db, log_activity, reset_engines

REQUIRED_TABLES = {"companies", "engagements", "findings", "reports", "audit_logs", "users"}
COUNT_TABLES = ["companies", "engagements", "findings", "reports", "audit_logs"]
MAX_BACKUP_MB = 50


def sqlite_path() -> Path | None:
    url = get_engine().url
    if url.get_backend_name() != "sqlite" or not url.database:
        return None
    return Path(url.database)


def create_backup() -> bytes:
    path = sqlite_path()
    if path is None or not path.exists():
        raise ValueError("Backup only works with the built-in SQLite database.")
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "backup.db"
        source, destination = sqlite3.connect(str(path)), sqlite3.connect(str(target))
        try:
            with destination:
                source.backup(destination)
        finally:
            source.close()
            destination.close()
        return target.read_bytes()


def _inspect_file(path: Path) -> dict:
    connection = sqlite3.connect(str(path))
    try:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("The file is damaged (it failed the integrity check).")
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = REQUIRED_TABLES - names
        if missing:
            raise ValueError("This does not look like a FinAudit AI backup. Missing: " + ", ".join(sorted(missing)))
        return {t: connection.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in COUNT_TABLES}
    except sqlite3.DatabaseError as err:
        raise ValueError(f"This is not a valid backup file: {err}") from err
    finally:
        connection.close()


def inspect_backup_bytes(data: bytes) -> dict:
    """Checks an uploaded file and returns how many rows it holds. Raises ValueError if it is not a backup."""
    if len(data) > MAX_BACKUP_MB * 1024 * 1024:
        raise ValueError(f"The file is larger than {MAX_BACKUP_MB} MB.")
    if data[:16] != b"SQLite format 3\x00":
        raise ValueError("This is not a SQLite backup file.")
    with tempfile.TemporaryDirectory() as tmp:
        candidate = Path(tmp) / "candidate.db"
        candidate.write_bytes(data)
        return _inspect_file(candidate)


def restore_backup(data: bytes, username: str = "system") -> dict:
    """Replaces the current database with the backup. All current data is lost."""
    path = sqlite_path()
    if path is None:
        raise ValueError("Restore only works with the built-in SQLite database.")
    summary = inspect_backup_bytes(data)
    with tempfile.TemporaryDirectory() as tmp:
        candidate = Path(tmp) / "restore.db"
        candidate.write_bytes(data)
        reset_engines()
        shutil.copyfile(candidate, path)
    for suffix in ("-wal", "-shm", "-journal"):
        Path(str(path) + suffix).unlink(missing_ok=True)
    reset_engines()
    init_db()  # upgrades the tables if the backup came from an older version
    log_activity("database_restored", f"rows restored: {summary}", username=username)
    return summary
