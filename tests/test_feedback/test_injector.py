"""v4 P1-2 unit tests: BM25 flywheel injection into Writer prompt."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from vn_agent.feedback import injector, store as fb_store


@pytest.fixture(autouse=True)
def _iso_feedback_root(tmp_path, monkeypatch):
    monkeypatch.setenv(fb_store._DEFAULT_ROOT_ENV, str(tmp_path))
    yield


def _scene(**kw) -> SimpleNamespace:
    """Minimal duck-typed Scene for injector consumption."""
    defaults = {
        "description": "",
        "title": "",
        "narrative_strategy": None,
        "characters_present": [],
    }
    defaults.update(kw)
    return SimpleNamespace(**defaults)


class TestTokenize:
    def test_latin_lowercased(self):
        assert injector._tokenize("Hello WORLD") == ["hello", "world"]

    def test_cjk_char_level(self):
        toks = injector._tokenize("对白啰嗦")
        assert set(toks) == {"对", "白", "啰", "嗦"}

    def test_mixed(self):
        toks = injector._tokenize("Writer 对白 too verbose")
        assert "writer" in toks and "对" in toks and "verbose" in toks

    def test_empty(self):
        assert injector._tokenize("") == []
        assert injector._tokenize(None) == []  # type: ignore[arg-type]


class TestBuildSceneQuery:
    def test_pulls_description_and_strategy(self):
        scene = _scene(
            description="A rooftop confrontation at dusk.",
            narrative_strategy="rupture",
        )
        q = injector.build_scene_query(scene)
        assert "rooftop" in q
        assert "rupture" in q

    def test_adds_character_hints_when_present(self):
        chars = {
            "alice": SimpleNamespace(role="protagonist", personality="curious"),
            "bob": SimpleNamespace(role="rival", personality="brash"),
        }
        scene = _scene(
            description="tea",
            characters_present=["alice", "bob"],
        )
        q = injector.build_scene_query(scene, chars)
        assert "curious" in q and "brash" in q and "protagonist" in q

    def test_extra_tokens_appended(self):
        scene = _scene(description="core")
        q = injector.build_scene_query(scene, None, extra=["theme_x", "校园恋爱"])
        assert "theme_x" in q and "校园恋爱" in q


class TestBuildInjection:
    def test_no_feedback_returns_empty(self):
        result = injector.build_injection(_scene(description="x"))
        assert result.is_empty
        assert result.text == ""
        assert result.matched == []

    def test_no_downvotes_returns_empty(self):
        fb_store.append(fb_store.FeedbackRecord(verdict="up", reason="good pacing"))
        result = injector.build_injection(_scene(description="x"))
        assert result.is_empty

    def test_topic_match_selected(self):
        # Two down-votes, only one topical. min_score=0.5 filters out the
        # zero-overlap doc under the small-corpus overlap fallback.
        fb_store.append(fb_store.FeedbackRecord(
            verdict="down", reason="dialogue too verbose on rooftop scenes",
        ))
        fb_store.append(fb_store.FeedbackRecord(
            verdict="down", reason="the mecha battle in the space station was boring",
        ))
        scene = _scene(description="A tense rooftop conversation at sunset.")
        result = injector.build_injection(scene, min_score=0.5)
        assert not result.is_empty
        assert "rooftop" in result.text
        assert "space station" not in result.text
        assert len(result.matched) == 1

    def test_topk_caps_matches(self):
        for i in range(6):
            fb_store.append(fb_store.FeedbackRecord(
                verdict="down", reason=f"rooftop conversation issue {i}",
            ))
        scene = _scene(description="rooftop dialogue scene")
        result = injector.build_injection(scene, top_k=2, min_score=-1.0)
        assert len(result.matched) == 2

    def test_up_votes_ignored(self):
        fb_store.append(fb_store.FeedbackRecord(verdict="up", reason="rooftop dialogue great"))
        result = injector.build_injection(_scene(description="rooftop scene"), min_score=0.0)
        assert result.is_empty

    def test_empty_reasons_ignored(self):
        fb_store.append(fb_store.FeedbackRecord(verdict="down", reason=None))
        fb_store.append(fb_store.FeedbackRecord(verdict="down", reason="  "))
        fb_store.append(fb_store.FeedbackRecord(verdict="down", reason="rooftop verbose"))
        result = injector.build_injection(_scene(description="rooftop"), min_score=-1.0)
        assert len(result.matched) == 1  # only the substantive one

    def test_long_reason_truncated(self):
        long_reason = "rooftop scene " + ("noise " * 200)
        fb_store.append(fb_store.FeedbackRecord(verdict="down", reason=long_reason))
        result = injector.build_injection(_scene(description="rooftop"), min_score=-1.0)
        assert result.matched
        # Truncation adds an ellipsis; length capped.
        assert len(result.matched[0]) <= injector._MAX_REASON_CHARS + 1

    def test_below_min_score_returns_empty(self):
        fb_store.append(fb_store.FeedbackRecord(
            verdict="down", reason="entirely unrelated topic space robots",
        ))
        result = injector.build_injection(_scene(description="tea garden"), min_score=100.0)
        assert result.is_empty

    def test_result_carries_ids_for_audit(self):
        record = fb_store.FeedbackRecord(verdict="down", reason="rooftop verbose")
        fb_store.append(record)
        result = injector.build_injection(_scene(description="rooftop"), min_score=-1.0)
        assert record.id in result.matched_ids

    def test_output_shape_prose(self):
        fb_store.append(fb_store.FeedbackRecord(verdict="down", reason="rooftop pacing sluggish"))
        result = injector.build_injection(_scene(description="rooftop"), min_score=-1.0)
        assert result.text.startswith("AVOID")
        assert "- rooftop pacing sluggish" in result.text

    def test_no_scene_returns_empty(self):
        fb_store.append(fb_store.FeedbackRecord(verdict="down", reason="anything"))
        assert injector.build_injection(None).is_empty


class TestChinese:
    def test_cjk_reason_matches_cjk_scene(self):
        fb_store.append(fb_store.FeedbackRecord(
            verdict="down", reason="对白太啰嗦，节奏拖沓",
        ))
        scene = _scene(description="两人在屋顶上对话")
        result = injector.build_injection(scene, min_score=-1.0)
        # "对" is shared between reason and scene → BM25 hit.
        assert not result.is_empty
        assert "对白" in result.text
