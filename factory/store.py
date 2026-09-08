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
                CREATE TABLE IF NOT EXISTS music_assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
                    path TEXT NOT NULL UNIQUE, license_type TEXT NOT NULL,
                    source_url TEXT, notes TEXT, approved INTEGER NOT NULL DEFAULT 0,
                    use_count INTEGER NOT NULL DEFAULT 0, last_used_at TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS autopilot (
                    id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL DEFAULT 0,
                    series_ids TEXT NOT NULL DEFAULT '["japan_after_rain","city_after_dark","rainy_refuges"]',
                    cadence INTEGER NOT NULL DEFAULT 3, publish_hour TEXT NOT NULL DEFAULT '19:00',
                    duration INTEGER NOT NULL DEFAULT 1800, horizon_days INTEGER NOT NULL DEFAULT 7,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS night_shift (
                    id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL DEFAULT 0,
                    start_hour TEXT NOT NULL DEFAULT '22:00', end_hour TEXT NOT NULL DEFAULT '07:00',
                    batch_limit INTEGER NOT NULL DEFAULT 2, last_run_at TEXT,
                    last_summary TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL
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
                "thumbnail_variant": "TEXT NOT NULL DEFAULT 'a'",
                "team_id": "TEXT NOT NULL DEFAULT 'youtube_ambient'",
                "music_asset_id": "INTEGER",
                "cohort_id": "TEXT",
            }
            for column, definition in additions.items():
                if column not in existing:
                    db.execute(f"ALTER TABLE jobs ADD COLUMN {column} {definition}")
            metrics_existing = {row[1] for row in db.execute("PRAGMA table_info(metrics)")}
            for column, definition in {
                "impressions": "INTEGER NOT NULL DEFAULT 0",
                "clicks": "INTEGER NOT NULL DEFAULT 0",
                "average_view_seconds": "REAL NOT NULL DEFAULT 0",
                "average_view_percentage": "REAL NOT NULL DEFAULT 0",
                "thumbnail_variant": "TEXT NOT NULL DEFAULT 'a'",
                "conversions": "INTEGER NOT NULL DEFAULT 0",
                "revenue": "REAL NOT NULL DEFAULT 0",
                "comments": "INTEGER NOT NULL DEFAULT 0",
                "shares": "INTEGER NOT NULL DEFAULT 0",
                "source": "TEXT NOT NULL DEFAULT 'manual'",
                "external_id": "TEXT",
                "snapshot_date": "TEXT",
            }.items():
                if column not in metrics_existing:
                    db.execute(f"ALTER TABLE metrics ADD COLUMN {column} {definition}")
            calendar_existing = {row[1] for row in db.execute("PRAGMA table_info(calendar)")}
            for column, definition in {
                "error": "TEXT",
                "updated_at": "TEXT",
                "origin": "TEXT NOT NULL DEFAULT 'manual'",
                "team_id": "TEXT NOT NULL DEFAULT 'youtube_ambient'",
            }.items():
                if column not in calendar_existing:
                    db.execute(f"ALTER TABLE calendar ADD COLUMN {column} {definition}")
            music_existing = {row[1] for row in db.execute("PRAGMA table_info(music_assets)")}
            for column, definition in {
                "human_review": "TEXT NOT NULL DEFAULT 'pending'",
                "human_reviewed_at": "TEXT",
            }.items():
                if column not in music_existing:
                    db.execute(f"ALTER TABLE music_assets ADD COLUMN {column} {definition}")
            db.execute(
                """INSERT OR IGNORE INTO autopilot(id,enabled,series_ids,cadence,publish_hour,duration,horizon_days,updated_at)
                   VALUES(1,0,?,3,'19:00',1800,7,?)""",
                (json.dumps(["japan_after_rain", "city_after_dark", "rainy_refuges"]), now()),
            )
            current = now()
            db.execute(
                """UPDATE autopilot SET series_ids=?,updated_at=?
                   WHERE series_ids=?""",
                (json.dumps(["japan_after_rain", "city_after_dark", "rainy_refuges"]), current,
                 json.dumps(["rainy_places", "cozy_worlds", "cosmic_focus"])),
            )
            db.execute(
                """UPDATE calendar SET status='archived',error=NULL,updated_at=?
                   WHERE status='planned' AND job_id IS NULL
                   AND series_id IN ('rainy_places','cozy_worlds','cosmic_focus','anime_nights')""",
                (current,),
            )
            db.execute(
                """INSERT OR IGNORE INTO night_shift(id,enabled,start_hour,end_hour,batch_limit,last_summary,updated_at)
                   VALUES(1,0,'22:00','07:00',2,'{}',?)""",
                (now(),),
            )

    def create_job(self, job: dict[str, Any]) -> None:
        timestamp = now()
        with self.connect() as db:
            db.execute(
                """INSERT INTO jobs(id,topic,status,duration,narration,subtitles,output_dir,metadata,
                   profile,priority,progress,source_asset,source_assets,team_id,music_asset_id,cohort_id,
                   created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (job["id"], job["topic"], "queued", job["duration"], int(job["narration"]),
                 int(job["subtitles"]), job["output_dir"], "{}", job.get("profile", "youtube_long"),
                 int(job.get("priority", 2)), 0, job.get("source_asset"),
                 json.dumps(job.get("source_assets", []), ensure_ascii=False),
                  job.get("team_id", "youtube_ambient"), job.get("music_asset_id"), job.get("cohort_id"),
                  timestamp, timestamp),
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
            calendar_status = {
                "queued": "producing", "planning": "producing", "assets": "producing",
                "rendering": "producing", "reviewing": "producing",
                "awaiting_approval": "ready", "approved": "approved",
                "failed": "failed", "rejected": "revision",
            }.get(status)
            if calendar_status:
                db.execute(
                    "UPDATE calendar SET status=?,error=?,updated_at=? WHERE job_id=?",
                    (calendar_status, error, now(), job_id),
                )

    def claim_job(self, job_id: str) -> bool:
        """Atomically reserve one queued/retryable job across processes."""
        timestamp = now()
        with self.connect() as db:
            cursor = db.execute(
                """UPDATE jobs SET status='planning',progress=8,error=NULL,updated_at=?
                   WHERE id=? AND status IN ('queued','failed','rejected')""",
                (timestamp, job_id),
            )
            if cursor.rowcount:
                db.execute(
                    "UPDATE calendar SET status='producing',error=NULL,updated_at=? WHERE job_id=?",
                    (timestamp, job_id),
                )
            return bool(cursor.rowcount)

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

    def add_metrics(self, job_id: str, platform: str, views: int, likes: int, watch_minutes: float,
                    impressions: int = 0, clicks: int = 0, average_view_seconds: float = 0,
                    thumbnail_variant: str = "a", conversions: int = 0, revenue: float = 0,
                    average_view_percentage: float = 0, comments: int = 0, shares: int = 0,
                    source: str = "manual", external_id: str | None = None,
                    snapshot_date: str | None = None) -> None:
        if not self.get_job(job_id):
            raise ValueError("Produção não encontrada")
        platform = platform.strip().lower()
        if platform not in {"youtube", "shorts", "tiktok", "reels", "shopee", "bilibili", "pinterest"}:
            raise ValueError("Plataforma de métricas inválida")
        thumbnail_variant = thumbnail_variant.lower()
        if thumbnail_variant not in {"a", "b"}:
            raise ValueError("Variante de thumbnail inválida")
        with self.connect() as db:
            db.execute("""INSERT INTO metrics(job_id,platform,views,likes,watch_minutes,impressions,clicks,
                       average_view_seconds,average_view_percentage,thumbnail_variant,conversions,revenue,
                       comments,shares,source,external_id,snapshot_date,recorded_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                       (job_id, platform, max(0, views), max(0, likes), max(0, watch_minutes),
                        max(0, impressions), max(0, clicks), max(0, average_view_seconds),
                        max(0, average_view_percentage), thumbnail_variant, max(0, conversions),
                        max(0, revenue), max(0, comments), max(0, shares), source.strip() or "manual",
                        external_id, snapshot_date, now()))
        self.event(job_id, "metrics", f"Métricas de {platform} registradas")

    def upsert_metrics_snapshot(self, job_id: str, platform: str, *, views: int = 0, likes: int = 0,
                                watch_minutes: float = 0, impressions: int = 0, clicks: int = 0,
                                average_view_seconds: float = 0, average_view_percentage: float = 0,
                                thumbnail_variant: str = "a", comments: int = 0, shares: int = 0,
                                source: str, external_id: str, snapshot_date: str) -> str:
        """Store one idempotent provider snapshot without replacing manual history."""
        if not self.get_job(job_id):
            raise ValueError("Produção não encontrada")
        with self.connect() as db:
            existing = db.execute(
                "SELECT id FROM metrics WHERE job_id=? AND platform=? AND source=? AND snapshot_date=?",
                (job_id, platform, source, snapshot_date),
            ).fetchone()
            values = (max(0, views), max(0, likes), max(0, watch_minutes), max(0, impressions),
                      max(0, clicks), max(0, average_view_seconds), max(0, average_view_percentage),
                      thumbnail_variant, max(0, comments), max(0, shares), external_id, now())
            if existing:
                db.execute("""UPDATE metrics SET views=?,likes=?,watch_minutes=?,impressions=?,clicks=?,
                           average_view_seconds=?,average_view_percentage=?,thumbnail_variant=?,comments=?,
                           shares=?,external_id=?,recorded_at=? WHERE id=?""", (*values, existing["id"]))
                operation = "updated"
            else:
                db.execute("""INSERT INTO metrics(job_id,platform,views,likes,watch_minutes,impressions,clicks,
                           average_view_seconds,average_view_percentage,thumbnail_variant,comments,shares,
                           source,external_id,snapshot_date,recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                           (job_id, platform, *values[:10], source, external_id, snapshot_date, values[11]))
                operation = "inserted"
        self.event(job_id, "metrics_sync", f"Snapshot {source} {snapshot_date} sincronizado")
        return operation

    def metrics_sync_status(self, source: str = "youtube_api") -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("""SELECT COUNT(*) AS snapshots,COUNT(DISTINCT job_id) AS jobs,
                              MAX(recorded_at) AS last_sync,MAX(snapshot_date) AS latest_snapshot
                              FROM metrics WHERE source=?""", (source,)).fetchone()
        return dict(row)

    def merge_metrics_reach(self, job_id: str, *, source: str, external_id: str,
                            snapshot_date: str, impressions: int, clicks: int) -> str:
        """Merge asynchronous reach fields without erasing targeted Analytics metrics."""
        if not self.get_job(job_id):
            raise ValueError("Produção não encontrada")
        with self.connect() as db:
            existing = db.execute(
                "SELECT id FROM metrics WHERE job_id=? AND platform='youtube' AND source=? AND snapshot_date=?",
                (job_id, source, snapshot_date),
            ).fetchone()
            if existing:
                db.execute("UPDATE metrics SET impressions=?,clicks=?,external_id=?,recorded_at=? WHERE id=?",
                           (max(0, impressions), max(0, clicks), external_id, now(), existing["id"]))
                operation = "updated"
            else:
                db.execute("""INSERT INTO metrics(job_id,platform,views,likes,watch_minutes,impressions,clicks,
                           average_view_seconds,average_view_percentage,thumbnail_variant,comments,shares,
                           source,external_id,snapshot_date,recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                           (job_id, "youtube", 0, 0, 0, max(0, impressions), max(0, clicks), 0, 0,
                            "a", 0, 0, source, external_id, snapshot_date, now()))
                operation = "inserted"
        self.event(job_id, "metrics_reach", f"Alcance {source} {snapshot_date} sincronizado")
        return operation

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

    def performance_insights(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("""
                WITH latest AS (
                    SELECT MAX(id) AS id FROM metrics GROUP BY job_id, platform
                )
                SELECT j.id, j.topic, j.profile, m.platform, m.views, m.likes, m.watch_minutes,
                       m.impressions, m.clicks, m.average_view_seconds, m.thumbnail_variant,
                       m.conversions, m.revenue,
                       json_extract(j.metadata,'$.creative_fingerprint.music_arrangement') AS music_arrangement,
                       json_extract(j.metadata,'$.creative_fingerprint.treatment') AS treatment,
                       json_extract(j.metadata,'$.creative_fingerprint.motion_effect') AS motion_effect,
                       CASE WHEN m.views > 0 THEN ROUND(100.0 * m.likes / m.views, 2) ELSE 0 END AS engagement_rate,
                       CASE WHEN m.views > 0 THEN ROUND(m.watch_minutes / m.views, 2) ELSE 0 END AS watch_minutes_per_view,
                       CASE WHEN m.impressions > 0 THEN ROUND(100.0 * m.clicks / m.impressions, 2) ELSE 0 END AS ctr,
                       CASE WHEN j.duration > 0 THEN ROUND(100.0 * m.average_view_seconds / j.duration, 2) ELSE 0 END AS retention_rate
                FROM metrics m
                JOIN latest l ON l.id=m.id
                JOIN jobs j ON j.id=m.job_id
                ORDER BY m.views DESC, engagement_rate DESC
                LIMIT 10
            """).fetchall()
            return [dict(row) for row in rows]

    def thumbnail_insights(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("""
                WITH latest AS (SELECT MAX(id) AS id FROM metrics GROUP BY job_id, platform),
                scored AS (
                    SELECT COALESCE(c.series_id,'sem-serie') AS series_id, m.thumbnail_variant,
                           SUM(m.impressions) AS impressions, SUM(m.clicks) AS clicks
                    FROM metrics m JOIN latest l ON l.id=m.id JOIN jobs j ON j.id=m.job_id
                    LEFT JOIN calendar c ON c.job_id=j.id
                    WHERE m.impressions > 0
                    GROUP BY COALESCE(c.series_id,'sem-serie'),m.thumbnail_variant
                )
                SELECT series_id,thumbnail_variant,impressions,clicks,
                       ROUND(100.0*clicks/impressions,2) AS ctr
                FROM scored ORDER BY series_id,ctr DESC,impressions DESC
            """).fetchall()
        return [dict(row) for row in rows]

    def add_calendar_item(self, topic: str, series_id: str | None, profile: str, duration: int,
                          scheduled_for: str, origin: str = "manual",
                          team_id: str = "youtube_ambient") -> int:
        if not topic.strip() or not scheduled_for:
            raise ValueError("Tema e data são obrigatórios")
        with self.connect() as db:
            cursor = db.execute("INSERT INTO calendar(topic,series_id,profile,duration,scheduled_for,origin,team_id,created_at) VALUES(?,?,?,?,?,?,?,?)",
                                (topic.strip(), series_id, profile, duration, scheduled_for, origin, team_id, now()))
            return int(cursor.lastrowid)

    def list_calendar(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM calendar ORDER BY scheduled_for, id")]

    def archive_stale_autopilot_plans(self, before: str) -> int:
        """Archive only overdue automatic plans that never started a production."""
        with self.connect() as db:
            cursor = db.execute(
                """UPDATE calendar SET status='archived',error=NULL,updated_at=?
                   WHERE origin='autopilot' AND status='planned' AND job_id IS NULL AND scheduled_for<?""",
                (now(), before),
            )
            return int(cursor.rowcount)

    def archive_unstarted_autopilot_plan(self, item_id: int, reason: str) -> bool:
        """Reversibly remove one unstarted automatic idea from the active agenda."""
        with self.connect() as db:
            cursor = db.execute(
                """UPDATE calendar SET status='archived',error=?,updated_at=?
                   WHERE id=? AND origin='autopilot' AND status='planned' AND job_id IS NULL""",
                (reason[:500], now(), item_id),
            )
            return bool(cursor.rowcount)

    def claim_due_calendar(self, at: datetime | None = None, allow_autopilot: bool = True) -> dict[str, Any] | None:
        local_now = (at or datetime.now().astimezone()).replace(tzinfo=None).isoformat(timespec="minutes")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                """SELECT * FROM calendar WHERE status='planned' AND scheduled_for<=?
                   AND (? OR origin!='autopilot') ORDER BY scheduled_for,id LIMIT 1""",
                (local_now, int(allow_autopilot)),
            ).fetchone()
            if not row:
                return None
            cursor = db.execute(
                "UPDATE calendar SET status='starting',error=NULL,updated_at=? WHERE id=? AND status='planned'",
                (now(), row["id"]),
            )
            return dict(row) if cursor.rowcount else None

    def claim_calendar_item(self, item_id: int) -> dict[str, Any] | None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM calendar WHERE id=? AND status IN ('planned','failed') AND job_id IS NULL",
                (item_id,),
            ).fetchone()
            if not row:
                return None
            cursor = db.execute(
                "UPDATE calendar SET status='starting',error=NULL,updated_at=? WHERE id=? AND status IN ('planned','failed') AND job_id IS NULL",
                (now(), item_id),
            )
            return dict(row) if cursor.rowcount else None

    def claim_next_calendar(self, allow_autopilot: bool = True) -> dict[str, Any] | None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                """SELECT * FROM calendar WHERE status='planned' AND job_id IS NULL
                   AND (? OR origin!='autopilot') ORDER BY scheduled_for,id LIMIT 1""",
                (int(allow_autopilot),),
            ).fetchone()
            if not row:
                return None
            cursor = db.execute(
                "UPDATE calendar SET status='starting',error=NULL,updated_at=? WHERE id=? AND status='planned' AND job_id IS NULL",
                (now(), row["id"]),
            )
            return dict(row) if cursor.rowcount else None

    def fail_calendar_item(self, item_id: int, error: str) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE calendar SET status='failed',error=?,updated_at=? WHERE id=?",
                (error[:500], now(), item_id),
            )

    def link_calendar_job(self, item_id: int, job_id: str) -> None:
        with self.connect() as db:
            cursor = db.execute("UPDATE calendar SET status='producing',job_id=?,error=NULL,updated_at=? WHERE id=?", (job_id, now(), item_id))
            if not cursor.rowcount:
                raise ValueError("Item do calendário não encontrado")

    def set_thumbnail_variant(self, job_id: str, variant: str) -> None:
        if variant not in {"a", "b"}:
            raise ValueError("Variante de thumbnail inválida")
        with self.connect() as db:
            cursor = db.execute("UPDATE jobs SET thumbnail_variant=?,updated_at=? WHERE id=?", (variant, now(), job_id))
            if not cursor.rowcount:
                raise ValueError("Produção não encontrada")

    def get_autopilot(self) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("SELECT * FROM autopilot WHERE id=1").fetchone()
        item = dict(row) if row else {}
        item["enabled"] = bool(item.get("enabled"))
        try:
            item["series_ids"] = json.loads(item.get("series_ids") or "[]")
        except json.JSONDecodeError:
            item["series_ids"] = []
        return item

    def update_autopilot(self, enabled: bool, series_ids: list[str], cadence: int,
                         publish_hour: str, duration: int, horizon_days: int = 7) -> dict[str, Any]:
        with self.connect() as db:
            db.execute(
                """UPDATE autopilot SET enabled=?,series_ids=?,cadence=?,publish_hour=?,duration=?,
                   horizon_days=?,updated_at=? WHERE id=1""",
                (int(enabled), json.dumps(series_ids), cadence, publish_hour, duration, horizon_days, now()),
            )
        return self.get_autopilot()

    def get_night_shift(self) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("SELECT * FROM night_shift WHERE id=1").fetchone()
        item = dict(row) if row else {}
        item["enabled"] = bool(item.get("enabled"))
        try:
            item["last_summary"] = json.loads(item.get("last_summary") or "{}")
        except json.JSONDecodeError:
            item["last_summary"] = {}
        return item

    def update_night_shift(self, enabled: bool, start_hour: str, end_hour: str, batch_limit: int,
                           summary: dict[str, Any] | None = None, ran: bool = False) -> dict[str, Any]:
        current = self.get_night_shift()
        with self.connect() as db:
            db.execute(
                """UPDATE night_shift SET enabled=?,start_hour=?,end_hour=?,batch_limit=?,last_run_at=?,
                   last_summary=?,updated_at=? WHERE id=1""",
                (int(enabled), start_hour, end_hour, batch_limit,
                 now() if ran else current.get("last_run_at"),
                 json.dumps(summary if summary is not None else current.get("last_summary", {}), ensure_ascii=False), now()),
            )
        return self.get_night_shift()

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
                item["available"] = Path(str(item.get("path", ""))).is_file()
            return items

    def get_asset(self, asset_id: int) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM assets WHERE id=? AND approved=1", (asset_id,)).fetchone()
        item = dict(row) if row else None
        if item:
            item["approved"] = bool(item["approved"])
            item["available"] = Path(str(item.get("path", ""))).is_file()
        return item

    def get_assets(self, asset_ids: list[int]) -> list[dict[str, Any]]:
        if not asset_ids:
            return []
        placeholders = ",".join("?" for _ in asset_ids)
        with self.connect() as db:
            rows = db.execute(f"SELECT * FROM assets WHERE id IN ({placeholders}) AND approved=1", asset_ids).fetchall()
            return [dict(row) for row in rows]

    def add_music_asset(self, name: str, path: str, license_type: str, source_url: str | None,
                        notes: str | None, approved: bool) -> int:
        if not name.strip() or not path.strip() or not license_type.strip():
            raise ValueError("Nome, caminho e licença são obrigatórios")
        with self.connect() as db:
            db.execute(
                """INSERT INTO music_assets(name,path,license_type,source_url,notes,approved,created_at)
                   VALUES(?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET name=excluded.name,
                   license_type=excluded.license_type,source_url=excluded.source_url,notes=excluded.notes,
                   approved=excluded.approved,human_review='pending',human_reviewed_at=NULL""",
                (name.strip(), path.strip(), license_type.strip(), source_url, notes, int(approved), now()),
            )
            row = db.execute("SELECT id FROM music_assets WHERE path=?", (path.strip(),)).fetchone()
            return int(row[0])

    def list_music_assets(self, approved_only: bool = False) -> list[dict[str, Any]]:
        query = "SELECT * FROM music_assets" + (" WHERE approved=1" if approved_only else "")
        query += " ORDER BY use_count,created_at,id"
        with self.connect() as db:
            items = [dict(row) for row in db.execute(query)]
        for item in items:
            item["approved"] = bool(item["approved"])
        return items

    def archive_music_assets_by_source(self, source_url: str) -> int:
        """Remove a catalog from rotation without deleting its files or history."""
        if not source_url.strip():
            raise ValueError("A origem do catálogo é obrigatória")
        with self.connect() as db:
            cursor = db.execute(
                "UPDATE music_assets SET approved=0 WHERE source_url=? AND approved=1",
                (source_url.strip(),),
            )
            return int(cursor.rowcount)

    def review_music_asset(self, asset_id: int, decision: str) -> dict[str, Any]:
        """Persist an explicit listening decision and remove rejected tracks from rotation."""
        if decision not in {"approved", "rejected"}:
            raise ValueError("A decisão deve aprovar ou reprovar a faixa")
        with self.connect() as db:
            row = db.execute("SELECT * FROM music_assets WHERE id=?", (asset_id,)).fetchone()
            if not row:
                raise ValueError("Música não encontrada")
            approved = 1 if decision == "approved" else 0
            db.execute(
                "UPDATE music_assets SET approved=?,human_review=?,human_reviewed_at=? WHERE id=?",
                (approved, decision, now(), asset_id),
            )
            invalidated: list[str] = []
            if decision == "rejected":
                for job in db.execute(
                    "SELECT id,metadata,music_asset_id FROM jobs WHERE status IN ('approved','awaiting_approval')"
                ).fetchall():
                    try:
                        metadata = json.loads(job["metadata"] or "{}")
                    except (TypeError, json.JSONDecodeError):
                        metadata = {}
                    music = metadata.get("music") if isinstance(metadata, dict) else {}
                    track_id = music.get("track_id") if isinstance(music, dict) else None
                    track_name = music.get("track_name") if isinstance(music, dict) else None
                    if (job["music_asset_id"] == asset_id or track_id == asset_id
                            or (track_name and track_name == row["name"])):
                        message = f"Música '{row['name']}' reprovada na audição; produção retirada da publicação"
                        db.execute(
                            "UPDATE jobs SET status='rejected',error=?,updated_at=? WHERE id=?",
                            (message, now(), job["id"]),
                        )
                        db.execute(
                            "UPDATE calendar SET status='revision',error=?,updated_at=? WHERE job_id=?",
                            (message, now(), job["id"]),
                        )
                        db.execute(
                            "INSERT INTO events(job_id,stage,message,created_at) VALUES(?,?,?,?)",
                            (job["id"], "music_review", message, now()),
                        )
                        invalidated.append(str(job["id"]))
            updated = db.execute("SELECT * FROM music_assets WHERE id=?", (asset_id,)).fetchone()
        item = dict(updated)
        item["approved"] = bool(item["approved"])
        item["invalidated_jobs"] = invalidated
        return item

    def get_music_asset(self, asset_id: int) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM music_assets WHERE id=? AND approved=1", (asset_id,)).fetchone()
            return dict(row) if row else None

    def get_music_asset_record(self, asset_id: int) -> dict[str, Any] | None:
        """Return a catalog record even when it is quarantined or rejected."""
        with self.connect() as db:
            row = db.execute("SELECT * FROM music_assets WHERE id=?", (asset_id,)).fetchone()
            if not row:
                return None
            item = dict(row)
            item["approved"] = bool(item["approved"])
            return item

    def assign_music_asset(self, job_id: str, asset_id: int) -> None:
        """Persist the automatic rotation choice so later audits remain traceable."""
        with self.connect() as db:
            cursor = db.execute(
                "UPDATE jobs SET music_asset_id=?,updated_at=? WHERE id=?",
                (asset_id, now(), job_id),
            )
            if not cursor.rowcount:
                raise ValueError("Produção não encontrada")

    def quarantine_legacy_music_jobs(self) -> list[str]:
        """Remove old synthetic/fallback audio packages from the publishable queue."""
        quarantined: list[str] = []
        message = "Beat sintético antigo reprovado; selecione uma nova música ouvida e aprovada"
        with self.connect() as db:
            rows = db.execute(
                "SELECT id,metadata FROM jobs WHERE status IN ('approved','awaiting_approval')"
            ).fetchall()
            for row in rows:
                try:
                    metadata = json.loads(row["metadata"] or "{}")
                except (TypeError, json.JSONDecodeError):
                    metadata = {}
                music = metadata.get("music") if isinstance(metadata, dict) else None
                if not isinstance(music, dict) or music.get("style") != "original_lofi_chill":
                    continue
                db.execute(
                    "UPDATE jobs SET status='rejected',error=?,updated_at=? WHERE id=?",
                    (message, now(), row["id"]),
                )
                db.execute(
                    "UPDATE calendar SET status='revision',error=?,updated_at=? WHERE job_id=?",
                    (message, now(), row["id"]),
                )
                db.execute(
                    "INSERT INTO events(job_id,stage,message,created_at) VALUES(?,?,?,?)",
                    (row["id"], "music_review", message, now()),
                )
                quarantined.append(str(row["id"]))
        return quarantined

    def establish_pilot_cohort(self, cohort_id: str, eligible_job_ids: list[str],
                               candidate_job_ids: list[str]) -> dict[str, list[str]]:
        """Tag one auditable pilot cohort and remove historical jobs from its review queue.

        Files are never deleted. Historical packages remain recoverable and can
        be rerendered later with a currently approved music asset.
        """
        cohort_id = cohort_id.strip()
        eligible = set(eligible_job_ids)
        candidates = set(candidate_job_ids)
        if not cohort_id or not eligible or not eligible.issubset(candidates):
            raise ValueError("Coorte piloto inválida")
        tagged: list[str] = []
        quarantined: list[str] = []
        message = "Produção histórica fora da coorte piloto; arquivos preservados para possível rerenderização"
        with self.connect() as db:
            placeholders = ",".join("?" for _ in candidates)
            rows = db.execute(
                f"SELECT id,metadata,status FROM jobs WHERE id IN ({placeholders})",
                tuple(candidates),
            ).fetchall()
            if len(rows) != len(candidates):
                raise ValueError("Uma ou mais produções da coorte não foram encontradas")
            for row in rows:
                try:
                    metadata = json.loads(row["metadata"] or "{}")
                except (TypeError, json.JSONDecodeError):
                    metadata = {}
                if row["id"] in eligible:
                    metadata["pilot_cohort_id"] = cohort_id
                    db.execute(
                        "UPDATE jobs SET cohort_id=?,metadata=?,error=NULL,updated_at=? WHERE id=?",
                        (cohort_id, json.dumps(metadata, ensure_ascii=False), now(), row["id"]),
                    )
                    db.execute(
                        "INSERT INTO events(job_id,stage,message,created_at) VALUES(?,?,?,?)",
                        (row["id"], "pilot_cohort", f"Incluída na coorte {cohort_id}", now()),
                    )
                    tagged.append(str(row["id"]))
                    continue
                metadata.pop("pilot_cohort_id", None)
                metadata["archive_reason"] = "historical_package_without_current_music_binding"
                db.execute(
                    "UPDATE jobs SET status='rejected',cohort_id=NULL,metadata=?,error=?,updated_at=? WHERE id=?",
                    (json.dumps(metadata, ensure_ascii=False), message, now(), row["id"]),
                )
                db.execute(
                    "UPDATE calendar SET status='revision',error=?,updated_at=? WHERE job_id=?",
                    (message, now(), row["id"]),
                )
                db.execute(
                    "INSERT INTO events(job_id,stage,message,created_at) VALUES(?,?,?,?)",
                    (row["id"], "pilot_archive", message, now()),
                )
                quarantined.append(str(row["id"]))
        return {"tagged": sorted(tagged), "quarantined": sorted(quarantined)}

    def reserve_music_asset(self, preferred_id: int | None = None) -> dict[str, Any] | None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if preferred_id:
                row = db.execute(
                    "SELECT * FROM music_assets WHERE id=? AND approved=1 AND human_review='approved'",
                    (preferred_id,),
                ).fetchone()
            else:
                row = db.execute(
                    """SELECT * FROM music_assets WHERE approved=1 AND human_review='approved'
                       ORDER BY use_count ASC, COALESCE(last_used_at,'') ASC, id ASC LIMIT 1"""
                ).fetchone()
            if not row:
                return None
            db.execute(
                "UPDATE music_assets SET use_count=use_count+1,last_used_at=? WHERE id=?",
                (now(), row["id"]),
            )
            item = dict(row)
            item["use_count"] = int(item["use_count"]) + 1
            item["last_used_at"] = now()
            item["approved"] = True
            return item
