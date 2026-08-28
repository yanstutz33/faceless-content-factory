from __future__ import annotations

import json
import hashlib
import math
import os
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
from .teams import DEFAULT_TEAM_ID, get_team
from .config import Settings
from .creative import CreativeDirector, MOTION_LABELS, MUSIC_ARRANGEMENTS
from .llm import OpenAIPlanEnhancer
from .store import Store


STARTER_SCENES = {
    "rain": ("lofi-rainy-cafe.jpg", "lofi-night-train.jpg", "lofi-record-store.jpg"),
    "cozy": ("lofi-cozy-study.jpg", "lofi-lakeside-cabin.jpg", "lofi-record-store.jpg"),
    "cosmic": ("lofi-cosmic-lounge.jpg", "lofi-lunar-observatory.jpg"),
    "focus": ("lofi-cozy-study.jpg", "lofi-night-train.jpg", "lofi-lakeside-cabin.jpg", "lofi-record-store.jpg"),
}

SUPPORTED_ASSET_LICENSES = {
    "original", "commercial_license", "public_domain", "cc0", "provider_generated",
    "original_ai_generated", "user_confirmed",
}


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
        self.crew = crew or ContentCrew(OpenAIPlanEnhancer(settings.openai_api_key, settings.openai_model))
        self.creative = CreativeDirector()
        (settings.data_dir / "jobs").mkdir(parents=True, exist_ok=True)

    def command(self, args: list[str]) -> None:
        proc = subprocess.run(args, cwd=self.settings.root, text=True, capture_output=True)
        if proc.returncode:
            raise RuntimeError(f"FFmpeg falhou ({proc.returncode}): {proc.stderr[-3000:]}")

    @staticmethod
    def _process_running(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False
        return True

    def acquire_job_lock(self, out: Path) -> tuple[Path, str] | None:
        """Reserve a job across server processes and recover abandoned locks."""
        lock_path = out / ".render.lock"
        token = uuid.uuid4().hex
        for _ in range(2):
            try:
                descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    lock = json.loads(lock_path.read_text(encoding="utf-8"))
                    owner_pid = int(lock.get("pid", 0))
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    owner_pid = 0
                if self._process_running(owner_pid):
                    return None
                lock_path.unlink(missing_ok=True)
                continue
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump({"pid": os.getpid(), "token": token}, handle)
                handle.flush()
                os.fsync(handle.fileno())
            return lock_path, token
        return None

    @staticmethod
    def release_job_lock(lock: tuple[Path, str] | None) -> None:
        if not lock:
            return
        lock_path, token = lock
        try:
            current = json.loads(lock_path.read_text(encoding="utf-8"))
            if current.get("token") == token:
                lock_path.unlink(missing_ok=True)
        except (OSError, json.JSONDecodeError):
            return

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
            "studio_version": "2.0",
            "tools": tools,
            "validation_engine": "ffprobe" if tools["ffprobe"]["ok"] else "ffmpeg-fallback",
            "data_dir": str(self.settings.data_dir),
            "free_gb": round(usage.free / (1024 ** 3), 1),
            "publish_mode": "manual-safe",
            "render_safety": {"atomic_promotion": True, "duplicate_claim": True,
                              "checksum_before_release": True},
            "narration_fallback": self.settings.narration_fallback,
            "llm_provider": {"configured": bool(self.settings.openai_api_key), "model": self.settings.openai_model},
            "youtube_connector": {"configured": bool(self.settings.youtube_client_secrets_file), "mode": "manual-safe"},
            "local_voice_fallback": {"enabled": self.settings.local_tts_fallback,
                                     "available": self.local_voice_available()},
        }

    def local_voice_available(self) -> bool:
        if not self.settings.local_tts_fallback or os.name != "nt":
            return False
        check = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
             "Add-Type -AssemblyName System.Speech;$v=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
             "$n=$v.GetInstalledVoices().Count;$v.Dispose();Write-Output $n"],
            text=True, capture_output=True, timeout=15,
        )
        try:
            return check.returncode == 0 and int(check.stdout.strip().splitlines()[-1]) > 0
        except (ValueError, IndexError):
            return False

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
        decode_samples = sorted({0.0, max(0.0, duration / 2 - 1), max(0.0, duration - 2)})
        for moment in decode_samples:
            sample = subprocess.run(
                [self.settings.ffmpeg, "-v", "error", "-ss", f"{moment:.3f}", "-i", str(video), "-t", "2",
                 "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"],
                text=True,
                capture_output=True,
            )
            if sample.returncode:
                raise RuntimeError(
                    f"FFmpeg não conseguiu decodificar o vídeo em {moment:.1f}s: {sample.stderr[-1200:]}"
                )
        channels = {"mono": 1, "stereo": 2, "5.1": 6, "7.1": 8}.get(audio_match.group(3))
        return {
            "passed": True,
            "validation_engine": "ffmpeg-fallback",
            "duration_seconds": round(duration, 3),
            "expected_duration_seconds": expected_duration,
            "size_bytes": video.stat().st_size,
            "decode_samples_seconds": decode_samples,
            "video": {"codec": video_match.group(1), "width": int(video_match.group(2)), "height": int(video_match.group(3)), "pixel_format": None},
            "audio": {"codec": audio_match.group(1), "sample_rate": audio_match.group(2), "channels": channels},
        }

    def quality_gate(self, video: Path, expected_duration: int, metadata: dict[str, Any],
                     technical_report: dict[str, Any] | None = None) -> dict[str, Any]:
        """Fast, deterministic checks that keep broken renders out of the approval queue."""
        technical_report = technical_report or self.inspect_video(video, expected_duration)
        duration = max(1.0, float(technical_report.get("duration_seconds") or expected_duration))
        sample_times = sorted({0.5, max(0.5, duration / 2), max(0.5, duration - 0.5)})
        frames: list[bytes] = []
        for moment in sample_times:
            proc = subprocess.run([
                self.settings.ffmpeg, "-v", "error", "-ss", f"{moment:.3f}", "-i", str(video),
                "-vf", "scale=160:90", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-",
            ], capture_output=True)
            if proc.returncode == 0 and len(proc.stdout) == 160 * 90:
                frames.append(proc.stdout)
        brightness = round(sum(sum(frame) / len(frame) for frame in frames) / max(1, len(frames)), 2)
        changed_ratios = []
        for first, second in zip(frames, frames[1:]):
            changed_ratios.append(sum(abs(a - b) >= 2 for a, b in zip(first, second)) / len(first))
        motion_ratio = round(max(changed_ratios, default=0), 5)

        volume = subprocess.run([
            self.settings.ffmpeg, "-hide_banner", "-t", str(min(30, expected_duration)), "-i", str(video),
            "-vn", "-af", "volumedetect", "-f", "null", "-",
        ], text=True, capture_output=True)
        volume_text = volume.stderr or volume.stdout
        mean_match = re.search(r"mean_volume:\s*(-?[\d.]+) dB", volume_text)
        max_match = re.search(r"max_volume:\s*(-?[\d.]+) dB", volume_text)
        mean_db = float(mean_match.group(1)) if mean_match else None
        max_db = float(max_match.group(1)) if max_match else None
        camera_motion = metadata.get("motion", {}).get("camera_motion")
        checks = [
            {"id": "container", "label": "Vídeo, áudio e duração", "passed": bool(technical_report.get("passed"))},
            {"id": "frames", "label": "Amostras visuais decodificadas", "passed": len(frames) >= 2,
             "value": f"{len(frames)}/{len(sample_times)}"},
            {"id": "brightness", "label": "Imagem sem tela preta ou estourada", "passed": 4 <= brightness <= 245,
             "value": brightness},
            {"id": "motion", "label": "Movimento visual presente", "passed": motion_ratio >= 0.001,
             "value": motion_ratio},
            {"id": "camera", "label": "Câmera fixa", "passed": camera_motion == "none", "value": camera_motion},
            {"id": "audio", "label": "Áudio audível sem clipping", "passed": mean_db is not None and max_db is not None and
             -38 <= mean_db <= -10 and -30 <= max_db <= -0.5, "value": {"mean_db": mean_db, "max_db": max_db}},
        ]
        failed = [check for check in checks if not check["passed"]]
        return {
            "passed": not failed,
            "score": round(100 * (len(checks) - len(failed)) / len(checks)),
            "checks": checks,
            "failed_check_ids": [check["id"] for check in failed],
            "sample_times": sample_times,
            "policy": "ambient_fixed_camera_v1",
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

    @staticmethod
    def verify_artifact_checksum(out: Path, name: str = "video.mp4") -> dict[str, Any]:
        manifest_path = out / "artifact-manifest.json"
        if not manifest_path.is_file():
            raise ValueError("Manifesto de integridade ausente; execute a auditoria novamente")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("Manifesto de integridade inválido; execute a auditoria novamente") from exc
        expected = next((item for item in manifest.get("files", []) if item.get("name") == name), None)
        artifact = out / name
        if not expected or not artifact.is_file():
            raise ValueError(f"{name} não está registrado no manifesto de integridade")
        digest = hashlib.sha256()
        with artifact.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        current = {"name": name, "size_bytes": artifact.stat().st_size, "sha256": digest.hexdigest()}
        if current["size_bytes"] != int(expected.get("size_bytes", -1)) or current["sha256"] != expected.get("sha256"):
            raise ValueError(f"{name} mudou após a validação; renderize ou audite novamente")
        return current

    def synthesize_narration(self, script: Path, output: Path) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "edge_tts", "--voice", "pt-BR-AntonioNeural", "--file", str(script), "--write-media", str(output)],
            text=True,
            capture_output=True,
            timeout=180,
        )
        if not proc.returncode and output.is_file() and output.stat().st_size > 0:
            return
        if not self.settings.local_tts_fallback or os.name != "nt":
            raise RuntimeError(f"TTS neural indisponível: {proc.stderr[-900:]}")
        wav_output = output.with_name("narration-local.wav")
        text = script.read_text(encoding="utf-8").replace("'", "''")
        destination = str(wav_output.resolve()).replace("'", "''")
        powershell = (
            "Add-Type -AssemblyName System.Speech;"
            "$voice=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
            "$voice.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::Male,"
            "[System.Speech.Synthesis.VoiceAge]::Adult,0,[Globalization.CultureInfo]'pt-BR');"
            f"$voice.SetOutputToWaveFile('{destination}');$voice.Speak('{text}');$voice.Dispose()"
        )
        local = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", powershell],
                               text=True, capture_output=True, timeout=180)
        if local.returncode or not wav_output.is_file() or wav_output.stat().st_size == 0:
            raise RuntimeError(f"TTS neural e voz local indisponíveis: {(local.stderr or proc.stderr)[-900:]}")
        self.command([self.settings.ffmpeg, "-y", "-i", str(wav_output), "-c:a", "libmp3lame", "-b:a", "96k", str(output)])

    @staticmethod
    def _midi_frequency(note: int) -> float:
        return 440.0 * (2.0 ** ((note - 69) / 12.0))

    def create_lofi_loop(self, output: Path, sound_profile: str, seed_text: str = "",
                         creative_dna: dict[str, Any] | None = None) -> dict[str, Any]:
        """Create a deterministic original music loop without copyrighted source audio."""
        creative_dna = creative_dna or {}
        sample_rate, loop_seconds = 22_050, 16
        seed = int(creative_dna.get("seed") or int(hashlib.sha256(f"{sound_profile}:{seed_text}".encode()).hexdigest()[:8], 16))
        rng = random.Random(seed)
        progressions = {
            "rain": ((53, 57, 60, 64), (52, 55, 59, 62), (57, 60, 64, 67), (55, 59, 62, 65)),
            "cozy": ((48, 52, 55, 59), (45, 48, 52, 55), (50, 53, 57, 60), (43, 47, 50, 53)),
            "cosmic": ((50, 53, 57, 60), (46, 50, 53, 57), (53, 57, 60, 64), (48, 52, 55, 59)),
            "focus": ((52, 55, 59, 62), (48, 52, 55, 59), (43, 47, 50, 52), (50, 52, 57, 62)),
        }
        base_chords = progressions.get(sound_profile, progressions["focus"])
        progression_variant = int(creative_dna.get("progression_variant", (seed >> 3) % len(base_chords))) % len(base_chords)
        chords = tuple(base_chords[(index + progression_variant) % len(base_chords)] for index in range(len(base_chords)))
        arrangement = self.creative.arrangement(str(creative_dna.get("music_arrangement", "")))
        if not creative_dna.get("music_arrangement"):
            arrangement = MUSIC_ARRANGEMENTS[(seed >> 7) % len(MUSIC_ARRANGEMENTS)]
        transpose = int(creative_dna.get("key_shift", (-2, 0, 2)[seed % 3]))
        bpm = int(creative_dna.get("bpm", 70 + seed % 13))
        melody_density = float(creative_dna.get("melody_density", .68))
        swing = float(creative_dna.get("swing", .07))
        texture = str(creative_dna.get("texture", "soft_tape"))
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
                music += math.sin(math.tau * frequency * wobble * t + phase_offsets[tone_index]) * arrangement["pad"]
                music += math.sin(math.tau * frequency * 2 * t) * arrangement["harmonic"]
            music *= pad_envelope

            beat_index = int(t / beat)
            beat_time = (t + (swing * beat if beat_index % 2 else 0)) % beat
            melody_note = chord[(beat_index + seed) % len(chord)] + 12
            pluck = math.sin(math.tau * self._midi_frequency(melody_note + transpose) * beat_time)
            melody_on = (((beat_index * 1_103_515_245 + seed) & 0xFFFF) / 0xFFFF) <= melody_density
            if melody_on:
                music += pluck * math.exp(-beat_time * arrangement["decay"]) * arrangement["pluck"]
            bass_note = chord[0] - 12 + transpose
            bass = math.sin(math.tau * self._midi_frequency(bass_note) * beat_time)
            music += bass * math.exp(-beat_time * 3.2) * arrangement["bass"]
            if beat_index % 4 in {0, 2}:
                music += math.sin(math.tau * (52 + 38 * math.exp(-beat_time * 16)) * beat_time) * math.exp(-beat_time * 12) * 0.20

            noise_state = (1_664_525 * noise_state + 1_013_904_223) & 0xFFFFFFFF
            noise = (noise_state / 0xFFFFFFFF) * 2 - 1
            if beat_index % 4 in {1, 3}:
                music += noise * math.exp(-beat_time * 18) * arrangement["snare"]
            half_beat_time = t % (beat / 2)
            music += noise * math.exp(-half_beat_time * 42) * 0.012
            texture_gain = {"clean_room": .0015, "soft_tape": .0035, "vinyl_dust": .0055,
                            "warm_noise": .0045, "air_hiss": .0028}.get(texture, .0035)
            music += noise * texture_gain
            music *= 0.92 + 0.08 * math.sin(math.tau * 0.11 * t)
            samples.append(max(-32767, min(32767, int(music * 32767))))

        with wave.open(str(output), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(samples.tobytes())
        return {"style": "original_lofi_chill", "bpm": bpm, "loop_seconds": loop_seconds, "seed": seed,
                "arrangement": arrangement["name"], "progression_variant": progression_variant,
                "key_shift": transpose, "melody_density": melody_density, "swing": swing,
                "texture": texture, "layers": ["pad", "harmonics", "melody", "bass", "kick", "snare", "hihat", "texture"]}

    def create_ambient_audio(self, output: Path, duration: int, sound_profile: str, seed_text: str = "",
                             creative_dna: dict[str, Any] | None = None) -> dict[str, Any]:
        loop = output.with_name("lofi-original-loop.wav")
        music = self.create_lofi_loop(loop, sound_profile, seed_text, creative_dna)
        fade_duration = min(2, max(0.25, duration / 2))
        fade = f"afade=t=in:st=0:d={fade_duration},afade=t=out:st={max(0, duration - fade_duration)}:d={fade_duration}"
        command = [self.settings.ffmpeg, "-y", "-stream_loop", "-1", "-i", str(loop)]
        layers = {
            "rain": ("white", "highpass=f=900,lowpass=f=6500,volume=0.26", "subtle_rain"),
            "cosmic": ("brown", "lowpass=f=420,volume=0.10", "deep_space_hum"),
            "cozy": ("brown", "highpass=f=120,lowpass=f=1800,volume=0.065", "warm_room_texture"),
            "focus": ("pink", "highpass=f=180,lowpass=f=4200,volume=0.035", "soft_focus_air"),
        }
        if sound_profile in layers:
            color, layer_filter, layer_name = layers[sound_profile]
            command.extend(["-f", "lavfi", "-i", f"anoisesrc=color={color}:amplitude=0.010:sample_rate=22050"])
            filters = f"[1:a]{layer_filter}[amb];[0:a]volume=0.88[music];[music][amb]amix=inputs=2:normalize=0,{fade}[a]"
            command.extend(["-filter_complex", filters, "-map", "[a]"])
            music["ambient_layer"] = layer_name
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
    def visual_motion(sound_profile: str, width: int, height: int, fps: int,
                      creative_dna: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
        """Describe a fixed-camera scene with a localized atmospheric overlay."""
        creative_dna = creative_dna or {}
        cycle_seconds = 12
        styles = {
            "rain": {"name": "chuva localizada", "effect": "localized_rain", "opacity": 0.34},
            "cosmic": {"name": "estrelas pulsantes", "effect": "localized_star_twinkle", "opacity": 0.42},
            "cozy": {"name": "fumaça suave da xícara", "effect": "localized_cup_steam", "opacity": 0.30},
            "focus": {"name": "fumaça suave da xícara", "effect": "localized_cup_steam", "opacity": 0.26},
        }
        style = styles.get(sound_profile, styles["focus"])
        effect = str(creative_dna.get("motion_effect") or style["effect"])
        density = float(creative_dna.get("motion_density", 1.0))
        vf = f"scale={width}:{height},format=gbrp"
        recipe = {
            "style": "localized_atmospheric_loop",
            "format": "mp4_h264",
            "cycle_seconds": cycle_seconds,
            "profile": sound_profile,
            "atmosphere": MOTION_LABELS.get(effect, style["name"]),
            "effects": [effect],
            "density": density,
            "overlay_opacity": round(min(.52, style["opacity"] * (.82 + density * .18)), 3),
            "camera_motion": "none",
            "source_policy": "original_or_commercially_licensed",
        }
        return vf, recipe

    def create_motion_overlay(self, output: Path, sound_profile: str, fps: int, seed_text: str = "",
                              creative_dna: dict[str, Any] | None = None) -> None:
        """Render a small seamless effects plate; black pixels disappear with screen blending."""
        creative_dna = creative_dna or {}
        width, height, seconds = 320, 180, 12
        seed = int(creative_dna.get("seed") or int(hashlib.sha256(f"{sound_profile}:{seed_text}".encode()).hexdigest()[:8], 16))
        rng = random.Random(seed)
        density = float(creative_dna.get("motion_density", 1.0))
        effect = str(creative_dna.get("motion_effect") or ("angled_rain" if sound_profile == "rain" else "star_twinkle" if sound_profile == "cosmic" else "cup_steam"))
        raindrops = [(rng.randrange(int(width * (.58 if effect == "window_drops" else .82))), rng.randrange(height),
                      rng.randrange(2, 6), rng.randrange(6, 15)) for _ in range(round(64 * density))]
        particles = [(rng.randrange(8, width - 8), rng.randrange(6, int(height * .78)), rng.random() * math.tau,
                      .5 + rng.random() * 1.6) for _ in range(round(48 * density))]

        command = [self.settings.ffmpeg, "-y", "-f", "rawvideo", "-pixel_format", "gray",
                   "-video_size", f"{width}x{height}", "-framerate", str(fps), "-i", "-", "-an",
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(output)]
        proc = subprocess.Popen(command, cwd=self.settings.root, stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

        def glow(frame: bytearray, cx: float, cy: float, rx: float, ry: float, strength: float) -> None:
            left, right = max(0, int(cx - rx)), min(width, int(cx + rx + 1))
            top, bottom = max(0, int(cy - ry)), min(height, int(cy + ry + 1))
            for y in range(top, bottom):
                for x in range(left, right):
                    distance = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2
                    if distance < 1:
                        index = y * width + x
                        value = int(strength * (1 - distance) ** 2)
                        frame[index] = min(255, frame[index] + value)

        try:
            assert proc.stdin is not None
            for frame_number in range(fps * seconds):
                frame = bytearray(width * height)
                t = frame_number / fps
                if effect in {"angled_rain", "window_drops", "rain_and_mist", "distant_splashes"}:
                    for x0, y0, speed, length in raindrops:
                        y = int((y0 + frame_number * speed / 2) % (height + length)) - length
                        drift = .04 if effect == "window_drops" else .10 if effect == "angled_rain" else .065
                        x = int((x0 - frame_number * speed * drift) % width)
                        for step in range(length):
                            px, py = (x + (0 if effect == "window_drops" else step // 4)) % width, y + step
                            if 0 <= py < height:
                                frame[py * width + px] = max(frame[py * width + px], 75 - step * 3)
                    if effect == "rain_and_mist":
                        glow(frame, width * (.48 + .05 * math.sin(t / 2)), height * .72, 52, 16, 24)
                elif effect == "cup_steam":
                    for wisp in range(4):
                        progress = (t / seconds + wisp / 4) % 1
                        cx = width * 0.545 + math.sin(math.tau * progress * 1.7 + wisp) * (3 + 5 * progress)
                        cy = height * (0.72 - 0.27 * progress)
                        strength = math.sin(math.pi * progress) ** 1.4 * 125
                        glow(frame, cx, cy, 4 + 5 * progress, 7 + 12 * progress, strength)
                else:
                    for x0, y0, phase, speed in particles:
                        progress = (t * speed / seconds + phase / math.tau) % 1
                        drift = 0 if effect in {"star_twinkle", "lamp_flicker", "window_glow", "signal_pulse"} else 18 * progress
                        x = (x0 + drift) % width
                        y = y0 - (12 * progress if effect in {"dust_motes", "firefly_glow", "soft_particles", "nebula_dust"} else 0)
                        pulse = max(0, math.sin(math.tau * progress + phase)) ** (2 if effect == "star_twinkle" else 1)
                        strength = pulse * (165 if effect in {"star_twinkle", "signal_pulse"} else 92)
                        radius = 2.2 if effect in {"firefly_glow", "drifting_sparks"} else 1.5
                        glow(frame, x, y, radius, radius, strength)
                proc.stdin.write(frame)
            proc.stdin.close()
            stderr = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
            if proc.wait() or not output.is_file():
                raise RuntimeError(f"FFmpeg não conseguiu gerar o overlay visual: {stderr[-1200:]}")
        finally:
            if proc.poll() is None:
                proc.kill()
            if proc.stderr:
                proc.stderr.close()

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
               source_assets: list[dict[str, Any]] | None = None,
               team_id: str = DEFAULT_TEAM_ID, source_asset_rights_confirmed: bool = False) -> str:
        topic = " ".join(topic.split()).strip()
        if len(topic) < 3:
            raise ValueError("Descreva um tema com pelo menos 3 caracteres")
        if profile not in PROFILES:
            raise ValueError("Perfil de saída inválido")
        team = get_team(team_id)
        if not team.creation_enabled:
            raise ValueError("Esta equipe trabalha pelo Centro de Afiliados")
        duration = max(5, min(int(duration), PROFILES[profile]["max_duration"]))
        assets = list(source_assets or [])
        if source_asset:
            if not source_asset_rights_confirmed:
                raise ValueError("Confirme os direitos comerciais da imagem avulsa antes de usá-la")
            assets.append({"name": Path(source_asset).stem, "path": source_asset, "license_type": "user_confirmed",
                           "source_url": None, "approved": True, "rights_confirmed": True})
        normalized_assets = []
        for asset in assets[:12]:
            if asset.get("approved") is not True or asset.get("license_type") not in SUPPORTED_ASSET_LICENSES:
                raise ValueError(f"Asset sem licença comercial aprovada: {asset.get('name', 'sem nome')}")
            if asset.get("license_type") == "user_confirmed" and asset.get("rights_confirmed") is not True:
                raise ValueError("A imagem avulsa precisa de confirmação explícita de direitos")
            source = Path(str(asset.get("path", ""))).expanduser().resolve()
            if not source.is_file() or source.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                raise ValueError(f"Asset inválido: {source}")
            normalized_assets.append({**asset, "path": str(source)})
        job_id = f"{safe_slug(topic)}-{uuid.uuid4().hex[:8]}"
        output_dir = self.settings.data_dir / "jobs" / job_id
        output_dir.mkdir(parents=True)
        self.store.create_job({"id": job_id, "topic": topic, "duration": duration, "narration": narration,
                               "subtitles": subtitles, "profile": profile, "priority": priority,
                               "team_id": team.id,
                               "source_asset": normalized_assets[0]["path"] if normalized_assets else None,
                               "source_assets": normalized_assets, "output_dir": str(output_dir)})
        return job_id

    def generate_plan(self, topic: str, duration: int, profile: str = "youtube_long", narration: bool = False,
                      team_id: str = DEFAULT_TEAM_ID) -> dict[str, Any]:
        return self.crew.run(topic, duration, profile, narration, team_id)

    def _create_backgrounds(self, job: dict[str, Any], out: Path, width: int, height: int,
                            sound_profile: str = "focus",
                            creative_dna: dict[str, Any] | None = None) -> list[Path]:
        creative_dna = creative_dna or {}
        crop_x = float(creative_dna.get("crop_x", .5))
        crop_y = float(creative_dna.get("crop_y", .5))
        treatment = str(creative_dna.get("visual_filter", "eq=contrast=1:saturation=1"))
        visual_filter = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}:x=(iw-ow)*{crop_x:.2f}:y=(ih-oh)*{crop_y:.2f},{treatment}"
        )
        assets = job.get("source_assets") or []
        backgrounds: list[Path] = []
        if assets:
            for index, asset in enumerate(assets):
                background = out / f"scene-{index + 1:02}.jpg"
                self.command([self.settings.ffmpeg, "-y", "-i", asset["path"], "-vf",
                              visual_filter,
                              "-frames:v", "1", str(background)])
                backgrounds.append(background)
            (out / "asset-manifest.json").write_text(json.dumps(assets, ensure_ascii=False, indent=2), encoding="utf-8")
            self.store.event(job["id"], "assets", f"{len(backgrounds)} asset(s) licenciado(s) enquadrado(s)")
        else:
            background = out / "background.jpg"
            starter_name = str(creative_dna.get("scene") or self.select_starter_scene(job["topic"], sound_profile))
            starter = self.settings.root / "assets" / "starter" / starter_name
            if starter.is_file():
                self.command([self.settings.ffmpeg, "-y", "-i", str(starter), "-vf",
                              visual_filter,
                              "-frames:v", "1", str(background)])
                (out / "asset-manifest.json").write_text(json.dumps([{
                    "name": starter.stem, "path": str(starter), "license_type": "original_ai_generated",
                    "source_url": None, "approved": True,
                }], ensure_ascii=False, indent=2), encoding="utf-8")
            else:
                self.command([self.settings.ffmpeg, "-y", "-f", "lavfi", "-i",
                              f"color=c=#071426:s={width}x{height},geq=r='8+18*Y/H':g='18+36*Y/H':b='38+50*Y/H',noise=alls=7:allf=t+u",
                              "-frames:v", "1", str(background)])
                (out / "asset-manifest.json").write_text(json.dumps([{
                    "name": "procedural-fallback", "path": str(background),
                    "license_type": "original_ai_generated", "source_url": None, "approved": True,
                }], ensure_ascii=False, indent=2), encoding="utf-8")
            backgrounds.append(background)
            self.store.event(job["id"], "assets", f"Cena visual original '{starter_name}' aplicada automaticamente")
        return backgrounds

    @staticmethod
    def scene_candidates(topic: str, sound_profile: str) -> tuple[str, ...]:
        preferred = Pipeline.select_starter_scene(topic, sound_profile)
        return tuple(dict.fromkeys((preferred, *STARTER_SCENES.get(sound_profile, STARTER_SCENES["focus"]))))

    def creative_status(self) -> dict[str, Any]:
        return self.creative.status(self.store.list_jobs(500), self.store.performance_insights())

    @staticmethod
    def select_starter_scene(topic: str, sound_profile: str) -> str:
        normalized = safe_slug(topic)
        keyword_scenes = (
            (("anime", "personagem"), "lofi-anime-rainy-apartment.jpg"),
            (("trem", "train", "vagao"), "lofi-night-train.jpg"),
            (("lago", "cabana", "lake"), "lofi-lakeside-cabin.jpg"),
            (("disco", "vinil", "record", "loja"), "lofi-record-store.jpg"),
            (("lua", "lunar", "observatorio"), "lofi-lunar-observatory.jpg"),
        )
        for keywords, scene in keyword_scenes:
            if any(keyword in normalized for keyword in keywords):
                return scene
        candidates = STARTER_SCENES.get(sound_profile, STARTER_SCENES["focus"])
        index = int(hashlib.sha256(f"{sound_profile}:{normalized}".encode()).hexdigest()[:8], 16) % len(candidates)
        return candidates[index]

    def run(self, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(job_id)
        if not job:
            raise KeyError(job_id)
        if job["status"] not in {"queued", "failed", "rejected"}:
            return job
        if not self.store.claim_job(job_id):
            return self.store.get_job(job_id) or job
        job = self.store.get_job(job_id) or job
        out = Path(job["output_dir"])
        job_lock = self.acquire_job_lock(out)
        if not job_lock:
            self.store.event(job_id, "render_lock", "Execução duplicada ignorada; a produção já está ativa em outro processo")
            return self.store.get_job(job_id) or job
        profile = PROFILES.get(job.get("profile"), PROFILES["youtube_long"])
        for stale_candidate in out.glob("video.rendering*.mp4"):
            stale_candidate.unlink(missing_ok=True)
        render_candidate = out / f"video.rendering-{uuid.uuid4().hex}.mp4"
        try:
            self.store.update(job_id, "planning", progress=8)
            plan = self.generate_plan(job["topic"], job["duration"], job.get("profile", "youtube_long"),
                                      job["narration"], job.get("team_id", DEFAULT_TEAM_ID))
            sound_profile = plan["visual"].get("sound_profile", "focus")
            asset_scenes = tuple(str(asset.get("name") or Path(str(asset.get("path", "scene"))).stem)
                                 for asset in (job.get("source_assets") or []))
            creative_dna = self.creative.plan(
                job["topic"], sound_profile, job.get("profile", "youtube_long"),
                asset_scenes or self.scene_candidates(job["topic"], sound_profile),
                self.store.list_jobs(500), self.store.performance_insights(), job_id,
            )
            plan["visual"]["creative_dna"] = creative_dna
            if creative_dna["novelty"]["risk"] == "high":
                plan["review"]["warnings"].append("DNA criativo ainda próximo do histórico; revise antes de publicar.")
            (out / "agents.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
            metadata = {**plan["seo"], "chapters": plan["script"]["chapters"], "production": plan["production"],
                        "agents": plan, "quality": plan["review"], "creative_dna": creative_dna}
            (out / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            (out / "script.txt").write_text(plan["script"]["intro"] + "\n", encoding="utf-8")
            for agent in plan["team"]["agents"]:
                self.store.event(job_id, agent["id"], f"{agent['name']} concluiu sua entrega")
            self.store.update(job_id, "planning", metadata=metadata, progress=28)

            if job["subtitles"]:
                end = min(job["duration"], 9)
                subtitle = f"1\n00:00:00,000 --> {srt_timestamp(end)}\n{plan['script']['intro']}\n"
                (out / "subtitles.srt").write_text(subtitle, encoding="utf-8")
                self.store.event(job_id, "subtitles", "Legenda SRT criada")

            self.store.update(job_id, "assets", metadata=metadata, progress=40)
            backgrounds = self._create_backgrounds(job, out, profile["width"], profile["height"],
                                                   sound_profile, creative_dna)
            audio = out / "ambient.wav"
            music = self.create_ambient_audio(audio, job["duration"], sound_profile, job["topic"], creative_dna)
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
            render_candidate.unlink(missing_ok=True)
            width, height, fps = profile["width"], profile["height"], profile["fps"]
            vf, motion = self.visual_motion(sound_profile, width, height, fps, creative_dna)
            motion_overlay = out / "motion-overlay.mp4"
            self.create_motion_overlay(motion_overlay, sound_profile, fps, job["topic"], creative_dna)
            scene_identity = backgrounds[0].name
            asset_manifest_path = out / "asset-manifest.json"
            if asset_manifest_path.is_file():
                asset_manifest = json.loads(asset_manifest_path.read_text(encoding="utf-8"))
                if asset_manifest:
                    scene_identity = str(asset_manifest[0].get("name") or scene_identity)
            metadata["creative_fingerprint"] = {**creative_dna,
                "scene": scene_identity,
                "music_arrangement": music.get("arrangement"),
                "music_seed": music.get("seed"),
                "motion_seed": hashlib.sha256(f"{creative_dna['seed']}:{creative_dna['motion_effect']}".encode()).hexdigest()[:12],
            }
            metadata["creative_dna"] = metadata["creative_fingerprint"]
            self.store.event(job_id, "novelty", f"Originalidade criativa: {creative_dna['novelty']['score']}/100; risco {creative_dna['novelty']['risk']}")
            metadata["motion"] = motion
            self.store.event(job_id, "motion", f"Loop visual de {motion['cycle_seconds']} s aplicado: {motion['atmosphere']}")
            blend = (f"[0:v]{vf}[base];[1:v]scale={width}:{height},format=gbrp[fx];"
                     f"[base][fx]blend=all_mode=screen:all_opacity={motion['overlay_opacity']},format=yuv420p[v]")
            if len(backgrounds) == 1:
                self.command([self.settings.ffmpeg, "-y", "-loop", "1", "-i", str(backgrounds[0]),
                              "-stream_loop", "-1", "-i", str(motion_overlay), "-i", str(audio),
                              "-filter_complex", blend, "-map", "[v]", "-map", "2:a:0", "-t", str(job["duration"]),
                              "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                              "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(render_candidate)])
            else:
                scene_dir = out / "render-scenes"
                scene_dir.mkdir(exist_ok=True)
                clips = []
                base_duration = job["duration"] / len(backgrounds)
                for index, background in enumerate(backgrounds):
                    clip = scene_dir / f"clip-{index + 1:02}.mp4"
                    clips.append(clip)
                    self.command([self.settings.ffmpeg, "-y", "-loop", "1", "-i", str(background),
                                  "-stream_loop", "-1", "-i", str(motion_overlay), "-filter_complex", blend, "-map", "[v]",
                                  "-t", f"{base_duration:.3f}", "-an", "-c:v", "libx264", "-preset", "veryfast",
                                  "-crf", "22", "-pix_fmt", "yuv420p", str(clip)])
                concat_file = scene_dir / "concat.txt"
                concat_file.write_text("\n".join(f"file '{clip.as_posix()}'" for clip in clips), encoding="utf-8")
                self.command([self.settings.ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
                              "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-t", str(job["duration"]),
                              "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(render_candidate)])
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

            media_report = self.inspect_video(render_candidate, job["duration"])
            gate = self.quality_gate(render_candidate, job["duration"], metadata, media_report)
            (out / "quality-gate.json").write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8")
            if not gate["passed"]:
                failed_labels = [check["label"] for check in gate["checks"] if not check["passed"]]
                raise RuntimeError("Controle de qualidade bloqueou o pacote: " + ", ".join(failed_labels))
            os.replace(render_candidate, video)
            media_report["size_bytes"] = video.stat().st_size
            media_report["atomic_promotion"] = True
            (out / "render-report.json").write_text(json.dumps(media_report, ensure_ascii=False, indent=2), encoding="utf-8")
            self.store.event(job_id, "verification", f"Vídeo, áudio e duração validados com {media_report['validation_engine']}")
            metadata["quality_gate"] = gate
            self.store.event(job_id, "quality_gate", f"Controle automático aprovado: {gate['score']}/100")

            self.store.update(job_id, "reviewing", metadata=metadata, progress=88)
            checklist = {
                "mode": "manual-safe", "ready_for_review": True, "platform_upload_performed": False,
                "quality_score": plan["review"]["score"], "compliance": plan["compliance"],
                "media_validation": media_report, "quality_gate": gate,
                "narration_requested": job["narration"],
                "narration_status": metadata.get("narration_status", "not_requested"),
                "steps": ["Assista aos 30 segundos iniciais", "Confira thumbnail, título e direitos", "Aprove no painel", "Envie manualmente ao YouTube Studio"],
            }
            (out / "publication-package.json").write_text(json.dumps(checklist, ensure_ascii=False, indent=2), encoding="utf-8")
            metadata["files"] = {"video": "video.mp4", "thumbnail": "thumbnail.jpg", "subtitles": "subtitles.srt" if job["subtitles"] else None,
                                 "agents": "agents.json", "publication": "publication-package.json",
                                 "render_report": "render-report.json", "quality_gate": "quality-gate.json", "manifest": "artifact-manifest.json",
                                 "motion_overlay": "motion-overlay.mp4"}
            metadata["thumbnail_variants"] = thumbnail_design["variants"]
            metadata["selected_thumbnail"] = "a"
            metadata["verification"] = media_report
            metadata["quality"] = plan["review"]
            (out / "agents.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
            (out / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            manifest = self.artifact_manifest(out, ["video.mp4", "motion-overlay.mp4", "thumbnail.jpg", "thumbnail-a.jpg", "thumbnail-b.jpg", "thumbnail-design.json", "subtitles.srt", "metadata.json", "agents.json", "publication-package.json", "render-report.json", "quality-gate.json"])
            (out / "artifact-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            self.store.update(job_id, "awaiting_approval", metadata=metadata, progress=100,
                              quality_score=plan["review"]["score"])
            self.store.event(job_id, "complete", "Pacote revisado e pronto; nenhum upload foi realizado")
            return self.store.get_job(job_id) or {}
        except Exception as exc:
            render_candidate.unlink(missing_ok=True)
            self.store.update(job_id, "failed", error=str(exc), progress=0)
            self.store.event(job_id, "failed", str(exc))
            raise
        finally:
            self.release_job_lock(job_lock)

    def approve(self, job_id: str) -> None:
        job = self.store.get_job(job_id)
        if not job or job["status"] not in {"awaiting_approval", "approved"}:
            raise ValueError("A produção ainda não está pronta para aprovação")
        if not job.get("metadata", {}).get("quality_gate", {}).get("passed"):
            raise ValueError("Execute e aprove o controle de qualidade antes da aprovação")
        self.verify_artifact_checksum(Path(job["output_dir"]))
        self.store.update(job_id, "approved", job["metadata"], progress=100, quality_score=job.get("quality_score"))
        self.store.event(job_id, "approved", "Aprovado para publicação manual")

    def audit_job(self, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(job_id)
        if not job or job["status"] not in {"awaiting_approval", "approved", "rejected"}:
            raise ValueError("A produção precisa estar renderizada antes da auditoria")
        out = Path(job["output_dir"])
        metadata = dict(job.get("metadata") or {})
        technical = self.inspect_video(out / "video.mp4", job["duration"])
        gate = self.quality_gate(out / "video.mp4", job["duration"], metadata, technical)
        metadata["verification"] = technical
        metadata["quality_gate"] = gate
        metadata.setdefault("files", {})["quality_gate"] = "quality-gate.json"
        (out / "quality-gate.json").write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest = self.artifact_manifest(out, [
            "video.mp4", "motion-overlay.mp4", "thumbnail.jpg", "thumbnail-a.jpg", "thumbnail-b.jpg",
            "subtitles.srt", "metadata.json", "render-report.json", "quality-gate.json",
            "publication-package.json", "youtube-upload.json", "vertical-short.mp4", "vertical-package.json",
        ])
        (out / "artifact-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        if gate["passed"]:
            status = "approved" if job["status"] == "approved" else "awaiting_approval"
            self.store.update(job_id, status, metadata, progress=100, quality_score=job.get("quality_score"))
            self.store.event(job_id, "quality_gate", f"Auditoria automática aprovada: {gate['score']}/100")
        else:
            labels = [check["label"] for check in gate["checks"] if not check["passed"]]
            reason = "Controle de qualidade: " + ", ".join(labels)
            self.store.update(job_id, "rejected", metadata, error=reason, progress=100, quality_score=job.get("quality_score"))
            self.store.event(job_id, "quality_gate", reason)
        return gate

    def prepare_youtube_package(self, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(job_id)
        if not job or job["status"] != "approved":
            raise ValueError("A produção precisa estar aprovada antes de preparar o YouTube")
        metadata = job.get("metadata") or {}
        if not metadata.get("verification", {}).get("passed"):
            raise ValueError("O arquivo ainda não passou pela validação técnica")
        if not metadata.get("quality_gate", {}).get("passed"):
            raise ValueError("O arquivo ainda não passou pelo controle de qualidade v0.9")
        out = Path(job["output_dir"])
        self.verify_artifact_checksum(out)
        payload = {
            "mode": "prepared_not_uploaded",
            "api": "youtube_data_api_v3",
            "operation": "videos.insert",
            "parts": ["snippet", "status"],
            "snippet": {"title": metadata.get("title", job["topic"]),
                        "description": metadata.get("description", ""),
                        "tags": metadata.get("tags", []), "categoryId": "10"},
            "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False},
            "media_file": "video.mp4",
            "thumbnail_file": "thumbnail.jpg",
            "captions_file": metadata.get("files", {}).get("subtitles"),
            "oauth_configured": bool(self.settings.youtube_client_secrets_file),
            "automatic_upload_allowed": False,
            "next_step": "Configurar OAuth, revisar este JSON e confirmar um upload privado.",
        }
        package = out / "youtube-upload.json"
        package.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest = self.artifact_manifest(out, ["video.mp4", "motion-overlay.mp4", "thumbnail.jpg", "thumbnail-a.jpg",
                                           "thumbnail-b.jpg", "subtitles.srt", "metadata.json", "agents.json",
                                           "publication-package.json", "render-report.json", "youtube-upload.json"])
        (out / "artifact-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        self.store.event(job_id, "youtube", "Pacote privado do YouTube preparado; nenhum upload foi realizado")
        return payload

    def prepare_vertical_package(self, job_id: str, duration: int = 30) -> dict[str, Any]:
        """Create one original 9:16 derivative and manual-safe metadata for short platforms."""
        job = self.store.get_job(job_id)
        if not job or job["status"] != "approved":
            raise ValueError("A produção precisa estar aprovada antes de criar recortes verticais")
        if not job.get("metadata", {}).get("quality_gate", {}).get("passed"):
            raise ValueError("O arquivo ainda não passou pelo controle de qualidade v0.9")
        out = Path(job["output_dir"])
        self.verify_artifact_checksum(out)
        source = out / "video.mp4"
        if not source.is_file():
            raise ValueError("Vídeo principal não encontrado")
        duration = max(5, min(int(duration), 60))
        vertical = out / "vertical-short.mp4"
        thumbnail = out / "vertical-thumbnail.jpg"
        filter_graph = (
            "[0:v]split=2[base][front];"
            "[base]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,gblur=sigma=28[bg];"
            "[front]scale=720:-2[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[v]"
        )
        self.command([
            self.settings.ffmpeg, "-y", "-stream_loop", "-1", "-i", str(source),
            "-filter_complex", filter_graph, "-map", "[v]", "-map", "0:a:0", "-t", str(duration),
            "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(vertical),
        ])
        self.command([
            self.settings.ffmpeg, "-y", "-ss", "1", "-i", str(vertical), "-frames:v", "1", "-q:v", "2", str(thumbnail)
        ])
        report = self.inspect_video(vertical, duration)
        if report.get("video", {}).get("width") != 720 or report.get("video", {}).get("height") != 1280:
            raise RuntimeError("O recorte vertical não foi renderizado em 720x1280")
        title = str(job.get("metadata", {}).get("title") or job["topic"])
        description = str(job.get("metadata", {}).get("description") or "")
        package = {
            "mode": "prepared_not_uploaded",
            "source_job_id": job_id,
            "source_rights": "inherits_approved_source_manifest",
            "video_file": "vertical-short.mp4",
            "thumbnail_file": "vertical-thumbnail.jpg",
            "duration_seconds": duration,
            "format": "9:16",
            "resolution": "720x1280",
            "platforms": {
                "youtube_shorts": {"title": f"{title[:85]} #Shorts", "description": description, "upload": "manual"},
                "instagram_reels": {"caption": f"{title}\n\n#lofi #chill #reels", "upload": "manual"},
                "tiktok": {"caption": f"{title}\n\n#lofi #chill #fyp", "upload": "manual"},
            },
            "automatic_upload_allowed": False,
            "validation": report,
        }
        (out / "vertical-package.json").write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest = self.artifact_manifest(out, [
            "video.mp4", "thumbnail.jpg", "metadata.json", "render-report.json", "youtube-upload.json",
            "vertical-short.mp4", "vertical-thumbnail.jpg", "vertical-package.json",
        ])
        (out / "artifact-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        self.store.event(job_id, "repurpose", f"Recorte vertical de {duration}s validado; nenhum upload foi realizado")
        return package

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
        manifest = self.artifact_manifest(out, [
            "video.mp4", "motion-overlay.mp4", "thumbnail.jpg", "thumbnail-a.jpg", "thumbnail-b.jpg",
            "thumbnail-design.json", "subtitles.srt", "metadata.json", "agents.json",
            "publication-package.json", "render-report.json", "quality-gate.json",
        ])
        (out / "artifact-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        self.store.set_thumbnail_variant(job_id, variant)
        self.store.update(job_id, job["status"], metadata, progress=job["progress"], quality_score=job.get("quality_score"))
        self.store.event(job_id, "thumbnail", f"Thumbnail {variant.upper()} selecionada para publicação manual")
