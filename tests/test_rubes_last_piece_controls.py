from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
ENV = BENCHMARK / "environments" / "rubes_last_piece_env"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("rubes_generator_test", BENCHMARK / "shared_scripts/incubator_generators/rubes_last_piece.py")
GRADER = _load("rubes_grader_test", BENCHMARK / "shared_runtime/server/incubator_graders/rubes_last_piece.py")
MATERIALIZER = _load("rubes_materializer_test", BENCHMARK / "tools/materialize_controlled_tasks.py")


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _task(level: int | None = None, interaction: str = "full", real_time: str = "live") -> dict:
    task = _read(ENV / "tasks/rubes_last_piece_seed_0001/task.json")
    if level is None:
        return task
    controls = _read(ENV / "controls.json")
    task["_control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": copy.deepcopy(controls["difficulty"][str(level)]["parameters"]),
    }
    return task


def _without_identity(value: dict) -> dict:
    result = copy.deepcopy(value)
    for key in ("task_id", "challenge_id", "control_condition"):
        result.pop(key, None)
    return result


def _failure_angle(public: dict, bay: dict, tool: dict) -> float:
    candidates = []
    for angle in public["contract"]["allowed_angles_deg"]:
        pose = [float(bay["anchor"][0]), float(bay["anchor"][1]), float(angle)]
        replay = GRADER.replay_lane(public, bay, tool, pose)
        if not replay["passed"] and replay["miss_offset"] is not None:
            candidates.append((abs(float(replay["miss_offset"])), float(angle)))
    return min(candidates)[1] if candidates else 90.0


def _solution(public: dict, truth: dict, interaction: str, *, failed_first: bool = False) -> dict:
    events: list[dict] = []
    placements: dict[str, dict] = {}
    place_source = {"simplified": "bay_place_button", "full": "direct_drag"}[interaction]
    rotate_source = {"simplified": "rotation_buttons", "full": "direct_right_click"}[interaction]
    tools = {item["id"]: item for item in public["tools"]}

    def add(kind: str, **details) -> None:
        events.append({"sequence": len(events) + 1, "kind": kind, **details})

    def placement_details(tool_id: str, bay: dict, pose: list[float]) -> dict:
        details = {"tool_id": tool_id, "bay_id": bay["id"], "pose": list(pose), "input_source": place_source}
        if interaction == "full":
            release = [float(bay["anchor"][0]), float(bay["anchor"][1])]
            details["gesture"] = {
                "origin": "rack",
                "start_tool_id": tool_id,
                "start_stage": None,
                "samples_stage": [list(release)],
                "release_stage": list(release),
            }
        return details

    target_angles: dict[str, float] = {}
    for bay in public["bays"]:
        oracle = truth["oracle_by_bay"][bay["id"]]
        tool_id = oracle["tool_id"]
        target = float(oracle["pose"][2])
        if failed_first and bay["sequence"] == 1:
            target = _failure_angle(public, bay, tools[tool_id])
        pose = [float(bay["anchor"][0]), float(bay["anchor"][1]), 45.0]
        placements[tool_id] = {"bay_id": bay["id"], "pose": pose}
        add("place", **placement_details(tool_id, bay, pose))
        turns = int(round(((target - 45.0) % 180.0) / 5.0))
        for _ in range(turns):
            pose = [pose[0], pose[1], pose[2] + 5.0]
            placements[tool_id]["pose"] = list(pose)
            add("rotate", tool_id=tool_id, delta_degrees=5.0, pose=list(pose), input_source=rotate_source)
        target_angles[bay["id"]] = target

    def append_run(attempt: int) -> dict:
        add("run_start", attempt=attempt)
        replay = GRADER.replay_run(public, placements)
        for release in replay["releases"]:
            add("release", bay_id=release["bay_id"], tool_id=release["tool_id"], tick=release["tick"], contact=release["contact"])
        if replay["passed"]:
            add("bell", tick=replay["ticks"])
        add("rollout_end", bell_rung=replay["passed"], tick=replay["ticks"], stalled_bay=replay["stalled_bay"], miss_offset=replay["miss_offset"], impact_error=replay["impact_error"])
        return replay

    attempt = 1
    replay = append_run(attempt)
    rewinds = 0
    if failed_first:
        assert replay["passed"] is False
        add("rewind")
        rewinds = 1
        first = public["bays"][0]
        oracle = truth["oracle_by_bay"][first["id"]]
        tool_id = oracle["tool_id"]
        pose = placements[tool_id]["pose"]
        turns = int(round(((float(oracle["pose"][2]) - pose[2]) % 180.0) / 5.0))
        for _ in range(turns):
            pose = [pose[0], pose[1], pose[2] + 5.0]
            placements[tool_id]["pose"] = list(pose)
            add("rotate", tool_id=tool_id, delta_degrees=5.0, pose=list(pose), input_source=rotate_source)
        attempt += 1
        replay = append_run(attempt)
    assert replay["passed"] is True
    release_sequence = [f"release:{item['bay_id']}" for item in replay["releases"]] + ["bell:ring"]
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "events": events,
        "placements": dict(sorted(placements.items())),
        "release_sequence": release_sequence,
        "bell_rung": True,
        "rollout_ticks": replay["ticks"],
        "attempts": attempt,
        "rewinds": rewinds,
        "physics_engine": public["contract"]["physics_engine"],
    }


