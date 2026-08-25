from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class AgentSpec:
    id: str
    name: str
    role: str
    output: str
    color: str


AGENTS = [
    AgentSpec("research", "Radar", "Pesquisa de oportunidade", "Público, intenção e palavras-chave", "#75D8B8"),
    AgentSpec("strategy", "Norte", "Estratégia editorial", "Promessa, formato e objetivo", "#FFB86B"),
    AgentSpec("script", "Roteirista", "Narrativa e retenção", "Roteiro, capítulos e ritmo", "#9EB6FF"),
    AgentSpec("visual", "Direção", "Direção visual e sonora", "Paleta, movimento e paisagem sonora", "#D99BFF"),
    AgentSpec("seo", "Descoberta", "Título e distribuição", "Título, descrição e tags", "#67D4FF"),
    AgentSpec("compliance", "Guardião", "Direitos e segurança", "Checklist de riscos e publicação", "#FF8B8B"),
    AgentSpec("review", "Crítica", "Controle de qualidade", "Score, alertas e recomendações", "#F6DA73"),
]


PROFILES = {
    "youtube_long": {"label": "YouTube longo", "width": 1280, "height": 720, "fps": 30, "default_duration": 1800, "max_duration": 14400},
    "vertical_short": {"label": "Shorts · Reels · TikTok", "width": 720, "height": 1280, "fps": 30, "default_duration": 45, "max_duration": 180},
    "preview": {"label": "Prévia rápida", "width": 960, "height": 540, "fps": 24, "default_duration": 12, "max_duration": 60},
}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:42] or "ambient"


class ContentCrew:
    """Deterministic local agents. Each output can later be replaced by an API provider."""

    def catalog(self) -> list[dict[str, str]]:
        return [asdict(agent) for agent in AGENTS]

    def ideas(self) -> list[dict[str, str]]:
        return [
            {"topic": "Biblioteca japonesa sob chuva suave ao anoitecer", "intent": "foco e leitura", "why": "Ambiente reconhecível e promessa imediata"},
            {"topic": "Cabana nórdica com lareira durante uma nevasca", "intent": "relaxamento e sono", "why": "Contraste entre abrigo e clima cria imersão"},
            {"topic": "Café parisiense vazio antes do amanhecer", "intent": "estudo e escrita", "why": "Cenário aspiracional com baixa distração"},
            {"topic": "Nave espacial observando uma tempestade em Júpiter", "intent": "foco profundo", "why": "Visual distintivo para série de ficção ambiente"},
            {"topic": "Jardim de inverno com chuva no telhado de vidro", "intent": "calma e meditação", "why": "Paisagem sonora rica e visual sereno"},
        ]

    def run(self, topic: str, duration: int, profile_id: str, narration: bool) -> dict[str, Any]:
        profile = PROFILES.get(profile_id, PROFILES["youtube_long"])
        topic_lower = topic.lower()
        mood = "acolhedor" if any(x in topic_lower for x in ("cabana", "café", "biblioteca", "lareira")) else "imersivo"
        use_case = "foco e leitura" if any(x in topic_lower for x in ("biblioteca", "café", "estudo", "chuva")) else "relaxamento e sono"
        keywords = list(dict.fromkeys([topic_lower, f"{topic_lower} ambience", use_case, "som ambiente", "ambiente imersivo"]))
        research = {
            "audience": f"Pessoas buscando {use_case} sem interrupções",
            "intent": "background listening",
            "keywords": keywords,
            "opportunity": "Promessa clara + longa permanência + identidade visual consistente",
        }
        strategy = {
            "promise": f"Transportar o público para {topic_lower} em poucos segundos",
            "primary_goal": "watch_time" if profile_id == "youtube_long" else "completion_rate",
            "hook": f"Você entrou em {topic_lower}. O mundo lá fora pode esperar.",
            "cadence": "entrada suave, estabilidade e microvariações sem cortes bruscos",
        }
        intro = (
            f"Bem-vindo a {topic}. Diminua o ritmo e deixe este ambiente acompanhar seu momento. "
            "Respire com calma. A partir daqui, a experiência segue sem interrupções."
        )
        chapter_seconds = 1200 if duration >= 2400 else max(300, duration // 3)
        chapters = []
        for second in range(0, duration, max(1, chapter_seconds)):
            hours, rest = divmod(second, 3600)
            minutes, seconds = divmod(rest, 60)
            chapters.append({"time": f"{hours:02}:{minutes:02}:{seconds:02}", "label": "Imersão" if second else "Entrada no ambiente"})
        script = {"intro": intro, "spoken": intro if narration else "", "chapters": chapters, "on_screen": [strategy["hook"]]}
        palette = ["#071426", "#153A4F", "#D8A96C"] if "chuva" in topic_lower else ["#0B1628", "#2A3750", "#CF9A62"]
        visual = {
            "mood": mood,
            "palette": palette,
            "motion": "slow_push_in",
            "sound": "brown noise, low warm drone, 2s fade",
            "asset_brief": f"Cena original de {topic_lower}, sem marcas, sem personagens identificáveis, composição cinematográfica",
        }
        minutes = max(1, math.ceil(duration / 60))
        title = f"{topic} — Ambiente para {use_case}"
        seo = {
            "title": title[:96],
            "description": (
                f"Entre em uma atmosfera de {topic_lower} criada para {use_case}.\n\n"
                f"Duração: {minutes} min · experiência original · use fones.\n\n"
                "#ambience #focus #relax"
            ),
            "tags": ["ambience", "focus", "relax", "study", slug(topic), profile["label"].lower()],
        }
        compliance = {
            "publish_mode": "manual_safe",
            "checks": ["asset original ou licenciado", "sem alegações enganosas", "metadados revisáveis", "upload não executado"],
            "risks": ["Confirmar licença de qualquer asset externo antes da aprovação"],
            "passed": True,
        }
        score = 92
        warnings = []
        if duration < 600 and profile_id == "youtube_long":
            score -= 8
            warnings.append("Para o canal principal, teste 30–120 minutos após validar a prévia.")
        if not narration:
            warnings.append("Sem narração: ideal para ambientação contínua e baixo atrito.")
        review = {
            "score": score,
            "verdict": "Pronto para prévia" if score >= 80 else "Requer ajustes",
            "warnings": warnings,
            "next_action": "Renderizar, assistir aos 30s iniciais e revisar o pacote antes de aprovar.",
        }
        return {
            "research": research,
            "strategy": strategy,
            "script": script,
            "visual": visual,
            "seo": seo,
            "compliance": compliance,
            "review": review,
            "production": {"profile": profile_id, "format": profile["label"], "resolution": f"{profile['width']}x{profile['height']}", "fps": profile["fps"], "duration_seconds": duration},
        }
