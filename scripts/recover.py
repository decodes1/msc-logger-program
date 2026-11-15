"""Restore a verified backup while preserving the old database for inspection."""

import argparse
import shutil
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from msc_logger.__main__ import InstanceLock, data_directory


def restore(backup, directory, profile):
    backup, directory = Path(backup).resolve(), Path(directory).resolve()
    destination = directory / f"{profile}.sqlite3"
    if not backup.is_file() or backup == destination:
        raise ValueError("Choose an existing backup file, not the active database.")
    directory.mkdir(parents=True, exist_ok=True)
    lock = InstanceLock(directory / f"{profile}.lock")
    temporary = directory / f"{profile}-restore.pending"
    try:
        with closing(sqlite3.connect(backup.as_uri() + "?mode=ro", uri=True)) as source:
            if source.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("The backup is damaged.")
            if source.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise ValueError("The backup uses an unsupported schema version.")
            required = {"settings", "tasks", "inventory", "reports", "completions", "samples", "events", "cases", "operations"}
            tables = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not required <= tables:
                raise ValueError("This is not an MSC Logger backup.")
            with closing(sqlite3.connect(temporary)) as target:
                source.backup(target)
                if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("The restored copy did not pass verification.")
        archive = directory / "recovery" / str(time.time_ns())
        archive.mkdir(parents=True)
        # Preserve all original files before replacing anything, including a possible WAL.
        for suffix in ("", "-wal", "-shm"):
            original = Path(str(destination) + suffix)
            if original.exists():
                shutil.copy2(original, archive / original.name)
        for suffix in ("-wal", "-shm"):
            Path(str(destination) + suffix).unlink(missing_ok=True)
        temporary.replace(destination)
        return archive
    finally:
        temporary.unlink(missing_ok=True)
        lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup", type=Path)
    parser.add_argument("--data-dir", type=Path, default=data_directory())
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--confirm-restore", action="store_true")
    args = parser.parse_args()
    if not args.confirm_restore:
        parser.error("Close MSC Logger and pass --confirm-restore to replace the active database.")
    archive = restore(args.backup, args.data_dir, "demo" if args.demo else "workspace")
    print(f"Backup restored. Previous files preserved in {archive}")


if __name__ == "__main__":
    main()
