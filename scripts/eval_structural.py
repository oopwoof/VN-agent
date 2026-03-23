"""Structural validation eval: test the checker on mock pipeline output + adversarial scripts.

Demonstrates what the 4-type structural checker catches.
Usage: uv run python scripts/eval_structural.py
"""
from __future__ import annotations

import asyncio
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def build_mock_script():
    """Build a VNScript from mock LLM data (same as what the pipeline produces)."""
    from vn_agent.schema.script import BranchOption, DialogueLine, Scene, VNScript
    from vn_agent.services.mock_llm import DIRECTOR_STEP1, DIRECTOR_STEP2

    step1 = json.loads(DIRECTOR_STEP1)
    step2 = json.loads(DIRECTOR_STEP2)

    scene_details = {s["id"]: s for s in step2["scenes"]}
    scenes = []
    for s in step1["scenes"]:
        detail = scene_details.get(s["id"], {})
        branches = [
            BranchOption(text=b["text"], next_scene_id=b["next_scene_id"])
            for b in detail.get("branches", [])
        ]
        scenes.append(Scene(
            id=s["id"],
            title=s["title"],
            description=s["description"],
            background_id=s.get("background_id", ""),
            characters_present=s.get("characters_present", []),
            next_scene_id=detail.get("next_scene_id"),
            branches=branches,
            dialogue=[
                DialogueLine(character_id="char_mara", text="Test.", emotion="neutral"),
            ],
        ))

    char_ids = [c["id"] for c in step1["characters"]]

    return VNScript(
        title=step1["title"],
        description=step1["description"],
        theme="test theme",
        start_scene_id=step1["start_scene_id"],
        scenes=scenes,
        characters=char_ids,
    )


def run_all_checks():
    """Run structural checker on valid + deliberately broken scripts."""
    from vn_agent.agents.reviewer import _structural_check

    base_script = build_mock_script()
    results = []

    # === Test 1: Valid mock script (baseline) ===
    r = _structural_check(base_script)
    results.append({
        "test": "Valid mock script (baseline)",
        "passed": r.passed,
        "issues": r.issues,
    })

    # === Test 2: Invalid start_scene_id ===
    broken = copy.deepcopy(base_script)
    broken.start_scene_id = "nonexistent_scene"
    r = _structural_check(broken)
    results.append({
        "test": "Invalid start_scene_id",
        "passed": r.passed,
        "issues": r.issues,
    })

    # === Test 3: Branch references non-existent scene ===
    broken = copy.deepcopy(base_script)
    from vn_agent.schema.script import BranchOption
    broken.scenes[0].branches.append(
        BranchOption(text="Go to void", next_scene_id="scene_that_doesnt_exist")
    )
    r = _structural_check(broken)
    results.append({
        "test": "Branch references non-existent scene",
        "passed": r.passed,
        "issues": r.issues,
    })

    # === Test 4: Unreachable scene (orphan) ===
    broken = copy.deepcopy(base_script)
    from vn_agent.schema.script import Scene, DialogueLine
    broken.scenes.append(Scene(
        id="orphan_scene",
        title="Orphan",
        description="No one can reach this",
        background_id="bg_void",
        characters_present=[],
        dialogue=[DialogueLine(character_id=None, text="Echo...", emotion="neutral")],
    ))
    r = _structural_check(broken)
    results.append({
        "test": "Unreachable orphan scene",
        "passed": r.passed,
        "issues": r.issues,
    })

    # === Test 5: Undeclared character speaks ===
    broken = copy.deepcopy(base_script)
    broken.scenes[0].dialogue.append(
        DialogueLine(character_id="char_ghost", text="I don't exist.", emotion="neutral")
    )
    r = _structural_check(broken)
    results.append({
        "test": "Undeclared character speaks",
        "passed": r.passed,
        "issues": r.issues,
    })

    # === Test 6: next_scene_id references non-existent scene ===
    broken = copy.deepcopy(base_script)
    broken.scenes[0].next_scene_id = "deleted_scene"
    r = _structural_check(broken)
    results.append({
        "test": "next_scene_id references non-existent scene",
        "passed": r.passed,
        "issues": r.issues,
    })

    # === Test 7: Multiple issues at once ===
    broken = copy.deepcopy(base_script)
    broken.start_scene_id = "wrong_start"
    broken.scenes[0].branches.append(
        BranchOption(text="Bad branch", next_scene_id="nowhere")
    )
    broken.scenes[1].dialogue.append(
        DialogueLine(character_id="char_unknown", text="Who am I?", emotion="neutral")
    )
    r = _structural_check(broken)
    results.append({
        "test": "Multiple simultaneous issues",
        "passed": r.passed,
        "issues": r.issues,
    })

    return results


def main():
    results = run_all_checks()

    print("=" * 60)
    print("STRUCTURAL VALIDATION EVALUATION")
    print("=" * 60)

    passed_count = 0
    caught_count = 0
    all_issue_types = set()

    for r in results:
        status = "PASS" if r["passed"] else f"FAIL ({len(r['issues'])} issues)"
        print(f"\n  [{status}] {r['test']}")
        for issue in r["issues"]:
            print(f"    → {issue}")
            all_issue_types.add(issue.split(":")[0].strip() if ":" in issue else issue[:50])

        if r["test"] == "Valid mock script (baseline)":
            if r["passed"]:
                passed_count += 1
        else:
            if not r["passed"]:
                caught_count += 1

    total_adversarial = len(results) - 1
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"  Baseline (valid script):     {'PASS' if passed_count else 'FAIL'}")
    print(f"  Adversarial detection rate:  {caught_count}/{total_adversarial} ({caught_count/total_adversarial:.0%})")
    print(f"  Defect types checked:        4 (start_scene, branch_ref, reachability, character_consistency)")
    print(f"  Total unique issues caught:  {sum(len(r['issues']) for r in results)}")

    summary = {
        "baseline_pass": passed_count == 1,
        "adversarial_tests": total_adversarial,
        "adversarial_caught": caught_count,
        "detection_rate": f"{caught_count/total_adversarial:.0%}",
        "defect_types": 4,
        "checks": [
            "start_scene_exists",
            "branch_references_valid",
            "all_scenes_reachable_bfs",
            "character_id_consistency",
        ],
        "results": results,
    }

    out = Path("eval_structural_results.json")
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nResults saved to {out}")


if __name__ == "__main__":
    main()
