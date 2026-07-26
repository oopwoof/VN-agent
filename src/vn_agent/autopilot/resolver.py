"""Preset resolution for P5 Autopilot.

config/presets/*.yaml existed before this module but were pure copy-paste
convention (a comment telling a human to paste the block into
config/settings.yaml) — nothing loaded them at runtime. This module is the
first runtime loader for that directory.
"""
from __future__ import annotations

import yaml

from vn_agent.config import ROOT, Settings, load_yaml_settings

_PRESETS_DIR = ROOT / "config" / "presets"


def load_preset(name: str) -> dict:
    """Read `config/presets/{name}.yaml` and flatten it into Settings-field
    shape, using the exact same algorithm as `load_yaml_settings()` (nested
    `section: {key: val}` -> `section_key: val`)."""
    path = _PRESETS_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Unknown preset {name!r}: {path} does not exist")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    flat: dict = {}
    for section, values in data.items():
        if isinstance(values, dict):
            for k, v in values.items():
                flat[f"{section}_{k}"] = v
        else:
            flat[section] = values
    return flat


def build_settings(preset_name: str) -> Settings:
    """Ambient config/settings.yaml as the base, preset as the overlay.

    Overlay order matters: presets only need to state the knobs they
    actually want to change (matching how the existing preset files are
    written), not restate every unrelated Settings field.
    """
    merged = {**load_yaml_settings(), **load_preset(preset_name)}
    return Settings(**merged)


def resolve_preset(theme: str) -> str:
    """Pick a preset name for `theme`.

    M0: always "autopilot_best" — one hand-picked recipe, no per-theme
    heuristic yet. Kept as a function (not a bare constant) so M1's
    tag/embedding-based selection is a body swap here, not a call-site
    migration across every caller.
    """
    return "autopilot_best"
