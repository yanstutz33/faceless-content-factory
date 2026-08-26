from __future__ import annotations

from datetime import datetime, time, timedelta
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

    def status(self) -> dict[str, Any]:
        config = self.store.get_night_shift()
        active = len(self.runner.snapshot().get("active", []))
        within = self.in_window()
        blockers = self.autopilot.blockers()
        mode = "off"
        if config.get("enabled"):
            mode = "blocked" if blockers else "active" if within else "waiting"
        return {**config, "within_window": within, "active_jobs": active, "blockers": blockers, "mode": mode,
                "publish_mode": "manual-safe"}

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
        blockers = self.autopilot.blockers()
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
        for _ in range(capacity):
            item = self.store.claim_next_calendar(allow_autopilot=True)
            if not item:
                break
            try:
                job_id = self.pipeline.create(item["topic"], item["duration"], False, True, item["profile"], priority=1)
                self.store.link_calendar_job(item["id"], job_id)
                self.store.event(job_id, "night_shift", "Produção antecipada pela operação noturna segura")
                self.runner.submit(job_id)
                created.append(job_id)
            except Exception as exc:
                self.store.fail_calendar_item(item["id"], str(exc))
        summary = {"created": created, "recovered": recovered, "reason": "completed", "shift_key": shift_key,
                   "publish_performed": False}
        self.store.update_night_shift(bool(config.get("enabled")), config["start_hour"], config["end_hour"],
                                      int(config["batch_limit"]), summary, ran=True)
        return summary

