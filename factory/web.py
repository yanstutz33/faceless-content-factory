from __future__ import annotations

import json
import mimetypes
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .agents import PROFILES
from .pipeline import Pipeline
from .store import Store
from .templates import SERIES, series_catalog


class JobRunner:
    def __init__(self, pipeline: Pipeline, workers: int = 1):
        self.pipeline = pipeline
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="factory-worker")
        self.active: set[str] = set()

    def submit(self, job_id: str) -> None:
        if job_id in self.active:
            return
        self.active.add(job_id)
        future = self.executor.submit(self.pipeline.run, job_id)
        future.add_done_callback(lambda _future: self.active.discard(job_id))


class Handler(SimpleHTTPRequestHandler):
    pipeline: Pipeline
    store: Store
    runner: JobRunner
    static_dir: Path

    def log_message(self, format: str, *args) -> None:
        return

    def translate_path(self, path: str) -> str:
        clean = urlparse(path).path
        if clean.startswith("/api/"):
            return str(self.static_dir / "missing")
        target = "index.html" if clean == "/" else clean.lstrip("/")
        return str(self.static_dir / target)

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
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
        allowed = {"video.mp4", "thumbnail.jpg", "subtitles.srt", "metadata.json", "agents.json", "publication-package.json"}
        if not job or name not in allowed:
            return self.send_json({"error": "Artefato não encontrado"}, 404)
        path = Path(job["output_dir"]) / name
        if not path.is_file():
            return self.send_json({"error": "Artefato ainda não foi gerado"}, 404)
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(path.stat().st_size))
        self.send_header("Content-Disposition", f'inline; filename="{path.name}"')
        self.end_headers()
        with path.open("rb") as file:
            self.wfile.write(file.read())

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1_000_000:
            raise ValueError("Requisição grande demais")
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/dashboard":
            summary = self.store.summary()
            jobs = self.store.list_jobs(100)
            recommendations = []
            if summary["awaiting_approval"]:
                recommendations.append({"tone": "action", "title": "Revise os pacotes prontos", "body": f"{summary['awaiting_approval']} produção(ões) aguardando sua decisão."})
            if not summary["views"]:
                recommendations.append({"tone": "info", "title": "Feche o ciclo de aprendizado", "body": "Após publicar manualmente, registre views e tempo assistido para orientar os próximos temas."})
            recommendations.append({"tone": "safe", "title": "Publicação protegida", "body": "O sistema prepara os arquivos, mas não envia nada automaticamente."})
            return self.send_json({"summary": summary, "jobs": jobs, "recommendations": recommendations})
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
                job_id = self.pipeline.create(
                    data.get("topic", "Biblioteca chuvosa à noite"), int(data.get("duration", 30)),
                    bool(data.get("narration", False)), bool(data.get("subtitles", True)),
                    data.get("profile", "youtube_long"), data.get("source_asset") or None, int(data.get("priority", 2)),
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
                item_id = self.store.add_calendar_item(str(data.get("topic", "")), data.get("series_id"),
                                                       data.get("profile", "youtube_long"), int(data.get("duration", 1800)),
                                                       str(data.get("scheduled_for", "")))
                return self.send_json({"id": item_id}, HTTPStatus.CREATED)
            if path.startswith("/api/calendar/") and path.endswith("/produce"):
                item_id = int(path.split("/")[-2])
                item = next((x for x in self.store.list_calendar() if x["id"] == item_id), None)
                if not item:
                    raise ValueError("Item do calendário não encontrado")
                job_id = self.pipeline.create(item["topic"], item["duration"], False, True, item["profile"])
                self.store.link_calendar_job(item_id, job_id)
                self.runner.submit(job_id)
                return self.send_json({"job_id": job_id}, HTTPStatus.ACCEPTED)
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
                else:
                    return self.send_json({"error": "Ação não encontrada"}, 404)
                return self.send_json(self.store.get_job(job_id))
            return self.send_json({"error": "Rota não encontrada"}, 404)
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            return self.send_json({"error": str(exc)}, 400)
        except Exception as exc:
            return self.send_json({"error": f"Falha interna: {exc}"}, 500)


def create_server(pipeline: Pipeline, store: Store, host: str, port: int, static_dir: Path) -> ThreadingHTTPServer:
    runner = JobRunner(pipeline)
    handler = type("FactoryHandler", (Handler,), {"pipeline": pipeline, "store": store, "runner": runner, "static_dir": static_dir})
    return ThreadingHTTPServer((host, port), handler)


def serve(pipeline: Pipeline, store: Store, host: str, port: int, static_dir: Path) -> None:
    server = create_server(pipeline, store, host, port, static_dir)
    print(f"Faceless Factory: http://{host}:{port}")
    print("Publicação automática: DESATIVADA")
    server.serve_forever()
