from __future__ import annotations

import copy
import importlib.util
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "pheromone_dispatch_env"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


SETUP = _load("pheromone_control_setup", BENCHMARK / "shared_scripts" / "setup_task.py")
MATERIALIZER = _load("pheromone_control_materializer", BENCHMARK / "tools" / "materialize_controlled_tasks.py")
GRADER = _load(
    "pheromone_control_grader",
    BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "pheromone_dispatch.py",
)
CONTROLS = _read(ENVIRONMENT / "controls.json")
BASE = _read(ENVIRONMENT / "tasks" / "pheromone_dispatch_seed_0001" / "task.json")


def _task(level: int, interaction: str) -> dict:
    return MATERIALIZER.controlled_task(
        BASE,
        mechanic_id="pheromone_dispatch",
        level=level,
        interaction=interaction,
        profile=CONTROLS["difficulty"][str(level)],
        task_dir_name=f"pheromone_dispatch_d{level}_{interaction}_seed_0001",
    )


def _without_control_identity(value: dict) -> dict:
    copied = copy.deepcopy(value)
    for field in ("task_id", "challenge_id", "control_condition"):
        copied.pop(field, None)
    return copied


def _samples(waypoints: list[list[float]]) -> list[dict[str, float]]:
    result: list[dict[str, float]] = []
    for index, (first, second) in enumerate(zip(waypoints, waypoints[1:])):
        if index == 0:
            result.append({"x": float(first[0]), "y": float(first[1])})
        for step in range(1, 13):
            amount = step / 12
            result.append({
                "x": float(first[0]) + (float(second[0]) - float(first[0])) * amount,
                "y": float(first[1]) + (float(second[1]) - float(first[1])) * amount,
            })
    return result


def _passing_payload(public: dict, truth: dict, interaction: str) -> dict:
    fields = list(public["fields"])
    paths = {field["id"]: _samples(truth["reference_paths"][field["id"]]) for field in fields}
    events: list[dict] = []

    def record(kind: str, tick: int, **details) -> None:
        events.append({
            "seq": len(events) + 1,
            "type": kind,
            "tick": tick,
            "input_surface": interaction,
            "input_method": "waypoint_clicks" if interaction == "simplified" else "continuous_pointer_trace",
            **details,
        })

    def stroke(field_id: str, tick: int, mode: str) -> None:
        points = paths[field_id]
        record("stroke_start", tick, field_id=field_id, mode=mode, point=points[0])
        for point in points[1:]:
            record("stroke_point", tick, field_id=field_id, mode=mode, point=point)
        record("stroke_end", tick, field_id=field_id, mode=mode, point=points[-1], samples=len(points))

    for field in fields:
        stroke(field["id"], 0, "route")
    record("dispatch", 0, paths=paths)

    refresh_ticks = list(range(40, 901, 40))
    physics = public["physics"]
    distances = {field["id"]: [-index * float(physics["ant_spacing"]) for index in range(int(public["ant_count"]))] for field in fields}
    delivered = {field["id"]: 0 for field in fields}
    done = {field["id"]: [False] * int(public["ant_count"]) for field in fields}
    carrying = {field["id"]: [False] * int(public["ant_count"]) for field in fields}
    last_refresh = {field["id"]: 0 for field in fields}
    metrics = {
        field["id"]: GRADER._metrics(
            [(point["x"], point["y"]) for point in paths[field["id"]]],
            tuple(field["cache"]),
        )
        for field in fields
    }


    completion_tick = None
    for tick in range(1, 901):
        if tick in refresh_ticks:
            for field in fields:
                last_refresh[field["id"]] = tick
        for field in fields:
            field_id = field["id"]
            if tick - last_refresh[field_id] > int(field["trail_ttl_ticks"]):
                continue
            total, cache_distance = metrics[field_id]
            for index in range(len(distances[field_id])):
                if done[field_id][index]:
                    continue
                distances[field_id][index] += float(field["speed"])
                if distances[field_id][index] < 0:
                    continue
                if distances[field_id][index] >= cache_distance:
                    carrying[field_id][index] = True
                if distances[field_id][index] >= total:
                    done[field_id][index] = True
                    if carrying[field_id][index]:
                        delivered[field_id] += 1
        if all(delivered[field["id"]] >= int(physics["delivery_required"]) for field in fields):
            completion_tick = tick
            break
    assert completion_tick is not None
    for tick in refresh_ticks:
        if tick >= completion_tick:
            break
        for field in fields:
            stroke(field["id"], tick, "refresh")
            record("refresh", tick, field_id=field["id"], path=paths[field["id"]])
    effective_last_refresh = {
        field["id"]: max((tick for tick in refresh_ticks if tick < completion_tick), default=0)
        for field in fields
    }
    record("delivery", completion_tick, delivered=delivered, last_refresh=effective_last_refresh)
    return {
        "mechanic_id": "pheromone_dispatch",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "interaction_mode": interaction,
        "events": events,
        "completed": True,
    }


