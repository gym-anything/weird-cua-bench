from __future__ import annotations

import copy
import importlib.util
import json
import math
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
MECHANIC = "apothecary_dead_reckoning"
ENV = BENCHMARK / "environments" / f"{MECHANIC}_env"
TASK_PATH = ENV / "tasks" / f"{MECHANIC}_seed_0001" / "task.json"
CONTROLS_PATH = ENV / "controls.json"
GENERATOR_PATH = BENCHMARK / "shared_scripts" / "incubator_generators" / f"{MECHANIC}.py"
GRADER_PATH = BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{MECHANIC}.py"
FRONTEND_PATH = BENCHMARK / "shared_runtime" / "app" / "mechanics" / f"{MECHANIC}.js"
SOLVER_PATH = BENCHMARK / "tools" / "incubator_solvers" / f"{MECHANIC}.py"
MATERIALIZER_PATH = BENCHMARK / "tools" / "materialize_controlled_tasks.py"


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _module("apothecary_generator_test", GENERATOR_PATH)
GRADER = _module("apothecary_grader_test", GRADER_PATH)
MATERIALIZER = _module("apothecary_materializer_test", MATERIALIZER_PATH)
TASK = json.loads(TASK_PATH.read_text(encoding="utf-8"))
CONTROLS = json.loads(CONTROLS_PATH.read_text(encoding="utf-8"))


def _task(level: int, interaction: str) -> dict:
    task = copy.deepcopy(TASK)
    profile = CONTROLS["difficulty"][str(level)]
    task["natural_language"] = profile["natural_language"]
    task["_control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": "live",
        "difficulty_parameters": copy.deepcopy(profile["parameters"]),
    }
    return task


def _center(rect: list[float]) -> list[float]:
    return [round(rect[0] + rect[2] / 2, 6), round(rect[1] + rect[3] / 2, 6)]


