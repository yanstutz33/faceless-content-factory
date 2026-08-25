from __future__ import annotations

import json
import hashlib
import math
import random
import re
import shutil
import subprocess
import sys
import textwrap
import unicodedata
import uuid
import wave
from array import array
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

    def diagnostics(self) -> dict[str, Any]:
        tools: dict[str, dict[str, Any]] = {}
        for name, executable in (("ffmpeg", self.settings.ffmpeg), ("ffprobe", self.settings.ffprobe)):
            try:
                proc = subprocess.run([executable, "-version"], text=True, capture_output=True, timeout=10)
                first_line = (proc.stdout or proc.stderr).splitlines()[0] if (proc.stdout or proc.stderr) else ""
                tools[name] = {"ok": proc.returncode == 0, "version": first_line[:180]}
            except (OSError, subprocess.TimeoutExpired) as exc:
                tools[name] = {"ok": False, "error": str(exc)}
        usage = shutil.disk_usage(self.settings.data_dir)
        return {
            "ok": tools["ffmpeg"]["ok"] and usage.free > 512 * 1024 * 1024,
            "studio_version": "0.6",
            "tools": tools,
            "validation_engine": "ffprobe" if tools["ffprobe"]["ok"] else "ffmpeg-fallback",
            "data_dir": str(self.settings.data_dir),
            "free_gb": round(usage.free / (1024 ** 3), 1),
            "publish_mode": "manual-safe",
            "narration_fallback": self.settings.narration_fallback,
        }

    def inspect_video(self, video: Path, expected_duration: int) -> dict[str, Any]:
        try:
            proc = subprocess.run(
                [self.settings.ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(video)],
                text=True,
                capture_output=True,
            )
        except OSError:
            return self.inspect_video_with_ffmpeg(video, expected_duration)
        if proc.returncode:
            return self.inspect_video_with_ffmpeg(video, expected_duration)
        try:
            probe = json.loads(proc.stdout)
            duration = float(probe.get("format", {}).get("duration", 0))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("FFprobe retornou um relatório inválido") from exc
        streams = probe.get("streams", [])
        video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
        audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
        tolerance = max(0.75, expected_duration * 0.02)
        if not video_stream or not audio_stream or abs(duration - expected_duration) > tolerance:
            raise RuntimeError(
                f"Validação de mídia falhou: duração={duration:.2f}s, vídeo={bool(video_stream)}, áudio={bool(audio_stream)}"
            )
        return {
            "passed": True,
            "validation_engine": "ffprobe",
            "duration_seconds": round(duration, 3),
            "expected_duration_seconds": expected_duration,
            "size_bytes": video.stat().st_size,
            "video": {
                "codec": video_stream.get("codec_name"),
                "width": video_stream.get("width"),
                "height": video_stream.get("height"),
                "pixel_format": video_stream.get("pix_fmt"),
            },
            "audio": {
                "codec": audio_stream.get("codec_name"),
                "sample_rate": audio_stream.get("sample_rate"),
                "channels": audio_stream.get("channels"),
            },
        }

    def inspect_video_with_ffmpeg(self, video: Path, expected_duration: int) -> dict[str, Any]:
        """Validate container metadata and decode a sample when ffprobe is unavailable."""
        metadata = subprocess.run(
            [self.settings.ffmpeg, "-hide_banner", "-i", str(video)],
            text=True,
            capture_output=True,
        )
        output = metadata.stderr or metadata.stdout
        duration_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", output)
        video_match = re.search(r"Video:\s*([^,\s]+).*?(\d{2,5})x(\d{2,5})", output)
        audio_match = re.search(r"Audio:\s*([^,\s]+).*?(\d+)\s*Hz.*?\b(mono|stereo|5\.1|7\.1)\b", output)
        if not duration_match or not video_match or not audio_match:
            raise RuntimeError("FFmpeg não conseguiu identificar duração, vídeo e áudio no arquivo final")
        hours, minutes, seconds = duration_match.groups()
        duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        tolerance = max(0.75, expected_duration * 0.02)
        if abs(duration - expected_duration) > tolerance:
            raise RuntimeError(f"Validação de mídia falhou: duração={duration:.2f}s")
        sample = subprocess.run(
            [self.settings.ffmpeg, "-v", "error", "-i", str(video), "-t", "1", "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"],
            text=True,
            capture_output=True,
        )
        if sample.returncode:
            raise RuntimeError(f"FFmpeg não conseguiu decodificar a amostra do vídeo: {sample.stderr[-1200:]}")
        channels = {"mono": 1, "stereo": 2, "5.1": 6, "7.1": 8}.get(audio_match.group(3))
        return {
            "passed": True,
            "validation_engine": "ffmpeg-fallback",
            "duration_seconds": round(duration, 3),
            "expected_duration_seconds": expected_duration,
            "size_bytes": video.stat().st_size,
            "video": {"codec": video_match.group(1), "width": int(video_match.group(2)), "height": int(video_match.group(3)), "pixel_format": None},
            "audio": {"codec": audio_match.group(1), "sample_rate": audio_match.group(2), "channels": channels},
        }

    @staticmethod
    def artifact_manifest(out: Path, names: list[str]) -> dict[str, Any]:
        files = []
        for name in names:
            path = out / name
            if not path.is_file():
                continue
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            files.append({"name": name, "size_bytes": path.stat().st_size, "sha256": digest.hexdigest()})
        return {"algorithm": "sha256", "files": files}

    def synthesize_narration(self, script: Path, output: Path) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "edge_tts", "--voice", "pt-BR-AntonioNeural", "--file", str(script), "--write-media", str(output)],
            text=True,
            capture_output=True,
            timeout=180,
        )
        if proc.returncode or not output.is_file() or output.stat().st_size == 0:
            raise RuntimeError(f"TTS neural indisponível: {proc.stderr[-900:]}")

    @staticmethod
    def _midi_frequency(note: int) -> float:
        return 440.0 * (2.0 ** ((note - 69) / 12.0))

    def create_lofi_loop(self, output: Path, sound_profile: str, seed_text: str = "") -> dict[str, Any]:
        """Create a deterministic original music loop without copyrighted source audio."""
        sample_rate, loop_seconds = 22_050, 12
        seed = int(hashlib.sha256(f"{sound_profile}:{seed_text}".encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)
        progressions = {
            "rain": ((53, 57, 60, 64), (52, 55, 59, 62), (57, 60, 64, 67), (55, 59, 62, 65)),
            "cozy": ((48, 52, 55, 59), (45, 48, 52, 55), (50, 53, 57, 60), (43, 47, 50, 53)),
            "cosmic": ((50, 53, 57, 60), (46, 50, 53, 57), (53, 57, 60, 64), (48, 52, 55, 59)),
            "focus": ((52, 55, 59, 62), (48, 52, 55, 59), (43, 47, 50, 52), (50, 52, 57, 62)),
        }
        chords = progressions.get(sound_profile, progressions["focus"])
        transpose = (-2, 0, 2)[seed % 3]
        bpm = 70 + seed % 13
        beat = 60.0 / bpm
        phase_offsets = [rng.random() * math.tau for _ in range(4)]
        samples = array("h")
        noise_state = seed or 1
        total = sample_rate * loop_seconds
        for index in range(total):
            t = index / sample_rate
            chord_index = min(3, int(t / (loop_seconds / 4)))
            chord_time = t % (loop_seconds / 4)
            chord_span = loop_seconds / 4
            pad_envelope = min(1.0, chord_time / 0.35, max(0.0, (chord_span - chord_time) / 0.45))
            chord = chords[chord_index]
            music = 0.0
            for tone_index, midi in enumerate(chord):
                frequency = self._midi_frequency(midi + transpose)
                wobble = 1.0 + 0.0025 * math.sin(math.tau * 0.18 * t + tone_index)
                music += math.sin(math.tau * frequency * wobble * t + phase_offsets[tone_index]) * 0.055
                music += math.sin(math.tau * frequency * 2 * t) * 0.009
            music *= pad_envelope

            beat_index = int(t / beat)
            beat_time = t % beat
            melody_note = chord[(beat_index + seed) % len(chord)] + 12
            pluck = math.sin(math.tau * self._midi_frequency(melody_note + transpose) * beat_time)
            music += pluck * math.exp(-beat_time * 4.8) * 0.085
            if beat_index % 4 in {0, 2}:
                music += math.sin(math.tau * (52 + 38 * math.exp(-beat_time * 16)) * beat_time) * math.exp(-beat_time * 12) * 0.20

            noise_state = (1_664_525 * noise_state + 1_013_904_223) & 0xFFFFFFFF
            noise = (noise_state / 0xFFFFFFFF) * 2 - 1
            if beat_index % 4 in {1, 3}:
                music += noise * math.exp(-beat_time * 18) * 0.075
            half_beat_time = t % (beat / 2)
            music += noise * math.exp(-half_beat_time * 42) * 0.012
            music += noise * 0.0035
            music *= 0.92 + 0.08 * math.sin(math.tau * 0.11 * t)
            samples.append(max(-32767, min(32767, int(music * 32767))))

        with wave.open(str(output), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(samples.tobytes())
        return {"style": "original_lofi_chill", "bpm": bpm, "loop_seconds": loop_seconds, "seed": seed}

    def create_ambient_audio(self, output: Path, duration: int, sound_profile: str, seed_text: str = "") -> dict[str, Any]:
        loop = output.with_name("lofi-original-loop.wav")
        music = self.create_lofi_loop(loop, sound_profile, seed_text)
        fade_duration = min(2, max(0.25, duration / 2))
        fade = f"afade=t=in:st=0:d={fade_duration},afade=t=out:st={max(0, duration - fade_duration)}:d={fade_duration}"
        command = [self.settings.ffmpeg, "-y", "-stream_loop", "-1", "-i", str(loop)]
        if sound_profile == "rain":
            command.extend(["-f", "lavfi", "-i", "anoisesrc=color=white:amplitude=0.010:sample_rate=22050"])
            filters = f"[1:a]highpass=f=900,lowpass=f=6500,volume=0.26[rain];[0:a]volume=0.88[music];[music][rain]amix=inputs=2:normalize=0,{fade}[a]"
            command.extend(["-filter_complex", filters, "-map", "[a]"])
            music["ambient_layer"] = "subtle_rain"
        else:
            command.extend(["-af", fade])
            music["ambient_layer"] = "none"
        command.extend(["-t", str(duration), "-ar", "22050", "-ac", "1", "-c:a", "pcm_s16le", str(output)])
        self.command(command)
        return music

    @staticmethod
    def filter_path(path: Path) -> str:
        return str(path.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")

    @staticmethod
    def visual_motion(sound_profile: str, width: int, height: int, fps: int) -> tuple[str, dict[str, Any]]:
        """Build a repeating ambient camera cycle instead of holding a still frame."""
        cycle_seconds = 12
        styles = {
            "rain": {"name": "chuva cinematográfica", "brightness": 0.006, "saturation": 0.82,
                     "contrast": 1.08, "zoom": 0.020, "pan_x": 12, "pan_y": 7},
            "cosmic": {"name": "pulso cósmico", "brightness": 0.012, "saturation": 1.08,
                       "contrast": 1.05, "zoom": 0.024, "pan_x": 14, "pan_y": 8},
            "cozy": {"name": "luz aconchegante", "brightness": 0.009, "saturation": 1.03,
                     "contrast": 1.03, "zoom": 0.018, "pan_x": 10, "pan_y": 6},
            "focus": {"name": "respiração de câmera", "brightness": 0.006, "saturation": 0.94,
                      "contrast": 1.04, "zoom": 0.016, "pan_x": 9, "pan_y": 5},
        }
        style = styles.get(sound_profile, styles["focus"])
        base_zoom = 1.035
        cycle = fps * cycle_seconds
        vf = (
            f"scale={int(width * 1.06)}:{int(height * 1.06)},"
            f"zoompan=z='{base_zoom}+{style['zoom']}*sin(2*PI*on/{cycle})':d=1:"
            f"x='iw/2-(iw/zoom/2)+{style['pan_x']}*sin(2*PI*on/{cycle})':"
            f"y='ih/2-(ih/zoom/2)+{style['pan_y']}*cos(2*PI*on/{cycle})':"
            f"s={width}x{height}:fps={fps},"
            f"eq=brightness='{style['brightness']}*sin(2*PI*t/{cycle_seconds})':"
            f"saturation={style['saturation']}:contrast={style['contrast']}:eval=frame,"
            "vignette=PI/5,format=yuv420p"
        )
        recipe = {
            "style": "ambient_seamless_loop",
            "format": "mp4_h264",
            "cycle_seconds": cycle_seconds,
            "profile": sound_profile,
            "atmosphere": style["name"],
            "effects": ["camera_breathing", "slow_pan", "light_pulse", "soft_vignette"],
            "source_policy": "original_or_commercially_licensed",
        }
        return vf, recipe

    def create_thumbnail(self, source: Path, output: Path, title: str, width: int, height: int, design: dict[str, Any], variant: str = "a") -> None:
        title_file = output.parent / "thumbnail-title.txt"
        eyebrow_file = output.parent / "thumbnail-eyebrow.txt"
        wrapped = "\n".join(textwrap.wrap(title.upper(), width=26 if variant == "b" else 30, max_lines=3, placeholder="…"))
        title_file.write_text(wrapped, encoding="utf-8")
        eyebrow_file.write_text(str(design.get("eyebrow", "AMBIENTE IMERSIVO")), encoding="utf-8")
        font_bold = self.filter_path(Path("C:/Windows/Fonts/georgiab.ttf"))
        font_ui = self.filter_path(Path("C:/Windows/Fonts/segoeuib.ttf"))
        title_path = self.filter_path(title_file)
        eyebrow_path = self.filter_path(eyebrow_file)
        font_size = max(30, round(height / 15))
        eyebrow_size = max(14, round(height / 42))
        if variant == "b":
            vf = (
                f"scale={width}:{height},drawbox=x=0:y=0:w=iw:h=ih:color=black@0.20:t=fill,"
                f"drawbox=x=iw*0.045:y=ih*0.08:w=iw*0.62:h=ih*0.52:color=#07101e@0.82:t=fill,"
                f"drawbox=x=iw*0.075:y=ih*0.18:w=iw*0.11:h=5:color=#ffb36a:t=fill,"
                f"drawtext=fontfile='{font_ui}':textfile='{eyebrow_path}':fontcolor=#ffb36a:fontsize={eyebrow_size}:x=w*0.075:y=h*0.12,"
                f"drawtext=fontfile='{font_bold}':textfile='{title_path}':fontcolor=white:fontsize={font_size}:x=w*0.075:y=h*0.25:line_spacing=10"
            )
        else:
            vf = (
                f"scale={width}:{height},drawbox=x=0:y=0:w=iw:h=ih:color=black@0.12:t=fill,"
                f"drawbox=x=0:y=ih*0.48:w=iw:h=ih*0.52:color=#07101e@0.78:t=fill,"
                f"drawbox=x=iw*0.06:y=ih*0.58:w=iw*0.08:h=5:color=#77e0bd:t=fill,"
                f"drawtext=fontfile='{font_ui}':textfile='{eyebrow_path}':fontcolor=#77e0bd:fontsize={eyebrow_size}:x=w*0.06:y=h*0.52,"
                f"drawtext=fontfile='{font_bold}':textfile='{title_path}':fontcolor=white:fontsize={font_size}:x=w*0.06:y=h*0.64:line_spacing=10"
            )
        self.command([self.settings.ffmpeg, "-y", "-i", str(source), "-vf", vf, "-frames:v", "1", "-q:v", "2", str(output)])

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

    def _create_backgrounds(self, job: dict[str, Any], out: Path, width: int, height: int,
                            sound_profile: str = "focus") -> list[Path]:
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
            starter_name = {"rain": "lofi-rainy-cafe.jpg", "cosmic": "lofi-cosmic-lounge.jpg",
                            "cozy": "lofi-cozy-study.jpg", "focus": "lofi-cozy-study.jpg"}.get(sound_profile, "lofi-cozy-study.jpg")
            starter = self.settings.root / "assets" / "starter" / starter_name
            if starter.is_file():
                self.command([self.settings.ffmpeg, "-y", "-i", str(starter), "-vf",
                              f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}",
                              "-frames:v", "1", str(background)])
                (out / "asset-manifest.json").write_text(json.dumps([{
                    "name": starter.stem, "path": str(starter), "license_type": "original_ai_generated",
                    "source_url": None, "approved": True,
                }], ensure_ascii=False, indent=2), encoding="utf-8")
            else:
                self.command([self.settings.ffmpeg, "-y", "-f", "lavfi", "-i",
                              f"color=c=#071426:s={width}x{height},geq=r='8+18*Y/H':g='18+36*Y/H':b='38+50*Y/H',noise=alls=7:allf=t+u",
                              "-frames:v", "1", str(background)])
            backgrounds.append(background)
            self.store.event(job["id"], "assets", f"Cena visual original '{starter_name}' aplicada automaticamente")
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
            sound_profile = plan["visual"].get("sound_profile", "focus")
            backgrounds = self._create_backgrounds(job, out, profile["width"], profile["height"], sound_profile)
            audio = out / "ambient.wav"
            music = self.create_ambient_audio(audio, job["duration"], sound_profile, job["topic"])
            metadata["sound_profile"] = sound_profile
            metadata["music"] = music
            self.store.event(job_id, "sound", f"Trilha lo-fi original gerada a {music['bpm']} BPM; perfil '{sound_profile}'")
            if job["narration"]:
                narration = out / "narration.mp3"
                try:
                    self.synthesize_narration(out / "script.txt", narration)
                    mixed = out / "ambient-with-narration.wav"
                    self.command([self.settings.ffmpeg, "-y", "-i", str(audio), "-i", str(narration),
                                  "-filter_complex", "[0:a]volume=0.52[bed];[1:a]adelay=1000:all=1[voice];[bed][voice]amix=inputs=2:duration=first:normalize=0[mix]",
                                  "-map", "[mix]", "-t", str(job["duration"]), "-c:a", "pcm_s16le", str(mixed)])
                    audio = mixed
                    metadata["narration_status"] = "rendered"
                    self.store.event(job_id, "narration", "Narração neural gerada e mixada")
                except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                    if not self.settings.narration_fallback:
                        raise
                    metadata["narration_status"] = "ambient_fallback"
                    plan["review"]["score"] = max(0, int(plan["review"]["score"]) - 6)
                    plan["review"]["warnings"].append("A voz neural estava indisponível; o pacote foi concluído somente com ambientação.")
                    self.store.event(job_id, "narration_fallback", "Voz neural indisponível; pacote concluído com ambientação")
            self.store.update(job_id, "rendering", metadata=metadata, progress=62)

            video = out / "video.mp4"
            width, height, fps = profile["width"], profile["height"], profile["fps"]
            vf, motion = self.visual_motion(sound_profile, width, height, fps)
            metadata["motion"] = motion
            self.store.event(job_id, "motion", f"Loop visual de {motion['cycle_seconds']} s aplicado: {motion['atmosphere']}")
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
            thumbnail_a = out / "thumbnail-a.jpg"
            thumbnail_b = out / "thumbnail-b.jpg"
            thumbnail = out / "thumbnail.jpg"
            self.create_thumbnail(backgrounds[0], thumbnail_a, job["topic"], width, height, plan["visual"]["thumbnail"], "a")
            self.create_thumbnail(backgrounds[0], thumbnail_b, job["topic"], width, height, plan["visual"]["thumbnail"], "b")
            shutil.copy2(thumbnail_a, thumbnail)
            thumbnail_design = {
                "selected": "a",
                "variants": [
                    {"id": "a", "file": "thumbnail-a.jpg", "style": "editorial inferior", "accent": "#77e0bd"},
                    {"id": "b", "file": "thumbnail-b.jpg", "style": "cartaz superior", "accent": "#ffb36a"},
                ],
                "brief": plan["visual"]["thumbnail"],
            }
            (out / "thumbnail-design.json").write_text(json.dumps(thumbnail_design, ensure_ascii=False, indent=2), encoding="utf-8")

            media_report = self.inspect_video(video, job["duration"])
            (out / "render-report.json").write_text(json.dumps(media_report, ensure_ascii=False, indent=2), encoding="utf-8")
            self.store.event(job_id, "verification", f"Vídeo, áudio e duração validados com {media_report['validation_engine']}")

            self.store.update(job_id, "reviewing", metadata=metadata, progress=88)
            checklist = {
                "mode": "manual-safe", "ready_for_review": True, "platform_upload_performed": False,
                "quality_score": plan["review"]["score"], "compliance": plan["compliance"],
                "media_validation": media_report,
                "narration_requested": job["narration"],
                "narration_status": metadata.get("narration_status", "not_requested"),
                "steps": ["Assista aos 30 segundos iniciais", "Confira thumbnail, título e direitos", "Aprove no painel", "Envie manualmente ao YouTube Studio"],
            }
            (out / "publication-package.json").write_text(json.dumps(checklist, ensure_ascii=False, indent=2), encoding="utf-8")
            metadata["files"] = {"video": "video.mp4", "thumbnail": "thumbnail.jpg", "subtitles": "subtitles.srt" if job["subtitles"] else None,
                                 "agents": "agents.json", "publication": "publication-package.json",
                                 "render_report": "render-report.json", "manifest": "artifact-manifest.json"}
            metadata["thumbnail_variants"] = thumbnail_design["variants"]
            metadata["selected_thumbnail"] = "a"
            metadata["verification"] = media_report
            metadata["quality"] = plan["review"]
            (out / "agents.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
            (out / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            manifest = self.artifact_manifest(out, ["video.mp4", "thumbnail.jpg", "thumbnail-a.jpg", "thumbnail-b.jpg", "thumbnail-design.json", "subtitles.srt", "metadata.json", "agents.json", "publication-package.json", "render-report.json"])
            (out / "artifact-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
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

    def select_thumbnail(self, job_id: str, variant: str) -> None:
        variant = variant.lower()
        if variant not in {"a", "b"}:
            raise ValueError("Variante de thumbnail inválida")
        job = self.store.get_job(job_id)
        if not job or job["status"] not in {"awaiting_approval", "approved", "rejected"}:
            raise ValueError("A produção ainda não tem thumbnails disponíveis")
        out = Path(job["output_dir"])
        source = out / f"thumbnail-{variant}.jpg"
        if not source.is_file():
            raise ValueError("Variante de thumbnail não encontrada")
        shutil.copy2(source, out / "thumbnail.jpg")
        metadata = dict(job["metadata"])
        metadata["selected_thumbnail"] = variant
        (out / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        design_path = out / "thumbnail-design.json"
        if design_path.is_file():
            design = json.loads(design_path.read_text(encoding="utf-8"))
            design["selected"] = variant
            design_path.write_text(json.dumps(design, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest = self.artifact_manifest(out, ["video.mp4", "thumbnail.jpg", "thumbnail-a.jpg", "thumbnail-b.jpg", "thumbnail-design.json", "subtitles.srt", "metadata.json", "agents.json", "publication-package.json", "render-report.json"])
        (out / "artifact-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        self.store.set_thumbnail_variant(job_id, variant)
        self.store.update(job_id, job["status"], metadata, progress=job["progress"], quality_score=job.get("quality_score"))
        self.store.event(job_id, "thumbnail", f"Thumbnail {variant.upper()} selecionada para publicação manual")
