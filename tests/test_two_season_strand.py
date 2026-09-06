from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "weird_captcha_gym" / "environments" / "two_season_strand_env"
GENERATOR_PATH = ROOT / "weird_captcha_gym" / "shared_scripts" / "incubator_generators" / "two_season_strand.py"
GRADER_PATH = ROOT / "weird_captcha_gym" / "shared_runtime" / "server" / "incubator_graders" / "two_season_strand.py"
FRONTEND_PATH = ROOT / "weird_captcha_gym" / "shared_runtime" / "app" / "mechanics" / "two_season_strand.js"
STYLES_PATH = ROOT / "weird_captcha_gym" / "shared_runtime" / "app" / "mechanics" / "two_season_strand.css"
PROVENANCE_PATH = ROOT / "weird_captcha_gym" / "shared_runtime" / "assets" / "provenance" / "two_season_strand_v0.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("two_season_strand_generator_test", GENERATOR_PATH)
GRADER = _load("two_season_strand_grader_test", GRADER_PATH)


def _task(level: int, interaction: str, real_time: str = "live") -> dict:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/two_season_strand_seed_0001/task.json").read_text(encoding="utf-8"))
    task["_control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": copy.deepcopy(controls["difficulty"][str(level)]["parameters"]),
    }
    task["natural_language"] = controls["difficulty"][str(level)]["natural_language"]
    return task


def _world(public: dict) -> dict:
    return {
        "palette": public["palette"],
        "initial_sequence": public["initial_sequence"],
        "season_orders": public["season_orders"],
        "target_pairs": public["target_pairs"],
        "parameters": public["parameters"],
        "fold_rule": public["fold_rule"],
    }


def _solution(public: dict, truth: dict, interaction: str) -> dict:
    sequence = list(truth["initial_sequence"])
    canonical = list(truth["canonical_sequence"])
    events: list[dict] = []
    remaining = set(truth["mutated_indices"])
    if interaction == "full":
        run = list(truth["canonical_paint_run"])
        color = canonical[run[0]]
        for index in run:
            sequence[index] = color
            remaining.discard(index)
        events.append({
            "sequence": 1,
            "indices": run,
            "color": color,
            "changed_count": len(run),
            "input_source": "strand_drag",
            "gesture": {
                "sample_count": 8,
                "travel_px": 24.0,
                "start_index": run[0],
                "end_index": run[-1],
            },
            "pair_progress_after": GRADER._pair_progress(sequence, truth["season_orders"], truth["target_pairs"]),
        })
    for index in sorted(remaining):
        color = canonical[index]
        sequence[index] = color
        events.append({
            "sequence": len(events) + 1,
            "indices": [index],
            "color": color,
            "changed_count": 1,
            "input_source": "strand_drag" if interaction == "full" else "palette_apply",
            **({
                "gesture": {
                    "sample_count": 4,
                    "travel_px": 14.0,
                    "start_index": index,
                    "end_index": index,
                },
            } if interaction == "full" else {}),
            "pair_progress_after": GRADER._pair_progress(sequence, truth["season_orders"], truth["target_pairs"]),
        })
    folds = {
        season: GRADER._pairs(sequence, truth["season_orders"][season])
        for season in ("spring", "winter")
    }
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction_mode": interaction,
        "edits": events,
        "final_sequence": sequence,
        "folds": folds,
        "edit_count": sum(event["changed_count"] for event in events),
        "completed": True,
    }


def test_all_ten_control_conditions_preserve_the_world_and_grade() -> None:
    for level in range(1, 6):
        worlds = []
        for interaction in ("simplified", "full"):
            public, truth = GENERATOR.generate(_task(level, interaction), f"strand-d{level}")
            decision = GRADER.grade(_solution(public, truth, interaction), truth, public)
            assert decision["passed"] is True, (level, interaction, decision)
            worlds.append(_world(public))
        assert worlds[0] == worlds[1]


