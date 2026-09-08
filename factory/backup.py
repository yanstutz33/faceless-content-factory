from __future__ import annotations

import sqlite3
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from shutil import copy2


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

    def test_restore(self, backup_name: str | None = None) -> dict:
        """Restore one backup into an isolated temporary copy and verify it is readable."""
        backups = sorted(self.backup_dir.glob("factory-*.sqlite3"),
                         key=lambda item: item.stat().st_mtime, reverse=True)
        if backup_name:
            if Path(backup_name).name != backup_name:
                raise ValueError("Informe somente o nome de um arquivo de backup")
            source = self.backup_dir / backup_name
            if not source.is_file() or source not in backups:
                raise FileNotFoundError("Backup não encontrado")
        elif backups:
            source = backups[0]
        else:
            raise FileNotFoundError("Nenhum backup disponível para o teste de restauração")

        with tempfile.TemporaryDirectory(prefix="faceless-factory-restore-") as temporary_dir:
            restored = Path(temporary_dir) / "factory-restored.sqlite3"
            copy2(source, restored)
            with closing(sqlite3.connect(f"file:{restored.as_posix()}?mode=ro", uri=True)) as database:
                integrity = database.execute("PRAGMA integrity_check").fetchone()[0]
                tables = [row[0] for row in database.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                ).fetchall()]
                row_counts = {}
                for table in tables:
                    safe_name = table.replace('"', '""')
                    row_counts[table] = database.execute(f'SELECT COUNT(*) FROM "{safe_name}"').fetchone()[0]
                user_version = database.execute("PRAGMA user_version").fetchone()[0]

            if integrity != "ok":
                raise RuntimeError("O backup restaurado não passou na verificação de integridade")
            if not tables:
                raise RuntimeError("O backup restaurado não contém a estrutura esperada")

        return {
            "restored": True,
            "source": source.name,
            "integrity": integrity,
            "tables": len(tables),
            "records": sum(row_counts.values()),
            "user_version": user_version,
            "isolated_copy_removed": True,
        }
