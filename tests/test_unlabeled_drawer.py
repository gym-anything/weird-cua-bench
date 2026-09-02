from __future__ import annotations

import copy
import functools
import importlib.util
import json
import shutil
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "weird_captcha_gym"
ENV = BENCH / "environments" / "unlabeled_drawer_env"
GENERATOR_PATH = BENCH / "shared_scripts" / "incubator_generators" / "unlabeled_drawer.py"
GRADER_PATH = BENCH / "shared_runtime" / "server" / "incubator_graders" / "unlabeled_drawer.py"
SOLVER_PATH = BENCH / "tools" / "incubator_solvers" / "unlabeled_drawer.py"
VERIFIER_PATH = ENV / "tasks" / "unlabeled_drawer_seed_0001" / "verifier.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("unlabeled_drawer_generator_test", GENERATOR_PATH)
GRADER = _load("unlabeled_drawer_grader_test", GRADER_PATH)
SOLVER = _load("unlabeled_drawer_solver_test", SOLVER_PATH)
VERIFIER = _load("unlabeled_drawer_exported_verifier_test", VERIFIER_PATH)


def _task(level: int, interaction: str, real_time: str = "live") -> dict:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/unlabeled_drawer_seed_0001/task.json").read_text(encoding="utf-8"))
    task["_control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": copy.deepcopy(controls["difficulty"][str(level)]["parameters"]),
    }
    return task


def _gesture(public: dict, destination: str, start_zone: str) -> dict:
    x1, y1, x2, y2 = public["drop_regions"][destination]
    sx1, sy1, sx2, sy2 = public["source_regions"][start_zone]
    return {
        "start_zone": start_zone,
        "gesture": {
            "start": [(sx1 + sx2) / 2, (sy1 + sy2) / 2],
            "end": [(x1 + x2) / 2, (y1 + y2) / 2],
            "travel_px": 480,
            "sample_count": 8,
        },
    }


def _solution(public: dict, truth: dict, interaction: str) -> dict:
    events = []

    def add(event: dict) -> None:
        events.append({"sequence": len(events) + 1, **event})

    plan = GENERATOR.visible_probe_plans(public["probe_specimens"], public["parameters"])[0]
    by_id = {item["id"]: item for item in public["probe_specimens"]}
    selected_probes = [by_id[specimen_id] for specimen_id in plan["specimen_ids"]]
    observed_outcomes = {
        specimen["id"]: truth["probe_outcomes"][specimen["id"]]
        for specimen in selected_probes
    }
    predictions = GENERATOR.infer_visible_predictions(
        public["probe_specimens"],
        public["final_specimens"],
        public["parameters"],
        plan["specimen_ids"],
        observed_outcomes,
    )
    for specimen in selected_probes:
        event = {
            "type": "probe",
            "specimen_id": specimen["id"],
            "outcome": observed_outcomes[specimen["id"]],
            "input_source": "specimen_drag" if interaction == "full" else "selected_test_button",
        }
        if interaction == "full":
            event.update(_gesture(public, "probe", "probe-rack"))
        add(event)
    add({"type": "open_final", "input_source": "seal_latch"})
    assignments = {}
    for specimen in public["final_specimens"]:
        specimen_id = specimen["id"]
        drawer = "accept" if predictions[specimen_id] else "reject"
        event = {
            "type": "assign",
            "specimen_id": specimen_id,
            "drawer": drawer,
            "before": None,
            "input_source": "specimen_drag" if interaction == "full" else "selected_drawer_button",
        }
        if interaction == "full":
            event.update(_gesture(public, drawer, "final-rack"))
        add(event)
        assignments[specimen_id] = drawer
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction_mode": interaction,
        "events": events,
        "tested_probe_ids": [item["id"] for item in selected_probes],
        "final_assignments": assignments,
        "completed": True,
    }


