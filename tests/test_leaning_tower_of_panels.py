from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
ENV = BENCHMARK / "environments" / "leaning_tower_of_panels_env"
GENERATOR_PATH = BENCHMARK / "shared_scripts" / "incubator_generators" / "leaning_tower_of_panels.py"
GRADER_PATH = BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "leaning_tower_of_panels.py"
MATERIALIZER_PATH = BENCHMARK / "tools" / "materialize_controlled_tasks.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("leaning_tower_generator_test", GENERATOR_PATH)
GRADER = _load("leaning_tower_grader_test", GRADER_PATH)
MATERIALIZER = _load("leaning_tower_materializer_test", MATERIALIZER_PATH)
CANVAS_WIDTH = 880.0
CANVAS_HEIGHT = 540.0


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _task(level: int, interaction: str) -> dict:
    base = _read(ENV / "tasks" / "leaning_tower_of_panels_seed_0001" / "task.json")
    controls = _read(ENV / "controls.json")
    task = copy.deepcopy(base)
    task["id"] = f"leaning_tower_of_panels_d{level}_{interaction}_seed_0001@0.2"
    task["metadata"]["control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": "live",
        "difficulty_parameters": controls["difficulty"][str(level)]["parameters"],
    }
    task["_control_condition"] = copy.deepcopy(task["metadata"]["control_condition"])
    return task


def _center(geometry: dict) -> tuple[float, float]:
    polygon = geometry["polygon"]
    return (
        sum(point[0] for point in polygon) / len(polygon),
        sum(point[1] for point in polygon) / len(polygon),
    )


def _trace(*points: tuple[float, float]) -> dict:
    return {
        "coordinate_space": "normalized_canvas_v1",
        "points": [
            {"x": round(x / CANVAS_WIDTH, 6), "y": round(y / CANVAS_HEIGHT, 6)}
            for x, y in points
        ],
    }


def _cell_center(public: dict, truth: dict, grid: list, index: int, view: int) -> tuple[float, float]:
    geometry = GRADER._cell_geometry(
        index,
        view,
        tuple(grid),
        tuple(truth["goal_grid"]),
        int(public["floor_count"]),
        int(public["sector_count"]),
        int(public["visible_arc_degrees"]),
    )
    assert geometry is not None
    return _center(geometry)


def _solution_payload(
    public: dict,
    truth: dict,
    interaction: str,
    *,
    hide_one_destination: bool = False,
) -> dict:
    grid = list(public["start_grid"])
    events = []
    panel_source = "panel_click" if interaction == "simplified" else "panel_drag"
    rotation_source = "rotation_buttons" if interaction == "simplified" else "tower_drag"
    sectors = int(public["sector_count"])
    view = 0
    for tile_id in truth["optimal_solution"]:
        from_index = grid.index(tile_id)
        to_index = grid.index(None)
        source_row, source_sector = divmod(from_index, sectors)
        blank_row, blank_sector = divmod(to_index, sectors)
        target_view = source_sector
        if hide_one_destination and source_row == blank_row:
            if blank_sector == (source_sector + 1) % sectors:
                target_view = (source_sector - 1) % sectors
                hide_one_destination = False
            elif blank_sector == (source_sector - 1) % sectors:
                target_view = (source_sector + 1) % sectors
                hide_one_destination = False
        while view != target_view:
            clockwise = (target_view - view) % sectors
            counter = (view - target_view) % sectors
            delta = 1 if clockwise <= counter else -1
            next_view = (view + delta) % sectors
            events.append(
                {
                    "sequence": len(events) + 1,
                    "kind": "rotate",
                    "input_source": rotation_source,
                    "view_before": view,
                    "delta": delta,
                    "view_after": next_view,
                    **(
                        {"pointer_trace": _trace((120, 270), (20, 270))}
                        if interaction == "full" and delta == 1
                        else {"pointer_trace": _trace((20, 270), (120, 270))}
                        if interaction == "full"
                        else {}
                    ),
                }
            )
            view = next_view
        slide_event = {
            "sequence": len(events) + 1,
            "kind": "slide",
            "input_source": panel_source,
            "tile_id": tile_id,
            "from_index": from_index,
            "to_index": to_index,
        }
        if interaction == "full":
            start_point = _cell_center(public, truth, grid, from_index, view)
            destination = GRADER._cell_geometry(
                to_index,
                view,
                tuple(grid),
                tuple(truth["goal_grid"]),
                int(public["floor_count"]),
                sectors,
                int(public["visible_arc_degrees"]),
            )
            if destination is not None:
                end_point = _center(destination)
            elif blank_sector == (source_sector + 1) % sectors:
                end_point = (CANVAS_WIDTH + 24, start_point[1])
            elif blank_sector == (source_sector - 1) % sectors:
                end_point = (-24, start_point[1])
            else:
                raise AssertionError("hidden opening is not a horizontal wrap neighbor")
            slide_event["pointer_trace"] = _trace(start_point, end_point)
        events.append(slide_event)
        grid[to_index], grid[from_index] = grid[from_index], None
    assert grid == truth["goal_grid"]
    return {
        "mechanic_id": "leaning_tower_of_panels",
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction_mode": interaction,
        "events": events,
        "final_grid": grid,
        "move_count": len(truth["optimal_solution"]),
        "view_sector": view,
        "optimal_move_count": public["optimal_move_count"],
        "allowed_moves": public["allowed_moves"],
    }


