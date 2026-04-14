"""Sprint 11-3 — persona fingerprint audit tests."""
from __future__ import annotations

from vn_agent.agents.persona_audit import (
    _extract_keywords,
    _line_matches_keywords,
    audit_personas,
)
from vn_agent.schema.character import CharacterProfile
from vn_agent.schema.script import DialogueLine, Scene, VNScript


def _char(cid, name, fp=None) -> CharacterProfile:
    return CharacterProfile(
        id=cid, name=name, role="supporting",
        personality="x", background="y",
        speech_fingerprint=fp or [],
    )


def _scene(sid, lines) -> Scene:
    return Scene(
        id=sid, title=sid, description="", background_id="bg",
        characters_present=[],
        dialogue=[DialogueLine(character_id=cid, text=text)
                  for cid, text in lines],
    )


class TestExtractKeywords:
    def test_quoted_phrase_preferred(self):
        # "bloody hell" should be extracted as a unit
        kw = _extract_keywords("says 'bloody hell' when frustrated")
        assert "bloody hell" in kw

    def test_falls_back_to_content_words(self):
        # No quotes — should pull content words >= 4 chars
        kw = _extract_keywords("speaks in short declarative sentences")
        # "speaks", "sentence", "sentences" are in stop list; others remain
        assert "short" in kw or "declarative" in kw

    def test_stop_words_excluded(self):
        kw = _extract_keywords("uses some often speaks under stress")
        # all of these are stop words or short
        assert len(kw) == 0 or "stress" not in kw

    def test_quoted_takes_priority(self):
        kw = _extract_keywords("prefers 'perhaps' over 'maybe' in every sentence")
        assert "perhaps" in kw and "maybe" in kw
        # content words should NOT be in the result when quotes exist
        assert "prefers" not in kw


class TestLineMatching:
    def test_substring_match(self):
        assert _line_matches_keywords("Perhaps we should go.", {"perhaps"})

    def test_case_insensitive(self):
        assert _line_matches_keywords("PERHAPS.", {"perhaps"})

    def test_no_match(self):
        assert not _line_matches_keywords("We need to leave.", {"perhaps"})


class TestAuditPersonas:
    def _build_script(self, n_scenes, lines_per_scene):
        scenes = [_scene(f"s{i}", lines_per_scene) for i in range(n_scenes)]
        return VNScript(
            title="T", description="", theme="", start_scene_id="s0",
            scenes=scenes,
        )

    def test_short_script_short_circuits(self):
        """Fewer than min_scenes → no audit, empty warnings."""
        script = self._build_script(5, [("alice", "anything")])
        chars = {"alice": _char("alice", "Alice",
                                fp=["uses 'perhaps' often"])}
        assert audit_personas(script, chars, min_scenes=10) == []

    def test_no_fingerprinted_characters_short_circuits(self):
        """All characters lack speech_fingerprint → empty warnings."""
        script = self._build_script(15, [("alice", "anything")])
        chars = {"alice": _char("alice", "Alice")}  # no fingerprint
        assert audit_personas(script, chars) == []

    def test_strong_fingerprint_match_no_warning(self):
        """Character hitting fingerprint >= threshold → no drift."""
        lines_per_scene = [("alice", "Perhaps we should begin.")]
        script = self._build_script(12, lines_per_scene)
        chars = {"alice": _char("alice", "Alice",
                                fp=["prefers 'perhaps' over 'maybe'"])}
        warnings = audit_personas(script, chars)
        # Alice's lines all contain "perhaps" → hit rate 100% → no warning
        assert warnings == []

    def test_drift_flagged(self):
        """Character missing fingerprint words in most lines → warning."""
        lines_per_scene = [("alice", "We should leave now.")]
        script = self._build_script(12, lines_per_scene)
        chars = {"alice": _char("alice", "Alice",
                                fp=["says 'perhaps' often"])}
        warnings = audit_personas(script, chars)
        assert len(warnings) == 1
        assert "Alice" in warnings[0]
        assert "drift" in warnings[0].lower() or "rate" in warnings[0].lower()

    def test_min_scene_speakers_skipped(self):
        """Characters with < 3 lines across the whole script are skipped."""
        scenes = [
            _scene("s0", [("alice", "Perhaps.")]),
            *[_scene(f"s{i}", [("bob", "Hi")]) for i in range(1, 15)],
        ]
        script = VNScript(
            title="T", description="", theme="", start_scene_id="s0",
            scenes=scenes,
        )
        chars = {
            "alice": _char("alice", "Alice", fp=["uses 'perhaps'"]),
            "bob": _char("bob", "Bob", fp=["says 'nevermind'"]),
        }
        warnings = audit_personas(script, chars)
        # Alice only has 1 line total — skipped. Bob has 14 but misses fp.
        assert not any("Alice" in w for w in warnings)
        assert any("Bob" in w for w in warnings)
