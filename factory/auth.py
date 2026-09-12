from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .workspaces import normalize_workspace_id


ROLES = frozenset({"admin", "editor", "reviewer"})
USERNAME_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{1,62}[a-z0-9])?$")
PASSWORD_ITERATIONS = 600_000
SESSION_HOURS = 8
SESSION_IDLE_MINUTES = 45
REAUTH_MINUTES = 5
RECOVERY_MINUTES = 15
SENSITIVE_DETAIL_WORDS = {"password", "secret", "token", "cookie", "authorization", "verifier"}


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).isoformat()


def _token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _scrub_detail(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: ("[redacted]" if any(word in key.lower() for word in SENSITIVE_DETAIL_WORDS)
                  else _scrub_detail(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_scrub_detail(item) for item in value]
    return value


class LocalAuth:
    """Local accounts, role membership and opaque expiring sessions.

    Raw passwords, session IDs, CSRF values and recovery tokens are never
    persisted. The database stores only salted password derivations and hashes
    of random bearer material.
    """

    def __init__(self, database: Path):
        database.parent.mkdir(parents=True, exist_ok=True)
        self.database = database
        self._init_schema()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=15000")
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def _init_schema(self) -> None:
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS auth_users (
                    id TEXT PRIMARY KEY, username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    password_hash TEXT NOT NULL, password_salt TEXT NOT NULL,
                    password_iterations INTEGER NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    failed_attempts INTEGER NOT NULL DEFAULT 0, locked_until TEXT,
                    created_at TEXT NOT NULL, password_changed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS auth_memberships (
                    user_id TEXT NOT NULL, workspace_id TEXT NOT NULL, role TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, workspace_id),
                    FOREIGN KEY(user_id) REFERENCES auth_users(id) ON DELETE CASCADE,
                    CHECK(role IN ('admin','editor','reviewer'))
                );
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token_hash TEXT PRIMARY KEY, csrf_hash TEXT NOT NULL,
                    user_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
                    created_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL, revoked_at TEXT, reauthenticated_at TEXT,
                    FOREIGN KEY(user_id) REFERENCES auth_users(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS auth_recovery_tokens (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL, issued_by TEXT NOT NULL,
                    created_at TEXT NOT NULL, expires_at TEXT NOT NULL, used_at TEXT,
                    FOREIGN KEY(user_id) REFERENCES auth_users(id) ON DELETE CASCADE,
                    FOREIGN KEY(issued_by) REFERENCES auth_users(id)
                );
                CREATE TABLE IF NOT EXISTS auth_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, workspace_id TEXT NOT NULL,
                    user_id TEXT, event TEXT NOT NULL, target TEXT,
                    outcome TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS auth_sessions_user ON auth_sessions(user_id, revoked_at);
                CREATE INDEX IF NOT EXISTS auth_sessions_expiry ON auth_sessions(expires_at);
                CREATE INDEX IF NOT EXISTS auth_audit_workspace ON auth_audit(workspace_id, id DESC);
            """)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(auth_sessions)")}
            if "reauthenticated_at" not in columns:
                db.execute("ALTER TABLE auth_sessions ADD COLUMN reauthenticated_at TEXT")

    @staticmethod
    def normalize_username(value: str) -> str:
        username = str(value or "").strip().lower()
        if not USERNAME_PATTERN.fullmatch(username):
            raise ValueError("Usuário deve ter de 3 a 64 caracteres simples")
        return username

    @staticmethod
    def validate_password(password: str) -> str:
        password = str(password or "")
        if len(password) < 12 or len(password) > 1024:
            raise ValueError("A senha deve ter de 12 a 1024 caracteres")
        if password.isspace():
            raise ValueError("A senha não pode conter apenas espaços")
        return password

    @staticmethod
    def _derive(password: str, salt_hex: str, iterations: int = PASSWORD_ITERATIONS) -> str:
        return hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), iterations, dklen=32
        ).hex()

    @classmethod
    def _password_record(cls, password: str) -> tuple[str, str, int]:
        password = cls.validate_password(password)
        salt = secrets.token_bytes(16).hex()
        return cls._derive(password, salt), salt, PASSWORD_ITERATIONS

    def audit(self, workspace_id: str, event: str, outcome: str, *, user_id: str | None = None,
              target: str | None = None, detail: dict[str, Any] | None = None) -> None:
        workspace_id = normalize_workspace_id(workspace_id)
        with self.connect() as db:
            db.execute(
                """INSERT INTO auth_audit(workspace_id,user_id,event,target,outcome,detail,created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (workspace_id, user_id, event, target, outcome,
                 json.dumps(_scrub_detail(detail or {}), ensure_ascii=False), _iso()),
            )

    def has_admin(self, workspace_id: str) -> bool:
        workspace_id = normalize_workspace_id(workspace_id)
        with self.connect() as db:
            row = db.execute(
                """SELECT 1 FROM auth_memberships m JOIN auth_users u ON u.id=m.user_id
                   WHERE m.workspace_id=? AND m.role='admin' AND u.active=1 LIMIT 1""",
                (workspace_id,),
            ).fetchone()
        return bool(row)

    def bootstrap_admin(self, username: str, password: str, workspace_id: str) -> dict[str, Any]:
        username = self.normalize_username(username)
        workspace_id = normalize_workspace_id(workspace_id)
        password_hash, salt, iterations = self._password_record(password)
        timestamp = _iso()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing_admin = db.execute(
                """SELECT 1 FROM auth_memberships m JOIN auth_users u ON u.id=m.user_id
                   WHERE m.workspace_id=? AND m.role='admin' AND u.active=1 LIMIT 1""",
                (workspace_id,),
            ).fetchone()
            if existing_admin:
                raise ValueError("O espaço já possui um administrador ativo")
            if db.execute("SELECT 1 FROM auth_users WHERE username=?", (username,)).fetchone():
                raise ValueError("O usuário já existe; conceda acesso com uma sessão administrativa")
            user_id = secrets.token_hex(16)
            db.execute(
                """INSERT INTO auth_users(id,username,password_hash,password_salt,password_iterations,
                   created_at,password_changed_at) VALUES(?,?,?,?,?,?,?)""",
                (user_id, username, password_hash, salt, iterations, timestamp, timestamp),
            )
            db.execute(
                "INSERT INTO auth_memberships(user_id,workspace_id,role,created_at) VALUES(?,?,?,?)",
                (user_id, workspace_id, "admin", timestamp),
            )
        self.audit(workspace_id, "admin_bootstrap", "success", user_id=user_id, target=username)
        return {"id": user_id, "username": username, "workspace_id": workspace_id, "role": "admin"}

    def _dummy_verify(self, password: str) -> None:
        # Avoid an obviously cheaper path for usernames that do not exist.
        self._derive(password, "00" * 16, PASSWORD_ITERATIONS)

    def login(self, username: str, password: str, workspace_id: str) -> dict[str, Any]:
        workspace_id = normalize_workspace_id(workspace_id)
        try:
            username = self.normalize_username(username)
        except ValueError:
            self._dummy_verify(str(password or ""))
            self.audit(workspace_id, "login", "denied", target="unknown")
            raise ValueError("Usuário, senha ou espaço inválido")
        now_at = _now()
        with self.connect() as db:
            row = db.execute(
                """SELECT u.*,m.role FROM auth_users u LEFT JOIN auth_memberships m
                   ON m.user_id=u.id AND m.workspace_id=? WHERE u.username=?""",
                (workspace_id, username),
            ).fetchone()
            if not row:
                self._dummy_verify(password)
                denied_user = None
                result = None
                success_user = None
            else:
                denied_user = str(row["id"])
                locked_until = datetime.fromisoformat(row["locked_until"]) if row["locked_until"] else None
                if locked_until and locked_until > now_at:
                    self.audit(workspace_id, "login", "locked", user_id=denied_user, target=username)
                    raise ValueError("Acesso temporariamente bloqueado após tentativas inválidas")
                candidate = self._derive(password, row["password_salt"], int(row["password_iterations"]))
                valid = bool(row["active"] and row["role"] and hmac.compare_digest(candidate, row["password_hash"]))
                if valid:
                    db.execute(
                        "UPDATE auth_users SET failed_attempts=0,locked_until=NULL WHERE id=?", (row["id"],)
                    )
                    raw_token = secrets.token_urlsafe(32)
                    csrf = secrets.token_urlsafe(24)
                    expires_at = now_at + timedelta(hours=SESSION_HOURS)
                    db.execute(
                        """INSERT INTO auth_sessions(token_hash,csrf_hash,user_id,workspace_id,created_at,
                           last_seen_at,expires_at,reauthenticated_at) VALUES(?,?,?,?,?,?,?,?)""",
                        (_token_hash(raw_token), _token_hash(csrf), row["id"], workspace_id,
                         _iso(now_at), _iso(now_at), _iso(expires_at), _iso(now_at)),
                    )
                    result = {
                        "session_token": raw_token, "csrf_token": csrf, "expires_at": _iso(expires_at),
                        "user": {"id": row["id"], "username": row["username"], "role": row["role"]},
                        "workspace_id": workspace_id,
                    }
                    success_user = str(row["id"])
                else:
                    attempts = int(row["failed_attempts"]) + 1
                    lock = _iso(now_at + timedelta(minutes=15)) if attempts >= 5 else None
                    db.execute(
                        "UPDATE auth_users SET failed_attempts=?,locked_until=? WHERE id=?",
                        (attempts, lock, row["id"]),
                    )
                    result = None
                    success_user = None
        if result is None:
            self.audit(workspace_id, "login", "denied", user_id=denied_user, target=username)
            raise ValueError("Usuário, senha ou espaço inválido")
        self.audit(workspace_id, "login", "success", user_id=success_user, target=username)
        return result

    def session(self, raw_token: str, *, touch: bool = True) -> dict[str, Any] | None:
        if not raw_token:
            return None
        now_at = _now()
        with self.connect() as db:
            row = db.execute(
                """SELECT s.*,u.username,u.active,m.role FROM auth_sessions s
                   JOIN auth_users u ON u.id=s.user_id
                   LEFT JOIN auth_memberships m ON m.user_id=s.user_id AND m.workspace_id=s.workspace_id
                   WHERE s.token_hash=?""",
                (_token_hash(raw_token),),
            ).fetchone()
            if not row or row["revoked_at"] or not row["active"] or not row["role"]:
                return None
            expires_at = datetime.fromisoformat(row["expires_at"])
            last_seen = datetime.fromisoformat(row["last_seen_at"])
            if expires_at <= now_at or last_seen + timedelta(minutes=SESSION_IDLE_MINUTES) <= now_at:
                db.execute("UPDATE auth_sessions SET revoked_at=? WHERE token_hash=?", (_iso(now_at), row["token_hash"]))
                return None
            if touch:
                db.execute("UPDATE auth_sessions SET last_seen_at=? WHERE token_hash=?", (_iso(now_at), row["token_hash"]))
            memberships = [dict(item) for item in db.execute(
                "SELECT workspace_id,role FROM auth_memberships WHERE user_id=? ORDER BY workspace_id",
                (row["user_id"],),
            )]
        return {
            "user_id": row["user_id"], "username": row["username"], "workspace_id": row["workspace_id"],
            "role": row["role"], "csrf_hash": row["csrf_hash"], "expires_at": row["expires_at"],
            "reauthenticated_at": row["reauthenticated_at"],
            "memberships": memberships,
        }

    def reauthenticate(self, raw_token: str, password: str) -> dict[str, Any]:
        """Verify the current user's password and timestamp only the session."""
        session = self.session(raw_token, touch=False)
        if not session:
            raise ValueError("Sessão inválida ou expirada")
        password = str(password or "")
        now_at = _now()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM auth_users WHERE id=? AND active=1", (session["user_id"],)
            ).fetchone()
            locked_until = datetime.fromisoformat(row["locked_until"]) if row and row["locked_until"] else None
            if locked_until and locked_until > now_at:
                valid = False
            else:
                candidate = self._derive(password, row["password_salt"], int(row["password_iterations"])) \
                    if row else self._derive(password, "00" * 16, PASSWORD_ITERATIONS)
                valid = bool(row and hmac.compare_digest(candidate, row["password_hash"]))
            if not valid:
                if row:
                    attempts = int(row["failed_attempts"]) + 1
                    lock = _iso(now_at + timedelta(minutes=15)) if attempts >= 5 else row["locked_until"]
                    db.execute("UPDATE auth_users SET failed_attempts=?,locked_until=? WHERE id=?",
                               (attempts, lock, row["id"]))
            else:
                db.execute("UPDATE auth_users SET failed_attempts=0,locked_until=NULL WHERE id=?", (row["id"],))
                db.execute(
                    "UPDATE auth_sessions SET reauthenticated_at=?,last_seen_at=? WHERE token_hash=? AND revoked_at IS NULL",
                    (_iso(now_at), _iso(now_at), _token_hash(raw_token)),
                )
        if not valid:
            self.audit(session["workspace_id"], "reauthentication", "denied", user_id=session["user_id"])
            raise ValueError("Senha atual inválida")
        self.audit(session["workspace_id"], "reauthentication", "success", user_id=session["user_id"])
        refreshed = self.session(raw_token, touch=False)
        assert refreshed is not None
        return refreshed

    @staticmethod
    def recently_reauthenticated(session: dict[str, Any], minutes: int = REAUTH_MINUTES) -> bool:
        try:
            verified_at = datetime.fromisoformat(str(session.get("reauthenticated_at") or ""))
        except ValueError:
            return False
        return verified_at + timedelta(minutes=max(1, min(int(minutes), 30))) > _now()

    @staticmethod
    def csrf_valid(session: dict[str, Any], csrf_token: str) -> bool:
        return bool(csrf_token) and hmac.compare_digest(_token_hash(csrf_token), str(session.get("csrf_hash", "")))

    def rotate_csrf(self, raw_token: str) -> str:
        session = self.session(raw_token, touch=False)
        if not session:
            raise ValueError("Sessão inválida ou expirada")
        csrf = secrets.token_urlsafe(24)
        with self.connect() as db:
            db.execute(
                "UPDATE auth_sessions SET csrf_hash=?,last_seen_at=? WHERE token_hash=? AND revoked_at IS NULL",
                (_token_hash(csrf), _iso(), _token_hash(raw_token)),
            )
        return csrf

    def logout(self, raw_token: str) -> bool:
        session = self.session(raw_token, touch=False)
        with self.connect() as db:
            cursor = db.execute(
                "UPDATE auth_sessions SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL",
                (_iso(), _token_hash(raw_token)),
            )
        if session:
            self.audit(session["workspace_id"], "logout", "success", user_id=session["user_id"])
        return bool(cursor.rowcount)

    def select_workspace(self, raw_token: str, workspace_id: str) -> dict[str, Any]:
        workspace_id = normalize_workspace_id(workspace_id)
        session = self.session(raw_token, touch=False)
        if not session:
            raise ValueError("Sessão inválida ou expirada")
        membership = next(
            (item for item in session["memberships"] if item["workspace_id"] == workspace_id), None
        )
        if not membership:
            self.audit(session["workspace_id"], "workspace_select", "denied",
                       user_id=session["user_id"], target=workspace_id)
            raise PermissionError("O usuário não possui acesso a este espaço")
        with self.connect() as db:
            db.execute(
                "UPDATE auth_sessions SET workspace_id=?,last_seen_at=? WHERE token_hash=?",
                (workspace_id, _iso(), _token_hash(raw_token)),
            )
        self.audit(workspace_id, "workspace_select", "success",
                   user_id=session["user_id"], target=workspace_id)
        selected = self.session(raw_token)
        assert selected is not None
        return selected

    def require_role(self, session: dict[str, Any], allowed: set[str]) -> None:
        if session.get("role") not in allowed:
            self.audit(session["workspace_id"], "authorization", "denied",
                       user_id=session["user_id"], detail={"required_roles": sorted(allowed)})
            raise PermissionError("Seu papel não permite esta ação")

    def create_user(self, actor: dict[str, Any], username: str, password: str, role: str) -> dict[str, Any]:
        self.require_role(actor, {"admin"})
        username = self.normalize_username(username)
        role = str(role or "").lower()
        if role not in ROLES:
            raise ValueError("Papel inválido")
        password_hash, salt, iterations = self._password_record(password)
        timestamp = _iso()
        user_id = secrets.token_hex(16)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM auth_users WHERE username=?", (username,)).fetchone():
                raise ValueError("O usuário já existe")
            db.execute(
                """INSERT INTO auth_users(id,username,password_hash,password_salt,password_iterations,
                   created_at,password_changed_at) VALUES(?,?,?,?,?,?,?)""",
                (user_id, username, password_hash, salt, iterations, timestamp, timestamp),
            )
            db.execute(
                "INSERT INTO auth_memberships(user_id,workspace_id,role,created_at) VALUES(?,?,?,?)",
                (user_id, actor["workspace_id"], role, timestamp),
            )
        self.audit(actor["workspace_id"], "user_create", "success", user_id=actor["user_id"], target=user_id,
                   detail={"role": role})
        return {"id": user_id, "username": username, "workspace_id": actor["workspace_id"], "role": role}

    def list_users(self, actor: dict[str, Any]) -> list[dict[str, Any]]:
        self.require_role(actor, {"admin"})
        with self.connect() as db:
            rows = db.execute(
                """SELECT u.id,u.username,u.active,u.created_at,m.role
                   FROM auth_memberships m JOIN auth_users u ON u.id=m.user_id
                   WHERE m.workspace_id=? ORDER BY u.username""",
                (actor["workspace_id"],),
            ).fetchall()
        return [dict(row) for row in rows]

    def grant_workspace(self, actor: dict[str, Any], user_id: str, workspace_id: str, role: str) -> dict[str, Any]:
        self.require_role(actor, {"admin"})
        workspace_id = normalize_workspace_id(workspace_id)
        role = str(role or "").lower()
        if role not in ROLES:
            raise ValueError("Papel inválido")
        if workspace_id != actor["workspace_id"]:
            raise PermissionError("Administre membros somente dentro do espaço da sessão")
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM auth_users WHERE id=? AND active=1", (user_id,)).fetchone():
                raise ValueError("Usuário não encontrado")
            db.execute(
                """INSERT INTO auth_memberships(user_id,workspace_id,role,created_at) VALUES(?,?,?,?)
                   ON CONFLICT(user_id,workspace_id) DO UPDATE SET role=excluded.role""",
                (user_id, workspace_id, role, _iso()),
            )
        self.audit(workspace_id, "membership_grant", "success", user_id=actor["user_id"], target=user_id,
                   detail={"role": role})
        return {"user_id": user_id, "workspace_id": workspace_id, "role": role}

    def issue_recovery(self, actor: dict[str, Any], username: str,
                       lifetime_minutes: int = RECOVERY_MINUTES) -> dict[str, Any]:
        self.require_role(actor, {"admin"})
        username = self.normalize_username(username)
        lifetime_minutes = max(5, min(60, int(lifetime_minutes)))
        with self.connect() as db:
            row = db.execute(
                """SELECT u.id FROM auth_users u JOIN auth_memberships m ON m.user_id=u.id
                   WHERE u.username=? AND u.active=1 AND m.workspace_id=?""",
                (username, actor["workspace_id"]),
            ).fetchone()
            if not row:
                raise ValueError("Usuário não encontrado neste espaço")
            token = secrets.token_urlsafe(32)
            expires_at = _now() + timedelta(minutes=lifetime_minutes)
            db.execute(
                """INSERT INTO auth_recovery_tokens(token_hash,user_id,workspace_id,issued_by,
                   created_at,expires_at) VALUES(?,?,?,?,?,?)""",
                (_token_hash(token), row["id"], actor["workspace_id"], actor["user_id"], _iso(), _iso(expires_at)),
            )
        self.audit(actor["workspace_id"], "recovery_issue", "success", user_id=actor["user_id"],
                   target=row["id"], detail={"lifetime_minutes": lifetime_minutes})
        return {"recovery_token": token, "expires_at": _iso(expires_at), "username": username}

    def recover(self, token: str, new_password: str) -> dict[str, Any]:
        password_hash, salt, iterations = self._password_record(new_password)
        timestamp = _iso()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                """SELECT r.*,u.username FROM auth_recovery_tokens r JOIN auth_users u ON u.id=r.user_id
                   WHERE r.token_hash=?""", (_token_hash(str(token or "")),)
            ).fetchone()
            if not row or row["used_at"] or datetime.fromisoformat(row["expires_at"]) <= _now():
                raise ValueError("Token de recuperação inválido, expirado ou já utilizado")
            db.execute(
                """UPDATE auth_users SET password_hash=?,password_salt=?,password_iterations=?,
                   password_changed_at=?,failed_attempts=0,locked_until=NULL WHERE id=?""",
                (password_hash, salt, iterations, timestamp, row["user_id"]),
            )
            db.execute("UPDATE auth_recovery_tokens SET used_at=? WHERE token_hash=?", (timestamp, row["token_hash"]))
            db.execute(
                "UPDATE auth_sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
                (timestamp, row["user_id"]),
            )
        self.audit(row["workspace_id"], "password_recovery", "success", user_id=row["user_id"])
        return {"username": row["username"], "workspace_id": row["workspace_id"], "sessions_revoked": True}

    def recent_audit(self, workspace_id: str, limit: int = 100) -> list[dict[str, Any]]:
        workspace_id = normalize_workspace_id(workspace_id)
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM auth_audit WHERE workspace_id=? ORDER BY id DESC LIMIT ?",
                (workspace_id, max(1, min(int(limit), 500))),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["detail"] = json.loads(item["detail"] or "{}")
            except json.JSONDecodeError:
                item["detail"] = {}
            result.append(item)
        return result