def _has_guaranteed_adaptive_visible_policy(public: dict) -> bool:
    """Independent full-profile decision tree using no hidden rule or oracle map."""
    probes = public["probe_specimens"]
    finals = public["final_specimens"]
    parameters = public["parameters"]
    hypotheses = GENERATOR.full_rule_hypotheses(
        parameters["rule_family"], parameters["feature_pool"]
    )
    probe_answers = [
        tuple(GENERATOR.evaluate_rule(specimen["features"], rule) for specimen in probes)
        for rule in hypotheses
    ]
    final_answers = [
        tuple(GENERATOR.evaluate_rule(specimen["features"], rule) for specimen in finals)
        for rule in hypotheses
    ]

    @functools.lru_cache(maxsize=None)
    def search(candidates: tuple[int, ...], available: tuple[int, ...], seals: int) -> bool:
        if len({final_answers[index] for index in candidates}) == 1:
            return True
        if seals == 0:
            return False
        for probe_index in available:
            branches = [
                tuple(index for index in candidates if probe_answers[index][probe_index] is outcome)
                for outcome in (False, True)
            ]
            if not all(branches):
                continue
            remaining = tuple(index for index in available if index != probe_index)
            if all(search(branch, remaining, seals - 1) for branch in branches):
                return True
        return False

    return search(
        tuple(range(len(hypotheses))),
        tuple(range(len(probes))),
        int(parameters["probe_count"]),
    )


def test_all_ten_control_conditions_generate_the_same_world_and_grade() -> None:
    for level in range(1, 6):
        worlds = []
        for interaction in ("simplified", "full"):
            public, truth = GENERATOR.generate(_task(level, interaction), "same-world")
            decision = GRADER.grade(_solution(public, truth, interaction), truth, public)
            assert decision["passed"] is True, (level, interaction, decision)
            worlds.append({key: public[key] for key in (
                "challenge_id", "probe_specimens", "final_specimens", "runtime_probe_outcomes", "parameters",
            )})
        assert worlds[0] == worlds[1]


def test_hundred_seed_visible_policy_reachability_and_balanced_classes() -> None:
    for level in range(1, 6):
        for seed_index in range(100):
            public, truth = GENERATOR.generate(_task(level, "full"), f"reachability-{level}-{seed_index}")
            assert {True, False} <= set(truth["probe_outcomes"].values())
            assert {True, False} <= set(truth["final_outcomes"].values())
            assert [item["style"]["serial"] for item in public["probe_specimens"]] == [
                f"P{index:02d}" for index in range(1, len(public["probe_specimens"]) + 1)
            ]
            assert [item["style"]["serial"] for item in public["final_specimens"]] == [
                f"F{index:02d}" for index in range(1, len(public["final_specimens"]) + 1)
            ]
            diagnostic = GENERATOR.visible_policy_diagnostics(
                public["probe_specimens"], public["final_specimens"], public["parameters"]
            )
            assert diagnostic["decisive"] is True, {
                "level": level,
                "seed": seed_index,
                "diagnostic": diagnostic,
            }
            plans = GENERATOR.visible_probe_plans(public["probe_specimens"], public["parameters"])
            assert plans
            assert all(set(plan["feature_indices"]) == set(truth["rule"]["indices"]) for plan in plans)
            full_profile = GENERATOR.full_profile_policy_diagnostics(
                public["probe_specimens"], public["final_specimens"], public["parameters"]
            )
            assert full_profile["decisive"] is True, {
                "level": level,
                "seed": seed_index,
                "diagnostic": full_profile,
            }
            assert GRADER.grade(_solution(public, truth, "full"), truth, public)["passed"] is True


def test_every_visible_policy_answer_branch_is_decisive() -> None:
    for level in range(1, 6):
        for seed_index in range(100):
            public, _truth = GENERATOR.generate(_task(level, "full"), f"all-branches-{level}-{seed_index}")
            diagnostic = GENERATOR.full_profile_policy_diagnostics(
                public["probe_specimens"], public["final_specimens"], public["parameters"]
            )
            assert diagnostic["decisive"] is True, {
                "level": level,
                "seed": seed_index,
                "reason": diagnostic["reason"],
                "ambiguous_branches": diagnostic["branches"],
                "plan": diagnostic["plan"],
            }
            assert diagnostic["branch_count"] >= 2
            assert _has_guaranteed_adaptive_visible_policy(public), {
                "level": level,
                "seed": seed_index,
                "probe_features": [item["features"] for item in public["probe_specimens"]],
                "final_features": [item["features"] for item in public["final_specimens"]],
            }


