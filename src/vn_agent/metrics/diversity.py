"""Diversity index — % of assets sourced from non-LLM channels.

Definition (M0):
    diversity_index = (upload + web_search + local_library) / total_assets

Where `total_assets` = uploads + web_search + library_hits + LLM-generated
outputs (backgrounds, sprites, BGM). LLM assets are inferred by walking
the output_dir's blackboard for scenes/characters and subtracting any
scene/sprite whose prompt carries the `[library:...]` provenance sentinel
(placed by scene_artist / character_designer when a library hit fires).

Why byte-level truth vs. self-report:
    Self-report ("assets metadata says diversity=50%") is trivially
    gameable. Byte-level truth walks the actual output directory + JSONL
    stores; if a file exists and no library_hits.jsonl entry claims it,
    it's counted as derived (LLM). The metric can only be improved by
    ACTUALLY uploading / matching / retrieving more non-LLM content.

Target: ≥ 30% for the v4 P0 milestone (see docs/v4/PRODUCT_v4.md §3.1).
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_LIBRARY_SENTINEL_RE = re.compile(r"\[library:([^\s\]·]+)")


@dataclass
class DiversityBreakdown:
    """Per-source counters + the derived index. JSON-serialisable via asdict."""
    total_assets: int = 0
    upload_chunks: int = 0
    web_search_chunks: int = 0
    library_hits: int = 0
    llm_generated_scenes: int = 0
    llm_generated_sprites: int = 0
    library_hit_targets: list[str] = field(default_factory=list)

    @property
    def non_llm(self) -> int:
        return self.upload_chunks + self.web_search_chunks + self.library_hits

    @property
    def llm(self) -> int:
        return self.llm_generated_scenes + self.llm_generated_sprites

    @property
    def diversity_index(self) -> float:
        """Ratio in [0, 1]. Returns 0.0 when total is 0."""
        if self.total_assets == 0:
            return 0.0
        return self.non_llm / self.total_assets

    def to_dict(self) -> dict:
        d = asdict(self)
        d["non_llm"] = self.non_llm
        d["llm"] = self.llm
        d["diversity_index"] = round(self.diversity_index, 4)
        return d


def compute(
    *,
    job_id: str | None = None,
    output_dir: Path | str | None = None,
    blackboard: dict | None = None,
) -> DiversityBreakdown:
    """Walk provenance streams and compute the diversity breakdown.

    Args:
        job_id: web job id used to look up `data/uploads/{job_id}/uploads.jsonl`.
        output_dir: the run's output directory, used for library_hits.jsonl.
        blackboard: current blackboard/state — read for scene/character
                    counts. When None, we skip the LLM-generated side of
                    the ledger (diversity_index will still work if callers
                    only care about non-LLM counts).

    All args are optional and additive: call with what you have. Returns
    a fully-populated `DiversityBreakdown` with 0s for missing sources.
    """
    b = DiversityBreakdown()

    # ── Uploads (P0-1) ─────────────────────────────────────────────────────
    if job_id:
        try:
            from vn_agent.assets.upload_store import load_chunks

            chunks = load_chunks(job_id)
            for ch in chunks:
                src = (ch.source_meta or {}).get("source", "upload")
                if src == "web_search":
                    b.web_search_chunks += 1
                elif src == "local_library":
                    b.library_hits += 1
                else:  # "upload" (default) and any unclassified user_upload
                    b.upload_chunks += 1
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Diversity: upload_store load failed for {job_id}: {e}")

    # ── Library hits (P0-2) ────────────────────────────────────────────────
    # Persistence is per-run (output_dir/library_hits.jsonl) so a job that
    # ran without web upload UI still counts its library hits.
    if output_dir is not None:
        hits_path = Path(output_dir) / "library_hits.jsonl"
        if hits_path.exists():
            try:
                with hits_path.open(encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            row = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        b.library_hits += 1
                        target = row.get("target_id") or row.get("asset_id")
                        if target:
                            b.library_hit_targets.append(str(target))
            except OSError as e:
                logger.debug(f"Diversity: library_hits read failed: {e}")

    # ── LLM-generated scenes / sprites (byte-truth via blackboard) ─────────
    if blackboard is not None:
        vn_script = blackboard.get("vn_script") if isinstance(blackboard, dict) else getattr(blackboard, "vn_script", None)
        characters = blackboard.get("characters") if isinstance(blackboard, dict) else getattr(blackboard, "characters", None)

        # Scenes: count unique background_ids as one asset each. Skip when
        # background_prompt starts with the `[library:...]` sentinel because
        # scene_artist's library hit-first branch left the sentinel in the
        # prompt to make this observation byte-level cheap.
        if vn_script and getattr(vn_script, "scenes", None):
            seen_bgs: set[str] = set()
            for scene in vn_script.scenes:
                bg_id = getattr(scene, "background_id", None)
                if not bg_id or bg_id in seen_bgs:
                    continue
                seen_bgs.add(bg_id)
                prompt = str(getattr(scene, "background_prompt", "") or "")
                if _LIBRARY_SENTINEL_RE.search(prompt):
                    # Already counted in library_hits above; don't double.
                    continue
                b.llm_generated_scenes += 1

        # Sprites: same treatment per (character, emotion). Character sprites
        # store their generation_prompt on EmotionSprite; the sentinel goes
        # in front there too.
        if characters:
            for char in characters.values():
                for sprite in getattr(char, "sprites", []) or []:
                    prompt = str(getattr(sprite, "generation_prompt", "") or "")
                    if _LIBRARY_SENTINEL_RE.search(prompt):
                        continue
                    b.llm_generated_sprites += 1

    b.total_assets = b.non_llm + b.llm
    return b


def annotate_blackboard(
    blackboard: dict,
    *,
    job_id: str | None = None,
    output_dir: Path | str | None = None,
) -> DiversityBreakdown:
    """Compute + attach `metrics.diversity_*` to the blackboard.

    Idempotent: overwrites the `metrics` dict's diversity subkeys each call.
    Returns the breakdown so callers can log / assert on it.
    """
    breakdown = compute(job_id=job_id, output_dir=output_dir, blackboard=blackboard)

    metrics = blackboard.setdefault("metrics", {}) if isinstance(blackboard, dict) else None
    if metrics is not None:
        metrics["diversity"] = breakdown.to_dict()
        metrics["diversity_index"] = round(breakdown.diversity_index, 4)

    return breakdown
