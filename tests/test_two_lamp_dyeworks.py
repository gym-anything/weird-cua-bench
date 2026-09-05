from __future__ import annotations

import copy
import importlib.util
import itertools
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "weird_captcha_gym" / "environments" / "two_lamp_dyeworks_env"
GENERATOR_PATH = ROOT / "weird_captcha_gym" / "shared_scripts" / "incubator_generators" / "two_lamp_dyeworks.py"
GRADER_PATH = ROOT / "weird_captcha_gym" / "shared_runtime" / "server" / "incubator_graders" / "two_lamp_dyeworks.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("two_lamp_dyeworks_generator_test", GENERATOR_PATH)
GRADER = _load("two_lamp_dyeworks_grader_test", GRADER_PATH)


def _task(level: int, interaction: str, real_time: str = "live") -> dict:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/two_lamp_dyeworks_seed_0001/task.json").read_text(encoding="utf-8"))
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
        "pigments": public["pigments"],
        "target": public["target"],
        "spectral_model": public["spectral_model"],
        "parameters": public["parameters"],
        "initial_lamp": public["initial_lamp"],
    }


def _strip_gesture(*, end_x: float = 892.44, end_y: float = 516.0) -> dict:
    opening_left = 815.0
    opening_top = 458.0
    opening_width = 242.0
    opening_height = 116.0
    inset = 12.0
    radius_x = opening_width / 2 - inset
    radius_y = opening_height / 2 - inset
    center_x = opening_left + opening_width / 2
    center_y = opening_top + opening_height / 2
    normalized_x = (end_x - center_x) / radius_x
    normalized_y = (end_y - center_y) / radius_y
    return {
        "travel_px": 260.0,
        "sample_count": 8,
        "target_region": "vat_opening_inner_ellipse_v1",
        "start_x": 1135.0,
        "start_y": 516.0,
        "end_x": end_x,
        "end_y": end_y,
        "opening_left": opening_left,
        "opening_top": opening_top,
        "opening_width": opening_width,
        "opening_height": opening_height,
        "opening_inset_px": inset,
        "endpoint_normalized_x": round(normalized_x, 5),
        "endpoint_normalized_y": round(normalized_y, 5),
        "endpoint_ellipse_value": round(normalized_x * normalized_x + normalized_y * normalized_y, 5),
    }


def _solution_for_recipe(public: dict, truth: dict, interaction: str, recipe: dict[str, int]) -> dict:
    events = []
    maximum = int(truth["parameters"]["maximum_units_per_pigment"])
    vat = 1
    for pigment_id in truth["pigment_ids"]:
        units = int(recipe[pigment_id])
        if units <= 0:
            continue
        event = {
            "sequence": len(events) + 1,
            "type": "dose",
            "vat": vat,
            "pigment": pigment_id,
            "units": units,
            "input_source": "plunger_drag" if interaction == "full" else "dose_buttons",
        }
        if interaction == "full":
            event["gesture"] = {
                "travel_px": 34.0 + 24.0 * units,
                "sample_count": 7,
                "start_ratio": 0,
                "end_ratio": units / maximum,
            }
        events.append(event)
    stir = {
        "sequence": len(events) + 1,
        "type": "stir",
        "vat": vat,
        "input_source": "stir_gesture" if interaction == "full" else "stir_button",
    }
    if interaction == "full":
        stir["gesture"] = {"angular_sweep_rad": 6.25, "travel_px": 318.0, "sample_count": 21}
    events.append(stir)
    dip = {
        "sequence": len(events) + 1,
        "type": "dip",
        "vat": vat,
        "input_source": "strip_drag" if interaction == "full" else "dip_button",
    }
    if interaction == "full":
        dip["gesture"] = _strip_gesture()
    events.append(dip)
    events.append({"sequence": len(events) + 1, "type": "lamp", "vat": vat, "illuminant": "sodium", "input_source": "lamp_switch"})
    events.append({"sequence": len(events) + 1, "type": "certify", "vat": vat, "input_source": "certify_button"})
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "events": events,
        "final_composition": recipe,
        "vat_index": 1,
        "vats_consumed": 1,
        "total_dispensed": sum(recipe.values()),
        "lamp": "sodium",
        "completed": True,
    }


def _solution(public: dict, truth: dict, interaction: str) -> dict:
    recipe = {pigment_id: 0 for pigment_id in truth["pigment_ids"]}
    for dose in truth["canonical_plan"]:
        recipe[dose["pigment"]] += int(dose["units"])
    return _solution_for_recipe(public, truth, interaction, recipe)


