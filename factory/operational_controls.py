"""Low-cost operational guardrails shared by future workers.

This module is intentionally independent from the HTTP layer and the existing
YouTube metrics synchronizer.  It provides local admission control, bounded
attempts, and a workspace-independent claim ledger that can be integrated by a
worker without granting it publishing credentials.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable


class OperationalLimitError(RuntimeError):
    """Raised when an operation would exceed a local safety limit."""


class CrossWorkspaceDuplicateError(RuntimeError):
    """Raised when the same destination payload is claimed by another workspace."""


def _now(value: datetime | None = None) -> datetime:
    return (value or datetime.now(UTC)).astimezone(UTC)


def _day(value: datetime) -> str:
    return _now(value).date().isoformat()


@dataclass(frozen=True)
class UsagePolicy:
    """Conservative local limits; all values can be overridden per worker."""

    max_active: int = 2
    max_queue: int = 12
    max_attempts: int = 3
    max_metric_syncs_per_day: int = 1

    def __post_init__(self) -> None:
        if min(self.max_active, self.max_queue, self.max_attempts,
               self.max_metric_syncs_per_day) < 1:
            raise ValueError("Limites operacionais devem ser positivos")


@dataclass
class UsageLedger:
    """Transactional ledger for admission checks, retries, and cost signals.

    SQLite is intentional here: workspaces can run in separate processes, so
    an in-process lock around JSON would not make queue limits atomic.
    """

    path: Path
    policy: UsagePolicy = field(default_factory=UsagePolicy)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS operations (
                operation_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL,
                kind TEXT NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL,
                day TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                error TEXT
            )""")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=15000")
        db.execute("PRAGMA journal_mode=WAL")
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def reserve(self, operation_id: str, workspace_id: str, kind: str = "render",
                now: datetime | None = None) -> dict[str, Any]:
        """Reserve one local operation, enforcing queue/active and metric limits."""
        if not operation_id or not workspace_id:
            raise ValueError("operation_id e workspace_id são obrigatórios")
        moment = _now(now)
        with self._lock:
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                existing = db.execute(
                    "SELECT * FROM operations WHERE operation_id=?", (operation_id,)
                ).fetchone()
                if existing and existing["state"] in {"reserved", "active"}:
                    return dict(existing)
                if existing and existing["state"] == "completed":
                    raise OperationalLimitError("operação já concluída")
                queued = db.execute(
                    "SELECT COUNT(*) FROM operations WHERE state IN ('reserved','active')"
                ).fetchone()[0]
                if queued >= self.policy.max_queue:
                    raise OperationalLimitError("limite local da fila atingido")
                if kind == "metrics" and db.execute(
                    "SELECT COUNT(*) FROM operations WHERE kind='metrics' AND day=?",
                    (_day(moment),),
                ).fetchone()[0] >= self.policy.max_metric_syncs_per_day:
                    raise OperationalLimitError("limite diário de sincronização de métricas atingido")
                row = {"operation_id": operation_id, "workspace_id": workspace_id, "kind": kind,
                       "state": "reserved", "attempts": int(existing["attempts"]) if existing else 0,
                       "day": _day(moment),
                       "created_at": existing["created_at"] if existing else moment.isoformat(),
                       "updated_at": moment.isoformat(),
                       "error": None}
                db.execute(
                    """INSERT INTO operations(operation_id,workspace_id,kind,state,attempts,day,
                       created_at,updated_at,error) VALUES(:operation_id,:workspace_id,:kind,:state,
                       :attempts,:day,:created_at,:updated_at,:error)
                       ON CONFLICT(operation_id) DO UPDATE SET workspace_id=excluded.workspace_id,
                       kind=excluded.kind,state=excluded.state,attempts=excluded.attempts,
                       day=excluded.day,created_at=excluded.created_at,updated_at=excluded.updated_at,
                       error=NULL""", row,
                )
                return row

    def start(self, operation_id: str, now: datetime | None = None) -> dict[str, Any]:
        with self._lock:
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT * FROM operations WHERE operation_id=?", (operation_id,)).fetchone()
                if not row:
                    raise KeyError(operation_id)
                active = db.execute("SELECT COUNT(*) FROM operations WHERE state='active'").fetchone()[0]
                if row["state"] != "active" and active >= self.policy.max_active:
                    raise OperationalLimitError("limite local de operações ativas atingido")
                db.execute("UPDATE operations SET state='active',updated_at=? WHERE operation_id=?",
                           (_now(now).isoformat(), operation_id))
                return dict(db.execute("SELECT * FROM operations WHERE operation_id=?", (operation_id,)).fetchone())

    def attempt(self, operation_id: str, now: datetime | None = None) -> dict[str, Any]:
        with self._lock:
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT * FROM operations WHERE operation_id=?", (operation_id,)).fetchone()
                if not row:
                    raise KeyError(operation_id)
                if int(row["attempts"]) >= self.policy.max_attempts:
                    raise OperationalLimitError("número máximo local de tentativas atingido")
                db.execute("UPDATE operations SET attempts=attempts+1,updated_at=? WHERE operation_id=?",
                           (_now(now).isoformat(), operation_id))
                return dict(db.execute("SELECT * FROM operations WHERE operation_id=?", (operation_id,)).fetchone())

    def finish(self, operation_id: str, state: str = "completed",
               now: datetime | None = None, error: str | None = None) -> dict[str, Any]:
        if state not in {"completed", "failed", "cancelled"}:
            raise ValueError("estado final inválido")
        with self._lock:
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                if not db.execute("SELECT 1 FROM operations WHERE operation_id=?", (operation_id,)).fetchone():
                    raise KeyError(operation_id)
                db.execute("UPDATE operations SET state=?,updated_at=?,error=? WHERE operation_id=?",
                           (state, _now(now).isoformat(), str(error)[:500] if error else None, operation_id))
                return dict(db.execute("SELECT * FROM operations WHERE operation_id=?", (operation_id,)).fetchone())

    def recover_interrupted(self, workspace_id: str,
                            now: datetime | None = None) -> int:
        """Release stale reservations for this workspace after a process restart."""
        with self._lock:
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                cursor = db.execute(
                    """UPDATE operations SET state='cancelled',updated_at=?,
                       error='interrupted process recovered'
                       WHERE workspace_id=? AND state IN ('reserved','active')""",
                    (_now(now).isoformat(), workspace_id),
                )
                return int(cursor.rowcount)

    def snapshot(self, workspace_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            with self._connect() as db:
                if workspace_id:
                    rows = db.execute(
                        "SELECT * FROM operations WHERE workspace_id=? ORDER BY created_at", (workspace_id,)
                    )
                else:
                    rows = db.execute("SELECT * FROM operations ORDER BY created_at")
                operations = [dict(row) for row in rows]
            states = {state: sum(row.get("state") == state for row in operations)
                      for state in ("reserved", "active", "completed", "failed", "cancelled")}
            failures = [{"operation_id": row.get("operation_id"), "kind": row.get("kind"),
                         "error": row.get("error", ""), "attempts": row.get("attempts", 0)}
                        for row in operations if row.get("state") == "failed"]
            return {"policy": self.policy.__dict__.copy(), "states": states,
                    "failures": failures[-20:], "operations": len(operations)}


@dataclass
class CrossWorkspaceClaims:
    """Atomically reserve one payload/platform for exactly one workspace."""

    path: Path
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS claims (
                claim_key TEXT PRIMARY KEY, platform TEXT NOT NULL, payload_key TEXT NOT NULL,
                workspace_id TEXT NOT NULL, job_id TEXT NOT NULL, created_at TEXT NOT NULL
            )""")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=15000")
        db.execute("PRAGMA journal_mode=WAL")
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def claim(self, workspace_id: str, platform: str, payload_key: str, job_id: str,
              now: datetime | None = None) -> dict[str, Any]:
        if not all((workspace_id, platform, payload_key, job_id)):
            raise ValueError("workspace, plataforma, payload e job são obrigatórios")
        claim_key = f"{platform}:{payload_key}"
        with self._lock:
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                existing = db.execute("SELECT * FROM claims WHERE claim_key=?", (claim_key,)).fetchone()
                if existing:
                    if existing["workspace_id"] != workspace_id:
                        raise CrossWorkspaceDuplicateError(
                            f"payload já reservado pelo workspace {existing['workspace_id']}"
                        )
                    if existing["job_id"] != job_id:
                        raise CrossWorkspaceDuplicateError("payload já reservado por outro job no workspace")
                    row = dict(existing)
                    row.pop("claim_key", None)
                    return {**row, "idempotent": True}
                row = {"claim_key": claim_key, "platform": platform, "payload_key": payload_key,
                       "workspace_id": workspace_id, "job_id": job_id,
                       "created_at": _now(now).isoformat()}
                db.execute(
                    """INSERT INTO claims(claim_key,platform,payload_key,workspace_id,job_id,created_at)
                       VALUES(:claim_key,:platform,:payload_key,:workspace_id,:job_id,:created_at)""", row,
                )
                row.pop("claim_key")
                return {**row, "idempotent": False}

    def list(self, workspace_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            with self._connect() as db:
                if workspace_id:
                    rows = db.execute(
                        """SELECT platform,payload_key,workspace_id,job_id,created_at FROM claims
                           WHERE workspace_id=? ORDER BY created_at""", (workspace_id,)
                    )
                else:
                    rows = db.execute(
                        "SELECT platform,payload_key,workspace_id,job_id,created_at FROM claims ORDER BY created_at"
                    )
                return [dict(row) for row in rows]


def credential_expiry_summary(credentials: Iterable[dict[str, Any]],
                              now: datetime | None = None,
                              warning_days: int = 14) -> list[dict[str, Any]]:
    """Return expiry state without returning token/client-secret values."""
    moment = _now(now)
    result = []
    for item in credentials:
        platform = str(item.get("platform") or "unknown")
        expires_at = item.get("expires_at")
        if not expires_at:
            result.append({"platform": platform, "state": "unknown", "expires_at": None})
            continue
        try:
            expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            result.append({"platform": platform, "state": "invalid", "expires_at": None})
            continue
        days = (expiry - moment).total_seconds() / 86400
        state = "expired" if days < 0 else "expiring_soon" if days <= warning_days else "healthy"
        result.append({"platform": platform, "state": state, "expires_at": expiry.isoformat(),
                       "days_remaining": round(days, 2)})
    return result


def operational_health(usage: UsageLedger, claims: CrossWorkspaceClaims,
                       credentials: Iterable[dict[str, Any]] = (),
                       now: datetime | None = None,
                       workspace_id: str | None = None) -> dict[str, Any]:
    """Compact, redacted health/cost/failure report for a future dashboard."""
    usage_report = usage.snapshot(workspace_id)
    return {
        "generated_at": _now(now).isoformat(),
        "mode": "manual-safe",
        "usage": usage_report,
        "claims": {"count": len(claims.list(workspace_id)), "cross_workspace_guard": True},
        "credentials": credential_expiry_summary(credentials, now=now),
        "cost_signals": {
            "metrics_syncs_limited": True,
            "network_contacted": False,
            "publishing_performed": False,
        },
    }
