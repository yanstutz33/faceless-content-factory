from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from .bilibili import BilibiliPackager
from .pipeline import Pipeline, SUPPORTED_ASSET_LICENSES
from .store import Store


class PublishingCenter:
    """Build manual-safe release packages without contacting any platform."""

    SOURCE_ARTIFACTS = (
        "video.mp4", "thumbnail.jpg", "metadata.json", "render-report.json",
        "quality-gate.json", "asset-manifest.json", "publication-package.json",
    )
    AUXILIARY_ARTIFACTS = (
        "motion-overlay.mp4", "visual-loop.mp4", "thumbnail-a.jpg", "thumbnail-b.jpg",
        "thumbnail-design.json", "subtitles.srt", "agents.json", "commerce-package.json",
        "pinterest-package.json",
    )
    PACKAGE_FILES = {
        "youtube_private": ("video.mp4", "thumbnail.jpg", "youtube-upload.json"),
        "vertical_manual": ("vertical-short.mp4", "vertical-thumbnail.jpg", "vertical-package.json"),
        "bilibili_manual": ("bilibili-cover.jpg", "bilibili-subtitles-zh-Hans.srt",
                            "bilibili-subtitles-en.srt", "bilibili-upload.json"),
    }

    def __init__(self, pipeline: Pipeline, store: Store):
        self.pipeline = pipeline
        self.store = store
        self.bilibili = BilibiliPackager(pipeline, store)
        self._integrity_cache: dict[str, tuple[Any, dict[str, Any]]] = {}
        self._integrity_lock = Lock()

    def _verified_manifest(self, out: Path, *, refresh: bool = False) -> dict[str, Any]:
        """Reuse hashes only while the manifest and every artifact's file stats match."""
        path = out / "artifact-manifest.json"
        if not path.is_file():
            raise ValueError("Manifesto de integridade ausente; execute a auditoria novamente")
        try:
            raw = path.read_text(encoding="utf-8")
            manifest = json.loads(raw)
            entries = manifest.get("files") if isinstance(manifest, dict) else None
            if not isinstance(entries, list) or not entries or any(
                not isinstance(item, dict) or not isinstance(item.get("name"), str)
                or not item["name"] for item in entries
            ):
                raise ValueError("Manifesto de integridade inválido; execute a auditoria novamente")
            stats = []
            for item in entries:
                name = item["name"]
                if Path(name).is_absolute() or ".." in Path(name).parts:
                    raise ValueError(f"Caminho inválido no manifesto de integridade: {name}")
                artifact = out / name
                if not artifact.is_file():
                    raise ValueError(f"Artefato ausente no manifesto: {name}")
                stat = artifact.stat()
                stats.append((name, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
            signature = (raw, tuple(stats))
            key = str(out.resolve())
            with self._integrity_lock:
                cached = self._integrity_cache.get(key)
                if refresh or cached is None or cached[0] != signature:
                    self.pipeline.verify_artifact_manifest(out)
                    self._integrity_cache[key] = (signature, manifest)
            return manifest
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("Manifesto de integridade ilegível; execute a auditoria novamente") from exc

    def _release_checks(self, out: Path, *, refresh_integrity: bool = False) -> list[dict[str, Any]]:
        checks = []
        for destination, names in self.PACKAGE_FILES.items():
            missing = [name for name in names if not (out / name).is_file()]
            checks.append({
                "id": destination, "label": destination, "passed": not missing,
                "detail": "Arquivos do pacote presentes" if not missing else
                "Prepare novamente o pacote; arquivos ausentes: " + ", ".join(missing),
            })
        release_path = out / "release-manifest.json"
        checks.append({"id": "release_manifest", "label": "Manifesto de publicação",
                       "passed": release_path.is_file(),
                       "detail": "Manifesto de publicação presente" if release_path.is_file() else
                       "Prepare o pacote completo para gerar release-manifest.json"})
        try:
            manifest = self._verified_manifest(out, refresh=refresh_integrity)
            registered = {item["name"]: item for item in manifest["files"]}
            required = set(self.SOURCE_ARTIFACTS) | {"release-manifest.json"}
            required.update(name for names in self.PACKAGE_FILES.values() for name in names)
            required.update(name for name in self.AUXILIARY_ARTIFACTS if (out / name).is_file())
            missing = sorted(required - registered.keys())
            if missing:
                raise ValueError("Prepare novamente o pacote; artefatos sem integridade registrada: "
                                 + ", ".join(missing))
            checks.append({"id": "integrity", "label": "Integridade completa", "passed": True,
                           "detail": f"{len(registered)} artefatos com integridade validada"})
            try:
                release = json.loads(release_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise ValueError("Manifesto de publicação inválido; prepare o pacote completo novamente") from exc
            sources = release.get("source_artifacts") if isinstance(release, dict) else None
            if not isinstance(sources, dict) or not set(self.SOURCE_ARTIFACTS).issubset(sources):
                raise ValueError("Prepare novamente o pacote para vincular os derivados à versão atual do vídeo")
            stale = [name for name in self.SOURCE_ARTIFACTS if sources[name] != registered[name]]
            if stale:
                raise ValueError("Pacote desatualizado; prepare os derivados novamente após alterações em: "
                                 + ", ".join(stale))
            checks.append({"id": "source_version", "label": "Versão dos derivados", "passed": True,
                           "detail": "Pacotes vinculados aos arquivos de origem atuais"})
        except (ValueError, OSError, UnicodeError) as exc:
            checks.append({"id": "source_version" if any(check["id"] == "integrity" for check in checks)
                           else "integrity", "label": "Integridade do pacote", "passed": False,
                           "detail": str(exc)})
        return checks

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
            isinstance(asset, dict)
            and asset.get("approved") is True
            and asset.get("license_type") in SUPPORTED_ASSET_LICENSES
            and (asset.get("license_type") != "user_confirmed" or asset.get("rights_confirmed") is True)
            for asset in assets
        )
        return (True, f"{len(assets)} asset(s) com origem aprovada") if valid else (
            False, "Existe mídia sem licença ou aprovação comprovada"
        )

    def _music_approval(self, job: dict[str, Any], metadata: dict[str, Any]) -> tuple[bool, str]:
        music = metadata.get("music") if isinstance(metadata, dict) else None
        if not isinstance(music, dict):
            return False, "Música não identificada no pacote"
        if music.get("style") == "original_lofi_chill":
            return False, "Beat sintético antigo bloqueado; escolha uma faixa ouvida e aprovada"
        asset_id = job.get("music_asset_id") or music.get("track_id")
        asset = self.store.get_music_asset_record(int(asset_id)) if asset_id else None
        if not asset and music.get("track_name"):
            asset = next(
                (item for item in self.store.list_music_assets()
                 if item.get("name") == music.get("track_name")),
                None,
            )
        if not asset:
            return False, "Faixa sem vínculo rastreável com a Biblioteca"
        if not asset.get("approved") or asset.get("human_review") != "approved":
            return False, f"Música reprovada ou ainda não ouvida: {asset.get('name', 'sem nome')}"
        return True, f"Música ouvida e aprovada: {asset['name']}"

    def audit(self, job: dict[str, Any], *, refresh_integrity: bool = False,
              check_release: bool = True) -> dict[str, Any]:
        out = Path(job["output_dir"])
        metadata = job.get("metadata") or {}
        rights_ok, rights_detail = self._asset_rights(out)
        music_ok, music_detail = self._music_approval(job, metadata)
        checks = [
            {"id": "format", "label": "Formato publicável",
             "passed": job.get("profile") == "youtube_long" and int(job.get("duration", 0)) >= 1800,
             "detail": "YouTube longo com pelo menos 30 minutos" if
             job.get("profile") == "youtube_long" and int(job.get("duration", 0)) >= 1800 else
             "Prévia ou teste curto não entra na publicação"},
            {"id": "approval", "label": "Aprovação editorial", "passed": job.get("status") == "approved",
             "detail": "Aprovado" if job.get("status") == "approved" else "Aguardando aprovação humana"},
            {"id": "technical", "label": "Validação técnica", "passed": bool(metadata.get("verification", {}).get("passed")),
             "detail": "Vídeo e áudio validados" if metadata.get("verification", {}).get("passed") else "Validação técnica pendente"},
            {"id": "quality", "label": "Controle automático", "passed": bool(metadata.get("quality_gate", {}).get("passed")),
             "detail": f"Nota {metadata.get('quality_gate', {}).get('score', 0)}/100"},
            {"id": "rights", "label": "Direitos de mídia", "passed": rights_ok, "detail": rights_detail},
            {"id": "music", "label": "Aprovação musical", "passed": music_ok, "detail": music_detail},
        ]
        eligibility_blockers = [check["detail"] for check in checks if not check["passed"]]
        release_checks = self._release_checks(out, refresh_integrity=refresh_integrity) if check_release else []
        blockers = eligibility_blockers + [check["detail"] for check in release_checks if not check["passed"]]
        return {
            "job_id": job["id"],
            "topic": job["topic"],
            "status": job["status"],
            "profile": job.get("profile", "youtube_long"),
            "duration": job["duration"],
            "updated_at": job.get("updated_at"),
            "title": metadata.get("title") or job["topic"],
            "thumbnail_variant": job.get("thumbnail_variant") or metadata.get("selected_thumbnail") or "a",
            "checks": checks,
            "release_checks": release_checks,
            "blockers": blockers,
            "eligibility_blockers": eligibility_blockers,
            "eligible": not eligibility_blockers,
            "packages": {check["id"]: check["passed"] for check in release_checks
                         if check["id"] in self.PACKAGE_FILES},
            "release_ready": check_release and not blockers,
            "automatic_upload_allowed": False,
        }

    def queue(self) -> dict[str, Any]:
        jobs = [job for job in self.store.list_jobs(500)
                if job.get("status") in {"approved", "awaiting_approval"}
                and job.get("profile") == "youtube_long" and int(job.get("duration", 0)) >= 1800]
        pilots = [job for job in jobs if str(job.get("cohort_id") or "").startswith("pilot-")]
        if pilots:
            cohort_id = max(pilots, key=lambda item: str(item.get("created_at") or "")).get("cohort_id")
            jobs = [job for job in pilots if job.get("cohort_id") == cohort_id]
        rows = [self.audit(job) for job in jobs]
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

    def pilot_certification(self, target: int = 10) -> dict[str, Any]:
        """Summarize automatic pilot gates without replacing human approval."""
        publishable = [job for job in self.store.list_jobs(500)
                       if job.get("status") in {"approved", "awaiting_approval"}
                       and job.get("profile") == "youtube_long" and int(job.get("duration", 0)) >= 1800]
        # Phase 2 and later runs also use cohort identifiers. Pilot
        # certification must remain pinned to the explicit human pilot.
        cohort_jobs = [job for job in publishable
                       if str(job.get("cohort_id") or "").startswith("pilot-")]
        cohort_id = None
        if cohort_jobs:
            cohort_id = max(cohort_jobs, key=lambda item: str(item.get("created_at") or "")).get("cohort_id")
            jobs = [job for job in cohort_jobs if job.get("cohort_id") == cohort_id]
        else:
            # Compatibility for fresh/test stores created before explicit cohorts.
            jobs = publishable
        # Certification reports creative/editorial gates, not package readiness.
        # Keep it responsive even on a cold cache with many gigabytes of video.
        # The queue and final upload still perform full release validation.
        audits = [self.audit(job, check_release=False) for job in jobs]

        track_names: list[str] = []
        visual_fingerprints: list[tuple[str, str, str, str]] = []
        novelty_scores: list[float] = []
        for job in jobs:
            metadata = job.get("metadata") or {}
            music = metadata.get("music") or {}
            track_name = str(music.get("track_name") or "").strip()
            if track_name:
                track_names.append(track_name.casefold())
            dna = metadata.get("creative_fingerprint") or metadata.get("creative_dna") or {}
            visual_fingerprints.append(tuple(str(dna.get(field) or "") for field in (
                "scene", "treatment", "composition", "motion_effect"
            )))
            novelty = dna.get("novelty") or {}
            try:
                novelty_scores.append(float(novelty.get("score")))
            except (TypeError, ValueError):
                pass

        total = len(jobs)
        technical_ready = sum(
            all(check["passed"] for check in audit["checks"] if check["id"] != "approval")
            for audit in audits
        )
        unique_tracks = len(set(track_names))
        unique_visuals = len(set(visual_fingerprints)) if visual_fingerprints else 0
        pending_review = sum(job.get("status") == "awaiting_approval" for job in jobs)
        approved = sum(job.get("status") == "approved" for job in jobs)
        checks = [
            {"id": "sample", "label": "Lote mínimo", "value": total, "target": target,
             "passed": total >= target, "detail": f"{total} de {target} vídeos necessários"},
            {"id": "duration", "label": "Duração válida", "value": total, "target": total,
             "passed": bool(total) and all(int(job.get("duration", 0)) >= 1800 for job in jobs),
             "detail": f"{total} com pelo menos 30 minutos"},
            {"id": "audio", "label": "Faixas distintas", "value": unique_tracks, "target": total,
             "passed": bool(total) and unique_tracks == total,
             "detail": f"{unique_tracks} faixas para {total} vídeos"},
            {"id": "visual", "label": "DNA visual distinto", "value": unique_visuals, "target": total,
             "passed": bool(total) and unique_visuals == total,
             "detail": f"{unique_visuals} combinações integrais para {total} vídeos"},
            {"id": "technical", "label": "Qualidade e direitos", "value": technical_ready, "target": total,
             "passed": bool(total) and technical_ready == total,
             "detail": f"{technical_ready} de {total} passaram sem contar aprovação editorial"},
        ]
        automatic_pass = all(check["passed"] for check in checks)
        human_target_met = approved >= target
        if not automatic_pass:
            status = "blocked"
            label = "Correções automáticas necessárias"
            next_action = "Complete o lote e corrija os controles marcados antes da revisão humana."
        elif human_target_met:
            status = "certified"
            label = "Piloto certificado"
            next_action = "Piloto criativo concluído e pronto para operação controlada."
        else:
            status = "human_review_pending"
            label = "Pronto tecnicamente · revisão humana pendente"
            next_action = f"Assista e aprove pelo menos {target} vídeos. Nenhum envio externo será feito."
        return {
            "cohort_id": cohort_id,
            "status": status,
            "label": label,
            "target": target,
            "candidate_count": total,
            "technical_ready_count": technical_ready,
            "approved_count": approved,
            "pending_review_count": pending_review,
            "unique_tracks": unique_tracks,
            "unique_visuals": unique_visuals,
            "minimum_novelty": round(min(novelty_scores), 1) if novelty_scores else None,
            "automatic_checks_passed": automatic_pass,
            "human_target_met": human_target_met,
            "checks": checks,
            "next_action": next_action,
        }

    def prepare(self, job_id: str, vertical_duration: int = 30) -> dict[str, Any]:
        job = self.store.get_job(job_id)
        if not job:
            raise ValueError("Produção não encontrada")
        before = self.audit(job, refresh_integrity=True)
        if not before["eligible"]:
            raise ValueError("Pacote bloqueado: " + "; ".join(before["eligibility_blockers"]))
        out = Path(job["output_dir"])
        original_manifest = self._verified_manifest(out)
        missing = [name for name in self.SOURCE_ARTIFACTS if not (out / name).is_file()]
        if missing:
            raise ValueError("Audite a produção antes de preparar o pacote; arquivos ausentes: " + ", ".join(missing))
        names = [item["name"] for item in original_manifest["files"]]
        names.extend(self.SOURCE_ARTIFACTS)
        names.extend(self.AUXILIARY_ARTIFACTS)
        names.extend(name for files in self.PACKAGE_FILES.values() for name in files)
        youtube = self.pipeline.prepare_youtube_package(job_id)
        self.pipeline.prepare_vertical_package(job_id, vertical_duration)
        bilibili = self.bilibili.prepare(job_id)
        job = self.store.get_job(job_id) or job
        # Destination packagers rebuild narrower manifests; restore every source
        # entry as well as the technical, rights and release evidence.
        manifest = self.pipeline.artifact_manifest(
            out, [name for name in dict.fromkeys(names) if name != "release-manifest.json"],
        )
        registered = {item["name"]: item for item in manifest["files"]}
        release = {
            "mode": "prepared_not_uploaded",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "job_id": job_id,
            "automatic_upload_allowed": False,
            "audit": before,
            "source_artifacts": {name: registered[name] for name in self.SOURCE_ARTIFACTS},
            "destinations": {
                "youtube": {"privacy": youtube["status"]["privacyStatus"], "package": "youtube-upload.json"},
                "shorts_reels_tiktok": {"upload": "manual", "package": "vertical-package.json"},
                "bilibili": {"upload": "manual", "package": "bilibili-upload.json",
                             "title": bilibili["localization"]["titles"]["zh_hans"]},
            },
            "files": ["video.mp4", "thumbnail.jpg", "youtube-upload.json", "vertical-short.mp4",
                      "vertical-thumbnail.jpg", "vertical-package.json", "bilibili-cover.jpg",
                      "bilibili-subtitles-zh-Hans.srt", "bilibili-subtitles-en.srt", "bilibili-upload.json"],
            "next_step": "Revisar os arquivos e enviar manualmente pelas plataformas oficiais.",
        }
        (out / "release-manifest.json").write_text(
            json.dumps(release, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        manifest["files"].extend(self.pipeline.artifact_manifest(out, ["release-manifest.json"])["files"])
        (out / "artifact-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        release["audit"] = self.audit(job, refresh_integrity=True)
        if not release["audit"]["release_ready"]:
            raise ValueError("Pacote bloqueado: " + "; ".join(release["audit"]["blockers"]))
        (out / "release-manifest.json").write_text(
            json.dumps(release, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        manifest["files"] = [item for item in manifest["files"] if item["name"] != "release-manifest.json"]
        manifest["files"].extend(self.pipeline.artifact_manifest(out, ["release-manifest.json"])["files"])
        (out / "artifact-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.store.event(job_id, "release", "Pacote completo preparado; nenhum upload foi realizado")
        return release