def test_environment_is_registered_with_static_observation() -> None:
    manifest = _read(BENCHMARK / "benchmark_manifest.json")
    assert "leaning_tower_of_panels_env" in manifest["environments"]
    assert manifest["environment_count"] == len(manifest["environments"])
    timing = _read(BENCHMARK / "real_time.json")["environments"]["leaning_tower_of_panels"]
    assert timing == {
        "play_time_seconds": 180,
        "observation_window_ms": 0,
        "frames_per_observation": 1,
    }
    assert _read(ENV / "env.json")["runner_options"] == timing


def test_all_profiles_are_deterministic_reachable_and_ordered() -> None:
    controls = _read(ENV / "controls.json")
    seen = []
    for level in range(1, 6):
        task = _task(level, "simplified")
        first = GENERATOR.generate(task, "leaning-profile-seed")
        second = GENERATOR.generate(task, "leaning-profile-seed")
        assert first == second
        public, truth = first
        parameters = controls["difficulty"][str(level)]["parameters"]
        assert parameters["scramble_distance_min"] <= truth["optimal_move_count"] <= parameters["scramble_distance_max"]
        assert truth["allowed_moves"] == truth["optimal_move_count"] + parameters["move_allowance"]
        assert len(truth["goal_grid"]) == parameters["floor_count"] * parameters["sector_count"]
        assert truth["goal_grid"].count(None) == truth["start_grid"].count(None) == 1
        payload = _solution_payload(public, truth, "simplified")
        grade = GRADER.grade(payload, truth, public)
        assert grade["passed"] is True, grade
        seen.append((len(public["tiles"]), truth["optimal_move_count"], public["mural"]["band_count"], public["allowed_moves"]))
    assert seen == sorted(seen, key=lambda item: (item[0], item[1], item[2]))
    assert len(set(seen)) == 5


def test_modes_share_the_world_and_wrong_surface_is_rejected() -> None:
    for level in range(1, 6):
        simple_public, simple_truth = GENERATOR.generate(_task(level, "simplified"), "same-world")
        full_public, full_truth = GENERATOR.generate(_task(level, "full"), "same-world")
        for key in (
            "challenge_id",
            "world_fingerprint",
            "floor_count",
            "sector_count",
            "visible_arc_degrees",
            "tiles",
            "start_grid",
            "mural",
            "opening_target_index",
            "optimal_move_count",
            "allowed_moves",
        ):
            assert simple_public[key] == full_public[key]
        assert simple_truth["goal_grid"] == full_truth["goal_grid"]
        assert simple_truth["optimal_solution"] == full_truth["optimal_solution"]

        payload = _solution_payload(simple_public, simple_truth, "simplified")
        assert GRADER.grade(payload, simple_truth, simple_public)["passed"] is True
        forged = copy.deepcopy(payload)
        forged["interaction_mode"] = "full"
        forged["task_id"] = full_public["task_id"]
        for event in forged["events"]:
            event["input_source"] = "tower_drag" if event["kind"] == "rotate" else "panel_drag"
        rejected = GRADER.grade(forged, full_truth, full_public)
        assert rejected["passed"] is False
        assert "pointer trace" in rejected["feedback"]


def test_uncontrolled_task_is_exactly_the_l4_simplified_world() -> None:
    base = _read(ENV / "tasks" / "leaning_tower_of_panels_seed_0001" / "task.json")
    uncontrolled_public, uncontrolled_truth = GENERATOR.generate(base, "baseline-fixed-seed")
    controlled_public, controlled_truth = GENERATOR.generate(_task(4, "simplified"), "baseline-fixed-seed")
    for key in (
        "challenge_id",
        "world_fingerprint",
        "floor_count",
        "sector_count",
        "tiles",
        "start_grid",
        "mural",
        "optimal_move_count",
        "allowed_moves",
    ):
        assert uncontrolled_public[key] == controlled_public[key]
    assert uncontrolled_truth["goal_grid"] == controlled_truth["goal_grid"]
    assert uncontrolled_truth["optimal_solution"] == controlled_truth["optimal_solution"]


