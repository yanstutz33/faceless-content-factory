from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps


ROOT = Path(__file__).parents[1]
OUTPUT = ROOT / "assets" / "channel"
SOURCE = ROOT / "assets" / "covers" / "nocturnal-rain-v1" / "rainy-window-memories.png"
AVATAR_SOURCE = OUTPUT / "3am-shelter-avatar-source.png"

INK = "#071116"
PAPER = "#f4efe4"
TEAL = "#5be0cf"
SOFT = "#aebdc2"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts/bahnschrift.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default(size=size)


def avatar() -> Path:
    image = Image.open(AVATAR_SOURCE).convert("RGB")
    image = ImageOps.fit(image, (800, 800), method=Image.Resampling.LANCZOS)
    path = OUTPUT / "3am-shelter-avatar-800.png"
    image.save(path, optimize=True)
    return path


def banner() -> Path:
    art = Image.open(SOURCE).convert("RGB")
    base = ImageOps.fit(art, (2560, 1440), method=Image.Resampling.LANCZOS)
    base = ImageEnhance.Brightness(base).enhance(.62).convert("RGBA")
    shade = Image.new("RGBA", base.size, (0, 0, 0, 0))
    shade_draw = ImageDraw.Draw(shade)
    shade_draw.rectangle((0, 0, 2560, 1440), fill=(4, 10, 14, 58))
    shade_draw.rounded_rectangle((500, 500, 2060, 940), radius=28, fill=(4, 10, 14, 172),
                                 outline=(91, 224, 207, 85), width=3)
    base = Image.alpha_composite(base, shade)
    draw = ImageDraw.Draw(base)
    draw.text((1280, 640), "3AM SHELTER", font=font(125, True), fill=PAPER, anchor="mm")
    draw.rectangle((930, 735, 1630, 742), fill=TEAL)
    draw.text((1280, 820), "A QUIET PLACE AFTER MIDNIGHT", font=font(34, True), fill=SOFT, anchor="mm")
    path = OUTPUT / "3am-shelter-youtube-banner-2560x1440.png"
    base.convert("RGB").save(path, optimize=True, quality=96)
    return path


def watermark() -> Path:
    image = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((18, 18, 282, 282), fill=(7, 17, 22, 218), outline=TEAL, width=5)
    draw.text((150, 132), "3AM", font=font(78, True), fill=PAPER, anchor="mm")
    draw.text((150, 198), "SHELTER", font=font(26, True), fill=TEAL, anchor="mm")
    path = OUTPUT / "3am-shelter-watermark-300.png"
    image.save(path, optimize=True)
    return path


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    paths = [avatar(), banner(), watermark()]
    manifest = {
        "brand": "3AM Shelter",
        "identity_scope": "independent_ambient_music_channel",
        "generated_by": "scripts/generate_channel_brand.py",
        "assets": [
            {"file": paths[0].name, "use": "YouTube profile image", "size": "800x800"},
            {"file": paths[1].name, "use": "YouTube channel banner", "size": "2560x1440",
             "safe_area": "central 1546x423"},
            {"file": paths[2].name, "use": "YouTube video watermark", "size": "300x300 transparent"},
        ],
        "source_identity": {
            "banner_visual": str(SOURCE.relative_to(ROOT)).replace("\\", "/"),
            "avatar_visual": str(AVATAR_SOURCE.relative_to(ROOT)).replace("\\", "/"),
            "rights": "approved user-supplied collection and generated original avatar artwork",
            "excluded_brands": ["Pausa Pra Anime", "YAMI"],
        },
        "palette": {"ink": INK, "paper": PAPER, "teal": TEAL, "soft": SOFT},
    }
    (OUTPUT / "brand-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\n".join(str(path) for path in paths))


if __name__ == "__main__":
    main()
