from __future__ import annotations

from typing import Any


SERIES: dict[str, dict[str, Any]] = {
    "japan_after_rain": {
        "name": "Japão depois da chuva", "description": "Ruas, lojas e cafés japoneses na madrugada azul.",
        "profile": "youtube_long", "duration": 3600, "narration": False,
        "team_id": "youtube_ambient",
        "topics": ["Loja de conveniência japonesa às 3 da manhã", "Rua residencial japonesa depois da chuva", "Café japonês na encosta sob chuva"],
        "color": "#4d7cff", "cover_asset": "rainy-konbini-clean.png",
    },
    "city_after_dark": {
        "name": "Cidade depois das três", "description": "Janelas altas, prédios silenciosos e luzes distantes.",
        "profile": "youtube_long", "duration": 3600, "narration": False,
        "team_id": "youtube_ambient",
        "topics": ["Cidade silenciosa às 3 da manhã", "Memórias diante de uma janela chuvosa", "Apartamento alto sobre a cidade à noite"],
        "color": "#2f8f84", "cover_asset": "emerald-city-3am.png",
    },
    "rainy_refuges": {
        "name": "Refúgios na madrugada", "description": "Interiores escuros com chuva do lado de fora e luz quente.",
        "profile": "youtube_long", "duration": 3600, "narration": False,
        "team_id": "youtube_ambient",
        "topics": ["Quarto silencioso diante da cidade chuvosa", "Sala de discos em uma noite sem sono", "Café vazio com vista para o mar à noite"],
        "color": "#ff9d58", "cover_asset": "rainy-vinyl-listening-room.png",
    },
    "anime_midnight": {
        "name": "Anime original à meia-noite", "description": "Personagens adultos originais, chuva urbana e melancolia lo-fi.",
        "profile": "youtube_long", "duration": 3600, "narration": False,
        "team_id": "youtube_ambient",
        "topics": ["Personagem anime original descansando diante da chuva", "Personagem anime original esperando junto à máquina de bebidas", "Personagem anime original observando a cidade pela janela"],
        "color": "#9c85ff", "cover_asset": "anime-window-night.png",
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