def test_all_ten_control_conditions_generate_same_world_and_grade() -> None:
    for level in range(1, 6):
        worlds = []
        for interaction in ("simplified", "full"):
            public, truth = GENERATOR.generate(_task(level, interaction), f"dyeworks-d{level}")
            decision = GRADER.grade(_solution(public, truth, interaction), truth, public)
            assert decision["passed"] is True, (level, interaction, decision)
            worlds.append(_world(public))
        assert worlds[0] == worlds[1]


def test_generated_targets_are_reachable_across_fresh_seeds() -> None:
    for level in range(1, 6):
        for seed_index in range(8):
            public, truth = GENERATOR.generate(_task(level, "full"), f"reach-{level}-{seed_index}")
            decision = GRADER.grade(_solution(public, truth, "full"), truth, public)
            assert decision["passed"] is True, (level, seed_index, decision)


def test_live_and_paused_preserve_the_dye_problem() -> None:
    live, _ = GENERATOR.generate(_task(4, "full", "live"), "same-clock-world")
    paused, _ = GENERATOR.generate(_task(4, "full", "paused"), "same-clock-world")
    assert _world(live) == _world(paused)
    assert live["control_condition"]["real_time"] == "live"
    assert paused["control_condition"]["real_time"] == "paused"


def test_baseline_and_source_contract_are_fixed() -> None:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    env = json.loads((ENV / "env.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/two_lamp_dyeworks_seed_0001/task.json").read_text(encoding="utf-8"))
    split = json.loads((ROOT / "weird_captcha_gym/splits/two_lamp_dyeworks_split.json").read_text(encoding="utf-8"))
    assert controls["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    assert controls["difficulty"]["4"]["parameters"] == {
        "pigment_count": 4, "target_components_min": 3, "target_components_max": 4,
        "target_total_min": 8, "target_total_max": 11, "maximum_units_per_pigment": 5,
        "vat_capacity_units": 13, "fresh_vats": 3, "tolerance_delta_e": 4.2,
        "metamer_daylight_max_de": 4.2, "metamer_sodium_min_de": 8.0,
        "graduation_support": "numbered",
    }
    assert env["runner_options"] == {"observation_window_ms": 0, "frames_per_observation": 1, "play_time_seconds": 180}
    assert task["metadata"]["source_anchors"] == ["BGUI-125", "BGUI-126", "BGUI-150"]
    assert task["metadata"]["status"] == "prototype_visual_candidate"
    assert len(split["variations_tasks"]) == 20


def test_hard_profiles_construct_a_cross_lamp_near_metamer() -> None:
    for level in (4, 5):
        public, truth = GENERATOR.generate(_task(level, "full"), f"near-metamer-{level}")
        decoy = truth["near_metamer"]
        assert decoy is not None
        assert decoy["daylight_delta_e"] <= float(public["parameters"]["metamer_daylight_max_de"])
        assert decoy["sodium_delta_e"] >= float(public["parameters"]["metamer_sodium_min_de"])
        recipe = decoy["recipe"]
        assert int(public["parameters"]["target_components_min"]) <= sum(units > 0 for units in recipe.values()) <= int(public["parameters"]["target_components_max"])
        assert int(public["parameters"]["target_total_min"]) <= sum(recipe.values()) <= int(public["parameters"]["target_total_max"])


def test_full_grade_accepted_surface_obeys_the_visible_lot_spec() -> None:
    for level in range(1, 6):
        for seed_index in range(20):
            public, truth = GENERATOR.generate(_task(level, "full"), f"accepted-surface-{level}-{seed_index}")
            pigment_ids = list(truth["pigment_ids"])
            parameters = truth["parameters"]
            maximum = int(parameters["maximum_units_per_pigment"])
            capacity = int(parameters["vat_capacity_units"])
            tolerance = float(parameters["tolerance_delta_e"])
            colour_matches = 0
            for vector in itertools.product(range(maximum + 1), repeat=len(pigment_ids)):
                if not 0 < sum(vector) <= capacity:
                    continue
                recipe = dict(zip(pigment_ids, vector, strict=True))
                reflectance = GRADER._reflectance(recipe, pigment_ids)
                sample_labs = {
                    illuminant: GRADER._lab(reflectance, illuminant)
                    for illuminant in GRADER.ILLUMINANTS
                }
                if not all(
                    GRADER._delta_e(sample_labs[illuminant], truth["target_lab"][illuminant]) <= tolerance
                    for illuminant in GRADER.ILLUMINANTS
                ):
                    continue
                colour_matches += 1
                component_count = sum(units > 0 for units in vector)
                total_units = sum(vector)
                within_visible_spec = (
                    int(parameters["target_components_min"]) <= component_count <= int(parameters["target_components_max"])
                    and int(parameters["target_total_min"]) <= total_units <= int(parameters["target_total_max"])
                )
                decision = GRADER.grade(_solution_for_recipe(public, truth, "full", recipe), truth, public)
                assert decision["passed"] is within_visible_spec, (
                    level,
                    seed_index,
                    recipe,
                    decision,
                )
                if not within_visible_spec:
                    assert "lot specification" in decision["feedback"]
            assert colour_matches > 0


