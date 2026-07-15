#!/usr/bin/env python3
from __future__ import annotations

import json
import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.weird_captcha_gym.shared_scripts.setup_task import generate_incubator_candidate


BENCH_ROOT = ROOT / "benchmarks" / "weird_captcha_gym"
MECHANICS = (
    "shadow_crime_lab",
    "trajectory_catcher",
    "jigsaw_slider_alignment",
    "microgame_gauntlet",
    "minecraft_block_grid",
    "relation_prompt_grounding",
    "rorschach_fixed_rubric",
    "single_scene_split_boxes",
    "top_face_dice_arithmetic",
    "trace_shape_without_walls",
    "wizard_critter_capture",
)


def _task(mechanic: str) -> dict:
    path = BENCH_ROOT / "environments" / f"{mechanic}_env" / "tasks" / f"{mechanic}_seed_0001" / "task.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _grader(mechanic: str):
    path = BENCH_ROOT / "shared_runtime" / "server" / "incubator_graders" / f"{mechanic}.py"
    spec = importlib.util.spec_from_file_location(f"final_eleven_audit_grader_{mechanic}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _audit(mechanic: str, public: dict, truth: dict) -> None:
    assert public["mechanic_id"] == truth["mechanic_id"] == mechanic
    assert public["task_id"] == truth["task_id"]
    assert public["challenge_id"] == truth["challenge_id"]
    assert "seed" not in public
    if mechanic == "shadow_crime_lab":
        assert len(public["probe_zones"]) == 4 and public["minimum_probe_zones"] == 4
        assert len(truth["solution"]["probe_path"]) == 4
        assert set(truth["solution"]["expected_tag_point"]) == {"x", "y"}
    elif mechanic == "trajectory_catcher":
        assert len(public["rounds"]) == len(truth["solutions"]) == 3
        assert all(round_data["capture_depth"] >= 60 and round_data["alignment_tolerance_deg"] <= 22 for round_data in public["rounds"])
    elif mechanic == "jigsaw_slider_alignment":
        piece = public["scene"]["piece"]
        assert piece["initial_rotation_deg"] % piece["rotation_step_deg"] == 0
        assert piece["initial_rotation_deg"] % 360 != piece["target_rotation_deg"]
        assert public["tolerances"]["rotation_deg"] <= 3
    elif mechanic == "microgame_gauntlet":
        rounds = {item["type"]: item for item in public["rounds"]}
        assert set(rounds) == {"pressure", "chord", "dial", "intercept", "route"}
        assert len(rounds["pressure"]["pulses"]) >= 7
        assert len(rounds["chord"]["chords"]) == 3
        assert len(rounds["intercept"]["packets"]) == 3
        assert len(rounds["route"]["points"]) >= 9 and rounds["route"]["corridor_radius"] <= 8
        assert rounds["dial"]["target_tolerance"] <= 13
    elif mechanic == "minecraft_block_grid":
        assert public["target_count"] == len(truth["diamond_ids"]) == 4
        assert len(truth["solution_steps"]) == 8
    elif mechanic == "relation_prompt_grounding":
        assert "constraints" not in public and len(public["projection_targets"]) == 5
        assert len({item["depth"] for item in public["projection_targets"]}) == 5
        assert len(truth["solution_positions"]) == 5
    elif mechanic == "rorschach_fixed_rubric":
        assert len(public["required_tools"]) == 2 and public["observations_required"] == 10
        assert len(public["cycles"]) == 10 and all(len(item["frames"]) == public["ticks_per_cycle"] for item in public["cycles"])
        signatures = set(truth["signatures"])
        assert sum(signatures.issubset(set(values)) for values in truth["response_signatures"].values()) == 1
    elif mechanic == "single_scene_split_boxes":
        assert len(public["tiles"]) == 9
        assert public["requirements"]["minimum_spatial_touches"] >= 8
        assert public["requirements"]["minimum_phase_touches"] >= 7
    elif mechanic == "top_face_dice_arithmetic":
        assert len(public["dice"]) == len(truth["solution_plans"]) == 4
        assert 10 <= public["target_sum"] <= 20
        assert len({plan["final_top"] for plan in truth["solution_plans"]}) >= 3
    elif mechanic == "trace_shape_without_walls":
        assert public["requirements"]["min_branch_coverage"] == 0
        assert public["requirements"]["min_probe_samples"] >= 24
        assert public["requirements"]["min_trace_samples"] >= 72
        assert len(public["branches"]) >= 3
    elif mechanic == "wizard_critter_capture":
        assert len(public["critters"]) == 5 and len(public["occluders"]) >= 3
        assert truth["solver_plans"] and truth["solver_freeze_ticks"] >= truth["requirements"]["minimum_freeze_ticks"]


def main() -> None:
    seed_count = 64
    for mechanic in MECHANICS:
        task = _task(mechanic)
        first = None
        for index in range(seed_count):
            seed = f"final-eleven-audit-{index:03d}-{mechanic}"
            public, truth = generate_incubator_candidate(task, seed)
            _audit(mechanic, public, truth)
            if index == 0:
                first = (public, truth)
                assert generate_incubator_candidate(task, seed) == first
                grader = _grader(mechanic)
                superficial = {
                    "mechanic_id": mechanic,
                    "task_id": truth["task_id"],
                    "challenge_id": truth["challenge_id"],
                    "completed": True,
                }
                assert grader.grade(superficial, truth, public).get("passed") is not True
                spoofed = dict(superficial, task_id=f"{truth['task_id']}-spoofed")
                assert grader.grade(spoofed, truth, public).get("passed") is not True
        print(f"PASS {mechanic}: {seed_count} generated contracts", flush=True)
    print(f"PASS final cohort: {len(MECHANICS) * seed_count} generated contracts", flush=True)


if __name__ == "__main__":
    main()
