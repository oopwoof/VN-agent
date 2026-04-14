"""Configuration loading with pydantic-settings."""
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field
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
    #   "action"   — inject raw text-shot into Writer prompt (current behavior).
    #                Better for galgame / action-anime VN where format fidelity
    #                and stage-direction-heavy dialogue matter more than
    #                subtextual depth.
    # Default kept as "action" for backward compatibility until Sprint 7-4
    # sweep data confirms which should win by default.
    writer_mode: Literal["literary", "action"] = "action"

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
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_index_path: str = ""  # pre-built index dir; empty = build on-the-fly

    # Tool calling (LLM function calling instead of free-text JSON)
    use_tool_calling: bool = True  # bind_tools for scene_artist/character_designer


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
