from __future__ import annotations

import json
import re
import subprocess
import sys
import unicodedata
import uuid
from pathlib import Path
from typing import Any

from .agents import ContentCrew, PROFILES
from .config import Settings
from .store import Store


def safe_slug(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")[:42] or "ambient"


def srt_timestamp(seconds: float) -> str:
    millis = round(seconds * 1000)
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


class Pipeline:
    def __init__(self, settings: Settings, store: Store, crew: ContentCrew | None = None):
        self.settings = settings
        self.store = store
        self.crew = crew or ContentCrew()
        (settings.data_dir / "jobs").mkdir(parents=True, exist_ok=True)

    def command(self, args: list[str]) -> None:
        proc = subprocess.run(args, cwd=self.settings.root, text=True, capture_output=True)
        if proc.returncode:
            raise RuntimeError(f"FFmpeg falhou ({proc.returncode}): {proc.stderr[-3000:]}")

    def create(self, topic: str, duration: int, narration: bool = False, subtitles: bool = True,
               profile: str = "youtube_long", source_asset: str | None = None, priority: int = 2,
               source_assets: list[dict[str, Any]] | None = None) -> str:
        topic = " ".join(topic.split()).strip()
        if len(topic) < 3:
            raise ValueError("Descreva um tema com pelo menos 3 caracteres")
        if profile not in PROFILES:
            raise ValueError("Perfil de saída inválido")
        duration = max(5, min(int(duration), PROFILES[profile]["max_duration"]))
        assets = list(source_assets or [])
        if source_asset:
            assets.append({"name": Path(source_asset).stem, "path": source_asset, "license_type": "fornecido pelo usuário",
                           "source_url": None, "approved": True})
        normalized_assets = []
        for asset in assets[:12]:
            source = Path(str(asset.get("path", ""))).expanduser().resolve()
            if not source.is_file() or source.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                raise ValueError(f"Asset inválido: {source}")
            normalized_assets.append({**asset, "path": str(source)})
        job_id = f"{safe_slug(topic)}-{uuid.uuid4().hex[:8]}"
        output_dir = self.settings.data_dir / "jobs" / job_id
        output_dir.mkdir(parents=True)
        self.store.create_job({"id": job_id, "topic": topic, "duration": duration, "narration": narration,
                               "subtitles": subtitles, "profile": profile, "priority": priority,
                               "source_asset": normalized_assets[0]["path"] if normalized_assets else None,
                               "source_assets": normalized_assets, "output_dir": str(output_dir)})
        return job_id

    def generate_plan(self, topic: str, duration: int, profile: str = "youtube_long", narration: bool = False) -> dict[str, Any]:
        return self.crew.run(topic, duration, profile, narration)

    def _create_backgrounds(self, job: dict[str, Any], out: Path, width: int, height: int) -> list[Path]:
        assets = job.get("source_assets") or []
        backgrounds: list[Path] = []
        if assets:
            for index, asset in enumerate(assets):
                background = out / f"scene-{index + 1:02}.jpg"
                self.command([self.settings.ffmpeg, "-y", "-i", asset["path"], "-vf",
                              f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}",
                              "-frames:v", "1", str(background)])
                backgrounds.append(background)
            (out / "asset-manifest.json").write_text(json.dumps(assets, ensure_ascii=False, indent=2), encoding="utf-8")
            self.store.event(job["id"], "assets", f"{len(backgrounds)} asset(s) licenciado(s) enquadrado(s)")
        else:
            background = out / "background.jpg"
            self.command([self.settings.ffmpeg, "-y", "-f", "lavfi", "-i",
                          f"color=c=#071426:s={width}x{height},geq=r='8+18*Y/H':g='18+36*Y/H':b='38+50*Y/H',noise=alls=7:allf=t+u",
                          "-frames:v", "1", str(background)])
            backgrounds.append(background)
            self.store.event(job["id"], "assets", "Cena visual original gerada localmente")
        return backgrounds

    def run(self, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(job_id)
        if not job:
            raise KeyError(job_id)
        if job["status"] not in {"queued", "failed", "rejected"}:
            return job
        out = Path(job["output_dir"])
        profile = PROFILES.get(job.get("profile"), PROFILES["youtube_long"])
        try:
            self.store.update(job_id, "planning", progress=8)
            plan = self.generate_plan(job["topic"], job["duration"], job.get("profile", "youtube_long"), job["narration"])
            (out / "agents.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
            metadata = {**plan["seo"], "chapters": plan["script"]["chapters"], "production": plan["production"],
                        "agents": plan, "quality": plan["review"]}
            (out / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            (out / "script.txt").write_text(plan["script"]["intro"] + "\n", encoding="utf-8")
            for agent in ("research", "strategy", "script", "visual", "seo", "compliance"):
                self.store.event(job_id, agent, f"Agente {agent} concluiu sua entrega")
            self.store.update(job_id, "planning", metadata=metadata, progress=28)

            if job["subtitles"]:
                end = min(job["duration"], 9)
                subtitle = f"1\n00:00:00,000 --> {srt_timestamp(end)}\n{plan['script']['intro']}\n"
                (out / "subtitles.srt").write_text(subtitle, encoding="utf-8")
                self.store.event(job_id, "subtitles", "Legenda SRT criada")

            self.store.update(job_id, "assets", metadata=metadata, progress=40)
            backgrounds = self._create_backgrounds(job, out, profile["width"], profile["height"])
            audio = out / "ambient.wav"
            self.command([self.settings.ffmpeg, "-y", "-f", "lavfi", "-i", "anoisesrc=color=brown:amplitude=0.035:sample_rate=44100",
                          "-f", "lavfi", "-i", "sine=frequency=110:sample_rate=44100",
                          "-filter_complex", "[1:a]volume=0.012[t];[0:a][t]amix=inputs=2,afade=t=in:st=0:d=2,afade=t=out:st=" + str(max(0, job["duration"] - 2)) + ":d=2[a]",
                          "-map", "[a]", "-t", str(job["duration"]), "-c:a", "pcm_s16le", str(audio)])
            if job["narration"]:
                narration = out / "narration.mp3"
                proc = subprocess.run([sys.executable, "-m", "edge_tts", "--voice", "pt-BR-AntonioNeural",
                                       "--file", str(out / "script.txt"), "--write-media", str(narration)], text=True, capture_output=True)
                if proc.returncode:
                    raise RuntimeError(f"TTS neural indisponível; gere sem narração ou verifique a conexão: {proc.stderr[-900:]}")
                mixed = out / "ambient-with-narration.wav"
                self.command([self.settings.ffmpeg, "-y", "-i", str(audio), "-i", str(narration),
                              "-filter_complex", "[0:a]volume=0.52[bed];[1:a]adelay=1000:all=1[voice];[bed][voice]amix=inputs=2:duration=first:normalize=0[mix]",
                              "-map", "[mix]", "-t", str(job["duration"]), "-c:a", "pcm_s16le", str(mixed)])
                audio = mixed
                self.store.event(job_id, "narration", "Narração neural gerada e mixada")
            self.store.update(job_id, "rendering", metadata=metadata, progress=62)

            video = out / "video.mp4"
            width, height, fps = profile["width"], profile["height"], profile["fps"]
            scaled_w, scaled_h = int(width * 1.05), int(height * 1.05)
            vf = f"scale={scaled_w}:{scaled_h},zoompan=z='min(zoom+0.00008,1.05)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps},format=yuv420p"
            if len(backgrounds) == 1:
                self.command([self.settings.ffmpeg, "-y", "-loop", "1", "-i", str(backgrounds[0]), "-i", str(audio),
                              "-vf", vf, "-t", str(job["duration"]), "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                              "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(video)])
            else:
                scene_dir = out / "render-scenes"
                scene_dir.mkdir(exist_ok=True)
                clips = []
                base_duration = job["duration"] / len(backgrounds)
                for index, background in enumerate(backgrounds):
                    clip = scene_dir / f"clip-{index + 1:02}.mp4"
                    clips.append(clip)
                    self.command([self.settings.ffmpeg, "-y", "-loop", "1", "-i", str(background), "-vf", vf,
                                  "-t", f"{base_duration:.3f}", "-an", "-c:v", "libx264", "-preset", "veryfast",
                                  "-crf", "22", "-pix_fmt", "yuv420p", str(clip)])
                concat_file = scene_dir / "concat.txt"
                concat_file.write_text("\n".join(f"file '{clip.as_posix()}'" for clip in clips), encoding="utf-8")
                self.command([self.settings.ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
                              "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-t", str(job["duration"]),
                              "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(video)])
                self.store.event(job_id, "rendering", f"Composição multicena concluída com {len(backgrounds)} cenas")
            thumbnail = out / "thumbnail.jpg"
            self.command([self.settings.ffmpeg, "-y", "-i", str(video), "-frames:v", "1", "-q:v", "2", str(thumbnail)])

            self.store.update(job_id, "reviewing", metadata=metadata, progress=88)
            checklist = {
                "mode": "manual-safe", "ready_for_review": True, "platform_upload_performed": False,
                "quality_score": plan["review"]["score"], "compliance": plan["compliance"],
                "steps": ["Assista aos 30 segundos iniciais", "Confira thumbnail, título e direitos", "Aprove no painel", "Envie manualmente ao YouTube Studio"],
            }
            (out / "publication-package.json").write_text(json.dumps(checklist, ensure_ascii=False, indent=2), encoding="utf-8")
            metadata["files"] = {"video": "video.mp4", "thumbnail": "thumbnail.jpg", "subtitles": "subtitles.srt" if job["subtitles"] else None,
                                 "agents": "agents.json", "publication": "publication-package.json"}
            self.store.update(job_id, "awaiting_approval", metadata=metadata, progress=100,
                              quality_score=plan["review"]["score"])
            self.store.event(job_id, "complete", "Pacote revisado e pronto; nenhum upload foi realizado")
            return self.store.get_job(job_id) or {}
        except Exception as exc:
            self.store.update(job_id, "failed", error=str(exc), progress=0)
            self.store.event(job_id, "failed", str(exc))
            raise

    def approve(self, job_id: str) -> None:
        job = self.store.get_job(job_id)
        if not job or job["status"] not in {"awaiting_approval", "approved"}:
            raise ValueError("A produção ainda não está pronta para aprovação")
        self.store.update(job_id, "approved", job["metadata"], progress=100, quality_score=job.get("quality_score"))
        self.store.event(job_id, "approved", "Aprovado para publicação manual")

    def reject(self, job_id: str, reason: str) -> None:
        job = self.store.get_job(job_id)
        if not job or job["status"] not in {"awaiting_approval", "approved"}:
            raise ValueError("A produção não está em revisão")
        self.store.update(job_id, "rejected", job["metadata"], error=reason or "Revisão solicitada", progress=100,
                          quality_score=job.get("quality_score"))
        self.store.event(job_id, "rejected", reason or "Revisão solicitada")
