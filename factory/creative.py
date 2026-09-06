from __future__ import annotations

import hashlib
import random
import re
from collections import defaultdict
from typing import Any, Iterable


TREATMENTS = (
    {"id": "nocturne_blue", "label": "Azul noturno", "filter": "eq=contrast=1.10:brightness=-0.035:saturation=0.88,hue=h=-7"},
    {"id": "amber_glow", "label": "Âmbar acolhedor", "filter": "eq=contrast=1.06:brightness=0.01:saturation=1.10,colorbalance=rs=.055:bs=-.025"},
    {"id": "violet_dream", "label": "Violeta onírico", "filter": "eq=contrast=1.08:brightness=-0.025:saturation=1.04,hue=h=13"},
    {"id": "teal_noir", "label": "Teal noir", "filter": "eq=contrast=1.14:brightness=-0.05:saturation=0.80,colorbalance=gs=.025:bs=.045"},
    {"id": "soft_film", "label": "Filme suave", "filter": "eq=contrast=.96:brightness=.015:saturation=.92,noise=alls=3:allf=u"},
    {"id": "moonlit_silver", "label": "Luar prateado", "filter": "eq=contrast=1.05:brightness=-.02:saturation=.62,colorbalance=bs=.035"},
    {"id": "dusk_mauve", "label": "Crepúsculo malva", "filter": "eq=contrast=1.02:brightness=-.015:saturation=.98,hue=h=7"},
    {"id": "emerald_night", "label": "Noite esmeralda", "filter": "eq=contrast=1.12:brightness=-.045:saturation=.78,colorbalance=gs=.055:bs=.015"},
)

COMPOSITIONS = (
    {"id": "centered", "label": "Centro contemplativo", "x": 0.50, "y": 0.50},
    {"id": "left_story", "label": "Narrativa à esquerda", "x": 0.28, "y": 0.50},
    {"id": "right_story", "label": "Narrativa à direita", "x": 0.72, "y": 0.50},
    {"id": "low_horizon", "label": "Horizonte baixo", "x": 0.50, "y": 0.68},
    {"id": "high_shelter", "label": "Abrigo elevado", "x": 0.50, "y": 0.30},
)

MOTION_BY_PROFILE = {
    "rain": ("angled_rain", "window_drops", "rain_and_mist", "distant_splashes"),
    "cosmic": ("star_twinkle", "drifting_sparks", "nebula_dust", "signal_pulse"),
    "cozy": ("cup_steam", "dust_motes", "firefly_glow", "lamp_flicker"),
    "focus": ("cup_steam", "dust_motes", "window_glow", "soft_particles"),
}

MOTION_LABELS = {
    "angled_rain": "chuva diagonal localizada", "window_drops": "gotas no vidro",
    "rain_and_mist": "chuva com névoa suave", "distant_splashes": "respingos distantes",
    "star_twinkle": "estrelas pulsantes", "drifting_sparks": "faíscas orbitais",
    "nebula_dust": "poeira de nebulosa", "signal_pulse": "pulso luminoso distante",
    "cup_steam": "fumaça suave da xícara", "dust_motes": "poeira iluminada",
    "firefly_glow": "pontos de luz orgânicos", "lamp_flicker": "luz ambiente oscilante",
    "window_glow": "reflexos suaves na janela", "soft_particles": "partículas atmosféricas",
}