def _payload(public: dict, truth: dict, *, exercise_recovery: bool = False) -> dict:
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    parameters = truth["parameters"]
    mechanics = truth["mechanics"]
    ingredients = {ingredient["id"]: ingredient for ingredient in truth["ingredients"]}
    position = [float(item) for item in truth["origin"]]
    heading = 0.0
    sequence = 0
    events: list[dict] = []
    contacted_bones: set[str] = set()
    contacted_vortices: set[str] = set()
    ingredient_spend = water_spend = bellows_spend = route_progress = 0

    def emit(kind: str, **details) -> None:
        nonlocal sequence
        sequence += 1
        events.append({"sequence": sequence, "type": kind, **details})

    def commit_path(commit: dict, *, passes_ring: bool) -> None:
        nonlocal position, heading, ingredient_spend, route_progress
        ingredient_id = str(commit["ingredient_id"])
        grind_step = int(commit["grind_step"])
        if interaction == "full":
            geometry = truth["interaction_geometry"]
            emit(
                "load_ingredient",
                ingredient_id=ingredient_id,
                input_source="jar_drag",
                gesture={
                    "start_root": _center(geometry["jar_rects"][ingredient_id]),
                    "end_root": _center(geometry["mortar_rect"]),
                    "travel_px": 245.0,
                    "sample_count": 12,
                },
            )
            emit("grind_start", grind_step=0, input_source="pestle_hold")
            for step in range(1, grind_step + 1):
                emit("grind_tick", grind_step=step, input_source="pestle_hold")
            emit("grind_release", grind_step=grind_step, input_source="pestle_hold")
        else:
            emit("load_ingredient", ingredient_id=ingredient_id, input_source="jar_select")
            emit("grind_set", grind_step=grind_step, input_source="curve_notches")

        path = GRADER._path_points(
            position,
            ingredients[ingredient_id],
            grind_step,
            int(parameters["grind_notches"]),
            int(mechanics["path_samples"]),
        )
        path_index = 0
        while path_index < len(path) - 1:
            before = position[:]
            before_index = path_index
            next_index = min(len(path) - 1, path_index + int(mechanics["stir_stride"]))
            segment = [position[:], *path[path_index + 1 : next_index + 1]]
            destination, new_bones, vortex_id, vortex_spin = GRADER._resolve_motion(
                segment,
                truth["bones"],
                truth["vortices"],
                contacted_bones,
                contacted_vortices,
            )
            position = destination
            heading = GRADER._heading(
                ingredients[ingredient_id],
                grind_step,
                int(parameters["grind_notches"]),
                next_index,
                int(mechanics["path_samples"]),
            )
            path_index = next_index
            finished = path_index == len(path) - 1 or vortex_id is not None
            if vortex_id is not None:
                heading = (heading + vortex_spin * float(mechanics["vortex_turn_degrees"])) % 360
            emit("stir", **{
                "ingredient_id": ingredient_id,
                "grind_step": grind_step,
                "path_index_before": before_index,
                "path_index_after": path_index,
                "from": [round(value, 4) for value in before],
                "to": [round(value, 4) for value in position],
                "contact_ids": new_bones,
                "vortex_id": vortex_id,
                "path_finished": finished,
                "input_source": "ladle_click",
            })
            if finished:
                break
        ingredient_spend += 1
        if passes_ring and vortex_id is None:
            route_progress += 1

    if exercise_recovery:
        probe = truth["recovery_probe"]
        commit_path(probe, passes_ring=False)
        if probe.get("expected_vortex_id"):
            assert probe["expected_vortex_id"] in contacted_vortices
        while math.dist(position, truth["origin"]) > .001:
            before = position[:]
            dx = float(truth["origin"][0]) - position[0]
            dy = float(truth["origin"][1]) - position[1]
            distance = math.hypot(dx, dy)
            step = min(distance, float(parameters["water_step"]))
            raw = [position[0] + dx / distance * step, position[1] + dy / distance * step]
            heading = math.degrees(math.atan2(dy, dx)) % 360
            motion = GRADER._line(position, raw)
            position, new_bones, vortex_id, vortex_spin = GRADER._resolve_motion(
                motion,
                truth["bones"],
                truth["vortices"],
                contacted_bones,
                contacted_vortices,
            )
            if vortex_id is not None:
                heading = (heading + vortex_spin * float(mechanics["vortex_turn_degrees"])) % 360
            water_spend += 1
            emit("water", **{
                "from": [round(value, 4) for value in before],
                "to": [round(value, 4) for value in position],
                "contact_ids": new_bones,
                "vortex_id": vortex_id,
                "input_source": "water_button",
            })
        assert water_spend <= int(parameters["water_budget"])

    for commit in truth["solution"]:
        commit_path(commit, passes_ring=True)

    target = next(effect for effect in truth["effects"] if effect["id"] == truth["target_effect_id"])
    assert math.dist(position, target["center"]) < .1
    emit(
        "seal",
        position=[round(value, 4) for value in position],
        effect_id=truth["target_effect_id"],
        input_source="seal_button",
    )
    return {
        "mechanic_id": MECHANIC,
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "events": events,
        "final_position": [round(value, 3) for value in position],
        "heading_deg": round(heading, 3),
        "ingredient_spend": ingredient_spend,
        "water_spend": water_spend,
        "bellows_spend": bellows_spend,
        "hazard_contacts": sorted(contacted_bones),
        "vortex_contacts": sorted(contacted_vortices),
        "sealed_effect_id": truth["target_effect_id"],
        "seal_count": 1,
        "route_progress": route_progress,
        "completed": True,
    }


def test_all_levels_and_interactions_are_deterministic_solvable_and_world_paired() -> None:
    world_keys = (
        "stage", "origin", "ingredients", "effects", "route_gates", "bones", "vortices",
        "parameters", "mechanics", "interaction_geometry", "order",
    )
    for level in range(1, 6):
        worlds = {}
        for interaction in ("simplified", "full"):
            task = _task(level, interaction)
            public, truth = GENERATOR.generate(task, f"matrix-{level}")
            repeated = GENERATOR.generate(task, f"matrix-{level}")
            assert (public, truth) == repeated
            assert "solution" not in public and "solution_trace" not in public
            assert public["challenge_id"] == truth["challenge_id"]
            assert len(truth["solution"]) == truth["parameters"]["route_commits"]
            assert len(public["route_gates"]) == truth["parameters"]["route_commits"]
            result = GRADER.grade(_payload(public, truth), truth, public)
            assert result["passed"] is True, (level, interaction, result)
            worlds[interaction] = {key: public[key] for key in world_keys}
        assert worlds["simplified"] == worlds["full"]


def test_every_visible_route_ring_uniquely_identifies_one_ingredient_and_notch() -> None:
    for level in range(1, 6):
        step_counts: Counter[int] = Counter()
        sequences: set[tuple[int, ...]] = set()
        for seed_index in range(40):
            task = _task(level, "full")
            _public, truth = GENERATOR.generate(task, f"ring-uniqueness-{seed_index}")
            position = truth["origin"][:]
            ingredients = {ingredient["id"]: ingredient for ingredient in truth["ingredients"]}
            for expected, gate in zip(truth["solution"], truth["route_gates"]):
                matches = GENERATOR.gate_matching_choices(
                    position,
                    truth["ingredients"],
                    int(truth["parameters"]["grind_notches"]),
                    gate,
                )
                assert matches == [expected], (level, seed_index, expected, matches)
                position = GENERATOR.path_points(
                    position,
                    ingredients[expected["ingredient_id"]],
                    int(expected["grind_step"]),
                    int(truth["parameters"]["grind_notches"]),
                )[-1]
            steps = tuple(int(item["grind_step"]) for item in truth["solution"])
            assert len(set(steps)) == len(steps)
            sequences.add(steps)
            step_counts.update(steps)
        assert max(step_counts.values()) / sum(step_counts.values()) < .4
        assert len(sequences) >= (10 if level == 1 else 30)