def test_controls_materialize_ten_tasks_and_register_real_time(tmp_path: Path) -> None:
    controls = _read(ENV / "controls.json")
    MATERIALIZER.validate_controls(controls, ENV)
    assert _read(BENCHMARK / "real_time.json")["environments"]["rubes_last_piece"] == controls["real_time"]
    written = MATERIALIZER.materialize_environment(ENV, tmp_path)
    assert len(written) == 10
    pairs = set()
    for path in written:
        condition = _read(path / "task.json")["metadata"]["control_condition"]
        pairs.add((condition["difficulty"], condition["interaction"]))
    assert pairs == {(level, interaction) for level in range(1, 6) for interaction in ("simplified", "full")}


def test_baseline_is_the_exact_l3_full_world() -> None:
    original_public, original_truth = GENERATOR.generate(_task(), "rube-baseline")
    baseline_public, baseline_truth = GENERATOR.generate(_task(3, "full"), "rube-baseline")
    assert _without_identity(original_public) == _without_identity(baseline_public)
    assert _without_identity(original_truth) == _without_identity(baseline_truth)


def test_profiles_change_serial_dependency_material_ambiguity_and_physical_target() -> None:
    expected = [(1, 0, 25, 0.0, 0.18), (2, 0, 19, 0.004, 0.05), (3, 1, 14, 0.007, 0.06), (4, 2, 11, 0.011, 0.05), (5, 3, 8, 0.015, 0.045)]
    for level, (links, decoys, radius, wind, impact_tolerance) in enumerate(expected, start=1):
        public, truth = GENERATOR.generate(_task(level, "full"), f"rube-profile-{level}")
        assert len(public["bays"]) == links
        assert len(public["tools"]) == links + decoys
        assert {bay["receiver_radius"] for bay in public["bays"]} == {radius}
        assert {bay["impact_tolerance"] for bay in public["bays"]} == {impact_tolerance}
        assert all(float(bay["impact_speed"]) > 0 for bay in public["bays"])
        assert max(abs(float(bay["wind_y"])) for bay in public["bays"]) <= wind * 1.21 + 1e-9
        assert len(truth["expected_release_sequence"]) == links + 1
        assert GRADER.grade(_solution(public, truth, "full"), truth, public)["passed"] is True


def test_public_setup_has_no_answer_key_and_oracle_replays_physical_contacts() -> None:
    public, truth = GENERATOR.generate(_task(3, "full"), "rube-no-static-answer")
    assert "oracle_by_bay" not in public
    assert all("target_pose" not in bay and "key_mark" not in bay and "key_color" not in bay for bay in public["bays"])
    assert all("is_spare" not in tool for tool in public["tools"])
    placements = {item["tool_id"]: {"bay_id": bay_id, "pose": item["pose"]} for bay_id, item in truth["oracle_by_bay"].items()}
    replay = GRADER.replay_run(public, placements)
    assert replay["passed"] is True
    assert len(replay["releases"]) == 3
    assert all(item["contact"] for item in replay["releases"])


def test_material_choice_constrains_every_lane_across_thirty_seeds() -> None:
    for level in range(2, 6):
        for seed_index in range(30):
            public, truth = GENERATOR.generate(_task(level, "full"), f"rube-material-{level}-{seed_index}")
            candidates: dict[str, list[tuple[str, float]]] = {}
            for bay in public["bays"]:
                rows = []
                valid_tools = set()
                for tool in public["tools"]:
                    for angle in public["contract"]["allowed_angles_deg"]:
                        pose = [float(bay["anchor"][0]), float(bay["anchor"][1]), float(angle)]
                        if GRADER.replay_lane(public, bay, tool, pose)["passed"]:
                            rows.append((tool["id"], float(angle)))
                            valid_tools.add(tool["id"])
                assert rows, (level, seed_index, bay["id"])
                assert len(valid_tools) < len(public["tools"]), (level, seed_index, bay["id"], valid_tools)
                candidates[bay["id"]] = rows

            def has_non_reusing_solution(index: int, used: set[str]) -> bool:
                if index == len(public["bays"]):
                    return True
                bay_id = public["bays"][index]["id"]
                return any(
                    tool_id not in used and has_non_reusing_solution(index + 1, used | {tool_id})
                    for tool_id, _angle in candidates[bay_id]
                )

            assert has_non_reusing_solution(0, set()), (level, seed_index)
            oracle_placements = {
                item["tool_id"]: {"bay_id": bay_id, "pose": item["pose"]}
                for bay_id, item in truth["oracle_by_bay"].items()
            }
            assert GRADER.replay_run(public, oracle_placements)["passed"] is True


