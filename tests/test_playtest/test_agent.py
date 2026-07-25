"""P4: agent.run_playtest — end-to-end over a small synthetic VNScript
built into a real on-disk Ren'Py project (via the real build_project(),
same as a real job would produce), with a fake vision judge llm."""
from __future__ import annotations

import pytest

from vn_agent.compiler.project_builder import build_project
from vn_agent.playtest.agent import PlaytestError, run_playtest, write_report
from vn_agent.playtest.schema import PlaytestFrameJudgment, PlaytestReport
from vn_agent.schema.script import BranchOption, Scene, VNScript, WorldVariable


def _build_script() -> VNScript:
    return VNScript(
        title="Test VN", description="d", theme="th", start_scene_id="s1",
        world_variables=[WorldVariable(name="flag", type="bool", initial_value=False, description="d")],
        scenes=[
            Scene(
                id="s1", title="Start", description="d", background_id="bg_a",
                branches=[
                    BranchOption(text="go free", next_scene_id="s2"),
                    BranchOption(text="go locked", next_scene_id="s3", requires={"flag": True}),
                ],
            ),
            Scene(id="s2", title="Free path", description="d", background_id="bg_b"),
            Scene(id="s3", title="Locked path", description="d", background_id="bg_b"),
        ],
    )


async def _fake_llm(system, user, schema=None, model=None, caller=None, **kw):  # noqa: ARG001
    return PlaytestFrameJudgment(
        ui_coherence_score=4, dead_end_risk="none",
        interactivity_pacing_score=4, player_agency_score=3,
        findings=[], summary="fake judgment",
    )


@pytest.fixture
def project_dir(tmp_path):
    script = _build_script()
    build_project(script, {}, tmp_path)
    return tmp_path


@pytest.mark.asyncio
async def test_run_playtest_writes_report_and_matches_known_graph(project_dir):
    report = await run_playtest(project_dir, llm=_fake_llm)

    assert isinstance(report, PlaytestReport)
    assert report.total_scenes == 3
    assert report.visited_scenes == 2  # s1, s2 — s3 gated off
    assert set(report.unreachable_scene_ids) == {"s3"}
    assert report.total_declared_branches == 2
    assert report.reachable_branches == 1
    assert report.coverage_score == pytest.approx(2 / 3, abs=0.01)
    assert report.branch_reachability_score == pytest.approx(0.5, abs=0.01)
    assert report.frames_judged == len(report.frames)
    assert all(f.judgment is not None for f in report.frames)

    report_path = project_dir / "playtest" / "report.json"
    assert report_path.exists()
    round_tripped = PlaytestReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    assert round_tripped.frames_judged == report.frames_judged

    frames_dir = project_dir / "playtest" / "frames"
    assert len(list(frames_dir.glob("*.png"))) == len(report.frames)


@pytest.mark.asyncio
async def test_run_playtest_missing_script_raises_playtest_error(tmp_path):
    with pytest.raises(PlaytestError):
        await run_playtest(tmp_path, llm=_fake_llm)


@pytest.mark.asyncio
async def test_run_playtest_one_bad_frame_degrades_not_crashes(project_dir):
    calls = {"n": 0}

    async def flaky_llm(system, user, schema=None, model=None, caller=None, **kw):  # noqa: ARG001
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated judge failure")
        return await _fake_llm(system, user, schema=schema, model=model, caller=caller, **kw)

    report = await run_playtest(project_dir, llm=flaky_llm)

    failed = [f for f in report.frames if f.judgment is None]
    assert len(failed) == 1
    assert "simulated judge failure" in failed[0].judge_error
    assert report.frames_judged == len(report.frames) - 1


def test_write_report_creates_parent_dirs(tmp_path):
    report = PlaytestReport(
        generated_at="now", script_title="t", total_scenes=1, visited_scenes=1,
        unreachable_scene_ids=[], total_declared_branches=0, reachable_branches=0,
        coverage_score=1.0, branch_reachability_score=1.0, dimension_scores={},
        frames=[], judge_model="m", frames_judged=0, frames_skipped=0,
    )
    path = write_report(report, tmp_path)
    assert path.exists()
