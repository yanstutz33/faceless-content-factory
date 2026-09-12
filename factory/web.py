from __future__ import annotations

import base64
import hmac
import json
import html
import mimetypes
import re
import socket
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .agents import PROFILES
from .autopilot import Autopilot
from .auth import LocalAuth
from .backup import BackupManager
from .commerce import CommercePackager, validate_commerce_brief
from .commercial_center import CommercialCenter
from .integrations import IntegrationManager
from .music_sources import FLOW_MUSIC_PROMPTS, flow_music_guide
from .pipeline import Pipeline, SUPPORTED_MUSIC_EXTENSIONS
from .publishing import PublishingCenter
from .nightshift import NightShift
from .operational_controls import (CrossWorkspaceClaims, CrossWorkspaceDuplicateError,
                                   OperationalLimitError, UsageLedger, UsagePolicy,
                                   operational_health)
from .store import Store
from .templates import SERIES, series_catalog
from .teams import DEFAULT_TEAM_ID, skill_catalog, team_catalog
from .workspace_lifecycle import WorkspaceLifecycle, WorkspaceLifecycleError
from .workspaces import DEFAULT_WORKSPACE_ID


class JobRunner:
    def __init__(self, pipeline: Pipeline, workers: int = 1,
                 usage: UsageLedger | None = None, workspace_id: str = "3am-shelter"):
        self.pipeline = pipeline
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="factory-worker")
        self.active: set[str] = set()
        self.lock = threading.RLock()
        self._health_at = 0.0
        self._health: dict = {}
        self.usage = usage
        self.workspace_id = workspace_id

    def submit(self, job_id: str) -> None:
        operation_id = f"render:{job_id}"
        with self.lock:
            if job_id in self.active:
                return
            if self.usage:
                try:
                    self.usage.reserve(operation_id, self.workspace_id, "render")
                    self.usage.attempt(operation_id)
                except Exception:
                    try:
                        self.usage.finish(operation_id, "cancelled")
                    except KeyError:
                        pass
                    raise
            self.active.add(job_id)
        try:
            future = self.executor.submit(self._run, job_id, operation_id)
        except Exception:
            with self.lock:
                self.active.discard(job_id)
            if self.usage:
                self.usage.finish(operation_id, "failed", error="worker submission failed")
            raise
        future.add_done_callback(lambda completed: self._finished(job_id, completed.exception()))

    def _run(self, job_id: str, operation_id: str):
        if self.usage:
            self.usage.start(operation_id)
        return self.pipeline.run(job_id)

    def _finished(self, job_id: str, error: BaseException | None = None) -> None:
        with self.lock:
            self.active.discard(job_id)
        if self.usage:
            self.usage.finish(
                f"render:{job_id}", "failed" if error else "completed",
                error=type(error).__name__ if error else None,
            )

    def snapshot(self) -> dict:
        with self.lock:
            return {"active": sorted(self.active), "worker_limit": self.executor._max_workers}

    def health(self) -> dict:
        with self.lock:
            if time.monotonic() - self._health_at < 60 and self._health:
                return {**self._health, "queue": self.snapshot()}
        diagnostics = self.pipeline.diagnostics()
        with self.lock:
            self._health = diagnostics
            self._health_at = time.monotonic()
        return {**diagnostics, "queue": self.snapshot()}

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=False)


class CalendarScheduler:
    """Turn due calendar plans into queued jobs without publishing them."""

    def __init__(self, pipeline: Pipeline, store: Store, runner: JobRunner, autopilot: Autopilot,
                 nightshift: NightShift | None = None, interval: int = 15):
        self.pipeline = pipeline
        self.store = store
        self.runner = runner
        self.autopilot = autopilot
        self.nightshift = nightshift
        self.interval = max(5, interval)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="calendar-scheduler", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
                if self.nightshift:
                    self.nightshift.run_once()
            except Exception:
                # A temporary database/tooling issue must not kill future checks.
                pass
            self._stop.wait(self.interval)

    def run_once(self) -> list[str]:
        created: list[str] = []
        self.autopilot.ensure_plan()
        autopilot_status = self.autopilot.status()
        allow_autopilot = bool(autopilot_status["enabled"]) and not autopilot_status["blocked"]
        for _ in range(5):
            item = self.store.claim_due_calendar(allow_autopilot=allow_autopilot)
            if not item:
                break
            try:
                job_id = self.pipeline.create(
                    item["topic"], item["duration"], False, True, item["profile"], priority=2,
                    team_id=item.get("team_id", DEFAULT_TEAM_ID),
                )
                self.store.link_calendar_job(item["id"], job_id)
                self.store.event(job_id, "calendar", "Produção iniciada automaticamente pelo calendário")
                self.runner.submit(job_id)
                created.append(job_id)
            except Exception as exc:
                self.store.fail_calendar_item(item["id"], str(exc))
        return created


class FactoryServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, server_address, handler, runner: JobRunner, scheduler: CalendarScheduler):
        self.runner = runner
        self.scheduler = scheduler
        super().__init__(server_address, handler)

    def server_close(self) -> None:
        self.scheduler.stop()
        self.runner.shutdown()
        super().server_close()


