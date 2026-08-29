from __future__ import annotations

from typing import Any


SERIES: dict[str, dict[str, Any]] = {
    "rainy_places": {
        "name": "Lugares sob chuva", "description": "Cenários acolhedores para foco e leitura.",
        "profile": "youtube_long", "duration": 3600, "narration": False,
        "team_id": "youtube_ambient",
        "topics": ["Biblioteca japonesa sob chuva", "Café vazio em uma noite chuvosa", "Jardim de inverno com chuva no vidro"],
        "color": "#67D4FF",
    },
    "cozy_worlds": {
        "name": "Mundos acolhedores", "description": "Abrigos quentes em climas intensos.",
        "profile": "youtube_long", "duration": 3600, "narration": False,
        "team_id": "youtube_ambient",
        "topics": ["Cabana nórdica durante uma nevasca", "Lareira em uma casa vitoriana", "Quarto no sótão durante uma tempestade"],
        "color": "#FFB86B",
    },
    "cosmic_focus": {
        "name": "Foco cósmico", "description": "Ficção ambiente para trabalho profundo.",
        "profile": "youtube_long", "duration": 3600, "narration": False,
        "team_id": "youtube_ambient",
        "topics": ["Estação orbital sobre Júpiter", "Nave cargueira cruzando uma nebulosa", "Observatório lunar abandonado"],
        "color": "#D99BFF",
    },
    "anime_nights": {
        "name": "Anime Nights original", "description": "Personagens adultos originais em noites lo-fi, sem franquias.",
        "profile": "youtube_long", "duration": 3600, "narration": False,
        "team_id": "youtube_ambient",
        "topics": ["Apartamento anime original sob chuva à meia-noite", "Personagem anime original estudando com música lo-fi", "Janela da cidade em uma noite anime original"],
        "color": "#5EC8D8",
    },
    "vertical_moments": {
        "name": "Momentos verticais", "description": "Recortes para Shorts, Reels e TikTok.",
        "profile": "vertical_short", "duration": 30, "narration": True,
        "team_id": "tiktok_experiments",
        "topics": ["30 segundos em uma biblioteca secreta", "Uma janela para a chuva em Tóquio", "Pausa junto à lareira"],
        "color": "#75D8B8",
    },
}


def series_catalog() -> list[dict[str, Any]]:
    return [{"id": key, **value} for key, value in SERIES.items() if value.get("profile") == "youtube_long"]

