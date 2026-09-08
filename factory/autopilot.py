from __future__ import annotations

import re
import shutil
import unicodedata
from datetime import datetime, timedelta
from typing import Any

from .config import Settings
from .store import Store
from .templates import SERIES


VARIATIONS = (
    "ao amanhecer", "à meia-noite", "em uma noite tranquila",
    "durante uma tempestade distante", "com luzes suaves", "para trabalho profundo",
)

DEFAULT_SERIES_IDS = ["japan_after_rain", "city_after_dark", "rainy_refuges"]
LEGACY_SERIES_MAP = {
    "rainy_places": "japan_after_rain",
    "cozy_worlds": "rainy_refuges",
    "cosmic_focus": "city_after_dark",
    "anime_nights": "anime_midnight",
}


class Autopilot:
    def __init__(self, settings: Settings, store: Store):
        self.settings = settings
        self.store = store

    @staticmethod
    def _key(value: str) -> str:
        folded = unicodedata.normalize("NFKD", value.casefold()).encode("ascii", "ignore").decode("ascii")
        return re.sub(r"\W+", " ", folded).strip()

    @classmethod
    def _compose_topic(cls, topic: str, variation: str) -> str | None:
        """Avoid contradictory combinations such as 'at night at dawn'."""
        if not variation:
            return topic
        folded = cls._key(topic)
        night_markers = ("noite", "noturno", "madrugada", "3 da manha", "meia noite")
        dawn_markers = ("amanhecer", "alvorada")
        if variation == "ao amanhecer" and any(marker in folded for marker in night_markers):
            return None
        if variation in {"à meia-noite", "em uma noite tranquila"} and (
            any(marker in folded for marker in night_markers) or any(marker in folded for marker in dawn_markers)
        ):
            return None
        return f"{topic} {variation}"

    @classmethod
    def _has_timing_conflict(cls, topic: str) -> bool:
        folded = cls._key(topic)
        has_night = any(marker in folded for marker in ("noite", "noturno", "madrugada", "3 da manha", "meia noite"))
        has_dawn = any(marker in folded for marker in ("amanhecer", "alvorada"))
        return has_night and has_dawn

    @staticmethod
    def _current_series_ids(values: Any) -> list[str]:
        if not isinstance(values, list):
            return DEFAULT_SERIES_IDS.copy()
        current = []
        for value in values:
            series_id = LEGACY_SERIES_MAP.get(str(value), str(value))
            if series_id in SERIES and series_id not in current:
                current.append(series_id)
        return current or DEFAULT_SERIES_IDS.copy()

    def blockers(self) -> list[str]:
        summary = self.store.summary()
        free_gb = shutil.disk_usage(self.settings.data_dir).free / (1024 ** 3)
        blockers = []
        if summary["awaiting_approval"] >= self.settings.autopilot_max_review:
            blockers.append(f"Revise os {summary['awaiting_approval']} pacotes prontos antes de gerar mais")
        if summary["in_progress"] >= self.settings.autopilot_max_active:
            blockers.append("A fila já atingiu o limite de trabalhos simultâneos")
        if free_gb < self.settings.autopilot_min_free_gb:
            blockers.append(f"Espaço livre abaixo de {self.settings.autopilot_min_free_gb:g} GB")
        return blockers

    def status(self) -> dict[str, Any]:
        config = self.store.get_autopilot()
        config["series_ids"] = self._current_series_ids(config.get("series_ids"))
        calendar = self.store.list_calendar()
        planned = [item for item in calendar if item.get("origin") == "autopilot" and item["status"] == "planned"]
        blockers = self.blockers()
        return {**config, "planned": len(planned), "blocked": bool(blockers), "blockers": blockers,
                "mode": "active" if config.get("enabled") and not blockers else "paused" if config.get("enabled") else "off"}

    def configure(self, data: dict[str, Any]) -> dict[str, Any]:
        current_config = self.store.get_autopilot()
        if isinstance(data.get("series_ids"), list) and not data["series_ids"]:
            raise ValueError("Escolha ao menos uma coleção válida")
        series_ids = self._current_series_ids(data.get("series_ids"))
        if not isinstance(series_ids, list) or not series_ids or any(item not in SERIES for item in series_ids):
            raise ValueError("Escolha ao menos uma série válida")
        cadence = max(1, min(7, int(data.get("cadence", 3))))
        duration = 1800 if int(data.get("duration", 3600)) < 3600 else 3600
        publish_hour = str(data.get("publish_hour", "19:00"))
        try:
            parsed = datetime.strptime(publish_hour, "%H:%M")
        except ValueError as exc:
            raise ValueError("Horário do piloto automático inválido") from exc
        publish_hour = parsed.strftime("%H:%M")
        horizon_days = max(7, min(42, int(data.get("horizon_days", current_config.get("horizon_days", 7)))))
        self.store.update_autopilot(bool(data.get("enabled", False)), series_ids, cadence, publish_hour,
                                    duration, horizon_days)
        return self.status()

    def apply_weekly_baseline(self, apply: bool = False, now_at: datetime | None = None) -> dict[str, Any]:
        """Safely reduce the editorial rhythm to one weekly plan without producing it."""
        now_at = now_at or datetime.now().astimezone().replace(tzinfo=None)
        stale = [item for item in self.store.list_calendar()
                 if item.get("origin") == "autopilot" and item.get("status") == "planned"
                 and not item.get("job_id") and item.get("scheduled_for", "") < now_at.isoformat(timespec="minutes")]
        if not apply:
            return {"applied": False, "stale_plans": len(stale), "cadence": 1,
                    "duration": 1800, "publish_hour": "19:00", "network_contacted": False,
                    "production_started": False}
        archived = self.store.archive_stale_autopilot_plans(now_at.isoformat(timespec="minutes"))
        archived_conflicts = 0
        for item in self.store.list_calendar():
            if self._has_timing_conflict(str(item.get("topic", ""))):
                archived_conflicts += int(self.store.archive_unstarted_autopilot_plan(
                    int(item["id"]), "Sugestão arquivada: combinação temporal contraditória"
                ))
        status = self.configure({
            "enabled": True,
            "series_ids": DEFAULT_SERIES_IDS,
            "cadence": 1,
            "publish_hour": "19:00",
            "duration": 1800,
            "horizon_days": 7,
        })
        created = self.ensure_plan(now_at=now_at, force=True)
        return {"applied": True, "archived_stale_plans": archived,
                "archived_conflicting_plans": archived_conflicts, "created": created,
                "status": self.status(), "network_contacted": False, "production_started": False}

    def ensure_plan(self, now_at: datetime | None = None, force: bool = False) -> list[dict[str, Any]]:
        config = self.store.get_autopilot()
        config["series_ids"] = self._current_series_ids(config.get("series_ids"))
        if not config.get("enabled") and not force:
            return []
        now_at = now_at or datetime.now().astimezone().replace(tzinfo=None)
        end = now_at + timedelta(days=int(config.get("horizon_days", 7)))
        existing_calendar = self.store.list_calendar()
        now_key = now_at.isoformat(timespec="minutes")
        end_key = end.isoformat(timespec="minutes")
        buffered = [item for item in existing_calendar if item.get("origin") == "autopilot" and
                    item["status"] in {"planned", "starting", "producing"} and
                    now_key <= item["scheduled_for"] <= end_key]
        needed = max(0, int(config["cadence"]) - len(buffered))
        if not needed:
            return []

        known = {self._key(item["topic"]) for item in existing_calendar}
        known.update(self._key(job["topic"]) for job in self.store.list_jobs(500))
        series_ids = list(config["series_ids"])
        insights = self.store.performance_insights()
        if insights:
            winner = self._key(insights[0]["topic"])
            series_ids.sort(key=lambda series_id: -sum(word in winner for topic in SERIES[series_id]["topics"] for word in self._key(topic).split()))

        candidates: list[tuple[str, str]] = []
        for variation in ("", *VARIATIONS):
            topic_count = max(len(SERIES[series_id]["topics"]) for series_id in series_ids)
            for topic_index in range(topic_count):
                for series_id in series_ids:
                    topics = SERIES[series_id]["topics"]
                    if topic_index >= len(topics):
                        continue
                    topic = topics[topic_index]
                    candidate = self._compose_topic(topic, variation)
                    if candidate and self._key(candidate) not in known:
                        candidates.append((series_id, candidate))
        if not candidates:
            return []

        created = []
        interval = max(1, int(config["horizon_days"]) // max(1, int(config["cadence"])))
        hour, minute = map(int, str(config["publish_hour"]).split(":"))
        start = (now_at + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        relevant_dates = []
        for item in existing_calendar:
            series_id = LEGACY_SERIES_MAP.get(str(item.get("series_id")), str(item.get("series_id")))
            if item.get("origin") != "autopilot" or series_id not in series_ids or item.get("status") in {"archived", "revision", "failed"}:
                continue
            try:
                relevant_dates.append(datetime.fromisoformat(str(item["scheduled_for"])))
            except (TypeError, ValueError):
                continue
        if relevant_dates:
            next_after_latest = max(relevant_dates) + timedelta(days=interval)
            next_after_latest = next_after_latest.replace(hour=hour, minute=minute, second=0, microsecond=0)
            start = max(start, next_after_latest)
        for index, (series_id, topic) in enumerate(candidates[:needed]):
            scheduled = start + timedelta(days=index * interval)
            item_id = self.store.add_calendar_item(
                topic, series_id, "youtube_long", 1800 if int(config["duration"]) < 3600 else 3600,
                scheduled.isoformat(timespec="minutes"), "autopilot",
                SERIES[series_id].get("team_id", "youtube_ambient"),
            )
            created.append({"id": item_id, "topic": topic, "scheduled_for": scheduled.isoformat(timespec="minutes")})
        return created
