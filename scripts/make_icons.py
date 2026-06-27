"""Generate PWA / home-screen icons for Vires.

    uv run --with pillow python scripts/make_icons.py

Dark slate field, amber "V" — the strength mark. Writes the icon set into
``web/public``. Re-run to regenerate.
"""

from __future__ import annotations

import pathlib

from PIL import Image, ImageDraw, ImageFont

OUT = pathlib.Path(__file__).resolve().parent.parent / "web" / "public"
BG = (15, 23, 42)  # slate-900
FG = (245, 158, 11)  # amber-500


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/SFNSDisplay.ttf",
        "/Library/Fonts/Arial.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make(size: int, name: str, *, maskable: bool = False, rounded: bool = False) -> None:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = int(size * 0.0) if maskable else int(size * 0.06)
    if rounded:
        d.rounded_rectangle([pad, pad, size - pad, size - pad], radius=int(size * 0.22), fill=BG)
    else:
        d.rectangle([pad, pad, size - pad, size - pad], fill=BG)
    font = _font(int(size * 0.62))
    d.text((size / 2, size / 2), "V", font=font, fill=FG, anchor="mm")
    OUT.mkdir(parents=True, exist_ok=True)
    img.save(OUT / name)
    print("wrote", name)


def main() -> None:
    make(192, "icon-192.png", rounded=True)
    make(512, "icon-512.png", rounded=True)
    make(512, "icon-512-maskable.png", maskable=True)
    make(180, "apple-touch-icon.png", rounded=True)
    make(32, "favicon-32.png", rounded=True)


if __name__ == "__main__":
    main()
