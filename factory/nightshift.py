from __future__ import annotations

from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any

from .autopilot import Autopilot
from .pipeline import Pipeline
from .store import Store


class NightShift:
    """Safely pull future calendar work into a bounded overnight render queue."""

    def __init__(self, pipeline: Pipeline, store: Store, runner: Any, autopilot: Autopilot):
        self.pipeline = pipeline
        self.store = store
        self.runner = runner
        self.autopilot = autopilot

    @staticmethod
    def _clock(value: str) -> time:
        return datetime.strptime(value, "%H:%M").time()

    def in_window(self, at: datetime | None = None) -> bool:
        config = self.store.get_night_shift()
        current = (at or datetime.now().astimezone()).time().replace(second=0, microsecond=0)
        start, end = self._clock(config["start_hour"]), self._clock(config["end_hour"])
        return start <= current < end if start < end else current >= start or current < end

    def configure(self, data: dict[str, Any]) -> dict[str, Any]:
        start, end = str(data.get("start_hour", "22:00")), str(data.get("end_hour", "07:00"))
        self._clock(start)
        self._clock(end)
        limit = max(1, min(5, int(data.get("batch_limit", 2))))
        self.store.update_night_shift(bool(data.get("enabled", False)), start, end, limit)
        return self.status()

    def _pilot_blockers(self, target: int = 10) -> list[str]:
        """Keep autonomous batches behind the explicit human pilot gate."""
        jobs = self.store.list_jobs(500)
        pilot_jobs = [job for job in jobs if str(job.get("cohort_id") or "").startswith("pilot-")]
        if not pilot_jobs:
            # Fresh installations and isolated tests remain backwards compatible.
            return []
        cohort_id = max(pilot_jobs, key=lambda item: str(item.get("created_at") or "")).get("cohort_id")
        cohort = [job for job in pilot_jobs if job.get("cohort_id") == cohort_id]
        approved = sum(job.get("status") == "approved" for job in cohort)
        if approved < target:
            return [f"Aprove {target - approved} vídeo(s) do lote piloto antes de iniciar a Fase 2"]
        return []

    def phase2_certification(self, target: int = 3) -> dict[str, Any]:
        """Certify autonomous local batches without treating review as publication."""
        jobs = self.store.list_jobs(1000)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for job in jobs:
            cohort_id = str(job.get("cohort_id") or "")
            if cohort_id.startswith("phase2-"):
                grouped.setdefault(cohort_id, []).append(job)

        batches = []
        terminal = {"awaiting_approval", "approved"}
        for cohort_id, cohort in grouped.items():
            invalid = []
            active = any(job.get("status") not in terminal | {"failed", "rejected"} for job in cohort)
            failed = any(job.get("status") in {"failed", "rejected"} for job in cohort)
            if not active and not failed:
                for job in cohort:
                    metadata = job.get("metadata") or {}
                    try:
                        self.pipeline.verify_artifact_manifest(Path(job["output_dir"]))
                    except (OSError, ValueError) as exc:
                        invalid.append(f"{job['id']}: {exc}")
                        continue
                    if not metadata.get("verification", {}).get("passed"):
                        invalid.append(f"{job['id']}: validação técnica pendente")
                    if not metadata.get("quality_gate", {}).get("passed"):
                        invalid.append(f"{job['id']}: controle de qualidade pendente")
                    if not (Path(job["output_dir"]) / "publication-package.json").is_file():
                        invalid.append(f"{job['id']}: pacote de publicação ausente")
            if active:
                status = "in_progress"
            elif failed or invalid:
                status = "failed"
            else:
                status = "successful"
            batches.append({
                "cohort_id": cohort_id,
                "status": status,
                "jobs": len(cohort),
                "awaiting_review": sum(job.get("status") == "awaiting_approval" for job in cohort),
                "invalid": invalid,
                "created_at": min(str(job.get("created_at") or "") for job in cohort),
                "publish_performed": False,
            })
        batches.sort(key=lambda item: item["created_at"])
        completed = [batch for batch in batches if batch["status"] in {"successful", "failed"}]
        consecutive = 0
        for batch in reversed(completed):
            if batch["status"] != "successful":
                break
            consecutive += 1
        pilot_blockers = self._pilot_blockers()
        if consecutive >= target:
            status = "certified"
            next_action = "Fase 2 certificada; a automação local está pronta para operação controlada."
        elif pilot_blockers:
            status = "blocked_by_pilot"
            next_action = pilot_blockers[0]
        elif any(batch["status"] == "in_progress" for batch in batches):
            status = "in_progress"
            next_action = "Aguardar a conclusão do lote autônomo atual."
        else:
            status = "ready"
            next_action = f"Executar mais {target - consecutive} lote(s) autônomo(s), sem publicação externa."
        return {
            "status": status,
            "target": target,
            "consecutive_successful_batches": consecutive,
            "remaining_batches": max(0, target - consecutive),
            "batches": batches,
            "pilot_blockers": pilot_blockers,
            "next_action": next_action,
            "automatic_upload_allowed": False,
        }

    def status(self) -> dict[str, Any]:
        config = self.store.get_night_shift()
        active = len(self.runner.snapshot().get("active", []))
        within = self.in_window()
        blockers = self.autopilot.blockers() + self._pilot_blockers()
        mode = "off"
        if config.get("enabled"):
            mode = "blocked" if blockers else "active" if within else "waiting"
        return {**config, "within_window": within, "active_jobs": active, "blockers": blockers, "mode": mode,
                "publish_mode": "manual-safe"}

    def daily_report(self, at: datetime | None = None) -> dict[str, Any]:
        """Summarize the local operation for one calendar day without triggering work."""
        current = at or datetime.now().astimezone()

        def is_today(value: str | None) -> bool:
            if not value:
                return False
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=current.tzinfo)
            return parsed.astimezone(current.tzinfo).date() == current.date()

        jobs = [job for job in self.store.list_jobs(500) if is_today(job.get("updated_at"))]
        completed = [job for job in jobs if job["status"] in {"awaiting_approval", "approved"}]
        blocked = [job for job in jobs if job["status"] in {"failed", "rejected"}]
        active = [job for job in jobs if job["status"] in {"queued", "planning", "assets", "rendering", "reviewing"}]
        awaiting = [job for job in jobs if job["status"] == "awaiting_approval"]
        config = self.store.get_night_shift()
        blockers = self.autopilot.blockers() + self._pilot_blockers()
        if blocked:
            next_action = f"Corrigir {len(blocked)} produção(ões) bloqueada(s)."
        elif awaiting:
            next_action = f"Revisar {len(awaiting)} produção(ões) concluída(s)."
        elif active:
            next_action = f"Acompanhar {len(active)} produção(ões) em andamento."
        elif blockers:
            next_action = blockers[0]
        else:
            next_action = "Operação livre para o próximo lote seguro."
        latest = sorted(jobs, key=lambda item: item.get("updated_at") or "", reverse=True)[:5]
        return {
            "date": current.date().isoformat(),
            "status": "attention" if blocked or awaiting or blockers else "working" if active else "clear",
            "summary": {
                "completed": len(completed), "blocked": len(blocked),
                "active": len(active), "awaiting_review": len(awaiting),
            },
            "next_action": next_action,
            "latest": [{"id": job["id"], "topic": job["topic"], "status": job["status"]} for job in latest],
            "last_shift": config.get("last_summary", {}),
            "publish_performed": False,
        }

    def run_once(self, force: bool = False) -> dict[str, Any]:
        config = self.store.get_night_shift()
        if not force and (not config.get("enabled") or not self.in_window()):
            return {"created": [], "recovered": [], "reason": "outside_window_or_disabled"}
        current = datetime.now().astimezone()
        start, end = self._clock(config["start_hour"]), self._clock(config["end_hour"])
        shift_day = current.date() - timedelta(days=1) if start >= end and current.time() < end else current.date()
        shift_key = shift_day.isoformat()
        if not force and config.get("last_summary", {}).get("shift_key") == shift_key:
            return {"created": [], "recovered": [], "reason": "already_ran_this_shift", "shift_key": shift_key}
        blockers = self.autopilot.blockers() + self._pilot_blockers()
        if blockers:
            summary = {"created": [], "recovered": [], "reason": blockers[0], "shift_key": shift_key}
            self.store.update_night_shift(bool(config.get("enabled")), config["start_hour"], config["end_hour"],
                                          int(config["batch_limit"]), summary, ran=True)
            return summary
        recovered = self.store.recover_interrupted()
        for job_id in self.store.queued_jobs():
            self.runner.submit(job_id)
        self.autopilot.ensure_plan(force=True)
        capacity = max(0, int(config["batch_limit"]) - len(self.runner.snapshot().get("active", [])))
        created = []
        cohort_id = f"phase2-{shift_key}-{current.strftime('%H%M%S')}"
        for _ in range(capacity):
            item = self.store.claim_next_calendar(allow_autopilot=True)
            if not item:
                break
            try:
                job_id = self.pipeline.create(item["topic"], item["duration"], False, True, item["profile"],
                                              priority=1, team_id=item.get("team_id", "youtube_ambient"),
                                              cohort_id=cohort_id)
                self.store.link_calendar_job(item["id"], job_id)
                self.store.event(job_id, "night_shift", "Produção antecipada pela operação noturna segura")
                self.runner.submit(job_id)
                created.append(job_id)
            except Exception as exc:
                self.store.fail_calendar_item(item["id"], str(exc))
        summary = {"created": created, "recovered": recovered, "reason": "completed", "shift_key": shift_key,
                   "cohort_id": cohort_id if created else None,
                   "publish_performed": False}
        self.store.update_night_shift(bool(config.get("enabled")), config["start_hour"], config["end_hour"],
                                      int(config["batch_limit"]), summary, ran=True)
        return summary

