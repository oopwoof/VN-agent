"""Pillow-based frame compositor for the P4 PlaytestAgent.

Why Pillow compositing instead of real Ren'Py engine screenshots: this repo
has zero existing Ren'Py headless-execution infrastructure (no subprocess
wrapper, no SDK path config, no --warp / renpy.screenshot() automation
anywhere) — building that from scratch was judged too large/risky a lift
for M0. Instead, this composites the SAME background + sprite PNGs the
pipeline already generates (real art in non-mock runs, 1x1 placeholder PNGs
in mock/text-only runs — both exist on disk after
`compiler.project_builder.build_project()` runs) with a synthetic dialogue-
box / choice-menu overlay approximating what Ren'Py would render at runtime.
M1 roadmap note: swap in true engine screenshots later if ever needed —
not planned now.
"""
from __future__ import annotations

import logging
import re
import textwrap
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from vn_agent.playtest.schema import WalkNode
from vn_agent.schema.character import CharacterProfile
from vn_agent.schema.script import Scene

logger = logging.getLogger(__name__)

CANVAS_SIZE: tuple[int, int] = (1280, 720)
# Matches compiler.project_builder._PLACEHOLDER_PNG's exact byte size (67
# bytes) and web.app._PLACEHOLDER_PNG_SIZE — same "is this a real asset or
# a 1x1 stand-in" check already used elsewhere in the pipeline.
_PLACEHOLDER_MAX_BYTES = 67

_BG_FALLBACK_COLOR = (30, 30, 38)
_OVERLAY_COLOR = (10, 10, 14, 200)
_SPRITE_FALLBACK_COLORS = ["#5577aa", "#aa5577", "#77aa55", "#aaaa55"]

# Chinese is the project's primary demo language (docs/v4/PRODUCT_v4.md §8:
# "中文 VN 一等公民") — Pillow's bundled default font is Latin-only, so
# without a real CJK font here every Chinese dialogue frame would render as
# tofu boxes for the vision judge to (mis)judge. Try common CJK-capable
# fonts across the platforms this runs on; fall back to Pillow's default
# (still correct for Latin text) if none are installed.
_CJK_FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",  # Windows: Microsoft YaHei
    "C:/Windows/Fonts/simhei.ttf",  # Windows: SimHei
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",  # Debian/Ubuntu fonts-noto-cjk
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",  # Debian/Ubuntu fonts-wqy-zenhei
    "/System/Library/Fonts/PingFang.ttc",  # macOS
]
_CJK_RE = re.compile(r"[一-鿿]")


def _has_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text))


@lru_cache(maxsize=16)
def _font(size: int) -> ImageFont.ImageFont:
    for path in _CJK_FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception as e:  # noqa: BLE001 — a broken font file must not crash compositing
                logger.debug(f"Failed to load font {path}: {e}")
                continue
    return ImageFont.load_default(size=size)


def _is_placeholder_asset(path: Path) -> bool:
    return not path.exists() or path.stat().st_size <= _PLACEHOLDER_MAX_BYTES


def _safe_name(node_id: str) -> str:
    return node_id.replace("::", "_").replace("/", "_")


