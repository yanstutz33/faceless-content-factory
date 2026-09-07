from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import secrets
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from .config import Settings
from .publishing import PublishingCenter
from .store import Store
from .vault import SecureVault


SENSITIVE_WORDS = {"token", "secret", "code", "verifier", "authorization", "partner_key"}
UPLOADED_DELIVERY_STATUSES = frozenset({
    "uploaded_verification_pending", "uploaded_private", "uploaded_public", "uploaded_unlisted",
})
YOUTUBE_SCOPES = (
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
)


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: ("[redacted]" if any(word in key.lower() for word in SENSITIVE_WORDS) else _scrub(item))
                for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


class IntegrationAudit:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()

    def record(self, event: str, platform: str, detail: dict[str, Any] | None = None) -> None:
        row = {"created_at": datetime.now(UTC).isoformat(), "event": event, "platform": platform,
               "detail": _scrub(detail or {})}
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")

    def recent(self, limit: int = 40) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines()[-max(1, min(limit, 200)):]:
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    rows.append(value)
            except json.JSONDecodeError:
                continue
        return list(reversed(rows))


class DeliveryLedger:
    """Persistent pre-upload queue. It never performs platform requests by itself."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()

    def _read(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def _write(self, rows: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    @staticmethod
    def retry_after(attempt: int, now: datetime | None = None) -> str:
        base = now or datetime.now(UTC)
        seconds = min(3600, 15 * (2 ** max(0, attempt - 1)))
        return (base + timedelta(seconds=seconds)).isoformat()

    def stage(self, job_id: str, platform: str, status: str, blockers: list[str]) -> dict[str, Any]:
        with self.lock:
            rows = self._read()
            existing = next((row for row in rows if row["job_id"] == job_id and row["platform"] == platform), None)
            # Preflight can refresh readiness, but cannot undo an upload that already happened.
            if (existing and existing.get("status") in UPLOADED_DELIVERY_STATUSES
                    and status not in UPLOADED_DELIVERY_STATUSES):
                return dict(existing)
            now = datetime.now(UTC).isoformat()
            if existing:
                existing.update({"status": status, "blockers": blockers, "updated_at": now})
                row = existing
            else:
                row = {"id": secrets.token_hex(8), "job_id": job_id, "platform": platform, "status": status,
                       "attempts": 0, "blockers": blockers, "created_at": now, "updated_at": now,
                       "next_attempt_at": None}
                rows.append(row)
            self._write(rows[-500:])
            return dict(row)

    def list(self) -> list[dict[str, Any]]:
        with self.lock:
            return list(reversed(self._read()))


class IntegrationManager:
    def __init__(self, settings: Settings, store: Store, publishing: PublishingCenter):
        self.settings = settings
        self.store = store
        self.publishing = publishing
        self.vault = SecureVault(settings.data_dir / "private" / "oauth.vault")
        self.audit = IntegrationAudit(settings.data_dir / "integration-audit.jsonl")
        self.deliveries = DeliveryLedger(settings.data_dir / "deliveries.json")

    def _youtube_credentials(self) -> dict[str, Any]:
        path = Path(self.settings.youtube_client_secrets_file).expanduser() if self.settings.youtube_client_secrets_file else None
        if not path or not path.is_file():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            credentials = value.get("web") or value.get("installed") or {}
            return credentials if isinstance(credentials, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _config(self, platform: str) -> dict[str, Any]:
        if platform == "youtube":
            value = self._youtube_credentials()
            redirects = value.get("redirect_uris") or []
            return {"client_id": value.get("client_id", ""), "client_secret": value.get("client_secret", ""),
                    "redirect_uri": redirects[0] if redirects else "http://127.0.0.1:8787/api/oauth/callback/youtube"}
        if platform == "tiktok":
            return {"client_id": self.settings.tiktok_client_key, "client_secret": self.settings.tiktok_client_secret,
                    "redirect_uri": self.settings.tiktok_redirect_uri}
        if platform == "reels":
            return {"client_id": self.settings.meta_app_id, "client_secret": self.settings.meta_app_secret,
                    "redirect_uri": self.settings.meta_redirect_uri}
        if platform == "pinterest":
            return {"client_id": self.settings.pinterest_app_id,
                    "client_secret": self.settings.pinterest_app_secret,
                    "redirect_uri": self.settings.pinterest_redirect_uri}
        if platform == "shopee":
            return {"client_id": self.settings.shopee_partner_id, "client_secret": self.settings.shopee_partner_key}
        if platform == "bilibili":
            return {"client_id": "", "client_secret": ""}
        raise ValueError("Plataforma não suportada")

    def _definitions(self) -> list[dict[str, Any]]:
        return [
            {"id": "youtube", "label": "YouTube", "oauth_supported": True, "package_ready": True,
             "scope": " ".join(YOUTUBE_SCOPES),
             "output": "Vídeo longo, capa, metadados e pacote privado",
             "manual_step": "Entrar com Google, escolher o canal e autorizar uploads e métricas somente leitura"},
            {"id": "tiktok", "label": "TikTok", "oauth_supported": True, "package_ready": True,
             "scope": "user.info.basic,video.upload", "output": "Vídeo 9:16 e textos de publicação",
             "manual_step": "Entrar no TikTok e autorizar o envio para a caixa de entrada"},
            {"id": "reels", "label": "Instagram Reels", "oauth_supported": True, "package_ready": True,
             "scope": "instagram_business_basic,instagram_business_content_publish",
             "output": "Vídeo 9:16 e textos de publicação",
             "manual_step": "Entrar na Meta e escolher a conta profissional"},
            {"id": "shopee", "label": "Shopee", "oauth_supported": False, "package_ready": True,
             "scope": "partner-account-link", "output": "Brief, direitos, produto e pacote vertical validados",
             "manual_step": "Vincular a conta de parceiro e confirmar o catálogo oficial"},
            {"id": "pinterest", "label": "Pinterest", "oauth_supported": True, "package_ready": True,
             "scope": "boards:read,boards:write,pins:read,pins:write,user_accounts:read",
             "output": "Video Pin original com produto Shopee, capa, link e payload local",
             "manual_step": "Aguardar o acesso trial, cadastrar a URL de retorno e autorizar a conta Business",
             "package_only": True, "code_ready": True},
            {"id": "bilibili", "label": "Bilibili", "oauth_supported": False, "package_ready": True,
             "scope": "manual-creator-upload",
             "output": "Vídeo longo, capa neutra, metadados e legendas em chinês simplificado e inglês",
             "manual_step": "Criar a conta de creator, revisar a localização e fazer o primeiro upload",
             "package_only": True, "code_ready": True},
        ]

    def readiness(self) -> dict[str, Any]:
        platforms = []
        vault_error = ""
        for definition in self._definitions():
            config = self._config(definition["id"])
            configured = bool(config.get("client_id") and config.get("client_secret") and
                              (config.get("redirect_uri") or not definition["oauth_supported"]))
            try:
                authenticated = self.vault.available and self.vault.contains(f"token:{definition['id']}")
            except RuntimeError:
                authenticated = False
                vault_error = "O cofre precisa ser reparado antes de conectar contas"
            state = ("planned" if definition.get("planned") else "connected" if authenticated else
                     "login_required" if definition["oauth_supported"] and configured else
                     "config_required" if definition["oauth_supported"] else
                     "package_ready" if definition.get("package_only") else "config_required")
            granted_scopes: set[str] = set()
            if authenticated and definition["id"] == "youtube":
                try:
                    granted_scopes = set(str((self.vault.get("token:youtube") or {}).get("scope", "")).split())
                except RuntimeError:
                    granted_scopes = set()
            platforms.append({**definition, "connector_configured": configured, "authenticated": authenticated,
                              "state": state, "code_ready": definition.get("code_ready", not definition.get("planned", False)),
                              "upload_enabled": False,
                              "metrics_read": definition["id"] == "youtube" and set(YOUTUBE_SCOPES[1:]).issubset(granted_scopes)})
        return {"mode": "manual-safe", "automatic_upload_allowed": False,
                "configured": sum(item["connector_configured"] for item in platforms),
                "connected": sum(item["authenticated"] for item in platforms), "total": len(platforms),
                "platforms": platforms, "vault": self.vault.status(),
                "security": "Tokens ficam criptografados localmente e nunca são enviados ao frontend.",
                "vault_error": vault_error}

    def oauth_start(self, platform: str) -> dict[str, Any]:
        definition = next((item for item in self._definitions() if item["id"] == platform), None)
        if not definition or not definition["oauth_supported"]:
            raise ValueError("Esta plataforma usa vinculação própria e ainda precisa da etapa manual")
        config = self._config(platform)
        if not config.get("client_id") or not config.get("client_secret") or not config.get("redirect_uri"):
            raise ValueError("Preencha as credenciais e a URL de retorno no arquivo .env")
        if not self.vault.available:
            raise ValueError("O cofre seguro não está disponível neste sistema")
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        self.vault.set(f"pending:{state}", {"platform": platform, "verifier": verifier,
                                           "created_at": datetime.now(UTC).isoformat()})
        if platform == "youtube":
            endpoint = "https://accounts.google.com/o/oauth2/v2/auth"
            params = {"client_id": config["client_id"], "redirect_uri": config["redirect_uri"],
                      "response_type": "code", "scope": definition["scope"], "access_type": "offline",
                      "include_granted_scopes": "true", "prompt": "consent", "state": state, "code_challenge": challenge,
                      "code_challenge_method": "S256"}
        elif platform == "tiktok":
            endpoint = "https://www.tiktok.com/v2/auth/authorize/"
            params = {"client_key": config["client_id"], "redirect_uri": config["redirect_uri"],
                      "response_type": "code", "scope": definition["scope"], "state": state,
                      "code_challenge": challenge, "code_challenge_method": "S256"}
        elif platform == "pinterest":
            endpoint = "https://www.pinterest.com/oauth/"
            params = {"client_id": config["client_id"], "redirect_uri": config["redirect_uri"],
                      "response_type": "code", "scope": definition["scope"], "state": state}
        else:
            endpoint = "https://www.facebook.com/dialog/oauth"
            params = {"client_id": config["client_id"], "redirect_uri": config["redirect_uri"],
                      "response_type": "code", "scope": definition["scope"], "state": state}
        self.audit.record("oauth_started", platform, {"redirect_uri": config["redirect_uri"]})
        return {"platform": platform, "authorization_url": endpoint + "?" + urlencode(params),
                "manual_action_required": True, "upload_performed": False}

    @staticmethod
    def _post_form(url: str, form: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
        request_headers = {"Content-Type": "application/x-www-form-urlencoded", **(headers or {})}
        request = Request(url, data=urlencode(form).encode(), headers=request_headers)
        with urlopen(request, timeout=30) as response:
            value = json.loads(response.read())
        if not isinstance(value, dict):
            raise RuntimeError("Resposta inválida do provedor")
        return value

    def oauth_callback(self, platform: str, state: str, code: str) -> dict[str, Any]:
        pending = self.vault.pop(f"pending:{state}") if state else None
        if not pending or pending.get("platform") != platform or not code:
            self.audit.record("oauth_rejected", platform, {"reason": "invalid_state"})
            raise ValueError("A autorização expirou ou não pertence a esta sessão")
        try:
            created_at = datetime.fromisoformat(str(pending["created_at"]))
        except (KeyError, TypeError, ValueError):
            created_at = datetime.min.replace(tzinfo=UTC)
        if datetime.now(UTC) - created_at > timedelta(minutes=15):
            self.audit.record("oauth_rejected", platform, {"reason": "expired_state"})
            raise ValueError("A autorização expirou; inicie o login novamente")
        config = self._config(platform)
        common = {"code": code, "redirect_uri": config["redirect_uri"], "grant_type": "authorization_code"}
        if platform == "youtube":
            token = self._post_form("https://oauth2.googleapis.com/token", {**common, "client_id": config["client_id"],
                                    "client_secret": config["client_secret"], "code_verifier": pending["verifier"]})
        elif platform == "tiktok":
            token = self._post_form("https://open.tiktokapis.com/v2/oauth/token/", {**common,
                                    "client_key": config["client_id"], "client_secret": config["client_secret"],
                                    "code_verifier": pending["verifier"]})
        elif platform == "reels":
            token = self._post_form("https://graph.facebook.com/oauth/access_token", {**common,
                                    "client_id": config["client_id"], "client_secret": config["client_secret"]})
        elif platform == "pinterest":
            basic = base64.b64encode(
                f"{config['client_id']}:{config['client_secret']}".encode()
            ).decode()
            token = self._post_form("https://api.pinterest.com/v5/oauth/token", common,
                                    {"Authorization": f"Basic {basic}"})
        else:
            raise ValueError("Callback não suportado")
        if not token.get("access_token"):
            self.audit.record("oauth_failed", platform, {"response_keys": sorted(token)})
            raise RuntimeError("O provedor não devolveu um token de acesso")
        previous_token = self.vault.get(f"token:{platform}") or {}
        if previous_token.get("refresh_token") and not token.get("refresh_token"):
            token["refresh_token"] = previous_token["refresh_token"]
        self.vault.set(f"token:{platform}", {**token, "stored_at": datetime.now(UTC).isoformat()})
        self.audit.record("oauth_connected", platform, {"response_keys": sorted(token)})
        return {"connected": True, "platform": platform, "upload_enabled": False}

    def disconnect(self, platform: str) -> dict[str, Any]:
        removed = self.vault.pop(f"token:{platform}") is not None
        self.audit.record("oauth_disconnected", platform, {"removed": removed})
        return {"platform": platform, "connected": False, "removed": removed}

    def preflight(self, platform: str, job_id: str | None = None) -> dict[str, Any]:
        definition = next((item for item in self._definitions() if item["id"] == platform), None)
        if not definition:
            raise ValueError("Plataforma não suportada")
        if definition.get("planned"):
            raise ValueError("Esta integração está registrada no roadmap, mas ainda não entrou em implementação")
        if definition.get("package_only"):
            raise ValueError("O pacote Pinterest está pronto na Central de afiliados; o pré-teste online aguarda o login oficial")
        queue = self.publishing.queue()["items"]
        item = next((entry for entry in queue if entry["job_id"] == job_id), None) if job_id else next((entry for entry in queue if entry["release_ready"]), None)
        checks = []
        checks.append({"id": "package", "passed": bool(item and item["release_ready"]),
                       "detail": "Pacote de mídia completo" if item and item["release_ready"] else "Prepare e aprove um pacote completo"})
        configured = bool(self._config(platform).get("client_id") and self._config(platform).get("client_secret"))
        checks.append({"id": "config", "passed": configured, "detail": "Credenciais detectadas" if configured else "Credenciais ainda não configuradas"})
        authenticated = self.vault.available and self.vault.contains(f"token:{platform}")
        checks.append({"id": "auth", "passed": authenticated, "detail": "Conta autorizada" if authenticated else definition["manual_step"]})
        checks.append({"id": "approval", "passed": False, "detail": "Confirmação final de envio permanece manual"})
        blockers = [check["detail"] for check in checks if not check["passed"]]
        operational_blockers = [check["detail"] for check in checks if check["id"] != "approval" and not check["passed"]]
        status = "manual_approval" if not operational_blockers else "blocked_auth" if not authenticated else "blocked_package"
        delivery = self.deliveries.stage(item["job_id"] if item else job_id or "unselected", platform, status, blockers)
        result = {"platform": platform, "job_id": item["job_id"] if item else job_id, "checks": checks,
                  "blockers": blockers, "ready_after_manual_approval": not operational_blockers,
                  "network_contacted": False, "upload_performed": False, "delivery": delivery}
        self.audit.record("preflight", platform, result)
        return result

    def _youtube_access_token(self) -> str:
        token = self.vault.get("token:youtube") or {}
        access_token = str(token.get("access_token", ""))
        refresh_token = str(token.get("refresh_token", ""))
        try:
            stored_at = datetime.fromisoformat(str(token.get("stored_at", "")))
            expires_at = stored_at + timedelta(seconds=int(token.get("expires_in", 3600)))
            expired = datetime.now(UTC) >= expires_at - timedelta(minutes=2)
        except (TypeError, ValueError):
            expired = not access_token
        if not expired and access_token:
            return access_token
        if not refresh_token:
            raise ValueError("A autorização do YouTube expirou; conecte a conta novamente")
        config = self._config("youtube")
        refreshed = self._post_form("https://oauth2.googleapis.com/token", {
            "client_id": config["client_id"], "client_secret": config["client_secret"],
            "refresh_token": refresh_token, "grant_type": "refresh_token",
        })
        access_token = str(refreshed.get("access_token", ""))
        if not access_token:
            raise RuntimeError("O Google não renovou a autorização do YouTube")
        self.vault.set("token:youtube", {
            **token, **refreshed, "refresh_token": refresh_token,
            "stored_at": datetime.now(UTC).isoformat(),
        })
        self.audit.record("oauth_refreshed", "youtube", {"response_keys": sorted(refreshed)})
        return access_token

    @staticmethod
    def _authorized_json(url: str, access_token: str, *, method: str = "GET",
                         payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(url, data=data, method=method, headers=headers)
        exc: HTTPError | None = None
        for attempt in range(3):
            try:
                with urlopen(request, timeout=45) as response:
                    value = json.loads(response.read())
                break
            except HTTPError as caught:
                exc = caught
                if caught.code in {429, 500, 502, 503, 504} and attempt < 2:
                    caught.close()
                    time.sleep(1.5 * (2 ** attempt))
                    continue
                break
        if exc is not None and 'value' not in locals():
            reason = ""
            try:
                payload = json.loads(exc.read())
                error = payload.get("error") or {}
                detail = str(error.get("message") or "")
                reasons = [str(item.get("reason") or "") for item in error.get("errors") or []]
                reasons.extend(str((item.get("metadata") or {}).get("service") or "")
                               for item in error.get("details") or [])
                reason = " ".join(reasons)
            except (ValueError, AttributeError):
                detail = ""
            if "accessNotConfigured" in reason and "youtubereporting.googleapis.com" in reason:
                raise ValueError(
                    "A YouTube Reporting API está desativada no projeto Google Cloud. Ative o serviço e tente novamente."
                ) from exc
            if "accessNotConfigured" in reason or "youtubeanalytics.googleapis.com" in reason:
                raise ValueError(
                    "A YouTube Analytics API está desativada no projeto Google Cloud. Ative o serviço e tente novamente."
                ) from exc
            if exc.code in {401, 403}:
                raise ValueError(
                    "A autorização do YouTube ainda não inclui métricas. Reconecte a conta uma vez no Hub."
                ) from exc
            raise RuntimeError(f"O YouTube recusou a consulta ({exc.code})" + (f": {detail}" if detail else "")) from exc
        if not isinstance(value, dict):
            raise RuntimeError("O YouTube devolveu métricas em formato inválido")
        return value

    @staticmethod
    def _authorized_bytes(url: str, access_token: str) -> bytes:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "youtubereporting.googleapis.com":
            raise ValueError("O Google devolveu um endereço de relatório não confiável")
        request = Request(url, headers={"Authorization": f"Bearer {access_token}"})
        with urlopen(request, timeout=90) as response:
            return response.read()

    def ensure_youtube_reach_reporting(self, confirmed: bool = False) -> dict[str, Any]:
        """Create exactly one official daily reach job after explicit user confirmation."""
        if not confirmed:
            raise ValueError("Confirmação explícita para criar o relatório diário é obrigatória")
        access_token = self._youtube_access_token()
        jobs = self._authorized_json(
            "https://youtubereporting.googleapis.com/v1/jobs?includeSystemManaged=true", access_token,
        ).get("jobs") or []
        job = next((item for item in jobs if item.get("reportTypeId") == "channel_reach_basic_a1"), None)
        created = False
        if not job:
            job = self._authorized_json(
                "https://youtubereporting.googleapis.com/v1/jobs", access_token, method="POST",
                payload={"reportTypeId": "channel_reach_basic_a1", "name": "FFactory Daily Reach"},
            )
            created = True
        safe = {key: job.get(key) for key in ("id", "name", "reportTypeId", "createTime")}
        self.vault.set("youtube:reach_job", safe)
        self.audit.record("reach_reporting_ready", "youtube", {**safe, "created": created})
        return {**safe, "created": created, "status": "waiting_for_first_report"}

    def sync_youtube_reach(self, access_token: str | None = None) -> dict[str, Any]:
        """Merge the newest asynchronous thumbnail reach report into daily snapshots."""
        token = access_token or self._youtube_access_token()
        stored = self.vault.get("youtube:reach_job") or {}
        job_id = str(stored.get("id") or "")
        if not job_id:
            jobs = self._authorized_json(
                "https://youtubereporting.googleapis.com/v1/jobs?includeSystemManaged=true", token,
            ).get("jobs") or []
            job = next((item for item in jobs if item.get("reportTypeId") == "channel_reach_basic_a1"), None)
            if not job:
                return {"status": "not_configured", "reports": 0, "rows": 0}
            job_id = str(job.get("id") or "")
            self.vault.set("youtube:reach_job", {key: job.get(key) for key in
                                                ("id", "name", "reportTypeId", "createTime")})
        payload = self._authorized_json(
            f"https://youtubereporting.googleapis.com/v1/jobs/{job_id}/reports?pageSize=50", token,
        )
        reports = payload.get("reports") or []
        if not reports:
            return {"status": "waiting_for_first_report", "job_id": job_id, "reports": 0, "rows": 0}
        report = max(reports, key=lambda item: str(item.get("createTime") or ""))
        raw = self._authorized_bytes(str(report.get("downloadUrl") or ""), token)
        publications = {item["video_id"]: item["job_id"] for item in self._youtube_publications()}
        imported = 0
        for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
            video_id = str(row.get("video_id") or "")
            snapshot_date = str(row.get("date") or "")
            if video_id not in publications or not snapshot_date:
                continue
            impressions = int(float(row.get("video_thumbnail_impressions") or 0))
            ctr = float(row.get("video_thumbnail_impressions_ctr") or 0)
            self.store.merge_metrics_reach(
                publications[video_id], source="youtube_api", external_id=video_id,
                snapshot_date=snapshot_date, impressions=impressions,
                clicks=round(impressions * ctr / 100),
            )
            imported += 1
        result = {"status": "synchronized", "job_id": job_id, "reports": len(reports),
                  "rows": imported, "report_id": report.get("id")}
        self.audit.record("reach_synchronized", "youtube", result)
        return result

    def _youtube_publications(self) -> list[dict[str, str]]:
        video_by_job: dict[str, str] = {}
        for row in self.audit.recent(200):
            if row.get("platform") != "youtube":
                continue
            detail = row.get("detail") or {}
            job_id, video_id = str(detail.get("job_id") or ""), str(detail.get("video_id") or "")
            if job_id and video_id and job_id not in video_by_job:
                video_by_job[job_id] = video_id
        uploaded = {
            str(row.get("job_id")) for row in self.deliveries.list()
            if row.get("platform") == "youtube" and row.get("status") in UPLOADED_DELIVERY_STATUSES
        }
        return [{"job_id": job_id, "video_id": video_id} for job_id, video_id in video_by_job.items()
                if job_id in uploaded and self.store.get_job(job_id)]

    def youtube_metrics_status(self) -> dict[str, Any]:
        publications = self._youtube_publications()
        try:
            token = self.vault.get("token:youtube") if self.vault.available else None
        except RuntimeError:
            token = None
        granted = set(str((token or {}).get("scope", "")).split())
        required = set(YOUTUBE_SCOPES[1:])
        snapshots = self.store.metrics_sync_status()
        reach_job = self.vault.get("youtube:reach_job") if self.vault.available else None
        return {
            "provider": "youtube",
            "mode": "read_only",
            "published_videos": len(publications),
            "metrics_scope_ready": required.issubset(granted),
            "reconnect_required": bool(token) and not required.issubset(granted),
            "authenticated": bool(token),
            "reach_reporting": {"configured": bool(reach_job),
                                "status": "waiting_for_first_report" if reach_job else "not_configured"},
            **snapshots,
        }

    @staticmethod
    def _analytics_row(payload: dict[str, Any]) -> dict[str, float]:
        headers = [str(item.get("name", "")) for item in payload.get("columnHeaders", [])]
        rows = payload.get("rows") or []
        if not rows:
            return {}
        return {name: float(value or 0) for name, value in zip(headers, rows[0]) if name}

    def sync_youtube_metrics(self) -> dict[str, Any]:
        """Import read-only YouTube statistics and Analytics into idempotent daily snapshots."""
        publications = self._youtube_publications()
        if not publications:
            raise ValueError("Nenhuma publicação do YouTube está vinculada a uma produção local")
        access_token = self._youtube_access_token()
        video_ids = [item["video_id"] for item in publications]
        stats_payload = self._authorized_json(
            "https://www.googleapis.com/youtube/v3/videos?" + urlencode({
                "part": "statistics,status", "id": ",".join(video_ids),
            }), access_token,
        )
        statistics = {str(item.get("id")): item.get("statistics") or {} for item in stats_payload.get("items", [])}
        end_date = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
        synced: list[dict[str, Any]] = []
        for publication in publications:
            video_id = publication["video_id"]
            base_params = {
                "ids": "channel==MINE", "startDate": "2005-02-14", "endDate": end_date,
                "filters": f"video=={video_id}",
            }
            core = self._analytics_row(self._authorized_json(
                "https://youtubeanalytics.googleapis.com/v2/reports?" + urlencode({
                    **base_params,
                    "metrics": "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,comments,shares",
                }), access_token,
            ))
            public_stats = statistics.get(video_id, {})
            views = int(core.get("views", public_stats.get("viewCount", 0)) or 0)
            likes = int(core.get("likes", public_stats.get("likeCount", 0)) or 0)
            # Thumbnail reach belongs to YouTube's asynchronous bulk Reporting API,
            # not the targeted Analytics query used here. Keep the daily snapshot
            # honest instead of turning an unsupported query into five false errors.
            impressions = 0
            ctr = 0.0
            operation = self.store.upsert_metrics_snapshot(
                publication["job_id"], "youtube", views=views, likes=likes,
                watch_minutes=float(core.get("estimatedMinutesWatched", 0) or 0),
                impressions=impressions, clicks=round(impressions * ctr / 100),
                average_view_seconds=float(core.get("averageViewDuration", 0) or 0),
                average_view_percentage=float(core.get("averageViewPercentage", 0) or 0),
                comments=int(core.get("comments", public_stats.get("commentCount", 0)) or 0),
                shares=int(core.get("shares", 0) or 0), source="youtube_api",
                external_id=video_id, snapshot_date=end_date,
            )
            synced.append({"job_id": publication["job_id"], "video_id": video_id, "operation": operation,
                           "views": views, "impressions": impressions, "ctr": ctr})
        reach = self.sync_youtube_reach(access_token)
        result = {"provider": "youtube", "mode": "read_only", "snapshot_date": end_date,
                  "synced": synced, "count": len(synced), "warnings": [], "reach": reach,
                  "upload_performed": False, "publication_changed": False}
        self.audit.record("metrics_synchronized", "youtube", result)
        return result

    def youtube_upload_private(self, job_id: str, confirmed: bool = False) -> dict[str, Any]:
        """Upload one approved release package; public/unlisted uploads are intentionally unsupported."""
        if not confirmed:
            raise ValueError("Confirmação explícita do envio privado é obrigatória")
        previous = next((row for row in self.deliveries.list()
                         if row.get("job_id") == job_id and row.get("platform") == "youtube"), None)
        if previous and previous.get("status") in UPLOADED_DELIVERY_STATUSES:
            raise ValueError("Este vídeo já foi enviado; a proteção contra upload duplicado bloqueou a operação")
        preflight = self.preflight("youtube", job_id)
        if not preflight["ready_after_manual_approval"]:
            raise ValueError("Pré-teste do YouTube bloqueado: " + "; ".join(preflight["blockers"]))
        item = next((entry for entry in self.publishing.queue()["items"] if entry["job_id"] == job_id), None)
        if not item or not item["release_ready"]:
            raise ValueError("Pacote completo e aprovado não encontrado")
        job = self.store.get_job(job_id)
        if not job:
            raise ValueError("Produção não encontrada")
        out = Path(job["output_dir"])
        video = out / "video.mp4"
        package_path = out / "youtube-upload.json"
        if not video.is_file() or not package_path.is_file():
            raise ValueError("Vídeo ou pacote do YouTube ausente")
        package = json.loads(package_path.read_text(encoding="utf-8"))
        status = package.get("status") or {}
        if status.get("privacyStatus") != "private":
            raise ValueError("O primeiro envio aceita somente privacidade privada")
        release_audit = self.publishing.audit(job, refresh_integrity=True)
        if not release_audit["release_ready"]:
            raise ValueError("Pacote do YouTube bloqueado: " + "; ".join(release_audit["blockers"]))
        access_token = self._youtube_access_token()
        metadata = {"snippet": package.get("snippet") or {}, "status": {
            "privacyStatus": "private", "selfDeclaredMadeForKids": bool(status.get("selfDeclaredMadeForKids", False))}}
        initiate = Request(
            "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
            data=json.dumps(metadata, ensure_ascii=False).encode("utf-8"), method="POST",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json; charset=UTF-8",
                     "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(video.stat().st_size)},
        )
        with urlopen(initiate, timeout=30) as response:
            upload_url = response.headers.get("Location", "")
        if not upload_url:
            raise RuntimeError("O YouTube não iniciou a sessão de upload")
        with video.open("rb") as stream:
            upload = Request(upload_url, data=stream, method="PUT",
                             headers={"Authorization": f"Bearer {access_token}", "Content-Type": "video/mp4",
                                      "Content-Length": str(video.stat().st_size)})
            with urlopen(upload, timeout=7200) as response:
                result = json.loads(response.read())
        video_id = str(result.get("id", ""))
        if not video_id:
            raise RuntimeError("O YouTube não confirmou o vídeo enviado")
        self.deliveries.stage(job_id, "youtube", "uploaded_verification_pending", [])
        self.audit.record("uploaded_verification_pending", "youtube", {"job_id": job_id, "video_id": video_id})
        thumbnail = out / "thumbnail.jpg"
        if thumbnail.is_file():
            thumb_request = Request(
                "https://www.googleapis.com/upload/youtube/v3/thumbnails/set?uploadType=media&videoId=" + video_id,
                data=thumbnail.read_bytes(), method="POST",
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "image/jpeg"},
            )
            with urlopen(thumb_request, timeout=120) as response:
                response.read()
        remote_privacy = (result.get("status") or {}).get("privacyStatus")
        if remote_privacy != "private":
            self.audit.record("upload_privacy_unverified", "youtube", {"job_id": job_id, "video_id": video_id})
            raise RuntimeError("O envio terminou, mas a privacidade privada não pôde ser confirmada")
        delivery = self.deliveries.stage(job_id, "youtube", "uploaded_private", [])
        safe = {"platform": "youtube", "job_id": job_id, "video_id": video_id,
                "privacy_status": "private", "upload_performed": True, "delivery": delivery}
        self.audit.record("uploaded_private", "youtube", safe)
        return safe