def test_original_baseline_is_full_level_two_and_solvable_without_control_metadata() -> None:
    public, truth = GENERATOR.generate(copy.deepcopy(TASK), "baseline-contract")
    assert "control_condition" not in public
    assert CONTROLS["baseline"] == {"difficulty": 2, "interaction": "full", "real_time": "live"}
    assert truth["parameters"] == CONTROLS["difficulty"]["2"]["parameters"]
    assert GRADER.grade(_payload(public, truth), truth, public)["passed"] is True


def test_grader_rejects_stale_identity_wrong_surface_and_forged_geometry() -> None:
    public, truth = GENERATOR.generate(_task(2, "full"), "tamper-contract")
    valid = _payload(public, truth)
    probed = copy.deepcopy(valid)
    first_load = next(event for event in probed["events"] if event["type"] == "load_ingredient")
    decoy_id = next(item["id"] for item in truth["ingredients"] if item["id"] != first_load["ingredient_id"])
    geometry = truth["interaction_geometry"]
    probed["events"].insert(0, {
        "sequence": 1,
        "type": "load_ingredient",
        "ingredient_id": decoy_id,
        "input_source": "jar_drag",
        "gesture": {
            "start_root": _center(geometry["jar_rects"][decoy_id]),
            "end_root": _center(geometry["mortar_rect"]),
            "travel_px": 245.0,
            "sample_count": 12,
        },
    })
    first_load["type"] = "replace_ingredient"
    first_load["previous_ingredient_id"] = decoy_id
    for sequence, event in enumerate(probed["events"], start=1):
        event["sequence"] = sequence
    assert GRADER.grade(probed, truth, public)["passed"] is True

    recovered = _payload(public, truth, exercise_recovery=True)
    recovered_result = GRADER.grade(recovered, truth, public)
    assert recovered_result["passed"] is True, recovered_result
    assert recovered_result["metrics"]["route_progress"] == len(truth["route_gates"])
    assert recovered_result["metrics"]["vortex_contact_count"] == 1
    assert recovered_result["metrics"]["water_spend"] > 0

    forged_progress = copy.deepcopy(valid)
    forged_progress["route_progress"] -= 1
    assert "submitted route_progress" in GRADER.grade(
        forged_progress, truth, public
    )["feedback"]

    stale = copy.deepcopy(valid)
    stale["challenge_id"] = "stale"
    assert GRADER.grade(stale, truth, public)["passed"] is False

    wrong_surface = copy.deepcopy(valid)
    wrong_load = next(event for event in wrong_surface["events"] if event["type"] == "load_ingredient")
    wrong_load["input_source"] = "jar_select"
    assert "wrong interaction surface" in GRADER.grade(wrong_surface, truth, public)["feedback"]

    forged = copy.deepcopy(valid)
    first_stir = next(event for event in forged["events"] if event["type"] == "stir")
    first_stir["to"][0] += 18
    assert "geometry" in GRADER.grade(forged, truth, public)["feedback"]

    altered_public = copy.deepcopy(public)
    altered_public["order"]["glyph"] = "forged"
    assert "public and hidden order disagree" in GRADER.grade(valid, truth, altered_public)["feedback"]

    misaligned_truth = copy.deepcopy(truth)
    misaligned_public = copy.deepcopy(public)
    misaligned_truth["route_gates"][0]["heading_deg"] += 11
    misaligned_public["route_gates"][0]["heading_deg"] += 11
    assert "does not uniquely identify" in GRADER.grade(
        valid, misaligned_truth, misaligned_public
    )["feedback"]


