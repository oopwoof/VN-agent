"""P0-2 unit tests: local open-source asset library."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from vn_agent.assets import library


@pytest.fixture
def tmp_manifest(tmp_path) -> Path:
    """Write a minimal manifest with a few placeholder assets on disk."""
    lib_dir = tmp_path / "assets"
    lib_dir.mkdir()

    # Real files so path-existence warnings don't spam the log.
    (lib_dir / "school_day.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (lib_dir / "school_night.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (lib_dir / "forest_dawn.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (lib_dir / "alice_neutral.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (lib_dir / "gentle_theme.ogg").write_bytes(b"OggS")

    manifest_path = lib_dir / "manifest.json"
    manifest_path.write_text(json.dumps({
        "$schema_version": 1,
        "assets": [
            {
                "id": "bg_school_day",
                "type": "background",
                "path": "school_day.png",
                "license": "CC0",
                "attribution": "Kenney (Public Domain)",
                "tags": ["school", "classroom", "day", "校园", "教室", "白天"],
                "width": 1920, "height": 1080,
            },
            {
                "id": "bg_school_night",
                "type": "background",
                "path": "school_night.png",
                "license": "CC0",
                "attribution": "Kenney (Public Domain)",
                "tags": ["school", "classroom", "night", "校园", "夜晚"],
            },
            {
                "id": "bg_forest_dawn",
                "type": "background",
                "path": "forest_dawn.png",
                "license": "CC-BY",
                "attribution": "OpenGameArt user X",
                "tags": ["forest", "outdoor", "dawn", "森林"],
            },
            {
                "id": "sprite_alice_neutral",
                "type": "character_sprite",
                "path": "alice_neutral.png",
                "license": "CC0",
                "attribution": "Kenney",
                "tags": ["female", "young", "neutral", "student"],
            },
            {
                "id": "bgm_gentle",
                "type": "bgm",
                "path": "gentle_theme.ogg",
                "license": "CC-BY",
                "attribution": "freesound.org / user Y",
                "tags": ["gentle", "slow", "hopeful"],
            },
        ],
    }), encoding="utf-8")
    return manifest_path


class TestManifestLoad:
    def test_missing_manifest_returns_empty(self, tmp_path):
        lib = library.AssetLibrary(tmp_path / "nonexistent.json")
        assert lib.size == 0
        assert lib.all() == []

    def test_loads_and_resolves_paths(self, tmp_manifest):
        lib = library.AssetLibrary(tmp_manifest)
        assert lib.size == 5
        # Path resolved relative to manifest dir.
        bg = next(a for a in lib.all() if a.id == "bg_school_day")
        assert bg.path.exists()
        assert bg.path.is_absolute()
        assert bg.license == "CC0"
        assert bg.width == 1080 or bg.width == 1920  # smoke on int passthrough

    def test_bad_manifest_json_returns_empty(self, tmp_path):
        p = tmp_path / "manifest.json"
        p.write_text("{ this is not json", encoding="utf-8")
        lib = library.AssetLibrary(p)
        assert lib.size == 0

    def test_invalid_entry_skipped_not_raised(self, tmp_path):
        lib_dir = tmp_path / "assets"
        lib_dir.mkdir()
        (lib_dir / "a.png").write_bytes(b"\x89PNG")
        p = lib_dir / "manifest.json"
        p.write_text(json.dumps({
            "assets": [
                {"id": "bad", "type": "moose"},  # missing required + bad type
                {
                    "id": "good", "type": "background", "path": "a.png",
                    "license": "CC0", "attribution": "author",
                },
            ],
        }), encoding="utf-8")
        lib = library.AssetLibrary(p)
        assert lib.size == 1
        assert lib.all()[0].id == "good"


class TestByType:
    def test_filters_by_type(self, tmp_manifest):
        lib = library.AssetLibrary(tmp_manifest)
        assert len(lib.by_type("background")) == 3
        assert len(lib.by_type("character_sprite")) == 1
        assert len(lib.by_type("bgm")) == 1
        assert lib.by_type("sfx") == []


class TestFindMatch:
    def test_exact_tag_match_returns_top_1(self, tmp_manifest):
        lib = library.AssetLibrary(tmp_manifest)
        matches = lib.find_match("school classroom day", "background", top_k=1)
        assert len(matches) == 1
        assert matches[0][0].id == "bg_school_day"
        # Score should be well above min_score default.
        assert matches[0][1] >= 0.35

    def test_chinese_tag_match(self, tmp_manifest):
        # Chinese tag "校园" tokenizes as one token; should still match.
        lib = library.AssetLibrary(tmp_manifest)
        result = lib.find_one("校园 白天", "background")
        assert result is not None
        assert result.id == "bg_school_day"

    def test_no_type_match_returns_empty(self, tmp_manifest):
        lib = library.AssetLibrary(tmp_manifest)
        assert lib.find_match("school", "sfx") == []

    def test_top_k_ordering(self, tmp_manifest):
        lib = library.AssetLibrary(tmp_manifest)
        # "school" should match both school_day and school_night.
        matches = lib.find_match("school", "background", top_k=3)
        ids = [m[0].id for m in matches]
        assert "bg_school_day" in ids or "bg_school_night" in ids
        # Scores are descending.
        scores = [m[1] for m in matches]
        assert scores == sorted(scores, reverse=True)

    def test_below_min_score_returns_empty(self, tmp_manifest):
        lib = library.AssetLibrary(tmp_manifest)
        # Query totally unrelated to any tag → below threshold.
        matches = lib.find_match("submarine periscope", "background", min_score=0.5)
        assert matches == []

    def test_find_one_convenience(self, tmp_manifest):
        lib = library.AssetLibrary(tmp_manifest)
        result = lib.find_one("forest", "background")
        assert result is not None
        assert result.id == "bg_forest_dawn"


class TestSourceMeta:
    def test_source_meta_populated(self, tmp_manifest):
        lib = library.AssetLibrary(tmp_manifest)
        asset = lib.find_one("forest", "background")
        assert asset is not None
        meta = asset.to_source_meta(query="forest dawn")
        assert meta["source"] == "local_library"
        assert meta["asset_id"] == "bg_forest_dawn"
        assert meta["asset_type"] == "background"
        assert meta["license"] == "CC-BY"
        assert "OpenGameArt" in meta["attribution"]
        assert meta["match_query"] == "forest dawn"


class TestEnvOverride:
    def test_env_var_overrides_default_path(self, tmp_manifest, monkeypatch):
        monkeypatch.setenv(library._DEFAULT_MANIFEST_ENV, str(tmp_manifest))
        lib = library.AssetLibrary()  # no explicit path
        assert lib.size == 5


class TestLexicalScore:
    """Direct unit tests for the scoring formula — no manifest needed."""

    def _asset(self, tags=(), aid="x", notes=""):
        return library.LibraryAsset(
            id=aid, type="background", path=Path("/tmp/x"),
            license="CC0", attribution="a", tags=tags, notes=notes,
        )

    def test_zero_when_empty_query(self):
        assert library._lexical_score("", self._asset(tags=("a", "b"))) == 0.0

    def test_all_tags_hit_ceiling(self):
        s = library._lexical_score("a b c", self._asset(tags=("a", "b", "c")))
        assert s > 0.5

    def test_no_overlap_zero(self):
        s = library._lexical_score("x y z", self._asset(tags=("a", "b"), aid="m"))
        assert s == 0.0

    def test_notes_substring_bonus(self):
        # No tags, but notes contain the query word — should still score > 0.
        s = library._lexical_score(
            "twilight", self._asset(tags=(), aid="scene1", notes="a twilight forest"),
        )
        assert s > 0.0