def test_replay_rejects_stale_illegal_and_tampered_submissions() -> None:
    public, truth = GENERATOR.generate(_task(4, "full"), "adversarial-seed")
    payload = _solution_payload(public, truth, "full")
    assert GRADER.grade(payload, truth, public)["passed"] is True

    hidden_destination = _solution_payload(public, truth, "full", hide_one_destination=True)
    assert GRADER.grade(hidden_destination, truth, public)["passed"] is True
    replay_view = 0
    hidden_destination_seen = False
    for event in hidden_destination["events"]:
        if event["kind"] == "rotate":
            replay_view = event["view_after"]
            continue
        destination_sector = event["to_index"] % public["sector_count"]
        sector_distance = min(
            (destination_sector - replay_view) % public["sector_count"],
            (replay_view - destination_sector) % public["sector_count"],
        )
        hidden_destination_seen |= (
            sector_distance * 360 / public["sector_count"]
            > public["visible_arc_degrees"] / 2
        )
    assert hidden_destination_seen is True

    stale = copy.deepcopy(payload)
    stale["challenge_id"] = "stale"
    assert GRADER.grade(stale, truth, public)["passed"] is False

    illegal = copy.deepcopy(payload)
    first_slide = next(event for event in illegal["events"] if event["kind"] == "slide")
    first_slide["from_index"] = first_slide["to_index"]
    assert "legal cylindrical slide" in GRADER.grade(illegal, truth, public)["feedback"]

    hidden = copy.deepcopy(payload)
    hidden["events"] = [event for event in hidden["events"] if event["kind"] != "rotate"]
    for sequence, event in enumerate(hidden["events"], start=1):
        event["sequence"] = sequence
    hidden["view_sector"] = 0
    assert any(
        phrase in GRADER.grade(hidden, truth, public)["feedback"]
        for phrase in ("visible arc", "panel geometry")
    )

    tampered = copy.deepcopy(payload)
    tampered["move_count"] += 1
    assert "move count differs" in GRADER.grade(tampered, truth, public)["feedback"]


def test_full_replay_enforces_presentation_faithful_pointer_geometry() -> None:
    public, truth = GENERATOR.generate(_task(4, "full"), "adversarial-seed")
    payload = _solution_payload(public, truth, "full")
    assert GRADER.grade(payload, truth, public)["passed"] is True

    rotation_index = next(index for index, event in enumerate(payload["events"]) if event["kind"] == "rotate")
    slide_index = next(index for index, event in enumerate(payload["events"]) if event["kind"] == "slide")

    missing_trace = copy.deepcopy(payload)
    del missing_trace["events"][rotation_index]["pointer_trace"]
    assert "pointer trace" in GRADER.grade(missing_trace, truth, public)["feedback"]

    short_turn = copy.deepcopy(payload)
    turn_points = short_turn["events"][rotation_index]["pointer_trace"]["points"]
    turn_points[-1]["x"] = turn_points[0]["x"] + 63.9 / CANVAS_WIDTH
    assert "64-pixel threshold" in GRADER.grade(short_turn, truth, public)["feedback"]

    panel_turn = copy.deepcopy(payload)
    initial_grid = tuple(public["start_grid"])
    panel_center = _cell_center(public, truth, list(initial_grid), 0, 0)
    delta = panel_turn["events"][rotation_index]["delta"]
    panel_turn["events"][rotation_index]["pointer_trace"] = _trace(
        panel_center,
        (panel_center[0] - 100 if delta == 1 else panel_center[0] + 100, panel_center[1]),
    )
    assert "open sky" in GRADER.grade(panel_turn, truth, public)["feedback"]

    grid = list(public["start_grid"])
    view = 0
    for event in payload["events"][:slide_index]:
        assert event["kind"] == "rotate"
        view = event["view_after"]
    slide = payload["events"][slide_index]
    source = slide["from_index"]
    blank = slide["to_index"]
    source_geometry = GRADER._cell_geometry(
        source,
        view,
        tuple(grid),
        tuple(truth["goal_grid"]),
        int(public["floor_count"]),
        int(public["sector_count"]),
        int(public["visible_arc_degrees"]),
    )
    blank_geometry = GRADER._cell_geometry(
        blank,
        view,
        tuple(grid),
        tuple(truth["goal_grid"]),
        int(public["floor_count"]),
        int(public["sector_count"]),
        int(public["visible_arc_degrees"]),
    )
    assert source_geometry is not None and blank_geometry is not None
    original_end = _center(blank_geometry)

    sky_start = copy.deepcopy(payload)
    sky_start["events"][slide_index]["pointer_trace"] = _trace((20, 270), original_end)
    assert "claimed frontmost panel" in GRADER.grade(sky_start, truth, public)["feedback"]

    blank_start = copy.deepcopy(payload)
    blank_start["events"][slide_index]["pointer_trace"] = _trace(original_end, original_end)
    assert "claimed frontmost panel" in GRADER.grade(blank_start, truth, public)["feedback"]

    source_top = source_geometry["polygon"]
    source_edge = ((source_top[0][0] + source_top[1][0]) / 2, source_top[0][1])
    source_just_inside = (source_edge[0], source_edge[1] + 0.1)
    source_just_outside = (source_edge[0], source_edge[1] - 0.1)
    inside_source = copy.deepcopy(payload)
    inside_source["events"][slide_index]["pointer_trace"] = _trace(source_just_inside, original_end)
    assert GRADER.grade(inside_source, truth, public)["passed"] is True
    outside_source = copy.deepcopy(payload)
    outside_source["events"][slide_index]["pointer_trace"] = _trace(source_just_outside, original_end)
    assert "claimed frontmost panel" in GRADER.grade(outside_source, truth, public)["feedback"]

    blank_top = blank_geometry["polygon"]
    blank_edge = ((blank_top[0][0] + blank_top[1][0]) / 2, blank_top[0][1])
    blank_just_inside = (blank_edge[0], blank_edge[1] + 0.1)
    blank_just_outside = (blank_edge[0], blank_edge[1] - 0.1)
    inside_drop = copy.deepcopy(payload)
    inside_drop["events"][slide_index]["pointer_trace"] = _trace(
        _center(source_geometry), blank_just_inside
    )
    assert GRADER.grade(inside_drop, truth, public)["passed"] is True
    outside_drop = copy.deepcopy(payload)
    outside_drop["events"][slide_index]["pointer_trace"] = _trace(
        _center(source_geometry), blank_just_outside
    )
    assert "visible opening" in GRADER.grade(outside_drop, truth, public)["feedback"]

    hidden = _solution_payload(public, truth, "full", hide_one_destination=True)
    hidden_index = next(
        index
        for index, event in enumerate(hidden["events"])
        if event["kind"] == "slide"
        and not 0 <= event["pointer_trace"]["points"][-1]["x"] <= 1
    )
    wrong_edge = copy.deepcopy(hidden)
    wrong_endpoint = wrong_edge["events"][hidden_index]["pointer_trace"]["points"][-1]
    wrong_endpoint["x"] = -0.03 if wrong_endpoint["x"] > 1 else 1.03
    assert "correct" in GRADER.grade(wrong_edge, truth, public)["feedback"]
    uncrossed_edge = copy.deepcopy(hidden)
    uncrossed_endpoint = uncrossed_edge["events"][hidden_index]["pointer_trace"]["points"][-1]
    uncrossed_endpoint["x"] = 1.0 if uncrossed_endpoint["x"] > 1 else 0.0
    assert "cross" in GRADER.grade(uncrossed_edge, truth, public)["feedback"]