def test_controlled_baseline_materializes_all_ten_and_preserves_original_generation(tmp_path: Path) -> None:
    MATERIALIZER.validate_controls(CONTROLS, ENVIRONMENT)
    written = MATERIALIZER.materialize_environment(ENVIRONMENT, tmp_path)
    assert len(written) == 10
    original_public, original_truth = SETUP.generate_task_state(BASE, "pheromone-baseline-preservation")
    controlled_public, controlled_truth = SETUP.generate_task_state(_task(4, "full"), "pheromone-baseline-preservation")
    assert _without_control_identity(original_public) == _without_control_identity(controlled_public)
    assert _without_control_identity(original_truth) == _without_control_identity(controlled_truth)


def _sparse_payload(public: dict, truth: dict, interaction: str) -> dict:
    events: list[dict] = []

    def record(kind: str, **details) -> None:
        events.append({
            "seq": len(events) + 1,
            "type": kind,
            "tick": 0,
            "input_surface": interaction,
            "input_method": "waypoint_clicks" if interaction == "simplified" else "continuous_pointer_trace",
            **details,
        })

    paths: dict[str, list[dict[str, float]]] = {}
    for field in public["fields"]:
        field_id = field["id"]
        points = [{"x": float(x), "y": float(y)} for x, y in truth["reference_paths"][field_id]]
        paths[field_id] = points
        record("stroke_start", field_id=field_id, mode="route", point=points[0])
        for point in points[1:]:
            record("stroke_point", field_id=field_id, mode="route", point=point)
        record("stroke_end", field_id=field_id, mode="route", point=points[-1], samples=len(points))
    record("dispatch", paths=paths)
    return {
        "mechanic_id": "pheromone_dispatch",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "interaction_mode": interaction,
        "events": events,
        "completed": True,
    }


def test_sparse_route_is_rejected_by_replay_and_the_browser_uses_the_same_boundary() -> None:
    original_public, original_truth = SETUP.generate_task_state(BASE, "pheromone-sparse-boundary")
    l4_public, l4_truth = SETUP.generate_task_state(_task(4, "full"), "pheromone-sparse-boundary")
    simple_public, simple_truth = SETUP.generate_task_state(_task(4, "simplified"), "pheromone-sparse-boundary")
    assert _without_control_identity(original_public) == _without_control_identity(l4_public)
    assert _without_control_identity(original_truth) == _without_control_identity(l4_truth)
    assert _without_control_identity(l4_public) == _without_control_identity(simple_public)
    assert _without_control_identity(l4_truth) == _without_control_identity(simple_truth)

    for public, truth, interaction in (
        (original_public, original_truth, "full"),
        (l4_public, l4_truth, "full"),
        (simple_public, simple_truth, "simplified"),
    ):
        sparse = _sparse_payload(public, truth, interaction)
        assert any(
            math.dist(first, second) > GRADER.MAX_ROUTE_SAMPLE_GAP
            for path in truth["reference_paths"].values()
            for first, second in zip(path, path[1:])
        )
        rejected = GRADER.grade(sparse, truth, public)
        assert rejected["passed"] is False
        assert rejected["feedback"] == "pheromone brush teleported, switched color, or changed mode"

    runtime = (BENCHMARK / "shared_runtime" / "app" / "mechanics" / "_interaction_vii_viii.js").read_text(encoding="utf-8")
    pheromone_runtime = runtime.split("registry.pheromone_dispatch = async", 1)[1].split("registry.clockwork_clutch_safe_v1", 1)[0]
    assert "const MAX_ROUTE_SAMPLE_GAP = 160" in pheromone_runtime
    assert "const hasSamplingGap" in pheromone_runtime
    assert "distance > MAX_ROUTE_SAMPLE_GAP" in pheromone_runtime
    assert "PLOT GAP TOO LARGE" in pheromone_runtime
    assert "BRUSH GAP TOO LARGE" in pheromone_runtime


