from __future__ import annotations

import json
import mimetypes
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .agents import PROFILES
from .pipeline import Pipeline
from .store import Store
from .templates import SERIES, series_catalog


class JobRunner:
    def __init__(self, pipeline: Pipeline, workers: int = 1):
        self.pipeline = pipeline
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="factory-worker")
        self.active: set[str] = set()
        self.lock = threading.RLock()
        self._health_at = 0.0
        self._health: dict = {}

    def submit(self, job_id: str) -> None:
        with self.lock:
            if job_id in self.active:
                return
            self.active.add(job_id)
        future = self.executor.submit(self.pipeline.run, job_id)
        future.add_done_callback(lambda _future: self._finished(job_id))

    def _finished(self, job_id: str) -> None:
        with self.lock:
            self.active.discard(job_id)

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

    def __init__(self, pipeline: Pipeline, store: Store, runner: JobRunner, interval: int = 15):
        self.pipeline = pipeline
        self.store = store
        self.runner = runner
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
            except Exception:
                # A temporary database/tooling issue must not kill future checks.
                pass
            self._stop.wait(self.interval)

    def run_once(self) -> list[str]:
        created: list[str] = []
        for _ in range(5):
            item = self.store.claim_due_calendar()
            if not item:
                break
            try:
                job_id = self.pipeline.create(
                    item["topic"], item["duration"], False, True, item["profile"], priority=2
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
    static_dir: Path

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
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; media-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_json(self, value: object, status: int = 200) -> None:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_artifact(self, job_id: str, name: str) -> None:
        job = self.store.get_job(job_id)
        allowed = {"video.mp4", "thumbnail.jpg", "thumbnail-a.jpg", "thumbnail-b.jpg", "subtitles.srt", "metadata.json", "agents.json", "publication-package.json",
                   "render-report.json", "artifact-manifest.json", "asset-manifest.json", "thumbnail-design.json"}
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

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or length > 1_000_000:
            raise ValueError("Requisição grande demais")
        value = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(value, dict):
            raise ValueError("O corpo da requisição precisa ser um objeto")
        return value

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/health":
            return self.send_json(self.runner.health())
        if path == "/api/dashboard":
            summary = self.store.summary()
            jobs = self.store.list_jobs(100)
            insights = self.store.performance_insights()
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
            recommendations.append({"tone": "safe", "title": "Publicação protegida", "body": "O sistema prepara os arquivos, mas não envia nada automaticamente."})
            return self.send_json({"summary": summary, "jobs": jobs, "recommendations": recommendations,
                                   "operation": self.runner.health()})
        if path == "/api/insights":
            return self.send_json(self.store.performance_insights())
        if path == "/api/jobs":
            limit = int(parse_qs(parsed.query).get("limit", ["100"])[0])
            return self.send_json(self.store.list_jobs(max(1, min(limit, 500))))
        if path == "/api/agents":
            return self.send_json(self.pipeline.crew.catalog())
        if path == "/api/ideas":
            return self.send_json(self.pipeline.crew.ideas())
        if path == "/api/profiles":
            return self.send_json(PROFILES)
        if path == "/api/series":
            return self.send_json(series_catalog())
        if path == "/api/calendar":
            return self.send_json(self.store.list_calendar())
        if path == "/api/assets":
            return self.send_json(self.store.list_assets())
        parts = path.strip("/").split("/")
        if len(parts) == 5 and parts[:2] == ["api", "jobs"] and parts[3] == "artifacts":
            return self.send_artifact(parts[2], parts[4])
        if len(parts) == 3 and parts[:2] == ["api", "jobs"]:
            job = self.store.get_job(parts[2])
            return self.send_json(job or {"error": "Produção não encontrada"}, 200 if job else 404)
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            data = self.read_json()
            if path == "/api/jobs":
                asset_ids = [int(value) for value in data.get("asset_ids", [])]
                selected_assets = self.store.get_assets(asset_ids)
                if len(selected_assets) != len(set(asset_ids)):
                    raise ValueError("Um ou mais assets não estão aprovados")
                job_id = self.pipeline.create(
                    data.get("topic", "Biblioteca chuvosa à noite"), int(data.get("duration", 30)),
                    bool(data.get("narration", False)), bool(data.get("subtitles", True)),
                    data.get("profile", "youtube_long"), data.get("source_asset") or None, int(data.get("priority", 2)),
                    selected_assets,
                )
                self.runner.submit(job_id)
                return self.send_json(self.store.get_job(job_id), HTTPStatus.ACCEPTED)
            if path == "/api/batches":
                series = SERIES.get(data.get("series_id", ""), {})
                topics = data.get("topics") or series.get("topics") or []
                if not isinstance(topics, list) or not topics:
                    raise ValueError("Informe ao menos um tema para o lote")
                if len(topics) > 20:
                    raise ValueError("O lote aceita até 20 produções")
                created = []
                for topic in topics:
                    job_id = self.pipeline.create(str(topic), int(data.get("duration") or series.get("duration", 30)),
                                                  bool(data.get("narration", series.get("narration", False))),
                                                  bool(data.get("subtitles", True)), data.get("profile") or series.get("profile", "youtube_long"),
                                                  None, int(data.get("priority", 1)))
                    self.runner.submit(job_id)
                    created.append(job_id)
                return self.send_json({"created": created, "count": len(created)}, HTTPStatus.ACCEPTED)
            if path == "/api/calendar":
                profile = str(data.get("profile", "youtube_long"))
                if profile not in PROFILES:
                    raise ValueError("Perfil de saída inválido")
                scheduled_for = str(data.get("scheduled_for", ""))
                try:
                    datetime.fromisoformat(scheduled_for)
                except ValueError as exc:
                    raise ValueError("Data e hora inválidas") from exc
                item_id = self.store.add_calendar_item(str(data.get("topic", "")), data.get("series_id"),
                                                       profile, max(5, min(int(data.get("duration", 1800)), PROFILES[profile]["max_duration"])),
                                                       scheduled_for)
                return self.send_json({"id": item_id}, HTTPStatus.CREATED)
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
            if path.startswith("/api/calendar/") and path.endswith("/produce"):
                item_id = int(path.split("/")[-2])
                item = self.store.claim_calendar_item(item_id)
                if not item:
                    raise ValueError("Item já iniciado ou não encontrado")
                try:
                    job_id = self.pipeline.create(item["topic"], item["duration"], False, True, item["profile"])
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
                                           int(data.get("likes", 0)), float(data.get("watch_minutes", 0)))
                elif action == "thumbnail":
                    self.pipeline.select_thumbnail(job_id, str(data.get("variant", "")))
                else:
                    return self.send_json({"error": "Ação não encontrada"}, 404)
                return self.send_json(self.store.get_job(job_id))
            return self.send_json({"error": "Rota não encontrada"}, 404)
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            return self.send_json({"error": str(exc)}, 400)
        except Exception as exc:
            return self.send_json({"error": f"Falha interna: {exc}"}, 500)


def create_server(pipeline: Pipeline, store: Store, host: str, port: int, static_dir: Path) -> ThreadingHTTPServer:
    runner = JobRunner(pipeline, pipeline.settings.workers)
    scheduler = CalendarScheduler(pipeline, store, runner, pipeline.settings.calendar_poll_seconds)
    handler = type("FactoryHandler", (Handler,), {"pipeline": pipeline, "store": store, "runner": runner, "static_dir": static_dir})
    server = FactoryServer((host, port), handler, runner, scheduler)
    store.recover_interrupted()
    for job_id in store.queued_jobs():
        runner.submit(job_id)
    scheduler.start()
    return server


def serve(pipeline: Pipeline, store: Store, host: str, port: int, static_dir: Path) -> None:
    server = create_server(pipeline, store, host, port, static_dir)
    print(f"Faceless Factory: http://{host}:{port}")
    print("Publicação automática: DESATIVADA")
    server.serve_forever()