def test_solver_plan_cannot_consult_unrevealed_outcomes_or_construction_ids() -> None:
    public, truth = GENERATOR.generate(_task(4, "full"), "oracleless-solver")
    oracleless = copy.deepcopy(public)
    oracleless.pop("runtime_probe_outcomes")
    probe_ids = SOLVER._choose_visible_probe_plan(oracleless)
    assert len(probe_ids) == int(public["parameters"]["probe_count"])
    assert [item["style"]["serial"] for item in public["probe_specimens"] if item["id"] in probe_ids]
    observed = {specimen_id: truth["probe_outcomes"][specimen_id] for specimen_id in probe_ids}
    predictions = SOLVER._infer_from_returned_outcomes(oracleless, probe_ids, observed)
    assert predictions == truth["final_outcomes"]
    source = SOLVER_PATH.read_text(encoding="utf-8")
    assert "runtime_probe_outcomes" not in source
    assert "split(\"-\", 2)" not in source


def test_normal_task_surface_contains_no_tutorial_or_next_step_copy() -> None:
    source = (BENCH / "shared_runtime/app/mechanics/unlabeled_drawer.js").read_text(encoding="utf-8")
    forbidden = (
        "Each seal stores",
        "Choose which evidence",
        "Review one archived",
        "File the current specimen",
        "The next will replace it",
        "CHOOSE → PROBE → RECALL → FILE",
        "CLOSED RECORDS CANNOT BE REOPENED",
    )
    assert not any(phrase in source for phrase in forbidden)


def test_live_and_paused_are_observation_schedules_not_task_branches() -> None:
    live, _ = GENERATOR.generate(_task(4, "full", "live"), "clock-equivalence")
    paused, _ = GENERATOR.generate(_task(4, "full", "paused"), "clock-equivalence")
    for key in ("challenge_id", "probe_specimens", "final_specimens", "runtime_probe_outcomes", "parameters"):
        assert live[key] == paused[key]
    assert live["control_condition"]["real_time"] == "live"
    assert paused["control_condition"]["real_time"] == "paused"


def test_replay_rejects_early_open_forged_feedback_wrong_surface_and_stationary_click() -> None:
    public, truth = GENERATOR.generate(_task(4, "full"), "negative-replay")

    early = _solution(public, truth, "full")
    early["events"].insert(0, early["events"].pop(int(public["parameters"]["probe_count"])))
    for sequence, event in enumerate(early["events"], 1):
        event["sequence"] = sequence
    assert GRADER.grade(early, truth, public)["passed"] is False

    forged = _solution(public, truth, "full")
    forged["events"][0]["outcome"] = not forged["events"][0]["outcome"]
    assert "forges drawer feedback" in GRADER.grade(forged, truth, public)["feedback"]

    wrong_surface = _solution(public, truth, "full")
    wrong_surface["events"][0]["input_source"] = "selected_test_button"
    assert "input surface" in GRADER.grade(wrong_surface, truth, public)["feedback"]

    stationary = _solution(public, truth, "full")
    stationary["events"][0]["gesture"]["travel_px"] = 0
    stationary["events"][0]["gesture"]["sample_count"] = 1
    assert "stationary click" in GRADER.grade(stationary, truth, public)["feedback"]

    false_start = _solution(public, truth, "full")
    false_start["events"][0]["gesture"]["start"] = [0.99, 0.01]
    assert false_start["events"][0]["start_zone"] == "probe-rack"
    assert "start coordinate" in GRADER.grade(false_start, truth, public)["feedback"]

    over_budget = _solution(public, truth, "full")
    tested_ids = set(over_budget["tested_probe_ids"])
    extra = next(item for item in public["probe_specimens"] if item["id"] not in tested_ids)
    open_index = int(public["parameters"]["probe_count"])
    over_budget["events"].insert(open_index, {
        "type": "probe",
        "specimen_id": extra["id"],
        "outcome": truth["probe_outcomes"][extra["id"]],
        "input_source": "specimen_drag",
        **_gesture(public, "probe", "probe-rack"),
    })
    for sequence, event in enumerate(over_budget["events"], 1):
        event["sequence"] = sequence
    over_budget["tested_probe_ids"].append(extra["id"])
    assert "unavailable specimen" in GRADER.grade(over_budget, truth, public)["feedback"]


