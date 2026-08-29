from __future__ import annotations

import re
import shutil
from datetime import datetime, timedelta
from typing import Any

from .config import Settings
from .store import Store
from .templates import SERIES


VARIATIONS = (
    "ao amanhecer", "à meia-noite", "em uma noite tranquila",
    "durante uma tempestade distante", "com luzes suaves", "para trabalho profundo",
)


class Autopilot:
    def __init__(self, settings: Settings, store: Store):
        self.settings = settings
        self.store = store

    @staticmethod
    def _key(value: str) -> str:
        return re.sub(r"\W+", " ", value.lower()).strip()

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
        calendar = self.store.list_calendar()
        planned = [item for item in calendar if item.get("origin") == "autopilot" and item["status"] == "planned"]
        blockers = self.blockers()
        return {**config, "planned": len(planned), "blocked": bool(blockers), "blockers": blockers,
                "mode": "active" if config.get("enabled") and not blockers else "paused" if config.get("enabled") else "off"}

    def configure(self, data: dict[str, Any]) -> dict[str, Any]:
        series_ids = data.get("series_ids") or ["rainy_places", "cozy_worlds", "cosmic_focus"]
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
        self.store.update_autopilot(bool(data.get("enabled", False)), series_ids, cadence, publish_hour, duration)
        return self.status()

    def ensure_plan(self, now_at: datetime | None = None, force: bool = False) -> list[dict[str, Any]]:
        config = self.store.get_autopilot()
        if not config.get("enabled") and not force:
            return []
        now_at = now_at or datetime.now().astimezone().replace(tzinfo=None)
        end = now_at + timedelta(days=int(config.get("horizon_days", 7)))
        existing_calendar = self.store.list_calendar()
        buffered = [item for item in existing_calendar if item.get("origin") == "autopilot" and
                    item["status"] in {"planned", "starting", "producing"} and item["scheduled_for"] <= end.isoformat(timespec="minutes")]
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
                    candidate = topic if not variation else f"{topic} {variation}"
                    if self._key(candidate) not in known:
                        candidates.append((series_id, candidate))
        if not candidates:
            return []

        created = []
        interval = max(1, int(config["horizon_days"]) // max(1, int(config["cadence"])))
        hour, minute = map(int, str(config["publish_hour"]).split(":"))
        start = (now_at + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        for index, (series_id, topic) in enumerate(candidates[:needed]):
            scheduled = start + timedelta(days=index * interval)
            item_id = self.store.add_calendar_item(
                topic, series_id, "youtube_long", 1800 if int(config["duration"]) < 3600 else 3600,
                scheduled.isoformat(timespec="minutes"), "autopilot",
                SERIES[series_id].get("team_id", "youtube_ambient"),
            )
            created.append({"id": item_id, "topic": topic, "scheduled_for": scheduled.isoformat(timespec="minutes")})
        return created
