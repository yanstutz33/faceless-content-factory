from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from typing import Any

from .llm import OpenAIPlanEnhancer
from .teams import DEFAULT_TEAM_ID, apply_team_playbook


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
    AgentSpec("repurpose", "Recorte", "Reaproveitamento multicanal", "Clipes verticais e pacote por plataforma", "#FF8FCB"),
]


PROFILES = {
    "youtube_long": {"label": "YouTube longo", "width": 1920, "height": 1080, "fps": 30,
                     "min_duration": 1800, "default_duration": 3600, "max_duration": 3600},
    "vertical_short": {"label": "Shorts · Reels · TikTok", "width": 720, "height": 1280, "fps": 30,
                       "min_duration": 15, "default_duration": 45, "max_duration": 180},
    "preview": {"label": "Prévia rápida · não publicável", "width": 960, "height": 540, "fps": 24,
                "min_duration": 5, "default_duration": 12, "max_duration": 60},
}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:42] or "ambient"


ENGLISH_AMBIENT_TITLES = (
    "Go to Sleep, It's 3 A.M.",
    "It's Okay. Get Some Rest.",
    "You Don't Have to Figure It Out Tonight.",
    "The World Can Wait Until Morning.",
    "Stay Here Until the Rain Stops.",
    "Let Your Mind Be Quiet for a While.",
    "Some Nights Are Meant for Letting Go.",
    "You Made It Through Another Day.",
    "Nothing Is Expected of You Tonight.",
    "Take a Breath. You're Safe Here.",
    "Maybe Tomorrow Will Feel Lighter.",
    "Rest Now. You've Done Enough.",
    "Leave the Noise Outside for Tonight.",
    "It's Late. Be Gentle with Yourself.",
    "You Can Start Again in the Morning.",
    "Let the Rain Carry Today Away.",
)


def english_ambient_metadata(topic: str, duration: int, use_case: str) -> tuple[str, str, list[str]]:
    """Create deterministic, natural English packaging without exposing Portuguese working topics."""
    index = sum(ord(character) for character in topic.casefold()) % len(ENGLISH_AMBIENT_TITLES)
    phrase = ENGLISH_AMBIENT_TITLES[index]
    purpose = "sleep and unwinding" if "sono" in use_case else "focus and quiet reflection"
    minutes = max(1, math.ceil(duration / 60))
    title = f"{phrase} | Rainy Night Lo-fi"
    description = (
        f"A quiet {minutes}-minute lo-fi session for {purpose}. Let the soft music and rainy-night "
        "atmosphere stay with you while you rest, read, study, or simply slow down.\n\n"
        "Headphones recommended. Original visual and licensed or original music.\n\n"
        "#lofi #rainynight #sleepmusic #studywithme"
    )
    return title[:96], description, ["lofi", "rainy night", "sleep music", "study music", "relax", "3 a.m."]


class ContentCrew:
    """Deterministic local agents. Each output can later be replaced by an API provider."""

    def __init__(self, enhancer: OpenAIPlanEnhancer | None = None):
        self.enhancer = enhancer or OpenAIPlanEnhancer()

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

    def run(self, topic: str, duration: int, profile_id: str, narration: bool,
            team_id: str = DEFAULT_TEAM_ID) -> dict[str, Any]:
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
        palette = ["#071426", "#153A4F", "#D8A96C"] if "chuv" in topic_lower else ["#0B1628", "#2A3750", "#CF9A62"]
        if any(x in topic_lower for x in ("chuv", "tempestade", "rain")):
            sound_profile = "rain"
            sound_direction = "beat lo-fi original com acordes suaves e chuva discreta ao fundo"
        elif any(x in topic_lower for x in ("nave", "espaço", "espacial", "júpiter", "nebulosa", "orbital", "lunar")):
            sound_profile = "cosmic"
            sound_direction = "lo-fi espacial original, acordes aéreos e beat relaxado"
        elif any(x in topic_lower for x in ("cabana", "lareira", "café", "quarto", "casa")):
            sound_profile = "cozy"
            sound_direction = "lo-fi acolhedor original, piano elétrico suave e beat quente"
        else:
            sound_profile = "focus"
            sound_direction = "música chill/lo-fi original para foco, com beat e acordes suaves"
        visual = {
            "mood": mood,
            "palette": palette,
            "motion": "câmera fixa; movimento localizado em fumaça, chuva ou pontos de luz",
            "sound": sound_direction,
            "sound_profile": sound_profile,
            "asset_brief": f"Cena original de {topic_lower}, sem marcas, sem personagens identificáveis, composição cinematográfica",
            "thumbnail": {
                "style_id": "nocturnal_rain_v1",
                "headline": "",
                "composition": "cena 16:9 limpa, noturna e cinematográfica; texto curto central opcional",
            },
        }
        title, description, tags = english_ambient_metadata(topic, duration, use_case)
        seo = {
            "title": title,
            "description": description,
            "tags": tags,
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
        plan = {
            "research": research,
            "strategy": strategy,
            "script": script,
            "visual": visual,
            "seo": seo,
            "compliance": compliance,
            "review": review,
            "production": {"profile": profile_id, "format": profile["label"], "resolution": f"{profile['width']}x{profile['height']}", "fps": profile["fps"], "duration_seconds": duration},
        }
        plan = apply_team_playbook(plan, team_id)
        return self.enhancer.enhance(topic, duration, profile_id, plan)

