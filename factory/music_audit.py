from __future__ import annotations

import hashlib
import json
import math
import subprocess
from array import array
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _pearson(first: list[float], second: list[float]) -> float:
    size = min(len(first), len(second))
    if size < 2:
        return 0.0
    left, right = first[:size], second[:size]
    left_mean, right_mean = sum(left) / size, sum(right) / size
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    left_energy = sum((value - left_mean) ** 2 for value in left)
    right_energy = sum((value - right_mean) ** 2 for value in right)
    denominator = math.sqrt(left_energy * right_energy)
    return numerator / denominator if denominator else 0.0


def _signature(samples: array, sample_rate: int) -> dict[str, list[float]]:
    window = max(1, sample_rate)
    rms, crossings, movement = [], [], []
    for start in range(0, len(samples) - window + 1, window):
        chunk = samples[start:start + window]
        scale = 32768.0
        rms.append(math.sqrt(sum((value / scale) ** 2 for value in chunk) / len(chunk)))
        crossings.append(sum(1 for a, b in zip(chunk, chunk[1:]) if (a < 0) != (b < 0)) / len(chunk))
        movement.append(sum(abs(b - a) for a, b in zip(chunk, chunk[1:])) / (len(chunk) * scale))
    waveform = [float(samples[index]) / 32768.0 for index in range(0, len(samples), max(1, sample_rate // 50))]
    return {"rms": rms, "crossings": crossings, "movement": movement, "waveform": waveform}


def _similarity(first: dict[str, list[float]], second: dict[str, list[float]]) -> dict[str, float]:
    waveform = abs(_pearson(first["waveform"], second["waveform"]))
    dynamics = abs(_pearson(first["rms"], second["rms"]))
    texture = abs(_pearson(first["crossings"], second["crossings"]))
    movement = abs(_pearson(first["movement"], second["movement"]))
    composite = 0.50 * dynamics + 0.25 * texture + 0.25 * movement
    return {"waveform": round(waveform, 4), "dynamics": round(dynamics, 4),
            "texture": round(texture, 4), "movement": round(movement, 4),
            "composite": round(composite, 4)}


class MusicDiversityAuditor:
    """Read-only acoustic comparison for the approved music rotation."""

    def __init__(self, ffmpeg: str, report_dir: Path):
        self.ffmpeg = ffmpeg
        self.report_dir = report_dir

    def _decode(self, path: Path, seconds: int, sample_rate: int) -> array:
        result = subprocess.run(
            [self.ffmpeg, "-v", "error", "-i", str(path), "-t", str(seconds), "-vn",
             "-ac", "1", "-ar", str(sample_rate), "-f", "s16le", "pipe:1"],
            capture_output=True, check=False,
        )
        if result.returncode != 0 or len(result.stdout) < sample_rate * 2:
            raise RuntimeError(f"Não foi possível analisar a música: {path.name}")
        samples = array("h")
        samples.frombytes(result.stdout)
        return samples

    def audit(self, tracks: list[dict[str, Any]], seconds: int = 90, sample_rate: int = 4000) -> dict[str, Any]:
        decoded: list[dict[str, Any]] = []
        failures = []
        for track in tracks:
            path = Path(str(track.get("path", "")))
            if not path.is_file():
                failures.append({"id": track.get("id"), "name": track.get("name"), "reason": "arquivo ausente"})
                continue
            try:
                decoded.append({"id": track.get("id"), "name": track.get("name"),
                                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                "signature": _signature(self._decode(path, seconds, sample_rate), sample_rate)})
            except RuntimeError as exc:
                failures.append({"id": track.get("id"), "name": track.get("name"), "reason": str(exc)})

        pairs = []
        for index, first in enumerate(decoded):
            for second in decoded[index + 1:]:
                scores = _similarity(first["signature"], second["signature"])
                exact = first["sha256"] == second["sha256"]
                if exact or scores["waveform"] >= 0.98 or scores["composite"] >= 0.995:
                    risk = "near_duplicate"
                elif scores["composite"] >= 0.96:
                    risk = "review"
                else:
                    risk = "distinct"
                pairs.append({"first_id": first["id"], "first": first["name"],
                              "second_id": second["id"], "second": second["name"],
                              "exact_file": exact, "risk": risk, **scores})
        pairs.sort(key=lambda item: (item["exact_file"], item["waveform"], item["composite"]), reverse=True)
        flagged = [item for item in pairs if item["risk"] != "distinct"]
        report = {
            "generated_at": datetime.now(UTC).isoformat(), "mode": "read_only",
            "tracks": len(decoded), "pairs_compared": len(pairs), "failures": failures,
            "exact_duplicates": sum(item["exact_file"] for item in pairs),
            "near_duplicates": sum(item["risk"] == "near_duplicate" for item in pairs),
            "review_pairs": sum(item["risk"] == "review" for item in pairs),
            "passed": not failures and not any(item["risk"] == "near_duplicate" for item in pairs),
            "flagged": flagged, "closest_pairs": pairs[:5],
            "policy": "Sinais acústicos auxiliam a revisão humana; nenhuma faixa é reprovada automaticamente.",
        }
        self.report_dir.mkdir(parents=True, exist_ok=True)
        (self.report_dir / "music-diversity.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return report
