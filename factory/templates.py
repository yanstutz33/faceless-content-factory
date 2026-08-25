from __future__ import annotations

from typing import Any


SERIES: dict[str, dict[str, Any]] = {
    "rainy_places": {
        "name": "Lugares sob chuva", "description": "Cenários acolhedores para foco e leitura.",
        "profile": "youtube_long", "duration": 3600, "narration": False,
        "topics": ["Biblioteca japonesa sob chuva", "Café vazio em uma noite chuvosa", "Jardim de inverno com chuva no vidro"],
        "color": "#67D4FF",
    },
    "cozy_worlds": {
        "name": "Mundos acolhedores", "description": "Abrigos quentes em climas intensos.",
        "profile": "youtube_long", "duration": 5400, "narration": False,
        "topics": ["Cabana nórdica durante uma nevasca", "Lareira em uma casa vitoriana", "Quarto no sótão durante uma tempestade"],
        "color": "#FFB86B",
    },
    "cosmic_focus": {
        "name": "Foco cósmico", "description": "Ficção ambiente para trabalho profundo.",
        "profile": "youtube_long", "duration": 7200, "narration": False,
        "topics": ["Estação orbital sobre Júpiter", "Nave cargueira cruzando uma nebulosa", "Observatório lunar abandonado"],
        "color": "#D99BFF",
    },
    "vertical_moments": {
        "name": "Momentos verticais", "description": "Recortes para Shorts, Reels e TikTok.",
        "profile": "vertical_short", "duration": 30, "narration": True,
        "topics": ["30 segundos em uma biblioteca secreta", "Uma janela para a chuva em Tóquio", "Pausa junto à lareira"],
        "color": "#75D8B8",
    },
}


def series_catalog() -> list[dict[str, Any]]:
    return [{"id": key, **value} for key, value in SERIES.items()]
