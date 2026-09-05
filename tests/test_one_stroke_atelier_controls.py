from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

from weird_captcha_gym.realtime import load_real_time_settings
from weird_captcha_gym.shared_scripts.setup_task import generate_task_state


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "one_stroke_atelier_env"
BASE_TASK = json.loads((ENVIRONMENT / "tasks" / "one_stroke_atelier_seed_0001" / "task.json").read_text())
CONTROLS = json.loads((ENVIRONMENT / "controls.json").read_text())


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MATERIALIZER = _load("atelier_materializer", BENCHMARK / "tools" / "materialize_controlled_tasks.py")
GRADER = _load("atelier_grader", BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "one_stroke_atelier.py")
SOLVER = _load("atelier_solver", BENCHMARK / "tools" / "incubator_solvers" / "one_stroke_atelier.py")


def _task(level: int, interaction: str) -> dict:
    return MATERIALIZER.controlled_task(
        BASE_TASK,
        mechanic_id="one_stroke_atelier",
        level=level,
        interaction=interaction,
        profile=CONTROLS["difficulty"][str(level)],
        task_dir_name=f"one_stroke_atelier_d{level}_{interaction}_seed_0001",
    )


def _without_surface(value: dict) -> dict:
    result = copy.deepcopy(value)
    result.pop("task_id", None)
    result.pop("control_condition", None)
    return result


def _gate_key(phase: int, prefix: list[str]) -> str:
    return f"{phase}|{'/'.join(prefix)}"


def _payload(truth: dict, interaction: str) -> dict:
    events: list[dict] = []
    selected: dict[str, str] = {}
    targets = {item["field"]: item["value"] for item in truth["target"]}
    prefix: list[str] = []
    locked_gates: list[dict] = []
    stroke_geometry: list[list[float]] = [copy.deepcopy(truth["start"])]

    def add(kind: str, source: str, **details: object) -> None:
        events.append({"sequence": len(events) + 1, "kind": kind, "input_source": source, **details})

    start_source = "direct_stroke" if interaction == "full" else "proxy_stroke"
    add("stroke_start", start_source, stroke=1, point=truth["start"], path_index=0)
    for phase, field in enumerate(truth["active_fields"]):
        gate = next(item for item in truth["gate_sets"][_gate_key(phase, prefix)] if item["value"] == targets[field])
        details: dict[str, object] = {
            "stroke": 1, "gate_id": gate["id"], "field": field,
            "value": gate["value"], "direction": gate["direction"],
        }
        x, y = gate["center"]
        if gate["orientation"] == "vertical":
            details["before"], details["after"] = ([x - 34, y], [x + 34, y]) if gate["direction"] == "right" else ([x + 34, y], [x - 34, y])
        else:
            details["before"], details["after"] = ([x, y - 34], [x, y + 34]) if gate["direction"] == "down" else ([x, y + 34], [x, y - 34])
        gates = truth["gate_sets"][_gate_key(phase, prefix)]
        route = SOLVER._route_around(stroke_geometry[-1], details["before"], [*locked_gates, *gates], truth["stage"])
        stroke_geometry.extend(copy.deepcopy(route[1:]))
        details["path_segment"] = len(stroke_geometry) - 1
        stroke_geometry.append(details["after"])
        add("gate_cross", "direct_stroke" if interaction == "full" else "proxy_gate", **details)
        selected[field] = gate["value"]
        prefix.append(gate["value"])
        memory = int(truth.get("locked_gate_memory") or 0)
        if memory:
            locked_gates.append(gate)
            locked_gates = locked_gates[-memory:]
    motif_points = truth["motif"]["points"]
    route = SOLVER._route_around(stroke_geometry[-1], motif_points[0], locked_gates, truth["stage"])
    stroke_geometry.extend(copy.deepcopy(route[1:]))
    for index, point in enumerate(motif_points):
        details = {"stroke": 1, "checkpoint": index, "point": point}
        if index == 0:
            details["path_segment"] = len(stroke_geometry) - 2
        else:
            details["path_segment"] = len(stroke_geometry) - 1
            stroke_geometry.append(copy.deepcopy(point))
        add("motif_sample", "direct_stroke" if interaction == "full" else "proxy_motif", **details)
    add("stroke_end", start_source, stroke=1, point=motif_points[-1], complete=True, termination="pointerup" if interaction == "full" else "proxy_end", path_index=len(stroke_geometry) - 1)
    return {
        "mechanic_id": "one_stroke_atelier", "challenge_id": truth["challenge_id"],
        "interaction": interaction, "events": events, "interruptions": [], "route_violations": [], "selected_fields": selected,
        "drawn_geometry": copy.deepcopy(motif_points), "stroke_geometry": stroke_geometry, "stroke_count": 1, "completed": True,
    }


