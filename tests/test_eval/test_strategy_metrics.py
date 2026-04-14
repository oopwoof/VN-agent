"""Sprint 8-2 — rule-based strategy metrics."""
from __future__ import annotations

import pytest

from vn_agent.eval.strategy_metrics import compute_signals
from vn_agent.schema.script import DialogueLine, Scene


def _mk_scene(scene_id: str, dialogue: list[DialogueLine]) -> Scene:
    return Scene(
        id=scene_id, title=scene_id, description="", background_id="bg",
        characters_present=[], dialogue=dialogue,
    )


def _line(text: str, emotion: str = "neutral", char: str | None = "a") -> DialogueLine:
    return DialogueLine(character_id=char, text=text, emotion=emotion)


class TestRuptureSignal:
    def test_calm_to_shock_produces_rupture(self):
        scene = _mk_scene("r", [
            _line("Quiet morning.", "neutral"),
            _line("Tea, black.", "neutral"),
            _line("Everything is fine.", "neutral"),
            _line("The letter arrived.", "thoughtful"),
            _line("HE'S DEAD.", "surprised"),  # <-- sudden shock
            _line("Impossible.", "scared"),
        ])
        sig = compute_signals(scene)
        assert sig.rupture >= 0.4, f"expected rupture signal, got {sig.rupture}"

    def test_monotone_scene_has_low_rupture(self):
        scene = _mk_scene("r2", [_line("...", "neutral")] * 8)
        sig = compute_signals(scene)
        assert sig.rupture < 0.2


class TestAccumulateSignal:
    def test_energy_ramp_produces_accumulate(self):
        scene = _mk_scene("a", [
            _line("Morning.", "neutral"),
            _line("Work to do.", "neutral"),
            _line("I want to tell you something.", "thoughtful"),
            _line("I've been thinking.", "thoughtful"),
            _line("I love you.", "loving"),
            _line("I really do.", "loving"),
            _line("I'm certain now.", "determined"),
        ])
        sig = compute_signals(scene)
        assert sig.accumulate > 0.6, f"expected strong accumulate, got {sig.accumulate}"


class TestErodeSignal:
    def test_shrinking_sentences_with_decay_produces_erode(self):
        scene = _mk_scene("e", [
            _line("I've always believed in you, in every bright possibility.", "happy"),
            _line("You said you would stay, and I took that as a promise.", "happy"),
            _line("Something is changing, I can feel it.", "thoughtful"),
            _line("I don't know you anymore.", "sad"),
            _line("...I see.", "sad"),
            _line("...", "sad"),
        ])
        sig = compute_signals(scene)
        assert sig.erode > 0.3, f"expected erode signal, got {sig.erode}"


class TestUncoverSignal:
    def test_proper_noun_reveal_in_back_half(self):
        scene = _mk_scene("u", [
            _line("Tell me what you found.", "neutral"),
            _line("A name, that's all.", "thoughtful"),
            _line("One name.", "thoughtful"),
            _line("Say it.", "scared"),
            _line("Caelen.", "surprised"),  # <-- reveal
            _line("Caelen Thorne. The man who owned the ship.", "thoughtful"),
            _line("Your father.", "sad"),
        ])
        sig = compute_signals(scene)
        assert sig.uncover > 0.3, f"expected uncover signal, got {sig.uncover}"


class TestContestSignal:
    def test_alternating_disagreement_produces_contest(self):
        scene = _mk_scene("c", [
            _line("We have to go.", "determined", "a"),
            _line("No.", "angry", "b"),
            _line("It isn't safe here.", "scared", "a"),
            _line("I'm staying.", "angry", "b"),
            _line("You'll die.", "sad", "a"),
            _line("Then I die.", "determined", "b"),
        ])
        sig = compute_signals(scene)
        assert sig.contest > 0.5, f"expected contest signal, got {sig.contest}"


class TestDriftSignal:
    def test_low_stakes_banter_is_drift(self):
        scene = _mk_scene("d", [
            _line("Nice weather.", "neutral"),
            _line("Mm.", "neutral"),
            _line("Saw a cat.", "neutral"),
            _line("Yeah?", "neutral"),
            _line("Just a cat.", "neutral"),
            _line("Sure.", "neutral"),
        ])
        sig = compute_signals(scene)
        assert sig.drift > 0.6, f"expected high drift, got {sig.drift}"

    def test_action_scene_is_not_drift(self):
        scene = _mk_scene("d2", [
            _line("RUN!", "scared", "a"),
            _line("I can't—", "scared", "b"),
            _line("Jump!", "determined", "a"),
            _line("The bridge is collapsing!", "surprised", "b"),
            _line("TAKE MY HAND!", "angry", "a"),
        ])
        sig = compute_signals(scene)
        assert sig.drift < 0.4, f"drift should be low for high-energy scene, got {sig.drift}"


class TestBestMatch:
    def test_best_match_returns_strongest_signal(self):
        # Construct a scene where contest dominates
        scene = _mk_scene("bm", [
            _line("Stop.", "angry", "a"),
            _line("No.", "angry", "b"),
            _line("I said stop.", "determined", "a"),
            _line("Make me.", "angry", "b"),
            _line("You leave me no choice.", "sad", "a"),
            _line("Do what you have to do.", "determined", "b"),
        ])
        sig = compute_signals(scene)
        assert sig.best_match() == "contest"


class TestEdgeCases:
    def test_empty_scene_all_zeros(self):
        scene = _mk_scene("empty", [])
        sig = compute_signals(scene)
        assert sig.as_dict() == {
            "accumulate": 0, "erode": 0, "rupture": 0,
            "uncover": 0, "contest": 0, "drift": 0,
        }

    def test_one_line_scene_all_zeros(self):
        scene = _mk_scene("single", [_line("Hello.")])
        sig = compute_signals(scene)
        # All signals should be 0 for a scene too short to compute
        assert sig.accumulate == 0 and sig.rupture == 0 and sig.contest == 0

    def test_signals_in_valid_range(self):
        scene = _mk_scene("range", [
            _line("One.", "neutral"),
            _line("Two.", "happy"),
            _line("Three.", "sad"),
            _line("Four.", "angry"),
        ])
        sig = compute_signals(scene)
        for k, v in sig.as_dict().items():
            assert 0.0 <= v <= 1.0, f"{k} out of range: {v}"


@pytest.mark.parametrize("pos,neg,expect_sign", [
    ("love hope trust warm", "", +1),
    ("fear hate lost dead", "", -1),
    ("love fear", "", 0.0),
])
def test_sentiment_sign(pos, neg, expect_sign):
    from vn_agent.eval.strategy_metrics import _sentiment
    text = pos + " " + neg
    s = _sentiment(text)
    if expect_sign > 0:
        assert s > 0.3
    elif expect_sign < 0:
        assert s < -0.3
    else:
        assert -0.3 <= s <= 0.3