def test_both_interactions_share_world_and_live_paused_share_decision_state() -> None:
    for level in range(1, 6):
        simple_public, simple_truth = GENERATOR.generate(_task(level, "simplified"), f"rube-pair-{level}")
        full_public, full_truth = GENERATOR.generate(_task(level, "full"), f"rube-pair-{level}")
        assert _without_identity(simple_public) == _without_identity(full_public)
        assert _without_identity(simple_truth) == _without_identity(full_truth)
        for interaction, public, truth in (("simplified", simple_public, simple_truth), ("full", full_public, full_truth)):
            assert GRADER.grade(_solution(public, truth, interaction), truth, public)["passed"] is True
        live, _ = GENERATOR.generate(_task(level, "full", "live"), f"rube-time-{level}")
        paused, _ = GENERATOR.generate(_task(level, "full", "paused"), f"rube-time-{level}")
        assert _without_identity(live) == _without_identity(paused)


def test_rewind_repair_and_adversarial_flight_claims_are_replayed() -> None:
    public, truth = GENERATOR.generate(_task(3, "full"), "rube-retry")
    repaired = _solution(public, truth, "full", failed_first=True)
    accepted = GRADER.grade(repaired, truth, public)
    assert accepted["passed"] is True, accepted

    wrong_source = copy.deepcopy(_solution(public, truth, "full"))
    wrong_source["events"][0]["input_source"] = "bay_place_button"
    assert GRADER.grade(wrong_source, truth, public)["passed"] is False

    off_station = copy.deepcopy(_solution(public, truth, "full"))
    first_place = next(item for item in off_station["events"] if item["kind"] == "place")
    first_place["pose"][0] += 3
    assert GRADER.grade(off_station, truth, public)["passed"] is False

    forged_contact = copy.deepcopy(_solution(public, truth, "full"))
    first_release = next(item for item in forged_contact["events"] if item["kind"] == "release")
    first_release["contact"][1] += 5
    assert GRADER.grade(forged_contact, truth, public)["passed"] is False

    missing_release = copy.deepcopy(_solution(public, truth, "full"))
    release_index = next(index for index, item in enumerate(missing_release["events"]) if item["kind"] == "release")
    missing_release["events"].pop(release_index)
    for index, event in enumerate(missing_release["events"], start=1):
        event["sequence"] = index
    assert GRADER.grade(missing_release, truth, public)["passed"] is False

    stale = copy.deepcopy(_solution(public, truth, "full"))
    stale["challenge_id"] = "stale-rube"
    assert GRADER.grade(stale, truth, public)["passed"] is False

    forged_impact = copy.deepcopy(repaired)
    failed_rollout = next(item for item in forged_impact["events"] if item["kind"] == "rollout_end" and item["bell_rung"] is False)
    failed_rollout["impact_error"] = 99
    assert GRADER.grade(forged_impact, truth, public)["passed"] is False


