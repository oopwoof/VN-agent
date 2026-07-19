"""Seed the local open-source asset library with placeholder CC0 assets.

Rationale: v4 P0-2 shipped an empty manifest (contract only). This script
generates 8 placeholder PNG backgrounds + 3 placeholder character sprites
using PIL — I hold the copyright and release them CC0. That makes the
library-hit demo actually work end-to-end without the pipeline calling
image-gen APIs; production users are expected to overwrite these files
with real Kenney / OpenGameArt / itch.io CC0 art (matching filenames
means no manifest edit required).

Idempotent: re-running overwrites files but keeps the manifest in sync.
Run: `uv run python scripts/seed_opensource_library.py`
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_ROOT = Path(__file__).resolve().parent.parent
_LIB_DIR = _ROOT / "data" / "assets" / "opensource"
_MANIFEST = _LIB_DIR / "manifest.json"


# Colour palette — deliberately muted so placeholders read as "reserved slots"
# not as final art. Matches typical VN backdrop moods (day/night/dusk/dawn).
_BG_PALETTE = {
    "day":    ((222, 236, 245), (170, 200, 220)),
    "night":  ((20, 30, 55),   (60, 65, 100)),
    "dusk":   ((235, 165, 130), (95, 60, 100)),
    "dawn":   ((250, 210, 190), (140, 175, 195)),
    "warm":   ((240, 220, 190), (180, 130, 100)),
    "cool":   ((190, 215, 225), (110, 140, 175)),
}


def _linear_gradient(size, top_rgb, bottom_rgb):
    """Two-stop vertical gradient, no dependencies beyond PIL."""
    w, h = size
    img = Image.new("RGB", (w, h))
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(top_rgb[0] * (1 - t) + bottom_rgb[0] * t)
        g = int(top_rgb[1] * (1 - t) + bottom_rgb[1] * t)
        b = int(top_rgb[2] * (1 - t) + bottom_rgb[2] * t)
        for x in range(w):
            img.putpixel((x, y), (r, g, b))
    return img


def _label(img, text, sub=""):
    """Overlay a subtle label so debug is obvious. Font fallback keeps
    the script runnable even without a Windows font available."""
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 48)
        subfont = ImageFont.truetype("arial.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
        subfont = ImageFont.load_default()
    box = draw.textbbox((0, 0), text, font=font)
    x = (img.width - (box[2] - box[0])) // 2
    y = img.height // 2 - 30
    draw.text((x + 2, y + 2), text, fill=(0, 0, 0, 90), font=font)
    draw.text((x, y), text, fill=(240, 240, 240), font=font)
    if sub:
        sbox = draw.textbbox((0, 0), sub, font=subfont)
        sx = (img.width - (sbox[2] - sbox[0])) // 2
        sy = y + 70
        draw.text((sx + 1, sy + 1), sub, fill=(0, 0, 0, 70), font=subfont)
        draw.text((sx, sy), sub, fill=(220, 220, 220), font=subfont)


def _make_bg(name, palette_key, sub=""):
    top, bot = _BG_PALETTE[palette_key]
    img = _linear_gradient((1920, 1080), top, bot)
    _label(img, name.replace("_", " ").title(), sub)
    return img


def _make_sprite(name, palette_key):
    """Solid 3:4 silhouette with alpha. Placeholder for a real character sprite."""
    top, bot = _BG_PALETTE[palette_key]
    w, h = 810, 1080
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    body = [(w // 2 - 180, 220), (w // 2 + 180, h - 40)]
    head = [(w // 2 - 110, 60), (w // 2 + 110, 260)]
    draw.rectangle(body, fill=(*top, 210))
    draw.ellipse(head, fill=(*bot, 220))
    _label(img, name.replace("_", " ").title())
    return img


# Manifest content — id, type, filename, tags, license, attribution.
# The generated PNGs live alongside the manifest; if you swap in real
# Kenney art with the same filename, no manifest edit needed.
_ENTRIES = [
    # Backgrounds
    ("bg_school_day",     "background", "school_day.png",     _make_bg("school day",     "day",  "教室 · 白天"),
        ["school", "classroom", "day", "校园", "教室", "白天"]),
    ("bg_school_night",   "background", "school_night.png",   _make_bg("school night",   "night", "教室 · 夜晚"),
        ["school", "classroom", "night", "校园", "夜晚"]),
    ("bg_school_dusk",    "background", "school_dusk.png",    _make_bg("school dusk",    "dusk",  "教室 · 黄昏"),
        ["school", "classroom", "dusk", "校园", "黄昏"]),
    ("bg_rooftop_day",    "background", "rooftop_day.png",    _make_bg("rooftop day",    "day",   "屋顶 · 白天"),
        ["rooftop", "outdoor", "day", "天台", "白天"]),
    ("bg_rooftop_night",  "background", "rooftop_night.png",  _make_bg("rooftop night",  "night", "屋顶 · 夜晚"),
        ["rooftop", "outdoor", "night", "天台", "夜晚"]),
    ("bg_forest_dawn",    "background", "forest_dawn.png",    _make_bg("forest dawn",    "dawn",  "森林 · 黎明"),
        ["forest", "outdoor", "dawn", "森林", "黎明"]),
    ("bg_cafe_warm",      "background", "cafe_warm.png",      _make_bg("cafe warm",      "warm",  "咖啡馆 · 温暖"),
        ["cafe", "indoor", "warm", "咖啡馆", "室内"]),
    ("bg_shrine_cool",    "background", "shrine_cool.png",    _make_bg("shrine cool",    "cool",  "神社 · 清凉"),
        ["shrine", "outdoor", "cool", "神社", "室外"]),
    # Character sprites — very generic placeholders. Real production expects
    # per-character sprite sets; these are here so the library-hit path is
    # exercised in Chinese-VN mock demos.
    ("sprite_student_female_neutral", "character_sprite", "student_female_neutral.png",
        _make_sprite("student female", "warm"),
        ["student", "female", "young", "neutral", "学生", "女", "青年"]),
    ("sprite_student_male_neutral",   "character_sprite", "student_male_neutral.png",
        _make_sprite("student male", "cool"),
        ["student", "male", "young", "neutral", "学生", "男", "青年"]),
    ("sprite_teacher_neutral",        "character_sprite", "teacher_neutral.png",
        _make_sprite("teacher", "dusk"),
        ["teacher", "adult", "neutral", "老师", "成年"]),
]


def main() -> int:
    _LIB_DIR.mkdir(parents=True, exist_ok=True)

    manifest = {
        "$schema_version": 1,
        "notes": [
            "v4 P0-2 opensource asset library.",
            "These placeholder assets are CC0 (author-generated via PIL, no external art used).",
            "Production users should replace files with real Kenney / OpenGameArt / itch.io art",
            "— matching filenames keeps the manifest valid without edits.",
            "Regenerate placeholders: `uv run python scripts/seed_opensource_library.py`",
        ],
        "assets": [],
    }

    for aid, atype, fname, img, tags in _ENTRIES:
        out = _LIB_DIR / fname
        # Save as PNG. Sprite entries carry alpha; backgrounds are RGB.
        img.save(out, "PNG", optimize=True)
        entry = {
            "id": aid,
            "type": atype,
            "path": fname,
            "license": "CC0",
            "attribution": "VN-Agent placeholder (author-generated, CC0)",
            "tags": tags,
        }
        if atype == "background":
            entry["width"] = 1920
            entry["height"] = 1080
        elif atype == "character_sprite":
            entry["width"] = 810
            entry["height"] = 1080
        manifest["assets"].append(entry)

    _MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Wrote {len(_ENTRIES)} assets + manifest to {_LIB_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
