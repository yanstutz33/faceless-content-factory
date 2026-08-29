from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DB_PATH = DATA / "factory.db"
JOBS_ROOT = (DATA / "jobs").resolve()


def main() -> None:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    archive = DATA / "archive" / f"legacy-under-30-min-{stamp}"
    archived_jobs = archive / "jobs"
    archive.mkdir(parents=True, exist_ok=False)
    archived_jobs.mkdir()

    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    rows = db.execute(
        "SELECT id,topic,profile,duration,status,output_dir FROM jobs WHERE duration<1800 ORDER BY created_at,id"
    ).fetchall()
    manifest = {"created_at": datetime.now(UTC).isoformat(), "rule": "duration < 1800 seconds",
                "count": len(rows), "jobs": [dict(row) for row in rows]}
    (archive / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copy2(DB_PATH, archive / "factory-before-cleanup.db")

    ids = [str(row["id"]) for row in rows]
    for row in rows:
        source = Path(str(row["output_dir"])).resolve()
        try:
            source.relative_to(JOBS_ROOT)
        except ValueError as exc:
            raise RuntimeError(f"Caminho de produção fora da pasta esperada: {source}") from exc
        if source.is_dir():
            shutil.move(str(source), str(archived_jobs / source.name))

    if ids:
        marks = ",".join("?" for _ in ids)
        with db:
            db.execute(f"DELETE FROM metrics WHERE job_id IN ({marks})", ids)
            db.execute(f"DELETE FROM events WHERE job_id IN ({marks})", ids)
            db.execute(f"DELETE FROM calendar WHERE duration<1800 OR job_id IN ({marks})", ids)
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "commerce_campaigns" in tables:
                db.execute(f"UPDATE commerce_campaigns SET job_id=NULL WHERE job_id IN ({marks})", ids)
            db.execute(f"DELETE FROM jobs WHERE id IN ({marks})", ids)
    db.execute("VACUUM")
    db.close()
    print(json.dumps({"archived": len(ids), "archive": str(archive), "remaining_short": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