def test_visible_input_surfaces_and_solver_do_not_mutate_private_state() -> None:
    frontend = FRONTEND_PATH.read_text(encoding="utf-8")
    solver = SOLVER_PATH.read_text(encoding="utf-8")
    assert 'addEventListener("pointerdown", startGrinding)' in frontend
    assert 'input_source: "pestle_hold"' in frontend
    assert 'input_source: "curve_notches"' in frontend
    assert 'loadIngredient(drag.ingredientId, "jar_drag"' in frontend
    assert 'loadIngredient(jar.dataset.ingredientId, "jar_select"' in frontend
    assert 'record(replacing ? "replace_ingredient" : "load_ingredient"' in frontend
    assert "function currentRouteGate()" in frontend
    assert "model?.state.route_gates?.[model.routeProgress]" in frontend
    assert "dataset.previewAligned" not in frontend
    assert "LOCKED" not in frontend
    assert "DO NOT MATCH" not in frontend
    assert "model.routeProgress" in frontend
    assert '"post_commit_only"' in GENERATOR_PATH.read_text(encoding="utf-8")
    assert "gate_heading_tolerance_degrees" in frontend
    assert "model.state.route_gates.forEach" not in frontend
    assert "page.mouse.down()" in solver and "page.mouse.up()" in solver
    assert "apothecaryDeadReckoningModel.position =" not in solver


def test_visible_surface_has_no_tutorial_or_partial_correctness_copy() -> None:
    frontend = FRONTEND_PATH.read_text(encoding="utf-8")
    forbidden = (
        "THREAD THE CENTER BEAD",
        "JUDGE THE CURVE",
        "JUDGE THE TRACE",
        "CHOOSE THE NEXT VECTOR",
        "OFF ROUTE",
        "CURRENT RING REMAINS",
        "USE WATER TO RECOVER",
        "VORTEX DISPLACED",
        "BONE SPUR CONTACT",
        "ANSWER SHOWN",
        "FRESH MAP ISSUED",
        "FOG WAKE",
        "BREW REJECTED",
        "VERIFIER OFFLINE",
        "THE JAR MISSED",
    )
    assert all(phrase not in frontend for phrase in forbidden)
    assert "state.challenge_id.toUpperCase()" not in frontend
    assert "context.fillText(String(index + 1)" not in frontend
    assert '<strong>${options.freshFailure ? "FAIL" : ""}</strong>' in frontend
    assert 'textContent = "PASS"' in frontend

    policy = (
        "Brew the ordered sigil. Solve only from screenshots and visible controls "
        "in the task webpage. Programs in an isolated agent sandbox may process screenshots "
        "and issue mouse and keyboard actions through the provided gateway. Do not access "
        "the task environment through Developer Tools, console, debugger, inspector, network "
        "or source inspection, DOM or page-state inspection, the task terminal or shell, "
        "address-bar or URL/query edits, reload/navigation, browser extensions, external "
        "applications, hidden state, or unrelated tabs."
    )
    assert TASK["description"] == policy
    assert TASK["natural_language"] == policy
    assert all(profile["natural_language"] == policy for profile in CONTROLS["difficulty"].values())
    assert all(
        value == policy
        for profile in CONTROLS["difficulty"].values()
        for value in (profile.get("natural_language_by_interaction") or {}).values()
    )


def test_materialized_capabilities_are_interaction_specific() -> None:
    mapping = TASK["metadata"]["capabilities_by_interaction"]
    temporal = "temporal understanding and memory"
    assert temporal in mapping["full"]
    assert temporal not in mapping["simplified"]
    assert temporal not in TASK["metadata"]["capabilities"]
    assert CONTROLS["interaction"]["full"]["capabilities"] == mapping["full"]
    assert CONTROLS["interaction"]["simplified"]["capabilities"] == mapping["simplified"]

    for interaction in ("full", "simplified"):
        materialized = MATERIALIZER.controlled_task(
            TASK,
            mechanic_id=MECHANIC,
            level=2,
            interaction=interaction,
            profile=CONTROLS["difficulty"]["2"],
            task_dir_name=f"{MECHANIC}_d2_{interaction}_seed_0001",
        )
        selected = materialized["metadata"]["control_condition"]["interaction"]
        assert materialized["metadata"]["capabilities_by_interaction"][selected] == mapping[interaction]
        assert (temporal in mapping[interaction]) is (interaction == "full")


def test_reported_l5_failures_and_additional_stress_seeds_generate() -> None:
    seeds = [
        "audit-distribution-41",
        "audit-distribution-106",
        "audit-distribution-303",
        *(f"l5-stress-{index}" for index in range(50)),
    ]
    task = _task(5, "full")
    for seed in seeds:
        public, truth = GENERATOR.generate(task, seed)
        assert len(public["effects"]) == task["_control_condition"]["difficulty_parameters"]["effect_count"]
        assert len(public["bones"]) == task["_control_condition"]["difficulty_parameters"]["bone_count"]
        assert len(truth["solution"]) == task["_control_condition"]["difficulty_parameters"]["route_commits"]
