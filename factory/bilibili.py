from __future__ import annotations

import json
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .pipeline import Pipeline
from .store import Store


class BilibiliPackager:
    """Create a localized, manual-safe Bilibili upload package."""

    SCENES = (
        (("chuva", "chuv", "rain"), "雨夜咖啡馆", "Rainy Night Cafe"),
        (("cafe", "coffee"), "深夜咖啡馆", "Late-Night Cafe"),
        (("cabana", "neve", "snow", "cabin"), "雪夜小屋", "Snowy Night Cabin"),
        (("trem", "train", "metro"), "深夜列车", "Late-Night Train"),
        (("cosmic", "cosmico", "cosmica", "espaco", "space"), "宇宙休息室", "Cosmic Lounge"),
        (("biblioteca", "estudo", "study", "focus", "foco"), "深夜学习室", "Late-Night Study Room"),
        (("anime", "personagem", "apartment", "apartamento"), "原创雨夜公寓", "Original Rainy-Night Apartment"),
        (("lago", "lake", "natureza", "forest", "floresta"), "湖畔静夜", "Quiet Night by the Lake"),
    )

    PURPOSES = (
        (("sono", "sleep", "dormir"), "助眠", "sleep"),
        (("foco", "focus", "estudo", "study", "trabalho"), "专注学习", "focus and study"),
        (("relax", "calma", "calm"), "放松", "relaxation"),
    )

    def __init__(self, pipeline: Pipeline, store: Store):
        self.pipeline = pipeline
        self.store = store

    @staticmethod
    def _fold(value: Any) -> str:
        text = unicodedata.normalize("NFKD", str(value or ""))
        return "".join(char for char in text if not unicodedata.combining(char)).lower()

    @classmethod
    def _localized_identity(cls, topic: str, metadata: dict[str, Any]) -> dict[str, str]:
        source = cls._fold(" ".join((topic, str(metadata.get("title", "")), str(metadata.get("description", "")))))
        scene_zh, scene_en = "静谧夜晚", "Quiet Night"
        for keywords, zh, en in cls.SCENES:
            if any(word in source for word in keywords):
                scene_zh, scene_en = zh, en
                break
        purpose_zh, purpose_en = "放松与专注", "relaxation and focus"
        for keywords, zh, en in cls.PURPOSES:
            if any(word in source for word in keywords):
                purpose_zh, purpose_en = zh, en
                break
        return {"scene_zh": scene_zh, "scene_en": scene_en,
                "purpose_zh": purpose_zh, "purpose_en": purpose_en}

    @staticmethod
    def _clean_title(value: str, limit: int) -> str:
        return re.sub(r"\s+", " ", value).strip()[:limit].rstrip(" -—|·")

    @staticmethod
    def _srt(text: str, seconds: int = 12) -> str:
        safe = " ".join(text.split())
        return f"1\n00:00:00,000 --> 00:00:{seconds:02d},000\n{safe}\n"

    def prepare(self, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(job_id)
        if not job or job.get("status") != "approved":
            raise ValueError("A produção precisa estar aprovada antes de preparar a Bilibili")
        metadata = job.get("metadata") or {}
        if not metadata.get("verification", {}).get("passed"):
            raise ValueError("O vídeo ainda não passou pela validação técnica")
        if not metadata.get("quality_gate", {}).get("passed"):
            raise ValueError("O vídeo ainda não passou pelo controle automático")

        out = Path(job["output_dir"])
        self.pipeline.verify_artifact_manifest(out)
        video = out / "video.mp4"
        cover = out / "bilibili-cover.jpg"
        self.pipeline.command([
            self.pipeline.settings.ffmpeg, "-y", "-ss", "2", "-i", str(video),
            "-frames:v", "1", "-vf", "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720",
            "-q:v", "2", str(cover),
        ])
        if not cover.is_file() or cover.stat().st_size < 1000:
            raise RuntimeError("A capa neutra da Bilibili não pôde ser gerada")

        identity = self._localized_identity(job["topic"], metadata)
        zh_title = self._clean_title(
            f"{identity['scene_zh']}｜原创 Lo-fi 氛围音乐 · {identity['purpose_zh']}", 80
        )
        en_title = self._clean_title(
            f"{identity['scene_en']} — Original Lo-fi Ambience for {identity['purpose_en']}", 100
        )
        duration_minutes = max(1, round(int(job["duration"]) / 60))
        zh_intro = f"欢迎来到{identity['scene_zh']}。这是原创的 Lo-fi 氛围音乐，适合{identity['purpose_zh']}。"
        en_intro = f"Welcome to {identity['scene_en']}. Original lo-fi ambience for {identity['purpose_en']}."
        (out / "bilibili-subtitles-zh-Hans.srt").write_text(self._srt(zh_intro), encoding="utf-8")
        (out / "bilibili-subtitles-en.srt").write_text(self._srt(en_intro), encoding="utf-8")

        package = {
            "mode": "prepared_not_uploaded",
            "platform": "bilibili",
            "created_at": datetime.now(UTC).isoformat(),
            "source_job_id": job_id,
            "source_rights": "inherits_approved_source_manifest",
            "localization": {
                "strategy": "curated_scene_and_intent_v1",
                "human_review_required": True,
                "titles": {"zh_hans": zh_title, "en": en_title,
                           "pt_br_source": self._clean_title(str(metadata.get("title") or job["topic"]), 100)},
                "descriptions": {
                    "zh_hans": f"原创 Lo-fi 氛围音乐与原创视觉。时长约 {duration_minutes} 分钟，适合{identity['purpose_zh']}。建议佩戴耳机。\n\n#原创音乐 #氛围音乐 #LoFi",
                    "en": f"Original lo-fi music and original visuals. Approximately {duration_minutes} minutes for {identity['purpose_en']}. Headphones recommended.\n\n#OriginalMusic #Ambience #LoFi",
                },
                "tags": ["原创音乐", "氛围音乐", "LoFi", "放松", "学习", "Original Music", "Ambience"],
            },
            "media": {
                "video": "video.mp4", "cover": "bilibili-cover.jpg",
                "subtitles": {"zh-Hans": "bilibili-subtitles-zh-Hans.srt", "en": "bilibili-subtitles-en.srt"},
                "rights_manifest": "asset-manifest.json", "integrity_manifest": "artifact-manifest.json",
            },
            "upload_plan": {
                "studio_url": "https://member.bilibili.com/platform/upload/video/frame",
                "international_studio_url": "https://studio.biliintl.com/",
                "type": "self_made_original",
                "category": "select_after_login",
                "steps": ["upload_video", "select_original_content", "upload_cover", "paste_localized_metadata",
                          "select_category", "upload_subtitles_after_draft", "review_and_submit"],
            },
            "manual_checks": [
                "Revisar chinês simplificado antes do primeiro envio",
                "Selecionar a categoria adequada no Creator Studio",
                "Confirmar que a conta aceita conteúdo internacional e música original",
                "Manter o vídeo como original e não adicionar elementos comerciais não declarados",
            ],
            "automatic_upload_allowed": False,
        }
        (out / "bilibili-upload.json").write_text(
            json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        names = [
            "video.mp4", "motion-overlay.mp4", "thumbnail.jpg", "thumbnail-a.jpg", "thumbnail-b.jpg",
            "subtitles.srt", "metadata.json", "agents.json", "asset-manifest.json", "render-report.json",
            "quality-gate.json", "youtube-upload.json", "vertical-short.mp4", "vertical-thumbnail.jpg",
            "vertical-package.json", "commerce-package.json", "pinterest-package.json",
            "bilibili-cover.jpg", "bilibili-subtitles-zh-Hans.srt", "bilibili-subtitles-en.srt",
            "bilibili-upload.json",
        ]
        manifest = self.pipeline.artifact_manifest(out, names)
        (out / "artifact-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.store.event(job_id, "bilibili", "Pacote bilíngue preparado localmente; nenhum upload foi realizado")
        return package