def test_materializes_all_ten_conditions_and_registers_clock(tmp_path: Path) -> None:
    MATERIALIZER.validate_controls(CONTROLS, ENVIRONMENT)
    assert CONTROLS["baseline"] == {"difficulty": 3, "interaction": "full", "real_time": "live"}
    assert CONTROLS["real_time"] == load_real_time_settings("one_stroke_atelier").__dict__
    written = MATERIALIZER.materialize_environment(ENVIRONMENT, tmp_path)
    conditions = {
        (task["metadata"]["control_condition"]["difficulty"], task["metadata"]["control_condition"]["interaction"])
        for task in (json.loads((path / "task.json").read_text()) for path in written)
    }
    assert conditions == {(level, mode) for level in range(1, 6) for mode in ("simplified", "full")}


def test_uncontrolled_original_is_preserved_at_l3_full() -> None:
    original_public, original_truth = generate_task_state(BASE_TASK, "atelier-original-baseline")
    controlled_public, controlled_truth = generate_task_state(_task(3, "full"), "atelier-original-baseline")
    assert _without_surface(original_public) == _without_surface(controlled_public)
    assert _without_surface(original_truth) == _without_surface(controlled_truth)
    assert controlled_truth["parameters"] == CONTROLS["difficulty"]["3"]["parameters"]


def test_interaction_modes_preserve_world_and_grader_binds_surface() -> None:
    for level in range(1, 6):
        simple_public, simple_truth = generate_task_state(_task(level, "simplified"), f"atelier-world-{level}")
        full_public, full_truth = generate_task_state(_task(level, "full"), f"atelier-world-{level}")
        assert simple_public["challenge_id"] == full_public["challenge_id"]
        assert _without_surface(simple_public) == _without_surface(full_public)
        assert _without_surface(simple_truth) == _without_surface(full_truth)
        simple_payload, full_payload = _payload(simple_truth, "simplified"), _payload(full_truth, "full")
        assert GRADER.grade(simple_payload, simple_truth, simple_public)["passed"] is True
        assert GRADER.grade(full_payload, full_truth, full_public)["passed"] is True
        crossed = copy.deepcopy(full_payload)
        crossed["challenge_id"] = simple_truth["challenge_id"]
        assert "interaction" in GRADER.grade(crossed, simple_truth, simple_public)["feedback"]
        wrong_source = copy.deepcopy(simple_payload)
        wrong_source["events"][1]["input_source"] = "direct_stroke"
        assert "wrong interaction" in GRADER.grade(wrong_source, simple_truth, simple_public)["feedback"]


def test_difficulty_changes_the_decision_and_control_problem() -> None:
    worlds = {}
    for level in range(1, 6):
        public, truth = generate_task_state(_task(level, "full"), "atelier-difficulty-comparison")
        profile = CONTROLS["difficulty"][str(level)]["parameters"]
        worlds[level] = truth
        assert len(truth["active_fields"]) == profile["phase_count"]
        assert len(truth["motif"]["points"]) == profile["motif_point_count"]
        assert len(truth["reversed_target_phases"]) == profile["reverse_count"]
        assert public["stroke_budget"] == profile["stroke_budget"]
    assert len(worlds[1]["gate_sets"]) < len(worlds[3]["gate_sets"]) < len(worlds[5]["gate_sets"])
    assert worlds[1]["motif"]["tolerance"] > worlds[3]["motif"]["tolerance"]
    assert [worlds[level]["locked_gate_memory"] for level in range(1, 6)] == [0, 0, 0, 1, 2]
    target_prefix = [item["value"] for item in worlds[3]["target"][:1]]
    alternative = next(item["value"] for item in worlds[3]["gate_sets"]["0|"] if item["value"] != target_prefix[0])
    target_centers = [item["center"] for item in worlds[3]["gate_sets"][f"1|{target_prefix[0]}"]]
    alternative_centers = [item["center"] for item in worlds[3]["gate_sets"][f"1|{alternative}"]]
    assert target_centers != alternative_centers