def test_controlled_materialization_writes_all_ten_tasks(tmp_path: Path) -> None:
    written = MATERIALIZER.materialize_environment(ENV, tmp_path)
    assert len(written) == 10
    names = {path.name for path in written}
    assert "leaning_tower_of_panels_d1_simplified_seed_0001" in names
    assert "leaning_tower_of_panels_d5_full_seed_0001" in names
    for path in written:
        task = _read(path / "task.json")
        condition = task["metadata"]["control_condition"]
        assert condition["difficulty"] in {1, 2, 3, 4, 5}
        assert condition["interaction"] in {"simplified", "full"}
        assert condition["real_time"] == "live"


def test_public_task_contract_and_source_record_are_complete() -> None:
    task = _read(ENV / "tasks" / "leaning_tower_of_panels_seed_0001" / "task.json")
    assert task["name"] == "The Leaning Tower of Panels"
    assert task["metadata"]["source_anchors"] == ["TRW-055", "TRW-030"]
    assert task["metadata"]["status"] == "prototype_visual_candidate"
    assert "visible controls" in task["description"]
    assert "Developer Tools" in task["natural_language"]
    provenance = _read(BENCHMARK / "shared_runtime" / "assets" / "provenance" / "leaning_tower_of_panels_v0.json")
    assert provenance["source_anchors"] == ["TRW-055", "TRW-030"]
    assert provenance["assets"] == []
    split = _read(BENCHMARK / "splits" / "leaning_tower_of_panels_split.json")
    assert split["test_tasks"] == []
    assert len(split["variations_tasks"]) == 20


def test_browser_module_exposes_both_bound_input_surfaces() -> None:
    source = (BENCHMARK / "shared_runtime" / "app" / "mechanics" / "leaning_tower_of_panels.js").read_text(encoding="utf-8")
    assert '"rotation_buttons"' in source
    assert '"tower_drag"' in source
    assert '"panel_click"' in source
    assert '"panel_drag"' in source
    assert "goal_grid" not in source
