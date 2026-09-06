from __future__ import annotations

import copy
import importlib.util
import json
import math
from pathlib import Path

from weird_captcha_gym.realtime import load_real_time_settings
from weird_captcha_gym.shared_scripts.setup_task import generate_task_state


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "residual_telescope_env"
BASE_TASK = json.loads((ENVIRONMENT / "tasks" / "residual_telescope_seed_0001" / "task.json").read_text())
CONTROLS = json.loads((ENVIRONMENT / "controls.json").read_text())


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MATERIALIZER = _load("residual_materializer", BENCHMARK / "tools" / "materialize_controlled_tasks.py")
GRADER = _load("residual_grader", BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "residual_telescope.py")


def _task(level: int, interaction: str) -> dict:
    return MATERIALIZER.controlled_task(
        BASE_TASK,
        mechanic_id="residual_telescope",
        level=level,
        interaction=interaction,
        profile=CONTROLS["difficulty"][str(level)],
        task_dir_name=f"residual_telescope_d{level}_{interaction}_seed_0001",
    )


def _without_surface(value: dict) -> dict:
    result = copy.deepcopy(value)
    result.pop("task_id", None)
    result.pop("control_condition", None)
    return result


def _shape_points(truth: dict, component: str) -> list[list[float]]:
    geometry = truth["target_geometry"]
    if component in {"disc", "core"}:
        shape = geometry[component]
        return [shape["center"], [shape["center"][0] + math.cos(shape["angle"]) * shape["radius"], shape["center"][1] + math.sin(shape["angle"]) * shape["radius"]]]
    if component == "bar":
        shape = geometry[component]
        dx = math.cos(shape["angle"]) * shape["length"] / 2
        dy = math.sin(shape["angle"]) * shape["length"] / 2
        return [[shape["center"][0] - dx, shape["center"][1] - dy], [shape["center"][0] + dx, shape["center"][1] + dy]]
    return geometry["arms"][int(component.split("_")[1]) - 1]


def _payload(truth: dict, interaction: str) -> dict:
    events: list[dict] = []
    shape_source = "direct_draw" if interaction == "full" else "proxy_points"
    parameter_source = "direct_slider" if interaction == "full" else "proxy_nudge"
    for component in truth["component_sequence"]:
        events.append({
            "sequence": len(events) + 1,
            "kind": "shape_commit",
            "component": component,
            "input_source": shape_source,
            "points": copy.deepcopy(_shape_points(truth, component)),
        })
    for spec in truth["parameter_specs"]:
        value = int(spec["initial"])
        target = int(truth["target_values"][spec["id"]])
        while value != target:
            value += 1 if target > value else -1
            events.append({
                "sequence": len(events) + 1,
                "kind": "parameter_set",
                "parameter_id": spec["id"],
                "value": value,
                "input_source": parameter_source,
            })
    return {
        "mechanic_id": "residual_telescope",
        "challenge_id": truth["challenge_id"],
        "interaction": interaction,
        "events": events,
        "completed": True,
    }