def test_reported_shortcuts_are_rejected_without_changing_their_targets() -> None:
    public, truth = GENERATOR.generate(_task(3, "full"), "audit-accepted-surface-2")
    assert truth["target_recipe"] == {"woad": 1, "madder": 1, "weld": 5}
    shortcut = {pigment_id: 0 for pigment_id in truth["pigment_ids"]}
    shortcut["weld"] = 5
    decision = GRADER.grade(_solution_for_recipe(public, truth, "full", shortcut), truth, public)
    assert decision["passed"] is False
    assert "requires 3–3 active dye families" in decision["feedback"]

    public, truth = GENERATOR.generate(_task(4, "full"), "audit-accepted-surface-0")
    assert truth["target_recipe"] == {"madder": 4, "weld": 1, "logwood": 1, "woad": 4}
    shortcut = {pigment_id: 0 for pigment_id in truth["pigment_ids"]}
    shortcut.update({"madder": 5, "woad": 5})
    decision = GRADER.grade(_solution_for_recipe(public, truth, "full", shortcut), truth, public)
    assert decision["passed"] is False
    assert "requires 3–4 active dye families" in decision["feedback"]


def test_profiles_change_dimensions_information_and_recovery() -> None:
    easy, _ = GENERATOR.generate(_task(1, "full"), "profile-structure")
    baseline, _ = GENERATOR.generate(_task(4, "full"), "profile-structure")
    hardest, _ = GENERATOR.generate(_task(5, "full"), "profile-structure")
    assert len(easy["pigments"]) == 2
    assert len(baseline["pigments"]) == len(hardest["pigments"]) == 4
    assert easy["parameters"]["fresh_vats"] == 5
    assert baseline["parameters"]["fresh_vats"] == 3
    assert hardest["parameters"]["fresh_vats"] == 2
    assert easy["parameters"]["graduation_support"] == "numbered"
    assert hardest["parameters"]["graduation_support"] == "sparse"
    assert easy["parameters"]["tolerance_delta_e"] > baseline["parameters"]["tolerance_delta_e"] > hardest["parameters"]["tolerance_delta_e"]


def test_wrong_interaction_stale_identity_and_forged_spectral_state_are_rejected() -> None:
    public, truth = GENERATOR.generate(_task(4, "full"), "negative-contract")
    payload = _solution(public, truth, "full")
    payload["events"][0]["input_source"] = "dose_buttons"
    assert GRADER.grade(payload, truth, public)["passed"] is False
    payload = _solution(public, truth, "full")
    payload["challenge_id"] = "stale"
    assert GRADER.grade(payload, truth, public)["passed"] is False
    payload = _solution(public, truth, "full")
    payload["final_composition"][truth["pigment_ids"][0]] += 1
    assert GRADER.grade(payload, truth, public)["passed"] is False
    forged_public = copy.deepcopy(public)
    forged_public["target"]["lab"]["daylight"][0] += 5
    assert GRADER.grade(_solution(public, truth, "full"), truth, forged_public)["passed"] is False


def test_full_strip_drop_requires_a_consistent_endpoint_inside_the_visible_opening() -> None:
    public, truth = GENERATOR.generate(_task(4, "full"), "strip-geometry-contract")
    valid = _solution(public, truth, "full")
    dip_index = next(index for index, event in enumerate(valid["events"]) if event["type"] == "dip")
    assert GRADER.grade(valid, truth, public)["passed"] is True

    missing = copy.deepcopy(valid)
    missing["events"][dip_index]["gesture"] = {"travel_px": 260.0, "sample_count": 8}
    decision = GRADER.grade(missing, truth, public)
    assert decision["passed"] is False
    assert "visible vat opening" in decision["feedback"]

    for label, point in {
        "vat_label": (936.0, 621.0),
        "stirrer_handle_below_rim": (950.0, 610.0),
        "lower_housing": (790.0, 600.0),
        "near_edge_miss": (1047.0, 516.0),
    }.items():
        invalid = copy.deepcopy(valid)
        invalid["events"][dip_index]["gesture"] = _strip_gesture(end_x=point[0], end_y=point[1])
        decision = GRADER.grade(invalid, truth, public)
        assert decision["passed"] is False, label
        assert "outside the visible vat opening" in decision["feedback"], (label, decision)


