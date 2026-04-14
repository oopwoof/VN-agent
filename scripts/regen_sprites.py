"""One-off: regenerate only the character sprites for an existing run.

Used to re-try after a prompt change without paying for Director/Writer
or re-firing backgrounds. Loads characters.json + VisualProfile from
the saved run, deletes the existing sprite dirs, and re-invokes
_generate_sprites per character.

Usage:
  uv run python scripts/regen_sprites.py <output_dir>
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vn_agent.agents.character_designer import _generate_sprites  # noqa: E402
from vn_agent.schema.character import CharacterProfile, VisualProfile  # noqa: E402


async def main(output_dir: Path) -> None:
    chars_path = output_dir / "characters.json"
    if not chars_path.exists():
        print(f"[FAIL] {chars_path} not found")
        sys.exit(1)

    raw = json.loads(chars_path.read_text(encoding="utf-8"))
    chars = {k: CharacterProfile.model_validate(v) for k, v in raw.items()}
    print(f"Regenerating sprites for {len(chars)} characters in {output_dir}")

    for char_id, char in chars.items():
        # VisualProfile is embedded inside CharacterProfile via .visual field.
        # If it's missing, synthesize a minimal one from the profile's
        # appearance hints — typical case is characters.json already carries
        # visual from the original run.
        visual_raw = raw[char_id].get("visual")
        if visual_raw is None:
            print(f"  [SKIP] {char_id}: no visual profile stored — need to re-run full character_designer")
            continue
        visual = VisualProfile.model_validate(visual_raw)

        sprite_dir = output_dir / "game" / "images" / "characters" / char_id
        if sprite_dir.exists():
            print(f"  [{char_id}] removing old sprites at {sprite_dir}")
            shutil.rmtree(sprite_dir)

        print(f"  [{char_id}] generating 3 sprites...")
        sprites, errors = await _generate_sprites(char, visual, str(output_dir))
        print(f"  [{char_id}] -> {len(sprites)} sprites, {len(errors)} errors")
        for e in errors:
            print(f"      ! {e}")

    print("\nDone. Re-run `renpy` to view the new sprites.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: uv run python scripts/regen_sprites.py <output_dir>")
        sys.exit(2)
    asyncio.run(main(Path(sys.argv[1])))
