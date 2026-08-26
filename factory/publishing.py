from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .pipeline import Pipeline
from .store import Store


class PublishingCenter:
    """Build manual-safe release packages without contacting any platform."""

    def __init__(self, pipeline: Pipeline, store: Store):
        self.pipeline = pipeline
        self.store = store

    @staticmethod
    def _asset_rights(out: Path) -> tuple[bool, str]:
        manifest = out / "asset-manifest.json"
        if not manifest.is_file():
            return False, "Manifesto de direitos não encontrado"
        try:
            assets = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False, "Manifesto de direitos inválido"
        if not isinstance(assets, list) or not assets:
            return False, "Nenhum asset rastreável no manifesto"
        valid = all(
            isinstance(asset, dict) and asset.get("approved") is True and asset.get("license_type")
            for asset in assets
        )
        return (True, f"{len(assets)} asset(s) com origem aprovada") if valid else (
            False, "Existe mídia sem licença ou aprovação comprovada"
        )

    def audit(self, job: dict[str, Any]) -> dict[str, Any]:
        out = Path(job["output_dir"])
        metadata = job.get("metadata") or {}
        rights_ok, rights_detail = self._asset_rights(out)
        checks = [
            {"id": "approval", "label": "Aprovação editorial", "passed": job.get("status") == "approved",
             "detail": "Aprovado" if job.get("status") == "approved" else "Aguardando aprovação humana"},
            {"id": "technical", "label": "Validação técnica", "passed": bool(metadata.get("verification", {}).get("passed")),
             "detail": "Vídeo e áudio validados" if metadata.get("verification", {}).get("passed") else "Validação técnica pendente"},
            {"id": "quality", "label": "Controle automático", "passed": bool(metadata.get("quality_gate", {}).get("passed")),
             "detail": f"Nota {metadata.get('quality_gate', {}).get('score', 0)}/100"},
            {"id": "rights", "label": "Direitos de mídia", "passed": rights_ok, "detail": rights_detail},
        ]
        blockers = [check["detail"] for check in checks if not check["passed"]]
        youtube_ready = (out / "youtube-upload.json").is_file()
        vertical_ready = (out / "vertical-package.json").is_file() and (out / "vertical-short.mp4").is_file()
        release_manifest_ready = (out / "release-manifest.json").is_file()
        return {
            "job_id": job["id"],
            "topic": job["topic"],
            "status": job["status"],
            "profile": job.get("profile", "youtube_long"),
            "duration": job["duration"],
            "title": metadata.get("title") or job["topic"],
            "thumbnail_variant": job.get("thumbnail_variant") or metadata.get("selected_thumbnail") or "a",
            "checks": checks,
            "blockers": blockers,
            "eligible": not blockers,
            "packages": {"youtube_private": youtube_ready, "vertical_manual": vertical_ready},
            "release_ready": not blockers and youtube_ready and vertical_ready and release_manifest_ready,
            "automatic_upload_allowed": False,
        }

    def queue(self) -> dict[str, Any]:
        rows = [self.audit(job) for job in self.store.list_jobs(500)
                if job.get("status") in {"approved", "awaiting_approval"}]
        rows.sort(key=lambda row: (not row["eligible"], not row["release_ready"], row["topic"].lower()))
        return {
            "mode": "manual-safe",
            "automatic_upload_allowed": False,
            "summary": {
                "total": len(rows),
                "eligible": sum(row["eligible"] for row in rows),
                "ready": sum(row["release_ready"] for row in rows),
                "blocked": sum(bool(row["blockers"]) for row in rows),
            },
            "items": rows,
        }

    def prepare(self, job_id: str, vertical_duration: int = 30) -> dict[str, Any]:
        job = self.store.get_job(job_id)
        if not job:
            raise ValueError("Produção não encontrada")
        before = self.audit(job)
        if not before["eligible"]:
            raise ValueError("Pacote bloqueado: " + "; ".join(before["blockers"]))
        youtube = self.pipeline.prepare_youtube_package(job_id)
        vertical = self.pipeline.prepare_vertical_package(job_id, vertical_duration)
        job = self.store.get_job(job_id) or job
        audit = self.audit(job)
        out = Path(job["output_dir"])
        release = {
            "mode": "prepared_not_uploaded",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "job_id": job_id,
            "automatic_upload_allowed": False,
            "audit": audit,
            "destinations": {
                "youtube": {"privacy": youtube["status"]["privacyStatus"], "package": "youtube-upload.json"},
                "shorts_reels_tiktok": {"upload": "manual", "package": "vertical-package.json"},
            },
            "files": ["video.mp4", "thumbnail.jpg", "youtube-upload.json", "vertical-short.mp4",
                      "vertical-thumbnail.jpg", "vertical-package.json"],
            "next_step": "Revisar os arquivos e enviar manualmente pelas plataformas oficiais.",
        }
        (out / "release-manifest.json").write_text(
            json.dumps(release, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        manifest = self.pipeline.artifact_manifest(out, release["files"] + ["release-manifest.json"])
        (out / "artifact-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.store.event(job_id, "release", "Pacote completo preparado; nenhum upload foi realizado")
        return release

