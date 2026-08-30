from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Any


COVER_STYLE_ID = "nocturnal_rain_v1"

# This catalog is intentionally narrow. It records the visual direction approved by
# the user instead of letting each production invent a different thumbnail style.
COVER_REFERENCES: tuple[dict[str, Any], ...] = (
    {"id": "rainy-konbini-rest", "label": "Loja noturna · rest.", "file": "rainy-konbini-rest.png", "embedded_text": "rest.",
     "keywords": ("rua", "loja", "conveniencia", "japao", "descanso", "rest")},
    {"id": "emerald-city-3am", "label": "Cidade esmeralda · 3am.", "file": "emerald-city-3am.png", "embedded_text": "3am.",
     "keywords": ("cidade", "predio", "madrugada", "3am", "urbano")},
    {"id": "anime-rainy-alley", "label": "Beco anime sob chuva", "file": "anime-rainy-alley.png", "embedded_text": None,
     "keywords": ("anime", "beco", "rua", "personagem", "solidao")},
    {"id": "rainy-hillside-cafe", "label": "Café chuvoso na colina", "file": "rainy-hillside-cafe.png", "embedded_text": None,
     "keywords": ("cafe", "cafeteria", "lago", "colina", "porto", "acolhedor")},
    {"id": "anime-sleeping-city", "label": "Sono sobre a cidade", "file": "anime-sleeping-city.png", "embedded_text": None,
     "keywords": ("anime", "sono", "dormir", "quarto", "cama", "relaxar")},
    {"id": "anime-window-night", "label": "Janela para a cidade", "file": "anime-window-night.png", "embedded_text": None,
     "keywords": ("anime", "janela", "cidade", "quarto", "contemplar")},
    {"id": "rainy-window-memories", "label": "Memórias na chuva", "file": "rainy-window-memories.png", "embedded_text": "memories.",
     "keywords": ("memoria", "memorias", "nostalgia", "janela", "chuva")},
    {"id": "rainy-konbini-clean", "label": "Loja noturna sem texto", "file": "rainy-konbini-clean.png", "embedded_text": None,
     "keywords": ("rua", "loja", "conveniencia", "japao", "chuva", "noite")},
    {"id": "rainy-vinyl-listening-room", "label": "Sala de vinil na chuva", "file": "rainy-vinyl-listening-room.png", "embedded_text": None,
     "keywords": ("vinil", "disco", "musica", "loja", "escuta", "fone", "estudo")},
)


def _normalized(value: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_text).split())


def cover_reference_dir(root: Path) -> Path:
    return root / "assets" / "covers" / COVER_STYLE_ID.replace("_", "-")


def cover_assets(root: Path) -> list[dict[str, Any]]:
    directory = cover_reference_dir(root)
    return [
        {
            "name": f"Capa oficial · {item['label']}",
            "path": str((directory / item["file"]).resolve()),
            "license_type": "provider_generated",
            "source_url": "ChatGPT · coleção fornecida pelo usuário em 2026-08-29",
            "notes": f"Coleção {COVER_STYLE_ID}; referência oficial; texto embutido: {item['embedded_text'] or 'nenhum'}",
            "approved": True,
        }
        for item in COVER_REFERENCES
        if (directory / item["file"]).is_file()
    ]


def select_cover_references(root: Path, topic: str,
                            excluded_ids: set[str] | None = None) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Return two distinct, deterministic covers from the approved visual collection."""
    directory = cover_reference_dir(root)
    available = [item for item in COVER_REFERENCES if (directory / item["file"]).is_file()]
    if len(available) < 2:
        return None
    words = set(_normalized(topic).split())
    seed = int(hashlib.sha256(f"{COVER_STYLE_ID}:{_normalized(topic)}".encode()).hexdigest()[:12], 16)
    ranked = []
    for index, item in enumerate(available):
        overlap = len(words.intersection(item["keywords"]))
        tie_break = int(hashlib.sha256(f"{seed}:{item['id']}".encode()).hexdigest()[:8], 16)
        ranked.append((overlap, tie_break, index, item))
    ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
    excluded_ids = excluded_ids or set()
    first_row = next((row for row in ranked if row[3]["id"] not in excluded_ids), None)
    if not first_row:
        return None
    first = first_row[3]
    # A/B always compares a clean image with a minimal-text image when possible.
    alternatives = [row for row in ranked if row[3]["id"] != first["id"]]
    complementary = [row for row in alternatives if bool(row[3]["embedded_text"]) != bool(first["embedded_text"])]
    second = (complementary or alternatives)[0][3]
    return ({**first, "path": str(directory / first["file"])},
            {**second, "path": str(directory / second["file"])})


def visual_direction() -> dict[str, Any]:
    return {
        "id": COVER_STYLE_ID,
        "format": "16:9 landscape",
        "style": "cinematic anime-realism with detailed nocturnal environments",
        "palette": "deep navy, petrol blue and emerald shadows with sparse warm amber light",
        "weather": "rain belongs outdoors or on glass; never inside a dry room",
        "camera": "fixed, wide and contemplative; no shake, fake zoom or parallax drift",
        "typography": "optional single short lowercase word centered in white; otherwise no text",
        "avoid": [
            "large title blocks", "eyebrows or badges", "dark lower-third panels", "collages",
            "recognizable copyrighted characters", "new logos or trademarks", "watermarks",
            "rain crossing indoor furniture or people",
        ],
        "prompt": (
            "Original 16:9 cinematic nocturnal scene, anime-realism, dense environmental detail, "
            "deep navy and petrol-blue palette, sparse warm amber practical lights, wet exterior "
            "reflections, quiet melancholic late-night mood, fixed wide camera, subtle film texture. "
            "Rain only outdoors or on window glass. No camera shake, no collage, no watermark, "
            "no existing character, no logo or trademark. Leave the image clean; optionally add "
            "one short lowercase white word centered with a final period."
        ),
    }
