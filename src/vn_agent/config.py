"""Configuration loading with pydantic-settings."""
from functools import lru_cache
from pathlib import Path

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
    llm_reviewer_model: str = "claude-haiku-4-5-20251001"
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

    # Eval / few-shot
    corpus_path: str = ""  # path to final_annotations.csv (empty = disabled)
    sessions_dir: str = ""  # optional dir of *.jsonl unannotated sessions to merge in
    few_shot_k: int = 2  # number of examples to inject into Writer prompt

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
