from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ACTIVE_STATUSES = ("queued", "planning", "assets", "rendering", "reviewing")


def now() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self.init()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=15000")
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def init(self) -> None:
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, topic TEXT NOT NULL, status TEXT NOT NULL,
                    duration INTEGER NOT NULL, narration INTEGER NOT NULL,
                    subtitles INTEGER NOT NULL, output_dir TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}', error TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                    stage TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                    platform TEXT NOT NULL, views INTEGER NOT NULL DEFAULT 0,
                    likes INTEGER NOT NULL DEFAULT 0, watch_minutes REAL NOT NULL DEFAULT 0,
                    recorded_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS calendar (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT NOT NULL,
                    series_id TEXT, profile TEXT NOT NULL, duration INTEGER NOT NULL,
                    scheduled_for TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'planned',
                    job_id TEXT, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
                    path TEXT NOT NULL UNIQUE, license_type TEXT NOT NULL,
                    source_url TEXT, notes TEXT, approved INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
            """)
            existing = {row[1] for row in db.execute("PRAGMA table_info(jobs)")}
            additions = {
                "profile": "TEXT NOT NULL DEFAULT 'youtube_long'",
                "priority": "INTEGER NOT NULL DEFAULT 2",
                "progress": "INTEGER NOT NULL DEFAULT 0",
                "source_asset": "TEXT",
                "quality_score": "INTEGER",
                "source_assets": "TEXT NOT NULL DEFAULT '[]'",
            }
            for column, definition in additions.items():
                if column not in existing:
                    db.execute(f"ALTER TABLE jobs ADD COLUMN {column} {definition}")

    def create_job(self, job: dict[str, Any]) -> None:
        timestamp = now()
        with self.connect() as db:
            db.execute(
                """INSERT INTO jobs(id,topic,status,duration,narration,subtitles,output_dir,metadata,
                   profile,priority,progress,source_asset,source_assets,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (job["id"], job["topic"], "queued", job["duration"], int(job["narration"]),
                 int(job["subtitles"]), job["output_dir"], "{}", job.get("profile", "youtube_long"),
                 int(job.get("priority", 2)), 0, job.get("source_asset"),
                 json.dumps(job.get("source_assets", []), ensure_ascii=False), timestamp, timestamp),
            )
        self.event(job["id"], "queued", "Produção adicionada à fila")

    def update(self, job_id: str, status: str, metadata: dict[str, Any] | None = None,
               error: str | None = None, progress: int | None = None, quality_score: int | None = None) -> None:
        fields: list[str] = ["status=?", "error=?", "updated_at=?"]
        values: list[Any] = [status, error, now()]
        if metadata is not None:
            fields.append("metadata=?")
            values.append(json.dumps(metadata, ensure_ascii=False))
        if progress is not None:
            fields.append("progress=?")
            values.append(max(0, min(100, progress)))
        if quality_score is not None:
            fields.append("quality_score=?")
            values.append(quality_score)
        values.append(job_id)
        with self.connect() as db:
            cursor = db.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE id=?", values)
            if not cursor.rowcount:
                raise ValueError("Produção não encontrada")

    def event(self, job_id: str, stage: str, message: str) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO events(job_id,stage,message,created_at) VALUES(?,?,?,?)", (job_id, stage, message, now()))

    @staticmethod
    def _job(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        try:
            item["metadata"] = json.loads(item.get("metadata") or "{}")
        except (TypeError, json.JSONDecodeError):
            item["metadata"] = {"recovery_warning": "Metadados antigos estavam corrompidos"}
        item["narration"] = bool(item["narration"])
        item["subtitles"] = bool(item["subtitles"])
        try:
            item["source_assets"] = json.loads(item.get("source_assets") or "[]")
        except (TypeError, json.JSONDecodeError):
            item["source_assets"] = []
        return item

    def recover_interrupted(self) -> list[str]:
        """Put unfinished work back in the queue after an unclean shutdown."""
        interrupted = ACTIVE_STATUSES[1:]
        placeholders = ",".join("?" for _ in interrupted)
        with self.connect() as db:
            rows = db.execute(
                f"SELECT id FROM jobs WHERE status IN ({placeholders}) ORDER BY priority DESC, created_at",
                interrupted,
            ).fetchall()
            ids = [str(row[0]) for row in rows]
            if ids:
                id_placeholders = ",".join("?" for _ in ids)
                db.execute(
                    f"UPDATE jobs SET status='queued', progress=0, error=NULL, updated_at=? WHERE id IN ({id_placeholders})",
                    (now(), *ids),
                )
                db.executemany(
                    "INSERT INTO events(job_id,stage,message,created_at) VALUES(?,?,?,?)",
                    [(job_id, "recovery", "Produção retomada após reinício do estúdio", now()) for job_id in ids],
                )
        return ids

    def queued_jobs(self) -> list[str]:
        with self.connect() as db:
            return [
                str(row[0])
                for row in db.execute(
                    "SELECT id FROM jobs WHERE status='queued' ORDER BY priority DESC, created_at"
                )
            ]

    def list_jobs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM jobs ORDER BY priority DESC, created_at DESC LIMIT ?", (limit,)).fetchall()
            return [self._job(row) for row in rows]

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                return None
            item = self._job(row)
            item["events"] = [dict(x) for x in db.execute("SELECT * FROM events WHERE job_id=? ORDER BY id", (job_id,))]
            item["metrics"] = [dict(x) for x in db.execute("SELECT * FROM metrics WHERE job_id=? ORDER BY id DESC", (job_id,))]
            return item

    def add_metrics(self, job_id: str, platform: str, views: int, likes: int, watch_minutes: float) -> None:
        if not self.get_job(job_id):
            raise ValueError("Produção não encontrada")
        platform = platform.strip().lower()
        if platform not in {"youtube", "shorts", "tiktok", "reels", "shopee"}:
            raise ValueError("Plataforma de métricas inválida")
        with self.connect() as db:
            db.execute("INSERT INTO metrics(job_id,platform,views,likes,watch_minutes,recorded_at) VALUES(?,?,?,?,?,?)",
                       (job_id, platform, max(0, views), max(0, likes), max(0, watch_minutes), now()))
        self.event(job_id, "metrics", f"Métricas de {platform} registradas")

    def summary(self) -> dict[str, Any]:
        jobs = self.list_jobs(500)
        status_counts: dict[str, int] = {}
        for job in jobs:
            status_counts[job["status"]] = status_counts.get(job["status"], 0) + 1
        with self.connect() as db:
            totals = db.execute("""
                WITH latest AS (
                    SELECT MAX(id) AS id FROM metrics GROUP BY job_id, platform
                )
                SELECT COALESCE(SUM(views),0), COALESCE(SUM(watch_minutes),0), COALESCE(SUM(likes),0)
                FROM metrics WHERE id IN (SELECT id FROM latest)
            """).fetchone()
        scored = [j["quality_score"] for j in jobs if j.get("quality_score") is not None]
        return {
            "total": len(jobs), "status": status_counts,
            "awaiting_approval": status_counts.get("awaiting_approval", 0),
            "in_progress": sum(status_counts.get(x, 0) for x in ("queued", "planning", "assets", "rendering", "reviewing")),
            "views": totals[0], "watch_minutes": round(totals[1], 1), "likes": totals[2],
            "average_quality": round(sum(scored) / len(scored)) if scored else None,
        }

    def add_calendar_item(self, topic: str, series_id: str | None, profile: str, duration: int, scheduled_for: str) -> int:
        if not topic.strip() or not scheduled_for:
            raise ValueError("Tema e data são obrigatórios")
        with self.connect() as db:
            cursor = db.execute("INSERT INTO calendar(topic,series_id,profile,duration,scheduled_for,created_at) VALUES(?,?,?,?,?,?)",
                                (topic.strip(), series_id, profile, duration, scheduled_for, now()))
            return int(cursor.lastrowid)

    def list_calendar(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM calendar ORDER BY scheduled_for, id")]

    def link_calendar_job(self, item_id: int, job_id: str) -> None:
        with self.connect() as db:
            cursor = db.execute("UPDATE calendar SET status='producing', job_id=? WHERE id=?", (job_id, item_id))
            if not cursor.rowcount:
                raise ValueError("Item do calendário não encontrado")

    def add_asset(self, name: str, path: str, license_type: str, source_url: str | None,
                  notes: str | None, approved: bool) -> int:
        if not name.strip() or not path.strip() or not license_type.strip():
            raise ValueError("Nome, caminho e licença são obrigatórios")
        with self.connect() as db:
            cursor = db.execute("""INSERT INTO assets(name,path,license_type,source_url,notes,approved,created_at)
                                 VALUES(?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET name=excluded.name,
                                 license_type=excluded.license_type,source_url=excluded.source_url,notes=excluded.notes,
                                 approved=excluded.approved""",
                                (name.strip(), path.strip(), license_type.strip(), source_url, notes, int(approved), now()))
            if cursor.lastrowid:
                return int(cursor.lastrowid)
            row = db.execute("SELECT id FROM assets WHERE path=?", (path.strip(),)).fetchone()
            return int(row[0])

    def list_assets(self, approved_only: bool = False) -> list[dict[str, Any]]:
        query = "SELECT * FROM assets" + (" WHERE approved=1" if approved_only else "") + " ORDER BY created_at DESC"
        with self.connect() as db:
            items = [dict(row) for row in db.execute(query)]
            for item in items:
                item["approved"] = bool(item["approved"])
            return items

    def get_assets(self, asset_ids: list[int]) -> list[dict[str, Any]]:
        if not asset_ids:
            return []
        placeholders = ",".join("?" for _ in asset_ids)
        with self.connect() as db:
            rows = db.execute(f"SELECT * FROM assets WHERE id IN ({placeholders}) AND approved=1", asset_ids).fetchall()
            return [dict(row) for row in rows]