def test_profiles_change_the_active_problem_and_interaction_preserves_the_world() -> None:
    expected_fields = [1, 1, 2, 2, 2]
    expected_delivery = [4, 6, 5, 7, 8]
    for level, field_count, delivery_required in zip(range(1, 6), expected_fields, expected_delivery, strict=True):
        public, truth = SETUP.generate_task_state(_task(level, "simplified"), "pheromone-profile-contract")
        assert public["control_condition"] == truth["control_condition"]
        assert len(public["fields"]) == field_count
        assert public["physics"]["delivery_required"] == delivery_required
    simple_public, simple_truth = SETUP.generate_task_state(_task(4, "simplified"), "pheromone-interaction-pair")
    full_public, full_truth = SETUP.generate_task_state(_task(4, "full"), "pheromone-interaction-pair")
    assert simple_public["challenge_id"] == full_public["challenge_id"]
    assert _without_control_identity(simple_public) == _without_control_identity(full_public)
    assert _without_control_identity(simple_truth) == _without_control_identity(full_truth)


def test_grader_binds_a_passing_transcript_to_its_selected_interaction_surface() -> None:
    for interaction in ("simplified", "full"):
        public, truth = SETUP.generate_task_state(_task(4, interaction), f"pheromone-{interaction}-replay")
        payload = _passing_payload(public, truth, interaction)
        assert GRADER.grade(payload, truth, public)["passed"] is True
        wrong_surface = copy.deepcopy(payload)
        wrong_surface["interaction_mode"] = "full" if interaction == "simplified" else "simplified"
        assert GRADER.grade(wrong_surface, truth, public)["passed"] is False
        wrong_events = copy.deepcopy(payload)
        wrong_events["events"][0]["input_surface"] = "full" if interaction == "simplified" else "simplified"
        assert GRADER.grade(wrong_events, truth, public)["passed"] is False
        wrong_procedure = copy.deepcopy(payload)
        wrong_procedure["events"][0]["input_method"] = "continuous_pointer_trace" if interaction == "simplified" else "waypoint_clicks"
        assert GRADER.grade(wrong_procedure, truth, public)["passed"] is False


def test_simplified_waypoint_plotter_requires_a_visible_safe_cache_route() -> None:
    public, truth = SETUP.generate_task_state(_task(4, "simplified"), "pheromone-simplified-waypoints")
    payload = _passing_payload(public, truth, "simplified")
    field_id = public["fields"][0]["id"]
    route_events = [
        event for event in payload["events"]
        if event.get("field_id") == field_id and event.get("mode") == "route" and event["type"] in {"stroke_start", "stroke_point"}
    ]
    assert len(route_events) > 18
    obstacle = public["obstacles"][0]
    unsafe_point = {"x": obstacle["x"], "y": obstacle["y"] - obstacle["h"] / 2 + 1}
    route_events[18]["point"] = unsafe_point
    dispatch = next(event for event in payload["events"] if event["type"] == "dispatch")
    dispatch["paths"][field_id][18] = unsafe_point
    assert GRADER.grade(payload, truth, public)["passed"] is False

    runtime = (BENCHMARK / "shared_runtime" / "app" / "mechanics" / "_interaction_vii_viii.js").read_text(encoding="utf-8")
    pheromone_runtime = runtime.split("registry.pheromone_dispatch = async", 1)[1].split("registry.clockwork_clutch_safe_v1", 1)[0]
    assert "data-proxy-field" not in pheromone_runtime
    assert "proxyRoute" not in pheromone_runtime
    assert "WAYPOINT FIELD PLOTTER" in pheromone_runtime
    assert "pheromone-commit" in pheromone_runtime