def test_gate_hit_regions_equal_rendered_bars_and_leave_real_gaps() -> None:
    orientations: set[str] = set()
    for level in range(1, 6):
        _, truth = generate_task_state(_task(level, "full"), f"atelier-gate-geometry-{level}")
        for gates in truth["gate_sets"].values():
            axis = 1 if gates[0]["orientation"] == "vertical" else 0
            ordered = sorted(gates, key=lambda gate: gate["center"][axis])
            orientations.add(ordered[0]["orientation"])
            for gate in ordered:
                assert gate["hit_half_length"] == gate["half_length"] + gate["tolerance"]
                x, y = gate["center"]
                half = gate["hit_half_length"]
                if gate["orientation"] == "vertical":
                    inside = ([x - 30, y + half], [x + 30, y + half])
                    outside = ([x - 30, y + half + 0.25], [x + 30, y + half + 0.25])
                else:
                    inside = ([x + half, y - 30], [x + half, y + 30])
                    outside = ([x + half + 0.25, y - 30], [x + half + 0.25, y + 30])
                if gate["direction"] in {"left", "up"}:
                    inside = tuple(reversed(inside))
                    outside = tuple(reversed(outside))
                assert GRADER._crosses(*inside, gate)
                assert not GRADER._crosses(*outside, gate)
            for first, second in zip(ordered, ordered[1:]):
                gap = second["center"][axis] - first["center"][axis] - first["hit_half_length"] - second["hit_half_length"]
                assert gap >= 16
                midpoint = (first["center"][axis] + first["hit_half_length"] + second["center"][axis] - second["hit_half_length"]) / 2
                for gate in (first, second):
                    x, y = gate["center"]
                    segment = ([x - 30, midpoint], [x + 30, midpoint]) if gate["orientation"] == "vertical" else ([midpoint, y - 30], [midpoint, y + 30])
                    if gate["direction"] in {"left", "up"}:
                        segment = tuple(reversed(segment))
                    assert not GRADER._crosses(*segment, gate)
    assert orientations == {"vertical", "horizontal"}