def test_full_drag_geometry_and_raw_gesture_evidence_are_enforced() -> None:
    public, truth = GENERATOR.generate(_task(2, "full"), "rube-drag-zones")
    accepted = _solution(public, truth, "full")
    first_place = next(item for item in accepted["events"] if item["kind"] == "place")
    first_bay = next(item for item in public["bays"] if item["id"] == first_place["bay_id"])

    boundary = copy.deepcopy(accepted)
    boundary_place = next(item for item in boundary["events"] if item["kind"] == "place")
    boundary_point = [float(first_bay["work_zone"][0]), float(first_bay["work_zone"][1])]
    boundary_place["gesture"]["release_stage"] = list(boundary_point)
    boundary_place["gesture"]["samples_stage"] = [list(boundary_point)]
    assert GRADER.grade(boundary, truth, public)["passed"] is True

    for release in ([10.0, 10.0], [0.0, 0.0], [760.0, 440.0], [800.0, 500.0]):
        off_station = copy.deepcopy(accepted)
        event = next(item for item in off_station["events"] if item["kind"] == "place")
        event["gesture"]["release_stage"] = list(release)
        event["gesture"]["samples_stage"] = [list(release)]
        assert GRADER.grade(off_station, truth, public)["passed"] is False

    missing_gesture = copy.deepcopy(accepted)
    next(item for item in missing_gesture["events"] if item["kind"] == "place").pop("gesture")
    assert GRADER.grade(missing_gesture, truth, public)["passed"] is False

    rejected_then_solved = copy.deepcopy(accepted)
    rejected_then_solved["events"].insert(0, {
        "kind": "drop_rejected",
        "tool_id": first_place["tool_id"],
        "input_source": "direct_drag",
        "gesture": {
            "origin": "rack",
            "start_tool_id": first_place["tool_id"],
            "start_stage": None,
            "samples_stage": [[10.0, 10.0]],
            "release_stage": [10.0, 10.0],
        },
    })
    for index, event in enumerate(rejected_then_solved["events"], start=1):
        event["sequence"] = index
    assert GRADER.grade(rejected_then_solved, truth, public)["passed"] is True

    forged_rejection = copy.deepcopy(rejected_then_solved)
    forged_rejection["events"][0]["gesture"]["samples_stage"] = [list(first_bay["anchor"])]
    forged_rejection["events"][0]["gesture"]["release_stage"] = list(first_bay["anchor"])
    assert GRADER.grade(forged_rejection, truth, public)["passed"] is False

    moved = copy.deepcopy(accepted)
    run_index = next(index for index, item in enumerate(moved["events"]) if item["kind"] == "run_start")
    first, second = public["bays"]
    first_tool = next(tool_id for tool_id, item in moved["placements"].items() if item["bay_id"] == first["id"])
    second_tool = next(tool_id for tool_id, item in moved["placements"].items() if item["bay_id"] == second["id"])
    first_angle = float(moved["placements"][first_tool]["pose"][2])
    second_angle = float(moved["placements"][second_tool]["pose"][2])

    def canvas_move(tool_id: str, source: dict, target: dict, angle: float) -> dict:
        start = [float(source["anchor"][0]), float(source["anchor"][1])]
        release = [float(target["anchor"][0]), float(target["anchor"][1])]
        return {
            "kind": "place",
            "tool_id": tool_id,
            "bay_id": target["id"],
            "pose": [release[0], release[1], angle],
            "input_source": "direct_drag",
            "gesture": {"origin": "canvas", "start_tool_id": tool_id, "start_stage": start, "samples_stage": [start, release], "release_stage": release},
        }

    second_release = [float(second["anchor"][0]), float(second["anchor"][1])]
    movement_events = [
        canvas_move(first_tool, first, second, first_angle),
        canvas_move(first_tool, second, first, first_angle),
        {
            "kind": "place",
            "tool_id": second_tool,
            "bay_id": second["id"],
            "pose": [second_release[0], second_release[1], second_angle],
            "input_source": "direct_drag",
            "gesture": {"origin": "rack", "start_tool_id": second_tool, "start_stage": None, "samples_stage": [second_release], "release_stage": second_release},
        },
    ]
    moved["events"][run_index:run_index] = movement_events
    for index, event in enumerate(moved["events"], start=1):
        event["sequence"] = index
    assert GRADER.grade(moved, truth, public)["passed"] is True

    simple_public, simple_truth = GENERATOR.generate(_task(2, "simplified"), "rube-drag-zones-simple")
    wrong_simple_source = _solution(simple_public, simple_truth, "simplified")
    next(item for item in wrong_simple_source["events"] if item["kind"] == "place")["input_source"] = "direct_drag"
    assert GRADER.grade(wrong_simple_source, simple_truth, simple_public)["passed"] is False


def test_renderer_uses_replayable_physics_without_visible_expected_mapping() -> None:
    source = (BENCHMARK / "shared_runtime/app/mechanics/rubes_last_piece.js").read_text(encoding="utf-8")
    assert "distanceToSegment" in source
    assert "projection" in source and "restitution" in source and "wind_y" in source
    assert "impact_speed" in source and "impact_tolerance" in source and "receiverEncountered" in source
    assert "expectedByBay" not in source and "key_mark" not in source
    assert '"direct_drag"' in source and '"bay_place_button"' in source
    assert '"direct_right_click"' in source and '"rotation_buttons"' in source
    assert 'state.control_condition?.interaction || "full"' in source
    assert 'data-trace-visible' in source
    assert 'item.trail = []; item.hidden = true' in source
    assert ': `STALL AT ${bay.label}`' in source
    assert 'bayAtDrop(release)' in source and '"drop_rejected"' in source
    assert 'samples_stage' in source and 'release_stage' in source

    solver_source = (BENCHMARK / "tools/incubator_solvers/rubes_last_piece.py").read_text(encoding="utf-8")
    assert "ground_truth" not in solver_source
    assert 'state_dir / "public_state.json"' in solver_source