MUSIC_ARRANGEMENTS = (
    {"name": "dusty_keys", "pad": .055, "harmonic": .009, "pluck": .085, "decay": 4.8, "snare": .075, "bass": .095, "melody": "steps", "rhythm": "boom_bap"},
    {"name": "felt_piano", "pad": .047, "harmonic": .015, "pluck": .105, "decay": 6.2, "snare": .052, "bass": .075, "melody": "sparse", "rhythm": "brushes"},
    {"name": "warm_tape_synth", "pad": .064, "harmonic": .005, "pluck": .065, "decay": 3.7, "snare": .063, "bass": .105, "melody": "pulse", "rhythm": "broken"},
    {"name": "night_rhodes", "pad": .050, "harmonic": .018, "pluck": .078, "decay": 5.5, "snare": .047, "bass": .090, "melody": "late", "rhythm": "half_time"},
    {"name": "glass_mallets", "pad": .040, "harmonic": .022, "pluck": .112, "decay": 7.1, "snare": .036, "bass": .065, "melody": "sparkle", "rhythm": "no_drums"},
    {"name": "deep_focus_pad", "pad": .074, "harmonic": .004, "pluck": .042, "decay": 3.2, "snare": .030, "bass": .115, "melody": "minimal", "rhythm": "pulse_only"},
    {"name": "cassette_guitar", "pad": .044, "harmonic": .012, "pluck": .096, "decay": 4.3, "snare": .058, "bass": .082, "melody": "syncopated", "rhythm": "swing_break"},
    {"name": "sleepy_chimes", "pad": .052, "harmonic": .020, "pluck": .070, "decay": 8.0, "snare": .025, "bass": .060, "melody": "floating", "rhythm": "no_drums"},
    {"name": "rainy_vibraphone", "pad": .046, "harmonic": .024, "pluck": .082, "decay": 7.4, "snare": .034, "bass": .072, "melody": "droplets", "rhythm": "brushes"},
    {"name": "midnight_wurlitzer", "pad": .058, "harmonic": .013, "pluck": .073, "decay": 5.0, "snare": .044, "bass": .102, "melody": "afterhours", "rhythm": "half_time"},
    {"name": "hollow_body_dream", "pad": .041, "harmonic": .016, "pluck": .092, "decay": 6.6, "snare": .040, "bass": .078, "melody": "gentle_arpeggio", "rhythm": "broken"},
    {"name": "analog_clouds", "pad": .080, "harmonic": .007, "pluck": .038, "decay": 4.1, "snare": .022, "bass": .110, "melody": "slow_orbit", "rhythm": "pulse_only"},
)

TEXTURES = ("clean_room", "soft_tape", "vinyl_dust", "warm_noise", "air_hiss")


def _tokens(value: str) -> set[str]:
    return {token for token in re.sub(r"[^a-z0-9áàâãéêíóôõúç]+", " ", value.lower()).split() if len(token) > 2}


def _fingerprint(job: dict[str, Any]) -> dict[str, Any]:
    metadata = job.get("metadata") or {}
    return metadata.get("creative_fingerprint") or metadata.get("creative_dna") or {}