def test_generated_worlds_are_reachable_and_coupled_across_seeds() -> None:
    for level in range(1, 6):
        parameters = _task(level, "full")["_control_condition"]["difficulty_parameters"]
        for seed_index in range(12):
            public, truth = GENERATOR.generate(_task(level, "full"), f"reach-{level}-{seed_index}")
            assert len(public["initial_sequence"]) == parameters["strand_length"]
            assert len(truth["mutated_indices"]) == parameters["mutation_count"]
            assert truth["coupled_node_count"] >= parameters["minimum_coupled_nodes"]
            assert len(truth["conflicting_repairs"]) >= parameters["minimum_conflicting_repairs"]
            assert all(
                item["spring_matched_delta"] * item["winter_matched_delta"] < 0
                for item in truth["conflicting_repairs"]
            )
            assert len(truth["target_pairs"]["winter"]) >= parameters["minimum_winter_pairs"]
            assert truth["initial_pair_delta"]["spring"] >= parameters["mutation_count"]
            assert truth["initial_pair_delta"]["winter"] >= max(2, parameters["mutation_count"] // 2)
            assert GRADER.grade(_solution(public, truth, "full"), truth, public)["passed"] is True


def test_live_and_paused_preserve_the_decision_problem() -> None:
    live, _ = GENERATOR.generate(_task(4, "full", "live"), "same-clock-world")
    paused, _ = GENERATOR.generate(_task(4, "full", "paused"), "same-clock-world")
    assert _world(live) == _world(paused)
    assert live["challenge_id"] == paused["challenge_id"]
    assert live["control_condition"]["real_time"] == "live"
    assert paused["control_condition"]["real_time"] == "paused"


def test_baseline_profiles_and_source_contract_are_fixed() -> None:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    env = json.loads((ENV / "env.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/two_season_strand_seed_0001/task.json").read_text(encoding="utf-8"))
    split = json.loads((ROOT / "weird_captcha_gym/splits/two_season_strand_split.json").read_text(encoding="utf-8"))
    assert controls["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    assert controls["difficulty"]["4"]["parameters"] == {
        "strand_length": 64,
        "mutation_count": 6,
        "edit_budget": 18,
        "index_label_stride": 4,
        "minimum_winter_pairs": 12,
        "minimum_coupled_nodes": 18,
        "minimum_conflicting_repairs": 4,
        "blueprint_guidance": "standard",
    }
    assert env["runner_options"] == {"observation_window_ms": 0, "frames_per_observation": 1, "play_time_seconds": 180}
    assert task["name"] == "Two-Season Strand"
    assert task["metadata"]["source_anchors"] == ["GWP-013", "GWP-014", "XCOG-244", "XCOG-247", "XCOG-248"]
    assert task["metadata"]["capabilities"] == ["visual_understanding_2d", "reasoning_and_planning"]
    assert task["metadata"]["status"] == "prototype_visual_candidate"
    assert len(split["variations_tasks"]) == 20


def test_selected_source_urls_and_season_tabs_are_present() -> None:
    provenance = json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))
    assert {entry["url"] for entry in provenance["sources"]} == {
        "https://eternagame.org/",
        "https://en.wikipedia.org/wiki/EteRNA",
        "https://github.com/eternagame/eterna100-benchmarking",
        "https://eternagame.org/get/?type=puzzle&nid=20111",
        "https://eternagame.org/get/?type=puzzles&puzzle_type=Basic&sort=solved&size=5",
        "https://www.biorxiv.org/content/10.1101/2021.08.26.457839v2",
    }
    frontend = FRONTEND_PATH.read_text(encoding="utf-8")
    assert 'role="tablist"' in frontend
    assert 'data-season-tab="${season}"' in frontend
    assert 'foldMarkup(model.activeSeason)' in frontend


def test_budget_exhaustion_submits_without_a_task_time_timer() -> None:
    frontend = FRONTEND_PATH.read_text(encoding="utf-8")
    styles = STYLES_PATH.read_text(encoding="utf-8")
    branch = frontend.split("if (projected > Number(model.state.parameters.edit_budget))", 1)[1].split("indices.forEach", 1)[0]
    assert "void submit(false);" in branch
    assert "setTimeout" not in branch
    assert "strand-verdict-snap" in branch
    assert ".strand-verdict-fail.strand-verdict-snap { animation: none; opacity: 1; }" in styles


def test_difficulty_changes_the_actual_constraint_problem() -> None:
    profiles = {
        level: GENERATOR.generate(_task(level, "full"), "profile-structure")[0]
        for level in range(1, 6)
    }
    assert [len(profiles[level]["initial_sequence"]) for level in range(1, 6)] == [40, 48, 56, 64, 80]
    assert [profiles[level]["parameters"]["mutation_count"] for level in range(1, 6)] == [2, 3, 4, 6, 9]
    assert profiles[1]["parameters"]["index_label_stride"] < profiles[4]["parameters"]["index_label_stride"] < profiles[5]["parameters"]["index_label_stride"]
    assert profiles[1]["parameters"]["blueprint_guidance"] == "strong"
    assert profiles[5]["parameters"]["blueprint_guidance"] == "sparse"