def test_full_strip_drop_rejects_forged_or_impossible_geometry_witnesses() -> None:
    public, truth = GENERATOR.generate(_task(4, "full"), "strip-geometry-forgery")
    payload = _solution(public, truth, "full")
    dip = next(event for event in payload["events"] if event["type"] == "dip")

    forged_endpoint = copy.deepcopy(payload)
    forged_dip = next(event for event in forged_endpoint["events"] if event["type"] == "dip")
    forged_dip["gesture"]["end_x"] += 80
    decision = GRADER.grade(forged_endpoint, truth, public)
    assert decision["passed"] is False
    assert "inconsistent" in decision["feedback"]

    impossible_travel = copy.deepcopy(payload)
    impossible_dip = next(event for event in impossible_travel["events"] if event["type"] == "dip")
    impossible_dip["gesture"]["travel_px"] = 80
    decision = GRADER.grade(impossible_travel, truth, public)
    assert decision["passed"] is False
    assert "shorter than its recorded endpoints" in decision["feedback"]

    started_inside = copy.deepcopy(payload)
    started_dip = next(event for event in started_inside["events"] if event["type"] == "dip")
    started_dip["gesture"]["start_x"] = dip["gesture"]["end_x"]
    started_dip["gesture"]["start_y"] = dip["gesture"]["end_y"]
    decision = GRADER.grade(started_inside, truth, public)
    assert decision["passed"] is False
    assert "begin outside" in decision["feedback"]


def test_vat_exhaustion_is_a_terminal_failure_not_a_pass() -> None:
    public, truth = GENERATOR.generate(_task(4, "simplified"), "exhaustion")
    events = []
    for vat in range(1, int(truth["parameters"]["fresh_vats"]) + 1):
        events.append({"sequence": len(events) + 1, "type": "dump", "vat": vat, "input_source": "dump_valve"})
    payload = {
        "mechanic_id": public["mechanic_id"], "task_id": public["task_id"], "challenge_id": public["challenge_id"],
        "events": events, "final_composition": {pigment_id: 0 for pigment_id in truth["pigment_ids"]},
        "vat_index": int(truth["parameters"]["fresh_vats"]), "vats_consumed": int(truth["parameters"]["fresh_vats"]),
        "total_dispensed": 0, "lamp": "daylight", "completed": False,
    }
    decision = GRADER.grade(payload, truth, public)
    assert decision["passed"] is False
    assert "vats" in decision["feedback"]


def test_browser_does_not_reveal_hidden_tolerance_before_certification() -> None:
    renderer = (ROOT / "weird_captcha_gym/shared_runtime/app/mechanics/two_lamp_dyeworks.js").read_text(encoding="utf-8")
    styles = (ROOT / "weird_captcha_gym/shared_runtime/app/mechanics/two_lamp_dyeworks.css").read_text(encoding="utf-8")
    assert "BOTH LAMPS AGREE" not in renderer
    assert 'certification.classList.toggle("is-ready", model.ready)' not in renderer
    assert ".dye-certify.is-ready" not in styles
    assert "BOTH LAMPS VIEWED · TEST OR ADJUST" in renderer
    assert "SEALED LOT SPEC" in renderer
    assert "recipeWithinSpec()" in renderer
    assert "LOT SPEC MISSED" in renderer


def test_every_task_instruction_has_the_complete_visible_ui_only_boundary() -> None:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/two_lamp_dyeworks_seed_0001/task.json").read_text(encoding="utf-8"))
    instructions = [task["description"], task["natural_language"]]
    instructions.extend(profile["natural_language"] for profile in controls["difficulty"].values())
    required = (
        "Solve only from screenshots and visible controls in the task webpage",
        "Developer Tools",
        "terminal/shell/Python",
        "address-bar or URL/query edits",
        "pre-existing, unrelated, blank, browser-settings, or non-task tab",
        "A tab opened by a visible task control is allowed only when it is part of the task",
    )
    assert all(all(fragment in instruction for fragment in required) for instruction in instructions)
    assert task["metadata"]["capabilities"] == [
        "visual_understanding_2d",
        "reasoning_and_planning",
        "exploration_and_interface_understanding",
    ]
