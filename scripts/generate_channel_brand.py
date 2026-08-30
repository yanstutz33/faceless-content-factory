from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps


ROOT = Path(__file__).parents[1]
OUTPUT = ROOT / "assets" / "channel"

INK = "#08080d"
PANEL = "#141018"
PAPER = "#f4efe4"
PURPLE = "#8a66ff"
SOFT = "#b8afc4"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts/bahnschrift.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default(size=size)


def circle_crop(source: Image.Image, size: int, border: int = 0) -> Image.Image:
    image = ImageOps.fit(source.convert("RGB"), (size, size), method=Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((border, border, size - border - 1, size - border - 1), fill=255)
    result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    result.paste(image, (0, 0), mask)
    return result


def avatar() -> Path:
    source = Image.open(OUTPUT / "pausa-pra-anime-profile-source.jpg")
    image = Image.new("RGBA", (800, 800), INK)
    draw = ImageDraw.Draw(image)
    draw.ellipse((52, 52, 748, 748), fill=PURPLE)
    draw.ellipse((70, 70, 730, 730), fill=PAPER)
    portrait = circle_crop(source, 610)
    image.alpha_composite(portrait, (95, 88))
    yami = circle_crop(Image.open(OUTPUT / "yami-mark-source.png"), 120)
    draw.ellipse((599, 588, 730, 719), fill=PAPER)
    image.alpha_composite(yami, (605, 594))
    path = OUTPUT / "pausa-pra-anime-avatar-800.png"
    image.convert("RGB").save(path, optimize=True)
    return path


def banner() -> Path:
    art = Image.open(OUTPUT / "pausa-pra-anime-banner-art.png").convert("RGB")
    base = ImageOps.fit(art, (2560, 1440), method=Image.Resampling.LANCZOS)
    base = base.filter(ImageFilter.GaussianBlur(20))
    base = ImageEnhance.Brightness(base).enhance(.52).convert("RGBA")

    foreground = ImageOps.contain(art, (2560, 1060), method=Image.Resampling.LANCZOS).convert("RGBA")
    base.alpha_composite(foreground, ((2560 - foreground.width) // 2, (1440 - foreground.height) // 2))

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rounded_rectangle((490, 500, 2070, 940), radius=18, fill=(8, 8, 13, 158),
                                   outline=(244, 239, 228, 38), width=2)
    base.alpha_composite(overlay)

    portrait = circle_crop(Image.open(OUTPUT / "pausa-pra-anime-profile-source.jpg"), 205)
    ring = Image.new("RGBA", (225, 225), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse((0, 0, 224, 224), fill=PURPLE)
    ring.alpha_composite(portrait, (10, 10))
    base.alpha_composite(ring, (555, 596))

    draw = ImageDraw.Draw(base)
    draw.text((830, 600), "PAUSA", font=font(105, bold=True), fill=PAPER, anchor="la", stroke_width=1,
              stroke_fill=INK)
    draw.text((830, 720), "PRA ANIME", font=font(105, bold=True), fill=PAPER, anchor="la", stroke_width=1,
              stroke_fill=INK)
    draw.rectangle((835, 828, 1475, 834), fill=PURPLE)
    draw.text((830, 870), "ANIMES  •  ANÁLISES  •  NERDICES", font=font(27, bold=True), fill=SOFT, anchor="la")
    yami = circle_crop(Image.open(OUTPUT / "yami-mark-source.png"), 56)
    base.alpha_composite(yami, (1790, 838))
    draw.text((1930, 868), "BY YAMI", font=font(24, bold=True), fill=PURPLE, anchor="ra")

    path = OUTPUT / "pausa-pra-anime-youtube-banner-2560x1440.png"
    base.convert("RGB").save(path, optimize=True, quality=96)
    return path


def watermark() -> Path:
    image = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((16, 16, 284, 284), fill=PURPLE)
    yami = circle_crop(Image.open(OUTPUT / "yami-mark-source.png"), 252)
    image.alpha_composite(yami, (24, 24))
    path = OUTPUT / "pausa-pra-anime-watermark-300.png"
    image.save(path, optimize=True)
    return path


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    paths = [avatar(), banner(), watermark()]
    manifest = {
        "brand": "PAUSA PRA ANIME",
        "handle": "@pausapraanime",
        "signature": "YAMI",
        "generated_by": "scripts/generate_channel_brand.py",
        "assets": [
            {"file": paths[0].name, "use": "YouTube profile image", "size": "800x800"},
            {"file": paths[1].name, "use": "YouTube channel banner", "size": "2560x1440",
             "safe_area": "central 1546x423"},
            {"file": paths[2].name, "use": "YouTube video watermark", "size": "300x300 transparent"},
        ],
        "source_identity": {
            "instagram": "https://www.instagram.com/pausapraanime/",
            "profile_source": "pausa-pra-anime-profile-source.jpg",
            "art_source": "pausa-pra-anime-banner-art.png",
            "fashion_brand_source": "yami-mark-source.png",
        },
        "palette": {"ink": INK, "panel": PANEL, "paper": PAPER, "purple": PURPLE, "soft": SOFT},
    }
    (OUTPUT / "brand-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n".join(str(path) for path in paths))


if __name__ == "__main__":
    main()