def _load_background(project_dir: Path, background_id: str, canvas_size: tuple[int, int]) -> Image.Image:
    canvas = Image.new("RGB", canvas_size, _BG_FALLBACK_COLOR)
    path = project_dir / "game" / "images" / "backgrounds" / f"{background_id}.png"
    if _is_placeholder_asset(path):
        draw = ImageDraw.Draw(canvas)
        draw.text(
            (canvas_size[0] // 2, canvas_size[1] // 2),
            f"[missing background: {background_id}]",
            fill=(120, 120, 130), font=_font(20), anchor="mm",
        )
        return canvas
    try:
        bg = Image.open(path).convert("RGB")
    except Exception as e:  # noqa: BLE001 — a corrupt asset must not crash the report
        logger.debug(f"Failed to load background {path}: {e}")
        return canvas

    bg_ratio = bg.width / bg.height
    canvas_ratio = canvas_size[0] / canvas_size[1]
    if bg_ratio > canvas_ratio:
        new_h = canvas_size[1]
        new_w = max(1, int(new_h * bg_ratio))
    else:
        new_w = canvas_size[0]
        new_h = max(1, int(new_w / bg_ratio))
    bg = bg.resize((new_w, new_h))
    left = (new_w - canvas_size[0]) // 2
    top = (new_h - canvas_size[1]) // 2
    bg = bg.crop((left, top, left + canvas_size[0], top + canvas_size[1]))
    canvas.paste(bg, (0, 0))
    return canvas


def _load_sprite(
    project_dir: Path, char_id: str, emotion: str, target_height: int,
    fallback_color: str, fallback_label: str,
) -> Image.Image:
    char_dir = project_dir / "game" / "images" / "characters" / char_id
    path = char_dir / f"{emotion}.png"
    if _is_placeholder_asset(path) and emotion != "neutral":
        neutral_path = char_dir / "neutral.png"
        if not _is_placeholder_asset(neutral_path):
            path = neutral_path

    if _is_placeholder_asset(path):
        width = max(1, int(target_height * 0.55))
        img = Image.new("RGBA", (width, target_height), fallback_color)
        draw = ImageDraw.Draw(img)
        draw.text((width // 2, target_height // 2), fallback_label, fill=(255, 255, 255), font=_font(18), anchor="mm")
        return img

    try:
        sprite = Image.open(path).convert("RGBA")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"Failed to load sprite {path}: {e}")
        width = max(1, int(target_height * 0.55))
        return Image.new("RGBA", (width, target_height), fallback_color)

    ratio = sprite.width / sprite.height
    new_w = max(1, int(target_height * ratio))
    return sprite.resize((new_w, target_height))


def _wrap(text: str, width: int) -> list[str]:
    if _has_cjk(text):
        # textwrap.wrap splits on whitespace — meaningless for space-less
        # CJK text (the whole sentence is one "word"), and CJK glyphs render
        # roughly 2x as wide as Latin ones, so wrap by raw character count
        # at half the Latin width instead.
        cjk_width = max(1, width // 2)
        return [text[i:i + cjk_width] for i in range(0, len(text), cjk_width)] or [""]
    return textwrap.wrap(text, width=width) or [""]


def _draw_dialogue_box(canvas: Image.Image, speaker_name: str | None, speaker_color: str, text: str) -> None:
    w, h = canvas.size
    box_h = int(h * 0.24)
    overlay = Image.new("RGBA", (w, box_h), _OVERLAY_COLOR)
    canvas.paste(overlay, (0, h - box_h), overlay)
    draw = ImageDraw.Draw(canvas)
    x, y = 40, h - box_h + 16
    if speaker_name:
        draw.text((x, y), speaker_name, fill=speaker_color, font=_font(26))
        y += 34
    else:
        y += 10
    for line in _wrap(text, width=90)[:3]:
        draw.text((x, y), line, fill=(235, 235, 235), font=_font(22))
        y += 28


def _draw_choice_menu(canvas: Image.Image, choice_texts: list[str], locked_choice_texts: list[str]) -> None:
    w, h = canvas.size
    box_h = int(h * 0.24)
    overlay = Image.new("RGBA", (w, box_h), _OVERLAY_COLOR)
    canvas.paste(overlay, (0, h - box_h), overlay)
    draw = ImageDraw.Draw(canvas)
    x, y = 60, h - box_h + 14
    entries = [(t, True) for t in choice_texts] + [(t, False) for t in locked_choice_texts]
    for text, enabled in entries[:4]:
        color = (230, 230, 230) if enabled else (110, 110, 110)
        label = text if enabled else f"{text} (locked)"
        draw.rounded_rectangle((x, y, w - 60, y + 30), radius=6, outline=color, width=1)
        draw.text((x + 12, y + 6), label, fill=color, font=_font(18))
        y += 40


def composite_frame(
    node: WalkNode,
    scene: Scene,
    characters: dict[str, CharacterProfile],
    project_dir: Path,
    out_dir: Path,
    *,
    canvas_size: tuple[int, int] = CANVAS_SIZE,
) -> Path:
    """Render one WalkNode as a flattened PNG under
    `out_dir/playtest/frames/<safe node_id>.png`. Pure Pillow — no LLM, no
    network, fully deterministic given the same on-disk assets."""
    canvas = _load_background(project_dir, scene.background_id, canvas_size)

    present = scene.characters_present[:3]
    if present:
        target_h = int(canvas_size[1] * 0.7)
        sprites: list[Image.Image] = []
        for i, char_id in enumerate(present):
            emotion = "neutral"
            if node.kind == "scene":
                for line in reversed(scene.dialogue):
                    if line.character_id == char_id:
                        emotion = line.emotion
                        break
            profile = characters.get(char_id)
            color = profile.color if profile else _SPRITE_FALLBACK_COLORS[i % len(_SPRITE_FALLBACK_COLORS)]
            label = profile.name if profile else char_id
            sprites.append(_load_sprite(project_dir, char_id, emotion, target_h, color, label))

        total_w = sum(s.width for s in sprites)
        gap = max(20, (canvas_size[0] - total_w) // (len(sprites) + 1))
        x = gap
        box_h = int(canvas_size[1] * 0.24)
        for sprite in sprites:
            y = max(0, canvas_size[1] - box_h - sprite.height)
            canvas.paste(sprite, (x, y), sprite)
            x += sprite.width + gap

    if node.kind == "choice_menu":
        _draw_choice_menu(canvas, node.choice_texts, node.locked_choice_texts)
    else:
        last_line = scene.dialogue[-1] if scene.dialogue else None
        speaker_name: str | None = None
        speaker_color = "#ffffff"
        text = last_line.text if last_line else "(no dialogue)"
        if last_line and last_line.character_id:
            profile = characters.get(last_line.character_id)
            speaker_name = profile.name if profile else last_line.character_id
            speaker_color = profile.color if profile else "#ffffff"
        _draw_dialogue_box(canvas, speaker_name, speaker_color, text)

    frames_dir = out_dir / "playtest" / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    frame_path = frames_dir / f"{_safe_name(node.node_id)}.png"
    canvas.convert("RGB").save(frame_path, format="PNG")
    return frame_path
