from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).parents[1]
OUTPUT = ROOT / "assets" / "channel"

INK = "#141018"
PANEL = "#1e1828"
PAPER = "#f4efe4"
PURPLE = "#9c85ff"
BLUE = "#69c7ff"
AMBER = "#f0aa4f"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/bahnschrift.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default(size=size)


def dot_grid(draw: ImageDraw.ImageDraw, width: int, height: int, step: int = 10) -> None:
    for y in range(0, height, step):
        for x in range(0, width, step):
            draw.ellipse((x, y, x + 1, y + 1), fill="#32283d")


def twin_f(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
    left, top, right, bottom = box
    width, height = right - left, bottom - top
    radius = max(10, width // 16)
    shadow = max(6, width // 28)
    draw.rounded_rectangle((left + shadow, top + shadow, right + shadow, bottom + shadow), radius=radius,
                           fill=PURPLE)
    draw.rounded_rectangle(box, radius=radius, fill=PAPER)
    letter = font(int(height * .52), bold=True)
    draw.text((left + width * .22, top + height * .49), "F", font=letter, fill=INK, anchor="mm")
    mirror = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    mirror_draw = ImageDraw.Draw(mirror)
    mirror_draw.text((width * .50, height * .49), "F", font=letter, fill=PURPLE, anchor="mm")
    mirror = mirror.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    draw._image.alpha_composite(mirror, (left, top))
    bar_y = bottom - max(8, height // 18)
    draw.rectangle((left + width * .12, bar_y, left + width * .42, bar_y + max(4, height // 32)), fill=BLUE)
    draw.rectangle((left + width * .45, bar_y, left + width * .75, bar_y + max(4, height // 32)), fill=AMBER)


def avatar() -> Path:
    image = Image.new("RGBA", (800, 800), INK)
    draw = ImageDraw.Draw(image)
    dot_grid(draw, 800, 800, 12)
    draw.rounded_rectangle((70, 70, 730, 730), radius=42, fill=PANEL, outline="#4a3d59", width=3)
    twin_f(draw, (190, 175, 610, 595))
    draw.text((400, 680), "FF/01", font=font(34, bold=True), fill=PURPLE, anchor="mm")
    path = OUTPUT / "ffactory-avatar-800.png"
    image.convert("RGB").save(path, quality=96)
    return path


def banner() -> Path:
    image = Image.new("RGBA", (2560, 1440), INK)
    draw = ImageDraw.Draw(image)
    dot_grid(draw, 2560, 1440, 10)
    draw.polygon([(1740, 0), (2560, 0), (2560, 1440), (1240, 1440)], fill="#20162f")
    draw.polygon([(1990, 0), (2260, 0), (1540, 1440), (1270, 1440)], fill="#32205a")
    draw.line((1810, 180, 1270, 1260), fill=BLUE, width=8)
    draw.line((1870, 180, 1330, 1260), fill=PURPLE, width=3)
    twin_f(draw, (585, 565, 825, 805))
    draw.text((910, 635), "FFACTORY", font=font(108, bold=True), fill=PAPER, anchor="lm")
    draw.text((914, 758), "AUTONOMOUS MOOD SYSTEMS", font=font(31, bold=True), fill=PURPLE, anchor="lm")
    draw.line((910, 815, 1730, 815), fill=PAPER, width=4)
    draw.text((1730, 875), "FF/01 · MOOD / MEDIA / MOTION", font=font(21, bold=True), fill="#a79fb2",
              anchor="ra")
    path = OUTPUT / "ffactory-youtube-banner-2560x1440.png"
    image.convert("RGB").save(path, quality=96)
    return path


def watermark() -> Path:
    image = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    twin_f(draw, (42, 34, 246, 238))
    path = OUTPUT / "ffactory-watermark-300.png"
    image.save(path)
    return path


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    paths = [avatar(), banner(), watermark()]
    manifest = {
        "brand": "FFACTORY",
        "system": "FF/01 · Autonomous Mood Systems",
        "generated_by": "scripts/generate_channel_brand.py",
        "assets": [
            {"file": paths[0].name, "use": "YouTube profile image", "size": "800x800"},
            {"file": paths[1].name, "use": "YouTube channel banner", "size": "2560x1440",
             "safe_area": "central 1546x423"},
            {"file": paths[2].name, "use": "YouTube video watermark", "size": "300x300 transparent"},
        ],
        "palette": {"ink": INK, "panel": PANEL, "paper": PAPER, "purple": PURPLE,
                    "blue": BLUE, "amber": AMBER},
    }
    (OUTPUT / "brand-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n".join(str(path) for path in paths))


if __name__ == "__main__":
    main()