class Handler(SimpleHTTPRequestHandler):
    pipeline: Pipeline
    store: Store
    runner: JobRunner
    autopilot: Autopilot
    nightshift: NightShift
    publishing: PublishingCenter
    integrations: IntegrationManager
    backups: BackupManager
    commerce: CommercePackager
    commercial: CommercialCenter
    usage: UsageLedger
    claims: CrossWorkspaceClaims
    lifecycle: WorkspaceLifecycle | None
    static_dir: Path
    auth: LocalAuth | None
    workspace_id: str

    def handle_one_request(self) -> None:
        self.request_id = uuid.uuid4().hex[:12]
        super().handle_one_request()

    def log_message(self, format: str, *args) -> None:
        return

    def translate_path(self, path: str) -> str:
        clean = unquote(urlparse(path).path)
        if clean.startswith("/api/"):
            return str(self.static_dir / "missing")
        target = Path("index.html" if clean == "/" else clean.lstrip("/"))
        static_root = self.static_dir.resolve()
        candidate = (static_root / target).resolve()
        try:
            candidate.relative_to(static_root)
        except ValueError:
            return str(static_root / "missing")
        return str(candidate)

    def end_headers(self) -> None:
        self.send_header("X-Request-ID", getattr(self, "request_id", "unknown"))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; media-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_json(self, value: object, status: int = 200,
                  headers: dict[str, str] | None = None) -> None:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for name, header_value in (headers or {}).items():
            self.send_header(name, header_value)
        try:
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return

    def send_api_error(self, message: str, status: int, code: str) -> None:
        self.send_json({"error": message, "code": code, "request_id": getattr(self, "request_id", "unknown")}, status)

    def is_local_request(self) -> bool:
        peer = str(self.client_address[0]).split("%", 1)[0]
        host = urlparse(f"//{self.headers.get('Host', '')}").hostname or ""
        forwarded = self.headers.get("CF-Connecting-IP") or self.headers.get("X-Forwarded-For")
        return not forwarded and peer in {"127.0.0.1", "::1"} and host in {"127.0.0.1", "localhost", "::1"}

    def remote_authenticated(self) -> bool:
        if self.is_local_request():
            return True
        settings = self.pipeline.settings
        if not settings.remote_access or not settings.remote_username or not settings.remote_password:
            return False
        authorization = self.headers.get("Authorization", "")
        if not authorization.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(authorization[6:], validate=True).decode("utf-8")
            username, password = decoded.split(":", 1)
        except (ValueError, UnicodeDecodeError):
            return False
        return hmac.compare_digest(username, settings.remote_username) and \
            hmac.compare_digest(password, settings.remote_password)

    def require_remote_auth(self) -> bool:
        if self.remote_authenticated():
            return True
        status = HTTPStatus.UNAUTHORIZED if self.pipeline.settings.remote_access else HTTPStatus.FORBIDDEN
        body = json.dumps({
            "error": "Acesso remoto requer autenticação" if status == HTTPStatus.UNAUTHORIZED else "Acesso remoto desativado",
            "code": "AUTH_REQUIRED" if status == HTTPStatus.UNAUTHORIZED else "REMOTE_DISABLED",
            "request_id": getattr(self, "request_id", "unknown"),
        }, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        if status == HTTPStatus.UNAUTHORIZED:
            self.send_header("WWW-Authenticate", 'Basic realm="FFactory", charset="UTF-8"')
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        return False

    def session_token(self) -> str:
        try:
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            value = cookie.get("ffactory_session")
            return value.value if value else ""
        except Exception:
            return ""

    def require_local_session(self) -> dict | None:
        if self.auth is None:
            self.auth_session = None
            return {"workspace_id": self.workspace_id, "role": "personal_owner"}
        session = self.auth.session(self.session_token())
        if not session:
            self.send_api_error("Faça login para continuar", HTTPStatus.UNAUTHORIZED, "LOGIN_REQUIRED")
            return None
        if session["workspace_id"] != self.workspace_id:
            self.send_api_error(
                "A sessão pertence a outro espaço", HTTPStatus.FORBIDDEN, "WORKSPACE_MISMATCH"
            )
            return None
        self.auth_session = session
        return session

    def require_role(self, allowed: set[str]) -> bool:
        if self.auth is None:
            return True
        session = getattr(self, "auth_session", None)
        if not session:
            return False
        try:
            self.auth.require_role(session, allowed)
            return True
        except PermissionError as exc:
            self.send_api_error(str(exc), HTTPStatus.FORBIDDEN, "ROLE_FORBIDDEN")
            return False

    @staticmethod
    def mutation_roles(path: str) -> set[str]:
        admin_prefixes = (
            "/api/system/", "/api/integrations/", "/api/music-sources/lyria/",
            "/api/covers/", "/api/auth/users", "/api/auth/memberships",
            "/api/auth/recovery-tokens", "/api/workspace/lifecycle/",
        )
        if path.startswith(admin_prefixes):
            return {"admin"}
        if re.fullmatch(r"/api/jobs/[^/]+/(approve|reject|quality-audit|release-package|youtube-package)", path):
            return {"admin", "reviewer"}
        return {"admin", "editor"}

    def secure_cookie(self, token: str, *, clear: bool = False) -> str:
        parts = [f"ffactory_session={'' if clear else token}", "Path=/", "HttpOnly", "SameSite=Strict"]
        if clear:
            parts.extend(["Max-Age=0", "Expires=Thu, 01 Jan 1970 00:00:00 GMT"])
        else:
            parts.append("Max-Age=28800")
        if not self.is_local_request() or self.headers.get("X-Forwarded-Proto", "").lower() == "https":
            parts.append("Secure")
        return "; ".join(parts)

    def require_lifecycle_admin(self) -> bool:
        if (self.workspace_id == DEFAULT_WORKSPACE_ID or self.lifecycle is None
                or self.auth is None):
            self.send_api_error("Gestão de workspace indisponível", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return False
        return self.require_role({"admin"})

    @staticmethod
    def public_export(result: dict) -> dict:
        manifest = result.get("manifest") or {}
        return {
            "workspace_id": (manifest.get("workspace") or {}).get("id"),
            "request_id": result.get("request_id"),
            "archive_name": Path(str(result.get("archive", ""))).name,
            "archive_sha256": result.get("archive_sha256"),
            "file_count": len(manifest.get("files") or []),
            "idempotent": bool(result.get("idempotent")),
        }

    def controlled(self, operation_id: str, kind: str, action):
        try:
            self.usage.reserve(operation_id, self.workspace_id, kind)
            self.usage.attempt(operation_id)
            self.usage.start(operation_id)
        except Exception:
            try:
                self.usage.finish(operation_id, "cancelled")
            except KeyError:
                pass
            raise
        try:
            result = action()
        except Exception as exc:
            self.usage.finish(operation_id, "failed", error=type(exc).__name__)
            raise
        self.usage.finish(operation_id, "completed")
        return result

    def claim_delivery(self, job_id: str, platform: str) -> dict:
        job = self.store.get_job(job_id)
        if not job:
            raise ValueError("Produção não encontrada")
        manifest_path = Path(job["output_dir"]) / "artifact-manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("Manifesto íntegro obrigatório antes da entrega") from exc
        video = next((item for item in manifest.get("files", []) if item.get("name") == "video.mp4"), None)
        digest = str((video or {}).get("sha256") or "")
        if not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("Hash do vídeo ausente antes da entrega")
        return self.claims.claim(self.workspace_id, platform, f"sha256:{digest}", job_id)

    def send_html(self, value: str, status: int = 200) -> None:
        body = value.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        try:
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return

    def send_artifact(self, job_id: str, name: str) -> None:
        job = self.store.get_job(job_id)
        allowed = {"video.mp4", "motion-overlay.mp4", "thumbnail.jpg", "thumbnail-a.jpg", "thumbnail-b.jpg", "subtitles.srt", "metadata.json", "agents.json", "publication-package.json",
                   "render-report.json", "artifact-manifest.json", "asset-manifest.json", "thumbnail-design.json", "youtube-upload.json",
                   "vertical-short.mp4", "vertical-thumbnail.jpg", "vertical-package.json", "quality-gate.json",
                   "release-manifest.json", "commerce-package.json", "pinterest-package.json",
                   "bilibili-cover.jpg", "bilibili-subtitles-zh-Hans.srt", "bilibili-subtitles-en.srt",
                   "bilibili-upload.json"}
        if not job or name not in allowed:
            return self.send_json({"error": "Artefato não encontrado"}, 404)
        path = Path(job["output_dir"]) / name
        if not path.is_file():
            return self.send_json({"error": "Artefato ainda não foi gerado"}, 404)
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        size = path.stat().st_size
        start, end = 0, size - 1
        status = HTTPStatus.OK
        range_header = self.headers.get("Range")
        if range_header:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
            if not match or (not match.group(1) and not match.group(2)):
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            if match.group(1):
                start = int(match.group(1))
                end = int(match.group(2)) if match.group(2) else size - 1
            else:
                suffix = int(match.group(2))
                start = max(0, size - suffix)
            end = min(end, size - 1)
            if start > end or start >= size:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            status = HTTPStatus.PARTIAL_CONTENT
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Disposition", f'inline; filename="{path.name}"')
        self.end_headers()
        with path.open("rb") as file:
            file.seek(start)
            remaining = length
            try:
                while remaining:
                    chunk = file.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                return

    def send_music_preview(self, asset_id: int) -> None:
        # Quarantine removes a track from production, not from the listening history.
        # Keeping the preview available lets the user compare it or reverse a decision.
        track = self.store.get_music_asset_record(asset_id)
        path = Path(str(track.get("path", ""))) if track else Path()
        if not track or not path.is_file():
            return self.send_api_error("Música não encontrada", HTTPStatus.NOT_FOUND, "NOT_FOUND")
        size = path.stat().st_size
        start, end = 0, size - 1
        status = HTTPStatus.OK
        range_header = self.headers.get("Range")
        if range_header:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
            if not match or (not match.group(1) and not match.group(2)):
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            if match.group(1):
                start = int(match.group(1))
                end = int(match.group(2)) if match.group(2) else size - 1
            else:
                start = max(0, size - int(match.group(2)))
            end = min(end, size - 1)
            if start > end or start >= size:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            status = HTTPStatus.PARTIAL_CONTENT
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "audio/wav")
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with path.open("rb") as file:
            file.seek(start)
            remaining = length
            try:
                while remaining:
                    chunk = file.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                return

    def send_asset_preview(self, asset_id: int) -> None:
        asset = self.store.get_asset(asset_id)
        path = Path(str(asset.get("path", ""))) if asset else Path()
        if not asset or not path.is_file():
            return self.send_api_error("Imagem não encontrada", HTTPStatus.NOT_FOUND, "NOT_FOUND")
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "image/jpeg")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return

    def send_channel_asset(self, name: str) -> None:
        allowed = {
            "3am-shelter-avatar-800.png",
            "3am-shelter-youtube-banner-2560x1440.png",
            "3am-shelter-watermark-300.png",
            "brand-manifest.json",
        }
        if name not in allowed:
            return self.send_api_error("Arquivo de marca não encontrado", HTTPStatus.NOT_FOUND, "NOT_FOUND")
        path = self.pipeline.settings.root / "assets" / "channel" / name
        if not path.is_file():
            return self.send_api_error("Kit do canal ainda não foi gerado", HTTPStatus.NOT_FOUND, "NOT_FOUND")
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", f'inline; filename="{path.name}"')
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return

    def send_template_cover(self, name: str) -> None:
        allowed = {str(item.get("cover_asset")) for item in SERIES.values() if item.get("cover_asset")}
        if name not in allowed:
            return self.send_api_error("Capa de template não encontrada", HTTPStatus.NOT_FOUND, "NOT_FOUND")
        path = self.pipeline.settings.root / "assets" / "covers" / "nocturnal-rain-v1" / name
        if not path.is_file():
            return self.send_api_error("Capa de template indisponível", HTTPStatus.NOT_FOUND, "NOT_FOUND")
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "image/png")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or length > 1_000_000:
            raise ValueError("Requisição grande demais")
        value = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(value, dict):
            raise ValueError("O corpo da requisição precisa ser um objeto")
        return value

    def trusted_mutation(self) -> bool:
        if not self.remote_authenticated():
            return False
        if self.headers.get("Sec-Fetch-Site", "").lower() == "cross-site":
            return False
        origin = self.headers.get("Origin")
        if self.is_local_request():
            if not origin or origin == "null":
                return True
            parsed = urlparse(origin)
            expected_port = int(self.server.server_address[1])
            return parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "localhost", "::1"} and \
                (parsed.port or (443 if parsed.scheme == "https" else 80)) == expected_port
        if not origin or origin == "null":
            return False
        parsed = urlparse(origin)
        request_host = urlparse(f"//{self.headers.get('Host', '')}")
        origin_port = parsed.port or (443 if parsed.scheme == "https" else 80)
        request_port = request_host.port or (443 if parsed.scheme == "https" else 80)
        return parsed.scheme == "https" and parsed.hostname == request_host.hostname and origin_port == request_port

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/healthz":
            self.send_json({"status": "ok"})
            return
        if not self.require_remote_auth():
            return
        if path == "/api/auth/status":
            session = self.auth.session(self.session_token(), touch=False) if self.auth else None
            return self.send_json({
                "enabled": self.auth is not None, "authenticated": bool(session),
                "workspace_id": self.workspace_id,
            })
        if path == "/api/auth/session":
            session = self.require_local_session()
            if not session:
                return
            public = {key: value for key, value in session.items() if key != "csrf_hash"}
            csrf = self.auth.rotate_csrf(self.session_token()) if self.auth else None
            return self.send_json({"enabled": self.auth is not None, "session": public,
                                   "csrf_token": csrf})
        # SameSite=Strict intentionally keeps the session cookie off the OAuth
        # provider redirect. The encrypted, one-time, expiring state created by
        # the admin-only oauth-start mutation authorizes this callback instead.
        if path.startswith("/api/oauth/callback/"):
            try:
                return self._do_GET()
            except (ValueError, KeyError, json.JSONDecodeError) as exc:
                return self.send_api_error(str(exc), HTTPStatus.BAD_REQUEST, "INVALID_REQUEST")
            except Exception as exc:
                print(f"[{getattr(self, 'request_id', 'unknown')}] GET {path}: {type(exc).__name__}")
                return self.send_api_error(
                    "Falha interna. Use o código da solicitação para diagnóstico.",
                    HTTPStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR",
                )
        if path.startswith("/api/") and not self.require_local_session():
            return
        try:
            self._do_GET()
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            self.send_api_error(str(exc), HTTPStatus.BAD_REQUEST, "INVALID_REQUEST")
        except Exception as exc:
            print(f"[{getattr(self, 'request_id', 'unknown')}] GET {urlparse(self.path).path}: {type(exc).__name__}")
            self.send_api_error("Falha interna. Use o código da solicitação para diagnóstico.", HTTPStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR")

    def _do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/health":
            return self.send_json(self.runner.health())
        if path == "/api/dashboard":
            summary = self.store.summary()
            jobs = self.store.list_jobs(100)
            insights = self.store.performance_insights()
            creative = self.pipeline.creative_status()
            autopilot = self.autopilot.status()
            recommendations = []
            if summary["awaiting_approval"]:
                recommendations.append({"tone": "action", "title": "Revise os pacotes prontos", "body": f"{summary['awaiting_approval']} produção(ões) aguardando sua decisão."})
            if not summary["views"]:
                recommendations.append({"tone": "info", "title": "Feche o ciclo de aprendizado", "body": "Após publicar manualmente, registre views e tempo assistido para orientar os próximos temas."})
            elif insights:
                leader = insights[0]
                recommendations.append({
                    "tone": "info", "title": "Repita o padrão que já atraiu público",
                    "body": f"{leader['topic']} lidera com {leader['views']} views em {leader['platform']}. Crie uma variação do mesmo clima e formato.",
                })
            if creative["learning"]["evidence_count"]:
                recommendations.append({
                    "tone": "safe", "title": "Aprendizado criativo ativo",
                    "body": f"{creative['learning']['evidence_count']} resultado(s) real(is) já influenciam os próximos DNAs sem repetir cegamente o vencedor.",
                })
            if autopilot["mode"] == "paused":
                recommendations.append({"tone": "action", "title": "Piloto pausado para proteger a operação", "body": autopilot["blockers"][0]})
            elif autopilot["mode"] == "active":
                recommendations.append({"tone": "safe", "title": "Semana sendo cuidada automaticamente", "body": f"{autopilot['planned']} conteúdo(s) já estão planejados e serão repostos pelo piloto."})
            recommendations.append({"tone": "safe", "title": "Publicação protegida", "body": "O sistema prepara os arquivos, mas não envia nada automaticamente."})
            operation = self.runner.health()
            operation["controls"] = operational_health(
                self.usage, self.claims, self.integrations.credential_expiry_records(),
                workspace_id=self.workspace_id,
            )
            return self.send_json({"summary": summary, "jobs": jobs, "recommendations": recommendations,
                                   "operation": operation, "creative": creative})
        if path == "/api/insights":
            return self.send_json(self.store.performance_insights())
        if path == "/api/thumbnail-insights":
            return self.send_json(self.store.thumbnail_insights())
        if path == "/api/creative-system":
            return self.send_json(self.pipeline.creative_status())
        if path == "/api/jobs":
            limit = int(parse_qs(parsed.query).get("limit", ["100"])[0])
            return self.send_json(self.store.list_jobs(max(1, min(limit, 500))))
        if path == "/api/agents":
            return self.send_json(self.pipeline.crew.catalog())
        if path == "/api/agent-teams":
            return self.send_json({"default_team": DEFAULT_TEAM_ID, "teams": team_catalog(), "skills": skill_catalog()})
        if path == "/api/ideas":
            return self.send_json(self.pipeline.crew.ideas())
        if path == "/api/profiles":
            return self.send_json({"youtube_long": PROFILES["youtube_long"]})
        if path == "/api/series":
            return self.send_json(series_catalog())
        if path == "/api/autopilot":
            return self.send_json(self.autopilot.status())
        if path == "/api/night-shift":
            return self.send_json(self.nightshift.status())
        if path == "/api/operations/daily-report":
            return self.send_json(self.nightshift.daily_report())
        if path == "/api/operations/phase2-certification":
            return self.send_json(self.nightshift.phase2_certification())
        if path == "/api/operations/health":
            return self.send_json(operational_health(
                self.usage, self.claims, self.integrations.credential_expiry_records(),
                workspace_id=self.workspace_id,
            ))
        if path == "/api/calendar":
            return self.send_json(self.store.list_calendar())
        if path == "/api/assets":
            return self.send_json(self.store.list_assets())
        if path == "/api/music-assets":
            return self.send_json(self.store.list_music_assets())
        if path == "/api/music-sources/flow":
            return self.send_json({**flow_music_guide(), "api": self.pipeline.lyria.status()})
        if path == "/api/library/readiness":
            return self.send_json(self.pipeline.library_readiness())
        if path == "/api/publishing":
            return self.send_json(self.publishing.queue())
        if path == "/api/publishing/pilot-certification":
            return self.send_json(self.publishing.pilot_certification())
        if path == "/api/platforms":
            return self.send_json(self.integrations.readiness())
        if path == "/api/integrations/audit":
            limit = int(parse_qs(parsed.query).get("limit", ["40"])[0])
            return self.send_json(self.integrations.audit.recent(limit))
        if path == "/api/auth/audit":
            if not self.require_role({"admin"}):
                return
            limit = int(parse_qs(parsed.query).get("limit", ["100"])[0])
            return self.send_json(self.auth.recent_audit(self.workspace_id, limit) if self.auth else [])
        if path == "/api/auth/users":
            if not self.require_role({"admin"}):
                return
            return self.send_json(self.auth.list_users(self.auth_session) if self.auth else [])
        if path == "/api/workspace/lifecycle/status":
            if not self.require_lifecycle_admin():
                return
            context = self.lifecycle.registry.get(self.workspace_id)
            return self.send_json({
                "eligible": True,
                "workspace": {"id": context.id, "name": context.name, "personal": False},
                "demo": self.lifecycle.demo_status(self.workspace_id),
            })
        if path == "/api/workspace/lifecycle/delete-plan":
            if not self.require_lifecycle_admin():
                return
            plan = self.lifecycle.deletion_plan(self.workspace_id)
            return self.send_json({key: value for key, value in plan.items() if key != "workspace_root"})
        if path == "/api/integrations/deliveries":
            return self.send_json(self.integrations.deliveries.list())
        if path == "/api/integrations/youtube/metrics-status":
            return self.send_json(self.integrations.youtube_metrics_status())
        if path == "/api/system/backups":
            return self.send_json(self.backups.list())
        if path == "/api/commerce-center":
            return self.send_json(self.commercial.overview())
        if path.startswith("/api/oauth/callback/"):
            platform = path.rsplit("/", 1)[-1]
            query = parse_qs(parsed.query)
            result = self.integrations.oauth_callback(platform, query.get("state", [""])[0], query.get("code", [""])[0])
            label = html.escape(platform.title())
            return self.send_html(f"<!doctype html><meta charset='utf-8'><title>Conta conectada</title><style>body{{font:16px system-ui;background:#09111f;color:#eef3fb;display:grid;place-items:center;min-height:100vh}}main{{max-width:520px;padding:32px;background:#101a2b;border-radius:18px}}a{{color:#77e0bd}}</style><main><h1>{label} conectado</h1><p>A autorização foi guardada no cofre local. Nenhum conteúdo foi publicado.</p><a href='/#connections'>Voltar ao Studio</a></main>")
        parts = path.strip("/").split("/")
        if len(parts) == 4 and parts[:2] == ["api", "assets"] and parts[3] == "preview":
            return self.send_asset_preview(int(parts[2]))
        if len(parts) == 4 and parts[:2] == ["api", "music-assets"] and parts[3] == "preview":
            return self.send_music_preview(int(parts[2]))
        if len(parts) == 3 and parts[:2] == ["api", "channel-assets"]:
            return self.send_channel_asset(parts[2])
        if len(parts) == 3 and parts[:2] == ["api", "template-covers"]:
            return self.send_template_cover(parts[2])
        if len(parts) == 5 and parts[:2] == ["api", "jobs"] and parts[3] == "artifacts":
            return self.send_artifact(parts[2], parts[4])
        if len(parts) == 3 and parts[:2] == ["api", "jobs"]:
            job = self.store.get_job(parts[2])
            return self.send_json(job or {"error": "Produção não encontrada"}, 200 if job else 404)
        if path.startswith("/api/"):
            return self.send_api_error("Rota não encontrada", HTTPStatus.NOT_FOUND, "NOT_FOUND")
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if not self.require_remote_auth():
            return
        if not self.trusted_mutation():
            return self.send_api_error("Requisição externa bloqueada", HTTPStatus.FORBIDDEN, "UNTRUSTED_ORIGIN")
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            return self.send_api_error("Envie a requisição como JSON", HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                                       "JSON_REQUIRED")
        try:
            data = self.read_json()
            if path == "/api/auth/login":
                if self.auth is None:
                    return self.send_api_error("Contas locais não estão ativadas", HTTPStatus.NOT_FOUND,
                                               "AUTH_DISABLED")
                requested_workspace = str(data.get("workspace_id") or self.workspace_id)
                if requested_workspace != self.workspace_id:
                    return self.send_api_error(
                        "Abra a instância correspondente ao espaço solicitado",
                        HTTPStatus.CONFLICT, "WORKSPACE_PROCESS_REQUIRED",
                    )
                result = self.auth.login(str(data.get("username", "")), str(data.get("password", "")),
                                         requested_workspace)
                raw_token = result.pop("session_token")
                return self.send_json(
                    result, headers={"Set-Cookie": self.secure_cookie(raw_token)}
                )
            if path == "/api/auth/recover":
                if self.auth is None:
                    return self.send_api_error("Contas locais não estão ativadas", HTTPStatus.NOT_FOUND,
                                               "AUTH_DISABLED")
                result = self.auth.recover(str(data.get("recovery_token", "")),
                                           str(data.get("new_password", "")))
                return self.send_json(result)
            session = self.require_local_session()
            if not session:
                return
            if self.auth is not None and not self.auth.csrf_valid(
                    session, self.headers.get("X-CSRF-Token", "")):
                return self.send_api_error("Confirmação de sessão ausente ou inválida", HTTPStatus.FORBIDDEN,
                                           "CSRF_REQUIRED")
            if path == "/api/auth/logout":
                if self.auth:
                    self.auth.logout(self.session_token())
                return self.send_json(
                    {"logged_out": True}, headers={"Set-Cookie": self.secure_cookie("", clear=True)}
                )
            if path == "/api/auth/workspace":
                requested = str(data.get("workspace_id", ""))
                membership = next(
                    (item for item in session.get("memberships", []) if item["workspace_id"] == requested), None
                )
                if not membership:
                    return self.send_api_error("Sem acesso ao espaço solicitado", HTTPStatus.FORBIDDEN,
                                               "WORKSPACE_FORBIDDEN")
                if requested != self.workspace_id:
                    return self.send_api_error(
                        "O espaço é autorizado, mas exige abrir sua instância isolada",
                        HTTPStatus.CONFLICT, "WORKSPACE_PROCESS_REQUIRED",
                    )
                selected = self.auth.select_workspace(self.session_token(), requested) if self.auth else session
                return self.send_json({
                    "workspace_id": selected["workspace_id"], "role": selected["role"]
                })
            if not self.require_role(self.mutation_roles(path)):
                return
            if path == "/api/auth/users":
                return self.send_json(self.auth.create_user(
                    session, str(data.get("username", "")), str(data.get("password", "")),
                    str(data.get("role", "")),
                ), HTTPStatus.CREATED)
            if path == "/api/auth/memberships":
                return self.send_json(self.auth.grant_workspace(
                    session, str(data.get("user_id", "")), str(data.get("workspace_id", "")),
                    str(data.get("role", "")),
                ))
            if path == "/api/auth/recovery-tokens":
                return self.send_json(self.auth.issue_recovery(
                    session, str(data.get("username", "")), int(data.get("lifetime_minutes", 15)),
                ), HTTPStatus.CREATED)
            if path.startswith("/api/workspace/lifecycle/"):
                if not self.require_lifecycle_admin():
                    return
                action = path.rsplit("/", 1)[-1]
                if action == "export":
                    result = self.lifecycle.export_workspace(
                        self.workspace_id, request_id=str(data.get("request_id") or "") or None
                    )
                    self.auth.audit(self.workspace_id, "workspace_export", "success",
                                    user_id=session["user_id"], detail={"request_id": result["request_id"]})
                    return self.send_json(self.public_export(result), HTTPStatus.CREATED)
                if action == "demo-seed":
                    result = self.lifecycle.seed_demo(self.workspace_id)
                    self.auth.audit(self.workspace_id, "workspace_demo_seed", "success",
                                    user_id=session["user_id"])
                    return self.send_json(result, HTTPStatus.CREATED)
                if action == "demo-reset":
                    result = self.lifecycle.reset_demo(self.workspace_id)
                    self.auth.audit(self.workspace_id, "workspace_demo_reset", "success",
                                    user_id=session["user_id"])
                    return self.send_json(result)
                if action == "delete":
                    if self.runner.snapshot()["active"]:
                        return self.send_api_error(
                            "Finalize as produções ativas antes de excluir o workspace",
                            HTTPStatus.CONFLICT, "WORKSPACE_BUSY",
                        )
                    password = str(data.get("password") or "")
                    if not password:
                        return self.send_api_error(
                            "Confirme sua senha atual para excluir o workspace",
                            HTTPStatus.UNAUTHORIZED, "REAUTH_REQUIRED",
                        )
                    try:
                        refreshed = self.auth.reauthenticate(self.session_token(), password)
                    except ValueError:
                        return self.send_api_error(
                            "Reautenticação inválida", HTTPStatus.UNAUTHORIZED, "REAUTH_FAILED"
                        )
                    if not self.auth.recently_reauthenticated(refreshed):
                        return self.send_api_error(
                            "Reautenticação recente obrigatória", HTTPStatus.UNAUTHORIZED,
                            "REAUTH_REQUIRED",
                        )
                    self.server.scheduler.stop()
                    try:
                        result = self.lifecycle.delete_workspace(
                            self.workspace_id, confirmation=str(data.get("confirmation") or "")
                        )
                        self.auth.audit(self.workspace_id, "workspace_delete", "success",
                                        user_id=session["user_id"])
                        public = {
                            "workspace_id": result["workspace_id"],
                            "deleted_at": result.get("deleted_at"),
                            "backup_name": Path(str(result.get("backup_archive", ""))).name,
                            "backup_sha256": result.get("backup_sha256"),
                            "already_deleted": bool(result.get("already_deleted")),
                        }
                        self.send_json(public)
                    finally:
                        threading.Thread(target=self.server.shutdown,
                                         name="workspace-delete-shutdown", daemon=True).start()
                    return
                return self.send_api_error("Rota não encontrada", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            if path == "/api/system/backup":
                return self.send_json(self.backups.create(), HTTPStatus.CREATED)
            if path == "/api/commerce/validate":
                return self.send_json(validate_commerce_brief(data))
            if path == "/api/commerce/package":
                return self.send_json(self.commerce.prepare(str(data.get("job_id", "")), data.get("product") or {},
                                                            int(data.get("duration", 30))), HTTPStatus.CREATED)
            if path == "/api/commerce-center/products":
                return self.send_json(self.commercial.create_product(data), HTTPStatus.CREATED)
            if path == "/api/commerce-center/campaigns":
                return self.send_json(self.commercial.create_campaign(data), HTTPStatus.CREATED)
            commerce_parts = path.strip("/").split("/")
            if len(commerce_parts) == 5 and commerce_parts[:3] == ["api", "commerce-center", "campaigns"]:
                campaign_id, action = commerce_parts[3], commerce_parts[4]
                if action == "metrics":
                    return self.send_json(self.commercial.record_metrics(campaign_id, data))
                if action == "package":
                    return self.send_json(self.commercial.prepare_campaign(campaign_id, int(data.get("duration", 30))),
                                          HTTPStatus.CREATED)
                if action == "pinterest-package":
                    return self.send_json(self.commercial.prepare_pinterest(campaign_id, data), HTTPStatus.CREATED)
            integration_parts = path.strip("/").split("/")
            if len(integration_parts) == 4 and integration_parts[:2] == ["api", "integrations"]:
                platform, action = integration_parts[2], integration_parts[3]
                if action == "oauth-start":
                    return self.send_json(self.integrations.oauth_start(platform))
                if action == "disconnect":
                    return self.send_json(self.integrations.disconnect(platform))
                if action == "preflight":
                    return self.send_json(self.integrations.preflight(platform, data.get("job_id")))
                if action == "upload-private" and platform == "youtube":
                    job_id = str(data.get("job_id", ""))
                    return self.send_json(self.controlled(
                        f"delivery:youtube:{job_id}", "delivery",
                        lambda: (self.claim_delivery(job_id, "youtube"),
                                 self.integrations.youtube_upload_private(
                                     job_id, data.get("confirmed") is True))[1],
                    ))
                if action == "sync-metrics" and platform == "youtube":
                    day = datetime.now().date().isoformat()
                    return self.send_json(self.controlled(
                        f"metrics:{self.workspace_id}:{day}", "metrics",
                        self.integrations.sync_youtube_metrics,
                    ))
            if path == "/api/jobs":
                asset_ids = [int(value) for value in data.get("asset_ids", [])]
                selected_assets = self.store.get_assets(asset_ids)
                if len(selected_assets) != len(set(asset_ids)):
                    raise ValueError("Um ou mais assets não estão aprovados")
                job_id = self.pipeline.create(
                    data.get("topic", "Biblioteca chuvosa à noite"), 1800 if int(data.get("duration", 3600)) < 3600 else 3600,
                    bool(data.get("narration", False)), bool(data.get("subtitles", True)),
                    "youtube_long", data.get("source_asset") or None, int(data.get("priority", 2)),
                    selected_assets, data.get("team_id", DEFAULT_TEAM_ID),
                    bool(data.get("source_asset_rights_confirmed", False)),
                    int(data["music_asset_id"]) if data.get("music_asset_id") else None,
                )
                self.runner.submit(job_id)
                return self.send_json(self.store.get_job(job_id), HTTPStatus.ACCEPTED)
            if path == "/api/batches":
                series = SERIES.get(data.get("series_id", ""), {})
                if not series or series.get("profile") != "youtube_long":
                    raise ValueError("Selecione uma série de vídeos longos do YouTube")
                topics = data.get("topics") or series.get("topics") or []
                if not isinstance(topics, list) or not topics:
                    raise ValueError("Informe ao menos um tema para o lote")
                if len(topics) > 20:
                    raise ValueError("O lote aceita até 20 produções")
                created = []
                for topic in topics:
                    requested_duration = int(data.get("duration") or series.get("duration", 3600))
                    job_id = self.pipeline.create(str(topic), 1800 if requested_duration < 3600 else 3600,
                                                  bool(data.get("narration", series.get("narration", False))),
                                                  bool(data.get("subtitles", True)), "youtube_long",
                                                  None, int(data.get("priority", 1)), None,
                                                  data.get("team_id") or series.get("team_id", DEFAULT_TEAM_ID))
                    self.runner.submit(job_id)
                    created.append(job_id)
                return self.send_json({"created": created, "count": len(created)}, HTTPStatus.ACCEPTED)
            if path == "/api/calendar":
                profile = "youtube_long"
                scheduled_for = str(data.get("scheduled_for", ""))
                try:
                    datetime.fromisoformat(scheduled_for)
                except ValueError as exc:
                    raise ValueError("Data e hora inválidas") from exc
                item_id = self.store.add_calendar_item(str(data.get("topic", "")), data.get("series_id"),
                                                       profile, 1800 if int(data.get("duration", 3600)) < 3600 else 3600,
                                                       scheduled_for, "manual",
                                                       data.get("team_id") or SERIES.get(str(data.get("series_id", "")), {}).get("team_id", DEFAULT_TEAM_ID))
                return self.send_json({"id": item_id}, HTTPStatus.CREATED)
            if path == "/api/autopilot":
                status = self.autopilot.configure(data)
                created = self.autopilot.ensure_plan(force=bool(status["enabled"]))
                return self.send_json({**self.autopilot.status(), "created": created})
            if path == "/api/autopilot/plan":
                created = self.autopilot.ensure_plan(force=True)
                return self.send_json({"created": created, "count": len(created), "status": self.autopilot.status()})
            if path == "/api/night-shift":
                return self.send_json(self.nightshift.configure(data))
            if path == "/api/night-shift/run":
                return self.send_json(self.nightshift.run_once(force=True), HTTPStatus.ACCEPTED)
            if path == "/api/assets":
                asset_path = Path(str(data.get("path", ""))).expanduser().resolve()
                if not asset_path.is_file() or asset_path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                    raise ValueError("Selecione uma imagem JPG, PNG ou WebP existente")
                if not bool(data.get("rights_confirmed", False)):
                    raise ValueError("Confirme os direitos de uso antes de aprovar o asset")
                asset_id = self.store.add_asset(str(data.get("name", asset_path.stem)), str(asset_path),
                                                str(data.get("license_type", "")), data.get("source_url"),
                                                data.get("notes"), True)
                return self.send_json({"id": asset_id}, HTTPStatus.CREATED)
            if path == "/api/music-assets":
                source = Path(str(data.get("path", ""))).expanduser().resolve()
                if not bool(data.get("rights_confirmed", False)):
                    raise ValueError("Confirme os direitos comerciais das músicas antes de importar")
                license_type = str(data.get("license_type", ""))
                if license_type not in {"original", "commercial_license", "public_domain", "cc0", "provider_generated"}:
                    raise ValueError("Licença musical inválida")
                if source.is_file():
                    candidates = [source]
                elif source.is_dir():
                    candidates = sorted(path for path in source.rglob("*")
                                        if path.is_file() and path.suffix.lower() in SUPPORTED_MUSIC_EXTENSIONS)[:200]
                else:
                    raise ValueError("Informe um arquivo ou uma pasta de músicas existente")
                if not candidates or any(path.suffix.lower() not in SUPPORTED_MUSIC_EXTENSIONS for path in candidates):
                    raise ValueError("Nenhuma música WAV, MP3, M4A, AAC, FLAC, OGG ou OPUS foi encontrada")
                imported = []
                for candidate in candidates:
                    self.pipeline.command([self.pipeline.settings.ffmpeg, "-v", "error", "-t", "1", "-i",
                                           str(candidate), "-f", "null", "-"])
                    name = str(data.get("name") or candidate.stem) if len(candidates) == 1 else candidate.stem
                    imported.append(self.store.add_music_asset(name, str(candidate), license_type,
                                                               data.get("source_url"), data.get("notes"), True))
                archived = 0
                if imported and bool(data.get("replace_synthetic_catalog", False)):
                    archived = self.store.archive_music_assets_by_source(
                        "generated-locally://faceless-factory/original-lofi-v1"
                    )
                return self.send_json({"ids": imported, "count": len(imported), "archived": archived},
                                      HTTPStatus.CREATED)
            music_review_parts = path.strip("/").split("/")
            if (len(music_review_parts) == 4 and music_review_parts[:2] == ["api", "music-assets"]
                    and music_review_parts[3] == "review"):
                return self.send_json(
                    self.store.review_music_asset(int(music_review_parts[2]), str(data.get("decision", "")))
                )
            if path == "/api/music-sources/lyria/configure":
                return self.send_json(self.pipeline.lyria.configure(str(data.get("api_key", ""))))
            if path == "/api/music-sources/lyria/disconnect":
                return self.send_json(self.pipeline.lyria.disconnect())
            if path == "/api/music-sources/lyria/generate":
                return self.send_json(self.pipeline.lyria.generate(
                    str(data.get("name", "Faixa Lyria")), str(data.get("prompt", "")),
                    str(data.get("model", "")), bool(data.get("rights_confirmed", False)),
                ), HTTPStatus.CREATED)
            if path == "/api/music-sources/lyria/generate-batch":
                return self.send_json(self.pipeline.lyria.generate_batch(
                    list(FLOW_MUSIC_PROMPTS), str(data.get("model", "")),
                    bool(data.get("rights_confirmed", False)), int(data.get("count", 12)),
                ), HTTPStatus.CREATED)
            if path == "/api/music-assets/bootstrap":
                return self.send_json(self.pipeline.bootstrap_original_music_catalog(), HTTPStatus.CREATED)
            if path == "/api/covers/migrate":
                return self.send_json(self.pipeline.synchronize_video_visuals())
            if path.startswith("/api/calendar/") and path.endswith("/produce"):
                item_id = int(path.split("/")[-2])
                item = self.store.claim_calendar_item(item_id)
                if not item:
                    raise ValueError("Item já iniciado ou não encontrado")
                try:
                    job_id = self.pipeline.create(item["topic"], item["duration"], False, True, item["profile"],
                                                  team_id=item.get("team_id", DEFAULT_TEAM_ID))
                    self.store.link_calendar_job(item_id, job_id)
                    self.runner.submit(job_id)
                    return self.send_json({"job_id": job_id}, HTTPStatus.ACCEPTED)
                except Exception as exc:
                    self.store.fail_calendar_item(item_id, str(exc))
                    raise
            parts = path.strip("/").split("/")
            if len(parts) == 4 and parts[:2] == ["api", "jobs"]:
                job_id, action = parts[2], parts[3]
                if action == "approve":
                    self.pipeline.approve(job_id)
                elif action == "reject":
                    self.pipeline.reject(job_id, str(data.get("reason", "Revisão solicitada")))
                elif action == "retry":
                    job = self.store.get_job(job_id)
                    if not job or job["status"] not in {"failed", "rejected"}:
                        raise ValueError("Somente falhas ou revisões podem ser executadas novamente")
                    self.store.update(job_id, "queued", job["metadata"], progress=0)
                    self.store.event(job_id, "queued", "Nova execução solicitada")
                    self.runner.submit(job_id)
                elif action == "metrics":
                    self.store.add_metrics(job_id, data.get("platform", "youtube"), int(data.get("views", 0)),
                                           int(data.get("likes", 0)), float(data.get("watch_minutes", 0)),
                                           int(data.get("impressions", 0)), int(data.get("clicks", 0)),
                                           float(data.get("average_view_seconds", 0)), str(data.get("thumbnail_variant", "a")),
                                           int(data.get("conversions", 0)), float(data.get("revenue", 0)))
                elif action == "thumbnail":
                    self.pipeline.select_thumbnail(job_id, str(data.get("variant", "")))
                elif action == "youtube-package":
                    return self.send_json(self.pipeline.prepare_youtube_package(job_id))
                elif action == "vertical-package":
                    return self.send_json(self.pipeline.prepare_vertical_package(job_id, int(data.get("duration", 30))))
                elif action == "smart-cuts":
                    durations = data.get("durations") or [15, 30, 60]
                    if not isinstance(durations, list):
                        raise ValueError("As durações dos cortes devem ser uma lista")
                    return self.send_json(self.pipeline.prepare_smart_cuts(job_id, durations))
                elif action == "bilibili-package":
                    return self.send_json(self.publishing.bilibili.prepare(job_id))
                elif action == "quality-audit":
                    return self.send_json(self.pipeline.audit_job(job_id))
                elif action == "release-package":
                    return self.send_json(self.publishing.prepare(job_id, int(data.get("vertical_duration", 30))))
                else:
                    return self.send_json({"error": "Ação não encontrada"}, 404)
                return self.send_json(self.store.get_job(job_id))
            return self.send_api_error("Rota não encontrada", HTTPStatus.NOT_FOUND, "NOT_FOUND")
        except PermissionError as exc:
            return self.send_api_error(str(exc), HTTPStatus.FORBIDDEN, "FORBIDDEN")
        except CrossWorkspaceDuplicateError as exc:
            return self.send_api_error(str(exc), HTTPStatus.CONFLICT, "DUPLICATE_DELIVERY")
        except OperationalLimitError as exc:
            return self.send_api_error(str(exc), HTTPStatus.TOO_MANY_REQUESTS, "OPERATION_LIMIT")
        except WorkspaceLifecycleError as exc:
            return self.send_api_error(str(exc), HTTPStatus.CONFLICT, "WORKSPACE_LIFECYCLE_ERROR")
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            return self.send_api_error(str(exc), HTTPStatus.BAD_REQUEST, "INVALID_REQUEST")
        except Exception as exc:
            print(f"[{getattr(self, 'request_id', 'unknown')}] POST {urlparse(self.path).path}: {type(exc).__name__}")
            return self.send_api_error("Falha interna. Use o código da solicitação para diagnóstico.", HTTPStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR")

    def _method_not_allowed(self) -> None:
        if not self.require_remote_auth():
            return
        self.send_api_error("Método não permitido para esta rota", HTTPStatus.METHOD_NOT_ALLOWED, "METHOD_NOT_ALLOWED")

    def do_HEAD(self) -> None:
        if not self.require_remote_auth():
            return
        super().do_HEAD()

    do_PUT = _method_not_allowed
    do_PATCH = _method_not_allowed
    do_DELETE = _method_not_allowed


def create_server(pipeline: Pipeline, store: Store, host: str, port: int, static_dir: Path,
                  *, auth: LocalAuth | None = None, workspace_id: str | None = None,
                  operational_dir: Path | None = None,
                  lifecycle: WorkspaceLifecycle | None = None) -> ThreadingHTTPServer:
    if pipeline.settings.remote_access and (
            not pipeline.settings.remote_username or len(pipeline.settings.remote_password) < 16):
        raise ValueError("Acesso remoto exige usuário e senha com pelo menos 16 caracteres")
    workspace_id = workspace_id or pipeline.settings.workspace_id
    if pipeline.settings.local_auth:
        if auth is None:
            raise ValueError("Contas locais ativadas sem uma base de autenticação")
        if not auth.has_admin(workspace_id):
            raise ValueError("Crie o primeiro administrador antes de ativar contas locais")
    else:
        auth = None
    operational_dir = operational_dir or pipeline.settings.data_dir / "private"
    controls_database = operational_dir / "operational-controls.sqlite3"
    usage = UsageLedger(controls_database, UsagePolicy(
        max_active=pipeline.settings.workers,
        max_queue=max(12, pipeline.settings.autopilot_max_review),
        max_attempts=3,
        max_metric_syncs_per_day=1,
    ))
    claims = CrossWorkspaceClaims(controls_database)
    usage.recover_interrupted(workspace_id)
    runner = JobRunner(pipeline, pipeline.settings.workers, usage, workspace_id)
    autopilot = Autopilot(pipeline.settings, store)
    nightshift = NightShift(pipeline, store, runner, autopilot)
    publishing = PublishingCenter(pipeline, store)
    integrations = IntegrationManager(pipeline.settings, store, publishing)
    backups = BackupManager(store.db_path, pipeline.settings.data_dir / "backups", pipeline.settings.backup_keep)
    commerce = CommercePackager(pipeline, store)
    commercial = CommercialCenter(store, commerce)
    scheduler = CalendarScheduler(pipeline, store, runner, autopilot, nightshift, pipeline.settings.calendar_poll_seconds)
    handler = type("FactoryHandler", (Handler,), {"pipeline": pipeline, "store": store, "runner": runner,
                                                   "autopilot": autopilot, "nightshift": nightshift,
                                                   "publishing": publishing, "integrations": integrations,
                                                   "backups": backups, "commerce": commerce, "commercial": commercial,
                                                   "usage": usage, "claims": claims,
                                                   "static_dir": static_dir, "auth": auth, "lifecycle": lifecycle,
                                                   "workspace_id": workspace_id})
    server = FactoryServer((host, port), handler, runner, scheduler)
    backups.ensure_daily()
    store.recover_interrupted()
    for job_id in store.queued_jobs():
        runner.submit(job_id)
    scheduler.start()
    return server


def serve(pipeline: Pipeline, store: Store, host: str, port: int, static_dir: Path,
          *, auth: LocalAuth | None = None, workspace_id: str | None = None,
          operational_dir: Path | None = None,
          lifecycle: WorkspaceLifecycle | None = None) -> None:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            print(f"Faceless Factory já está ativo em http://{host}:{port}")
            return
    except OSError:
        pass
    server = create_server(pipeline, store, host, port, static_dir,
                           auth=auth, workspace_id=workspace_id,
                           operational_dir=operational_dir, lifecycle=lifecycle)
    print(f"Faceless Factory: http://{host}:{port}")
    print("Publicação automática: DESATIVADA")
    try:
        server.serve_forever()
    finally:
        server.server_close()