def test_materializes_all_ten_conditions_and_registers_static_clock(tmp_path: Path) -> None:
    MATERIALIZER.validate_controls(CONTROLS, ENVIRONMENT)
    assert CONTROLS["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    assert CONTROLS["real_time"] == load_real_time_settings("residual_telescope").__dict__
    written = MATERIALIZER.materialize_environment(ENVIRONMENT, tmp_path)
    conditions = {
        (task["metadata"]["control_condition"]["difficulty"], task["metadata"]["control_condition"]["interaction"])
        for task in (json.loads((path / "task.json").read_text()) for path in written)
    }
    assert conditions == {(level, mode) for level in range(1, 6) for mode in ("simplified", "full")}


def test_interaction_modes_preserve_world_and_bind_input_surface() -> None:
    for level in range(1, 6):
        simplified_public, simplified_truth = generate_task_state(_task(level, "simplified"), f"residual-world-{level}")
        full_public, full_truth = generate_task_state(_task(level, "full"), f"residual-world-{level}")
        assert simplified_public["challenge_id"] == full_public["challenge_id"]
        assert _without_surface(simplified_public) == _without_surface(full_public)
        assert _without_surface(simplified_truth) == _without_surface(full_truth)
        simplified_payload = _payload(simplified_truth, "simplified")
        full_payload = _payload(full_truth, "full")
        assert len(simplified_payload["events"]) == len(full_payload["events"])
        assert [event["value"] for event in simplified_payload["events"] if event["kind"] == "parameter_set"] == [event["value"] for event in full_payload["events"] if event["kind"] == "parameter_set"]
        assert GRADER.grade(simplified_payload, simplified_truth, simplified_public)["passed"] is True
        assert GRADER.grade(full_payload, full_truth, full_public)["passed"] is True
        crossed = _payload(full_truth, "full")
        crossed["challenge_id"] = simplified_truth["challenge_id"]
        assert "interaction" in GRADER.grade(crossed, simplified_truth, simplified_public)["feedback"]
        wrong_source = _payload(simplified_truth, "simplified")
        wrong_source["events"][0]["input_source"] = "direct_draw"
        assert "wrong interaction surface" in GRADER.grade(wrong_source, simplified_truth, simplified_public)["feedback"]


def test_difficulty_changes_the_actual_reconstruction_problem() -> None:
    worlds = {}
    for level in range(1, 6):
        public, truth = generate_task_state(_task(level, "full"), "residual-difficulty-comparison")
        profile = CONTROLS["difficulty"][str(level)]["parameters"]
        worlds[level] = truth
        assert len(truth["parameter_specs"]) == profile["parameter_count"]
        assert len(truth["target_geometry"]["arms"]) == profile["arm_count"]
        assert public["move_budget"] == profile["move_budget"]
    assert len(worlds[1]["component_sequence"]) < len(worlds[3]["component_sequence"]) < len(worlds[5]["component_sequence"])
    assert worlds[1]["residual_threshold"] > worlds[4]["residual_threshold"] > worlds[5]["residual_threshold"]
    assert worlds[1]["geometry_tolerance"] > worlds[4]["geometry_tolerance"] > worlds[5]["geometry_tolerance"]


def test_grader_checks_order_geometry_parameters_residual_and_budget() -> None:
    public, truth = generate_task_state(_task(4, "full"), "residual-negative-replays")
    passing = _payload(truth, "full")
    assert GRADER.grade(passing, truth, public)["passed"] is True
    wrong_order = copy.deepcopy(passing)
    wrong_order["events"][0], wrong_order["events"][1] = wrong_order["events"][1], wrong_order["events"][0]
    wrong_order["events"][0]["sequence"], wrong_order["events"][1]["sequence"] = 1, 2
    assert "unlocked order" in GRADER.grade(wrong_order, truth, public)["feedback"]
    bad_geometry = copy.deepcopy(passing)
    bad_geometry["events"][0]["points"][0] = [0, 0]
    assert "disc center" in GRADER.grade(bad_geometry, truth, public)["feedback"]
    bad_parameter = copy.deepcopy(passing)
    final_first_id = next(event for event in bad_parameter["events"] if event["kind"] == "parameter_set")["parameter_id"]
    target = int(truth["target_values"][final_first_id])
    bad_parameter["events"].append({
        "sequence": len(bad_parameter["events"]) + 1,
        "kind": "parameter_set",
        "parameter_id": final_first_id,
        "value": target + 1 if target < 10 else target - 1,
        "input_source": "direct_slider",
    })
    assert "optical parameters" in GRADER.grade(bad_parameter, truth, public)["feedback"]
    skipped_step = copy.deepcopy(passing)
    first_parameter = next(event for event in skipped_step["events"] if event["kind"] == "parameter_set")
    first_parameter["value"] = 8
    assert "exactly one calibrated step" in GRADER.grade(skipped_step, truth, public)["feedback"]
    over_budget = copy.deepcopy(passing)
    while len(over_budget["events"]) <= truth["move_budget"]:
        copied = copy.deepcopy(over_budget["events"][-1])
        copied["sequence"] = len(over_budget["events"]) + 1
        over_budget["events"].append(copied)
    assert "move budget" in GRADER.grade(over_budget, truth, public)["feedback"]


def test_grader_replays_recovery_redraws_as_geometry_replacements() -> None:
    public, truth = generate_task_state(_task(4, "full"), "residual-redraw-replay")
    passing = _payload(truth, "full")
    redraw = copy.deepcopy(passing["events"][0])
    passing["events"].insert(1, redraw)
    for sequence, event in enumerate(passing["events"], start=1):
        event["sequence"] = sequence
    assert GRADER.grade(passing, truth, public)["passed"] is True
    bad_redraw = copy.deepcopy(passing)
    bad_redraw["events"][1]["points"][0] = [0, 0]
    assert "disc center" in GRADER.grade(bad_redraw, truth, public)["feedback"]


def test_browser_contract_uses_real_canvas_geometry_and_distinct_controls() -> None:
    source = (BENCHMARK / "shared_runtime" / "app" / "mechanics" / "residual_telescope.js").read_text()
    assert "direct_draw" in source and "proxy_points" in source
    assert "direct_slider" in source and "proxy_nudge" in source
    assert "pointerdown" in source and "pointermove" in source and "setPointerCapture" in source
    assert "target_pixels" in source and "renderField" in source and "segmentDistance" in source
    assert "geometryForRender" in source and "residual-redraw" in source
    assert "Math.abs(value - model.values[parameterId]) !== 1" in source
    assert 'model.helpers.setReadout("SET"' in source
    forbidden_visible_copy = (
        "Tune every rail",
        "Read the signed residual",
        "NEXT MASK UNLOCKED",
        "MASK SEQUENCE REQUIRED",
        "BEGIN WITH THE DISC",
        "CENTER → RIM",
        "2 POINTS",
        "CERTIFY AGAIN TO RETRY",
        "fresh specimen issued",
    )
    assert all(token not in source for token in forbidden_visible_copy)
    assert "setInterval" not in source and "Date.now" not in source and "requestAnimationFrame" not in source
    export_hook = (
        ENVIRONMENT / "tasks" / "residual_telescope_seed_0001" / "export_result.sh"
    ).read_text()
    assert "/workspace/shared_scripts/export_result.sh" in export_hook
    assert "attempts.jsonl" in export_hook
    assert 'payload["graded_attempts"]' in export_hook