def test_incorrect_final_sort_and_mutated_contract_are_rejected() -> None:
    public, truth = GENERATOR.generate(_task(5, "simplified"), "negative-final")
    incorrect = _solution(public, truth, "simplified")
    assignment = next(event for event in incorrect["events"] if event["type"] == "assign")
    assignment["drawer"] = "reject" if assignment["drawer"] == "accept" else "accept"
    incorrect["final_assignments"][assignment["specimen_id"]] = assignment["drawer"]
    assert GRADER.grade(incorrect, truth, public)["passed"] is False

    mutated = copy.deepcopy(public)
    mutated["runtime_probe_outcomes"] = dict(mutated["runtime_probe_outcomes"])
    first = next(iter(mutated["runtime_probe_outcomes"]))
    mutated["runtime_probe_outcomes"][first] = not mutated["runtime_probe_outcomes"][first]
    assert "browser oracle commitment" in GRADER.grade(_solution(public, truth, "simplified"), truth, mutated)["feedback"]

    sequential = _solution(public, truth, "simplified")
    assignments = [index for index, event in enumerate(sequential["events"]) if event["type"] == "assign"]
    first, second = assignments[:2]
    sequential["events"][first], sequential["events"][second] = sequential["events"][second], sequential["events"][first]
    for sequence, event in enumerate(sequential["events"], 1):
        event["sequence"] = sequence
    assert "unavailable specimen" in GRADER.grade(sequential, truth, public)["feedback"]


def test_baseline_sources_profiles_and_static_clock_contract() -> None:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/unlabeled_drawer_seed_0001/task.json").read_text(encoding="utf-8"))
    env = json.loads((ENV / "env.json").read_text(encoding="utf-8"))
    split = json.loads((BENCH / "splits" / "unlabeled_drawer_split.json").read_text(encoding="utf-8"))
    assert controls["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    assert controls["difficulty"]["4"]["parameters"] == {
        "rule_family": "xor2", "feature_pool": 5, "probe_count": 4,
        "probe_bank_count": 7, "final_count": 6, "nuisance_strength": 0.5,
    }
    assert [controls["difficulty"][str(level)]["parameters"]["rule_family"] for level in range(1, 6)] == [
        "literal", "literal", "and2", "xor2", "paired4",
    ]
    assert all(
        controls["difficulty"][str(level)]["parameters"]["probe_bank_count"]
        > controls["difficulty"][str(level)]["parameters"]["probe_count"]
        for level in range(1, 6)
    )
    assert controls["interaction"]["simplified"]["implemented"] is True
    assert controls["interaction"]["full"]["implemented"] is True
    assert controls["real_time"] == {"play_time_seconds": 180, "observation_window_ms": 0, "frames_per_observation": 1}
    assert env["runner_options"] == controls["real_time"]
    assert task["metadata"]["source_anchors"] == ["COG-027", "BGAM-659"]
    assert task["metadata"]["status"] == "prototype_visual_candidate"
    assert task["difficulty"] == "hard"
    assert len(split["variations_tasks"]) == 20


def test_final_trays_cover_the_profile_boundary_cases() -> None:
    expected = {
        1: Counter({(0,): 2, (1,): 2}),
        2: Counter({(0,): 2, (1,): 2}),
        3: Counter({(0, 0): 1, (0, 1): 1, (1, 0): 1, (1, 1): 2}),
        4: Counter({(0, 0): 2, (0, 1): 2, (1, 0): 1, (1, 1): 1}),
    }
    for level in range(1, 6):
        _public, truth = GENERATOR.generate(_task(level, "full"), f"final-boundaries-{level}")
        rule = truth["rule"]
        normalized = Counter(
            tuple(bool(item["features"][index]) ^ invert for index, invert in zip(rule["indices"], rule["invert"]))
            for item in truth["final_specimens"]
        )
        if level < 5:
            assert normalized == expected[level]
        else:
            assert len(normalized) == 8
            assert {GENERATOR.evaluate_rule(item["features"], rule) for item in truth["final_specimens"]} == {False, True}


def test_exported_task_verifier_replays_the_server_result(tmp_path: Path) -> None:
    public, truth = GENERATOR.generate(_task(4, "full"), "exported-verifier")
    result = _solution(public, truth, "full")
    result["server_grade"] = GRADER.grade(result, truth, public)
    exported = tmp_path / "task_result.json"
    exported.write_text(json.dumps({"result": result, "ground_truth": truth, "public_state": public}), encoding="utf-8")

    def copy_from_env(source: str, destination: str) -> None:
        assert source == "/tmp/task_result.json"
        shutil.copyfile(exported, destination)

    decision = VERIFIER.verify_task(env_info={"copy_from_env": copy_from_env})
    assert decision["passed"] is True
    assert decision["score"] == 100
