from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path


class BackupManager:
    def __init__(self, database: Path, backup_dir: Path, keep: int = 10):
        self.database = database
        self.backup_dir = backup_dir
        self.keep = max(2, keep)

    def create(self) -> dict:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        target = self.backup_dir / f"factory-{stamp}.sqlite3"
        with closing(sqlite3.connect(self.database)) as source, closing(sqlite3.connect(target)) as destination:
            with destination:
                source.backup(destination)
                integrity = destination.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            target.unlink(missing_ok=True)
            raise RuntimeError("A cópia do banco não passou na verificação de integridade")
        backups = sorted(self.backup_dir.glob("factory-*.sqlite3"), key=lambda item: item.stat().st_mtime, reverse=True)
        for old in backups[self.keep:]:
            old.unlink(missing_ok=True)
        return {"created": True, "file": target.name, "size_bytes": target.stat().st_size,
                "integrity": integrity, "retained": min(len(backups), self.keep)}

    def list(self) -> list[dict]:
        if not self.backup_dir.exists():
            return []
        return [{"file": item.name, "size_bytes": item.stat().st_size,
                 "modified_at": datetime.fromtimestamp(item.stat().st_mtime, UTC).isoformat()}
                for item in sorted(self.backup_dir.glob("factory-*.sqlite3"), reverse=True)]

    def ensure_daily(self) -> dict:
        today = datetime.now(UTC).date()
        latest = self.list()
        if latest and datetime.fromisoformat(latest[0]["modified_at"]).date() == today:
            return {"created": False, "reason": "daily_backup_exists", "latest": latest[0]}
        return self.create()