def test_wrong_interaction_stale_identity_and_forged_folds_are_rejected() -> None:
    public, truth = GENERATOR.generate(_task(4, "full"), "negative-contract")
    payload = _solution(public, truth, "full")
    payload["edits"][0]["input_source"] = "palette_apply"
    assert GRADER.grade(payload, truth, public)["passed"] is False
    payload = _solution(public, truth, "full")
    payload["challenge_id"] = "stale"
    assert GRADER.grade(payload, truth, public)["passed"] is False
    payload = _solution(public, truth, "full")
    payload["folds"]["spring"] = []
    assert GRADER.grade(payload, truth, public)["passed"] is False
    forged_public = copy.deepcopy(public)
    forged_public["target_pairs"]["winter"] = []
    assert GRADER.grade(_solution(public, truth, "full"), truth, forged_public)["passed"] is False


def test_full_requires_physical_strokes_and_preserves_per_bead_edit_cost() -> None:
    public, truth = GENERATOR.generate(_task(4, "full"), "stroke-only-contract")
    full = _solution(public, truth, "full")
    simplified_public, simplified_truth = GENERATOR.generate(_task(4, "simplified"), "stroke-only-contract")
    simplified = _solution(simplified_public, simplified_truth, "simplified")
    assert all(event["input_source"] == "strand_drag" for event in full["edits"])
    assert all(event["input_source"] == "palette_apply" for event in simplified["edits"])
    assert full["edit_count"] == simplified["edit_count"] == len(truth["mutated_indices"])
    assert GRADER.grade(full, truth, public)["passed"] is True
    assert GRADER.grade(simplified, simplified_truth, simplified_public)["passed"] is True

    click_only = copy.deepcopy(full)
    click_only["edits"][0].pop("gesture")
    click_only["edits"][0]["input_source"] = "direct_cycle"
    assert "wrong interaction input" in GRADER.grade(click_only, truth, public)["feedback"]


def test_full_drag_geometry_and_budget_are_enforced() -> None:
    public, truth = GENERATOR.generate(_task(4, "full"), "drag-contract")
    payload = _solution(public, truth, "full")
    assert GRADER.grade(payload, truth, public)["passed"] is True
    short = copy.deepcopy(payload)
    short["edits"][0]["gesture"]["travel_px"] = 3
    assert "shorter" in GRADER.grade(short, truth, public)["feedback"]
    discontinuous = copy.deepcopy(payload)
    discontinuous["edits"][0]["indices"][1] += 2
    assert "contiguous" in GRADER.grade(discontinuous, truth, public)["feedback"]
    wrong_endpoints = copy.deepcopy(payload)
    wrong_endpoints["edits"][0]["gesture"]["end_index"] += 1
    assert "endpoints" in GRADER.grade(wrong_endpoints, truth, public)["feedback"]
    over_budget = copy.deepcopy(truth)
    over_budget["parameters"]["edit_budget"] = 2
    forged_public = copy.deepcopy(public)
    forged_public["parameters"]["edit_budget"] = 2
    assert GRADER.grade(payload, over_budget, forged_public)["passed"] is False


def test_hidden_solution_is_not_in_the_public_state() -> None:
    public, truth = GENERATOR.generate(_task(4, "full"), "secrecy")
    assert "canonical_sequence" not in public
    assert "mutated_indices" not in public
    assert "canonical_paint_run" not in public
    assert truth["canonical_sequence"] != truth["initial_sequence"]


def test_every_instruction_has_the_complete_visible_ui_only_boundary() -> None:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/two_season_strand_seed_0001/task.json").read_text(encoding="utf-8"))
    instructions = [task["description"], task["natural_language"]]
    instructions.extend(profile["natural_language"] for profile in controls["difficulty"].values())
    required = (
        "Solve only from screenshots and visible controls in the task webpage",
        "Developer Tools",
        "isolated agent sandbox",
        "provided gateway",
        "the task terminal or shell",
        "address-bar or URL/query edits",
        "pre-existing, unrelated, blank, browser-settings, or non-task tab",
        "A tab opened by a visible task control is allowed only when it is part of the task",
    )
    assert all(all(fragment in instruction for fragment in required) for instruction in instructions)
