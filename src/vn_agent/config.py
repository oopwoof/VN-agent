"""Configuration loading with pydantic-settings."""
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API Keys
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    stability_api_key: str = Field(default="", alias="STABILITY_API_KEY")
    suno_api_key: str = Field(default="", alias="SUNO_API_KEY")

    # Phase 13-1 / Step 1: Anthropic key pool for 50-scene long-form runs.
    # Single key goes 429 under sustained load; round-robin + per-key cooldown
    # + exp backoff + jitter keeps the pipeline moving. Haiku / Sonnet tier
    # limits differ, so split pools avoid Haiku bursts exhausting Sonnet budget.
    # Resolution order (in services.llm._pool_for):
    #   1. Model is Haiku     → anthropic_api_keys_haiku  (if set)
    #   2. Model is Sonnet/other → anthropic_api_keys_sonnet (if set)
    #   3. Fallback           → anthropic_api_keys (shared generic pool)
    #   4. Final fallback     → single anthropic_api_key (backward compat)
    # Populate via CSV env vars:
    #   VN_ANTHROPIC_API_KEYS="key1,key2,key3"
    #   VN_ANTHROPIC_KEYS_SONNET="sk-ant-...,sk-ant-..."
    #   VN_ANTHROPIC_KEYS_HAIKU="sk-ant-...,sk-ant-..."
    anthropic_api_keys: list[str] = Field(
        default_factory=list, alias="VN_ANTHROPIC_API_KEYS",
    )
    anthropic_api_keys_sonnet: list[str] = Field(
        default_factory=list, alias="VN_ANTHROPIC_KEYS_SONNET",
    )
    anthropic_api_keys_haiku: list[str] = Field(
        default_factory=list, alias="VN_ANTHROPIC_KEYS_HAIKU",
    )
    anthropic_max_retries: int = 4            # total attempts incl. rotations
    anthropic_backoff_base: float = 1.5       # seconds (capped below)
    anthropic_backoff_cap: float = 30.0       # seconds
    anthropic_backoff_jitter: float = 0.5     # multiplier range: [1-j, 1+j]

    @field_validator(
        "anthropic_api_keys",
        "anthropic_api_keys_sonnet",
        "anthropic_api_keys_haiku",
        mode="before",
    )
    @classmethod
    def _split_csv_keys(cls, v: str | list[str] | None) -> list[str]:
        """Env vars come in as CSV strings; split + strip."""
        if v is None:
            return []
        if isinstance(v, str):
            return [k.strip() for k in v.split(",") if k.strip()]
        return list(v)

    # Sprint 10-1: Google Gemini API key (used by Nano Banana image provider).
    # Free tier covers text models; image generation (gemini-2.5-flash-image)
    # requires a paid-tier account. Pipeline falls back to gpt-image-1 / DALL-E
    # on 4xx so missing payment doesn't brick the run.
    google_api_key: str = Field(default="", alias="GOOGLE_API_KEY")

    # Loaded from settings.yaml
    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-4-6"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 16000
    llm_max_retries: int = 3

    # Optional overrides for local / free providers
    # llm_base_url: when set, ChatOpenAI uses this as base_url (Ollama / LM Studio / Groq / OpenRouter)
    # llm_api_key:  explicit key override; avoids needing OPENAI_API_KEY for local servers
    llm_base_url: str = ""
    llm_api_key: str = ""

    # Per-agent model overrides
    llm_director_model: str = "claude-sonnet-4-6"
    llm_writer_model: str = "claude-sonnet-4-6"
    # Sprint 7-5b: DialogueReviewer is Sonnet. Earlier iterations tried
    # Haiku-only or Sonnet-only; both failed differently (Haiku rubber-stamped
    # at 5.0, Sonnet alone handled mechanical issues at full-model cost).
    # Final architecture: Python _mechanical_check() gates first (cheap,
    # deterministic), Sonnet reviewer only fires on structurally-valid output
    # where its narrative judgment (voice/subtext/arc/pacing) actually adds
    # value. Structural duplication with structure_reviewer avoided by
    # scoping Reviewer's prompt to craft dimensions only.
    llm_reviewer_model: str = "claude-sonnet-4-6"
    llm_structure_reviewer_model: str = "claude-sonnet-4-6"  # narrative audit
    # Sprint 9-6: State Orchestrator — translates world_state dict to
    # narrative constraint text for Writer. Translation work, not
    # narrative judgment → Haiku per the project model-selection rule.
    llm_state_orchestrator_model: str = "claude-haiku-4-5-20251001"
    # Sprint 11-1: per-scene summarizer (Haiku, ≤100 words each).
    # Translation work, not creative. Gated by enable_scene_summarization.
    llm_summarizer_model: str = "claude-haiku-4-5-20251001"
    llm_character_designer_model: str = "claude-haiku-4-5-20251001"
    llm_scene_artist_model: str = "claude-haiku-4-5-20251001"
    llm_music_director_model: str = "claude-haiku-4-5-20251001"

    image_provider: str = "openai"
    image_model: str = "dall-e-3"

    music_strategy: str = "library"
    music_library_path: str = "config/music_library.yaml"
    music_audio_format: str = "ogg"

    max_scenes: int = 20
    max_revision_rounds: int = 3
    min_dialogue_lines: int = 5
    max_dialogue_lines: int = 20
    reviewer_skip_llm: bool = False
    # Rubric average (1-5 scale) below which the Reviewer fails the script
    # and triggers a Writer revision round. Matches the prompt's stated bar.
    reviewer_pass_threshold: float = 3.5

    # Eval / few-shot
    corpus_path: str = ""  # path to final_annotations.csv (empty = disabled)
    sessions_dir: str = ""  # optional dir of *.jsonl unannotated sessions to merge in
    few_shot_k: int = 2  # number of examples to inject into Writer prompt

    # Writer generation mode (Sprint 7-1):
    #   "literary" — zero-shot with physics-framework system prompt, no raw
    #                text few-shot injected (RAG retrieval still runs for audit).
    #                Better for psychological / literary VN output.
    #   "action"   — inject raw text-shot into Writer prompt.
    #                Better for galgame / action-anime VN where format fidelity
    #                and stage-direction-heavy dialogue matter more than
    #                subtextual depth.
    # Default flipped to "literary" after Sprint 8-5 sweep (2026-04-14):
    # literary mean 4.17 vs action 3.92 vs baseline_self_refine 3.45 vs
    # baseline_single 3.25. literary beat action on BOTH themes including
    # the action-leaning dragon (4.5 vs 4.17), so the physics prompt is
    # the right default even when the theme sounds like "action mode's
    # territory." Flip to "action" explicitly when the user wants
    # galgame/furry VN style fidelity.
    writer_mode: Literal["literary", "action"] = "literary"

    # How many prior scenes' full dialogue to inject into Writer prompt (Sprint 7-2).
    # 0 = no prior context (rely on scene.entry_context card only).
    # 1 = previous scene, keeps character voice coherent across boundaries.
    writer_context_window: int = 0  # safe default; raise in literary configs

    # LLM-as-judge model for scripts/eval_strategy_adherence.py (Sprint 7-3).
    # Decoupled from llm_reviewer_model so eval can use Sonnet even when the
    # pipeline Reviewer is on Haiku.
    llm_judge_model: str = "claude-sonnet-4-6"
    # Sprint 8-1: cross-model judge — an independent non-Anthropic model scores
    # the same scenes so we can check inter-rater agreement and defuse the
    # "Sonnet grading Sonnet's own output" echo-chamber critique. Empty string
    # or missing OpenAI key → secondary judge skipped (Sonnet-only mode).
    llm_judge_model_secondary: str = "gpt-4o"

    # Sprint 8-4: Anthropic prompt caching. When True and provider=anthropic,
    # system prompts ≥1500 chars are tagged with cache_control={"type":
    # "ephemeral"}. First call of a job pays 1.25× input cost; subsequent
    # calls within 5 minutes pay 0.1× — huge wins for Writer (6-18 identical
    # system-prompt calls per run) and DialogueReviewer (revision rounds).
    # No-op for OpenAI / Ollama / other providers.
    enable_prompt_caching: bool = True

    # Embedding RAG (requires [rag] extras: sentence-transformers + faiss-cpu)
    use_semantic_retrieval: bool = True  # use embedding similarity; False = label filter
    rag_pre_filter_strategy: bool = True  # strategy hard-constraint before vector rank

    # Sprint 10-2: lore retrieval — facts-not-style RAG that runs in
    # BOTH literary and action modes. Cheap (~80ms build, ~$0.008/run)
    # and orthogonal to dialogue RAG. Turn off to compare.
    use_lore_retrieval: bool = True
    lore_k: int = 4  # top-k lore entities to inject per scene

    # Sprint 11-1: per-scene Haiku summarization for long-form memory.
    # Default OFF — adds 1 Haiku call per scene (~$0.002 × N_scenes).
    # Turn on for runs with 15+ scenes where writer_context_window
    # alone doesn't carry enough prior context.
    enable_scene_summarization: bool = False
    summarization_min_scenes: int = 15  # below this, summarization is pointless

    # Phase 13-1 / Step 6: chapter-level rollups. Default ON per product goal
    # (50+ scene long-form VN is the north star; short demos stay unchanged
    # because they don't meet the 10-scene min). Rollup fires async in
    # background every chapter_rollup_every scenes; pending rollups are
    # awaited at the next chapter boundary before Writer's prompt prefix
    # is rebuilt. Dynamic-length 200-800 word summary (matches narrative
    # density — high-tension chapters get 800, transitional get 200).
    enable_chapter_rollup: bool = True
    chapter_rollup_every: int = 10
    chapter_rollup_min_scenes: int = 10   # below this, skip — short demos unaffected
    rollup_target_min_words: int = 200
    rollup_target_max_words: int = 800

    # Phase 13-2 Step 2 (route 4): thinking_fanout — per-scene planning
    # pass between state_orchestrator and writer. Produces structured
    # SceneThinking artifacts that Step 4 hands to parallel Writer workers
    # for cross-scene coordination (callbacks, voice charter, opening/
    # closing beats). Default OFF until Step 4 parallel writing lands.
    # min_scenes gate keeps ≤10-scene demos from paying LLM cost they
    # don't benefit from (thinking matters most for 10+ scene runs).
    #
    # Model = Sonnet (NOT Haiku). Thinking is narrative/structural reasoning
    # (cross-scene callback planning, voice charter application, foreshadow
    # tracking) — exactly what feedback_model_selection says Sonnet owns.
    # GIGO applies: if thinking is shallow, 50 parallel Writers amplify
    # shallowness. Cost delta on 50 scenes: ~$1.25 extra; trivial vs ~$15
    # total run. Haiku path documented under Tier 3 (legacy, research).
    enable_thinking_fanout: bool = False
    thinking_fanout_min_scenes: int = 10
    llm_thinking_model: str = "claude-sonnet-4-6"

    # Phase 13-2 Step 3 (route 4): cross_ref_sync — one-shot revision pass
    # where each scene sees its context_deps' SceneThinking and revises
    # its own plan to resolve callback collisions / voice conflicts.
    # Single round only (ARCHITECTURE.md 路线四 explicitly rules out
    # fixed-point iteration). Default OFF until Step 4 proves it lifts
    # quality; on by default only when thinking_fanout is on.
    # Runs AFTER thinking_fanout — min threshold matches thinking's.
    enable_cross_ref_sync: bool = False
    cross_ref_sync_min_scenes: int = 10
    # Phase 13-2 Step 4a: Writer consumes scene.thinking as its final
    # briefing. Default OFF so the existing Writer path is unchanged
    # while we A/B validate whether thinking injection improves dialogue
    # quality (before Step 4b invests in parallel writing infrastructure
    # that depends on thinking being useful).
    # When True and scene.thinking is populated, _format_thinking_block
    # renders intent/beats/callbacks/voice/risks as the last signal
    # Writer sees before the "write dialogue" instruction.
    writer_consume_thinking: bool = False
    # Phase 13-2 Step 3.5 (post-Gemini-review): Tier 2 Director arbitration.
    # When ON, conflicts that Tier 1 (deterministic) had to fall back to
    # "latest claimant wins" get re-arbitrated by a second Director LLM
    # call. Not a new agent — reuses llm_director_model. Default OFF
    # because Tier 1 is already production-safe; Tier 2 is opt-in quality.
    enable_director_arbitration: bool = False
    # Phase 13-2 Step 3.5: legacy LLM self-revision path. Kept behind a
    # flag because symmetric Haiku revision can erase callbacks via a
    # logic race (both scenes delete given peer's plan). OFF by default;
    # research use only.
    enable_cross_ref_sync_llm_revise: bool = False
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_index_path: str = ""  # pre-built index dir; empty = build on-the-fly

    # Tool calling (LLM function calling instead of free-text JSON)
    use_tool_calling: bool = True  # bind_tools for scene_artist/character_designer

    # Sprint 12-3b: sprite post-processing — run rembg (u2net_human_seg)
    # over each generated character sprite to strip the solid background.
    # Ren'Py composites sprites over scene backgrounds; without alpha,
    # the character appears inside a visible rectangle. Requires the
    # [cutout] extra (`uv sync --extra cutout`). Gracefully no-ops with
    # a warning if rembg isn't installed.
    sprite_cutout: bool = True
    sprite_cutout_model: str = "u2net_human_seg"  # u2net | u2net_human_seg | isnet-general-use

    # Sprint 12-3e: sprite & BG aspect + display-zoom coupling.
    # Nano Banana returns fixed output resolutions per aspect_ratio
    # selection (no custom-size knob), so the Ren'Py transform zoom
    # in init.rpy.j2 needs to stay in lockstep with whatever aspect
    # we ask for. Any change here must be matched in the paired
    # number — both lines or neither. Actual Gemini outputs we've
    # observed: "3:4" → 864×1184, "16:9" → 1344×768.
    sprite_aspect_ratio: str = "3:4"
    sprite_zoom: float = 0.45       # 864×1184 × 0.45 → 389×533 (49% of 1080)
    bg_aspect_ratio: str = "16:9"
    bg_zoom: float = 1.4286         # 1344×768 × 1.4286 → 1920×1097 (fills 1920 wide,
                                    # 17px top+bottom crop — cheaper than black bars)


def _load_yaml_settings() -> dict:
    config_path = ROOT / "config" / "settings.yaml"
    if not config_path.exists():
        return {}
    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    # Flatten nested yaml into flat Settings fields
    flat: dict = {}
    for section, values in data.items():
        if isinstance(values, dict):
            for k, v in values.items():
                flat[f"{section}_{k}"] = v
        else:
            flat[section] = values
    return flat


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    yaml_data = _load_yaml_settings()
    return Settings(**yaml_data)


def get_music_library() -> dict:
    settings = get_settings()
    path = ROOT / settings.music_library_path
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