class CreativeDirector:
    """Creates diverse, reproducible creative DNA and learns softly from measured results."""

    feature_weights = {
        "scene": .24, "treatment": .13, "composition": .09, "motion_effect": .15,
        "music_arrangement": .19, "progression_variant": .08, "texture": .07, "bpm_bucket": .05,
    }

    @staticmethod
    def _learning(insights: Iterable[dict[str, Any]]) -> dict[str, Any]:
        scores: dict[str, dict[str, list[float]]] = {
            "music_arrangement": defaultdict(list), "treatment": defaultdict(list),
            "motion_effect": defaultdict(list),
        }
        evidence = 0
        for item in insights:
            views = int(item.get("views") or 0)
            impressions = int(item.get("impressions") or 0)
            if views < 25 or (float(item.get("ctr") or 0) > 0 and impressions < 100):
                continue
            signal = (
                min(100.0, float(item.get("retention_rate") or 0)) * .50
                + min(20.0, float(item.get("ctr") or 0)) * 2.0
                + min(20.0, float(item.get("engagement_rate") or 0)) * .50
            )
            if signal <= 0:
                continue
            evidence += 1
            for feature in scores:
                value = item.get(feature)
                if value:
                    scores[feature][str(value)].append(signal)
        preferred = {}
        for feature, values in scores.items():
            if values:
                preferred[feature] = max(values, key=lambda key: sum(values[key]) / len(values[key]))
        return {
            "evidence_count": evidence, "preferred": preferred,
            "mode": "measured" if evidence else "exploration",
            "reason": "Métricas com amostra mínima influenciaram 20% da seleção; novidade continua prioritária."
            if evidence else "Sem amostra mínima de métricas: exploração equilibrada ativada.",
        }

    @classmethod
    def similarity(cls, candidate: dict[str, Any], existing: dict[str, Any]) -> tuple[float, list[str]]:
        compared = 0.0
        matched = 0.0
        reused = []
        for feature, weight in cls.feature_weights.items():
            left = candidate.get(feature)
            right = existing.get(feature)
            if left is None or right is None:
                continue
            compared += weight
            if left == right:
                matched += weight
                reused.append(feature)
        return (matched / compared if compared else 0.0), reused

    def _candidate(self, topic: str, sound_profile: str, profile: str, scenes: tuple[str, ...], attempt: int) -> dict[str, Any]:
        seed = int(hashlib.sha256(f"creative-v2:{topic}:{sound_profile}:{profile}:{attempt}".encode()).hexdigest()[:12], 16)
        rng = random.Random(seed)
        treatment = TREATMENTS[rng.randrange(len(TREATMENTS))]
        composition = COMPOSITIONS[rng.randrange(len(COMPOSITIONS))]
        arrangement = MUSIC_ARRANGEMENTS[rng.randrange(len(MUSIC_ARRANGEMENTS))]
        bpm = rng.randrange(66, 88)
        return {
            "version": "creative_dna_v2", "seed": seed, "attempt": attempt,
            # The first scene is selected semantically by the pipeline. Novelty may vary every
            # other creative dimension, but must not turn a train topic into a greenhouse.
            "scene": scenes[0],
            "treatment": treatment["id"], "treatment_label": treatment["label"],
            "visual_filter": treatment["filter"],
            "composition": composition["id"], "composition_label": composition["label"],
            "crop_x": composition["x"], "crop_y": composition["y"],
            "motion_effect": MOTION_BY_PROFILE.get(sound_profile, MOTION_BY_PROFILE["focus"])[rng.randrange(4)],
            "motion_density": round(.72 + rng.random() * .70, 2),
            "music_arrangement": arrangement["name"],
            "progression_variant": rng.randrange(4), "bpm": bpm, "bpm_bucket": bpm // 4,
            "key_shift": (-5, -2, 0, 2, 5)[rng.randrange(5)],
            "melody_density": round(.32 + rng.random() * .58, 2),
            "swing": round(.03 + rng.random() * .13, 3),
            "texture": TEXTURES[rng.randrange(len(TEXTURES))],
        }

    def plan(self, topic: str, sound_profile: str, profile: str, scenes: tuple[str, ...],
             history: Iterable[dict[str, Any]], insights: Iterable[dict[str, Any]],
             current_job_id: str | None = None) -> dict[str, Any]:
        historical = [job for job in history if job.get("id") != current_job_id and _fingerprint(job)]
        learning = self._learning(insights)
        preferred = learning["preferred"]
        best: dict[str, Any] | None = None
        best_rank = -10.0
        for attempt in range(48):
            candidate = self._candidate(topic, sound_profile, profile, scenes, attempt)
            closest = {"similarity": 0.0, "job_id": None, "topic": None, "reused_fields": []}
            for job in historical:
                score, reused = self.similarity(candidate, _fingerprint(job))
                topic_overlap = _tokens(topic) & _tokens(str(job.get("topic", "")))
                if topic_overlap:
                    score = min(1.0, score + min(.12, len(topic_overlap) * .025))
                if score > closest["similarity"]:
                    closest = {"similarity": score, "job_id": job.get("id"),
                               "topic": job.get("topic"), "reused_fields": reused}
            learning_matches = sum(candidate.get(key) == value for key, value in preferred.items())
            rank = (1.0 - closest["similarity"]) * .80 + (learning_matches / max(1, len(preferred))) * .20
            if rank > best_rank:
                best_rank, best = rank, {**candidate, "closest": closest}
        assert best is not None
        closest = best.pop("closest")
        similarity = float(closest["similarity"])
        best["novelty"] = {
            "score": round((1.0 - similarity) * 100, 1),
            "risk": "low" if similarity < .50 else "medium" if similarity < .72 else "high",
            "closest_job_id": closest["job_id"], "closest_topic": closest["topic"],
            "reused_fields": closest["reused_fields"], "candidates_evaluated": 48,
        }
        best["learning"] = learning
        return best

    @staticmethod
    def arrangement(name: str) -> dict[str, Any]:
        return next((item for item in MUSIC_ARRANGEMENTS if item["name"] == name), MUSIC_ARRANGEMENTS[0])

    def status(self, history: Iterable[dict[str, Any]], insights: Iterable[dict[str, Any]]) -> dict[str, Any]:
        fingerprints = [_fingerprint(job) for job in history if _fingerprint(job)]
        scores = [float(item.get("novelty", {}).get("score", 0)) for item in fingerprints if item.get("novelty")]
        return {
            "engine": "creative_dna_v2", "history_count": len(fingerprints),
            "catalog": {"treatments": len(TREATMENTS), "compositions": len(COMPOSITIONS),
                        "motions": sum(len(items) for items in MOTION_BY_PROFILE.values()),
                        "music_arrangements": len(MUSIC_ARRANGEMENTS), "textures": len(TEXTURES),
                        "candidate_space": len(TREATMENTS) * len(COMPOSITIONS) * 4 * len(MUSIC_ARRANGEMENTS) * 4 * len(TEXTURES)},
            "average_novelty": round(sum(scores) / len(scores), 1) if scores else None,
            "high_risk_repetitions": sum(item.get("novelty", {}).get("risk") == "high" for item in fingerprints),
            "learning": self._learning(insights),
            "future_modules": {"smart_cuts": {"status": "available", "uses": "creative DNA, chapters and retention signals"}},
        }