def test_grader_rejects_wrong_field_direction_geometry_and_motif() -> None:
    public, truth = generate_task_state(_task(3, "full"), "atelier-negative-replays")
    passing = _payload(truth, "full")
    assert GRADER.grade(passing, truth, public)["passed"] is True
    wrong_value = copy.deepcopy(passing)
    wrong_value["selected_fields"][truth["active_fields"][0]] = "impossible"
    assert "reported badge fields" in GRADER.grade(wrong_value, truth, public)["feedback"]
    wrong_direction = copy.deepcopy(passing)
    wrong_direction["events"][1]["direction"] = "up"
    assert "wrong direction" in GRADER.grade(wrong_direction, truth, public)["feedback"]
    bad_geometry = copy.deepcopy(passing)
    bad_geometry["events"][1]["before"] = [0, 0]
    bad_geometry["events"][1]["after"] = [1, 1]
    assert "geometry" in GRADER.grade(bad_geometry, truth, public)["feedback"]
    sparse_crossing = copy.deepcopy(passing)
    gate_event = sparse_crossing["events"][1]
    gate = next(item for item in truth["gate_sets"]["0|"] if item["id"] == gate_event["gate_id"])
    x, y = gate["center"]
    if gate["orientation"] == "vertical":
        gate_event["before"], gate_event["after"] = ([0, y], [truth["stage"]["width"], y]) if gate["direction"] == "right" else ([truth["stage"]["width"], y], [0, y])
    else:
        gate_event["before"], gate_event["after"] = ([x, 0], [x, truth["stage"]["height"]]) if gate["direction"] == "down" else ([x, truth["stage"]["height"]], [x, 0])
    segment = gate_event["path_segment"]
    sparse_crossing["stroke_geometry"][segment] = gate_event["before"]
    sparse_crossing["stroke_geometry"][segment + 1] = gate_event["after"]
    assert GRADER.grade(sparse_crossing, truth, public)["passed"] is True
    detached_crossing = copy.deepcopy(passing)
    detached_crossing["events"][1]["path_segment"] += 1
    assert "detached" in GRADER.grade(detached_crossing, truth, public)["feedback"] or "continuous" in GRADER.grade(detached_crossing, truth, public)["feedback"]
    missing_stroke_path = copy.deepcopy(passing)
    missing_stroke_path.pop("stroke_geometry")
    assert "continuous stroke geometry" in GRADER.grade(missing_stroke_path, truth, public)["feedback"]
    skipped_motif = copy.deepcopy(passing)
    skipped_motif["events"].pop(-2)
    for index, event in enumerate(skipped_motif["events"], start=1):
        event["sequence"] = index
    assert "motif" in GRADER.grade(skipped_motif, truth, public)["feedback"]
    bad_drawing = copy.deepcopy(passing)
    bad_drawing["drawn_geometry"].insert(2, [0, 0])
    assert "motif corridor" in GRADER.grade(bad_drawing, truth, public)["feedback"]


def test_grader_rejects_locked_bar_recross_and_cancelled_release() -> None:
    for interaction in ("full", "simplified"):
        public, truth = generate_task_state(_task(4, interaction), "atelier-locked-replay")
        passing = _payload(truth, interaction)
        assert GRADER.grade(passing, truth, public)["passed"] is True
        recross = copy.deepcopy(passing)
        first_cross = next(event for event in recross["events"] if event["kind"] == "gate_cross")
        insertion = first_cross["path_segment"] + 2
        recross["stroke_geometry"].insert(insertion, copy.deepcopy(first_cross["before"]))
        for event in recross["events"]:
            if event.get("path_segment", -1) >= insertion - 1 and event is not first_cross:
                event["path_segment"] += 1
        recross["events"][-1]["path_index"] += 1
        assert "locked spent bar" in GRADER.grade(recross, truth, public)["feedback"]
    public, truth = generate_task_state(_task(4, "full"), "atelier-cancelled-release")
    passing = _payload(truth, "full")
    cancelled_end = copy.deepcopy(passing)
    cancelled_end["events"][-1]["termination"] = "pointercancel"
    assert "normal pointer release" in GRADER.grade(cancelled_end, truth, public)["feedback"]
    malformed_interrupt = copy.deepcopy(passing)
    malformed_interrupt["interruptions"] = [{"sequence": 1, "kind": "stroke_cancel", "input_source": "direct_stroke", "termination": "pointerup", "complete": False}]
    assert "interrupted-stroke" in GRADER.grade(malformed_interrupt, truth, public)["feedback"]


def test_browser_contract_is_input_driven_and_click_inert_in_full_mode() -> None:
    source = (BENCHMARK / "shared_runtime" / "app" / "mechanics" / "one_stroke_atelier.js").read_text()
    assert "direct_stroke" in source and "proxy_gate" in source and "proxy_motif" in source
    assert "pointerdown" in source and "pointermove" in source and "setPointerCapture" in source
    assert "pointercancel" in source and "lostpointercapture" in source and "cancelStroke" in source
    assert "setInterval" not in source and "Date.now" not in source
    for forbidden in ("THE HOUSE RULE", "ONE PHYSICAL HOLD", "ORDER IS BINDING", "KEEP HOLDING", "BENCH RECONFIGURED", "fresh commission issued"):
        assert forbidden not in source
