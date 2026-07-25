from __future__ import annotations

import copy
import importlib.util
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "weird_captcha_gym"
CONTROLLED_ENVIRONMENTS = (
    "input_lag_forklift_env",
    "surreal_apple_on_tree_grid_env",
    "rotating_keyboard_env",
    "rotate_wrong_thing_upright_env",
    "insider_trading_captcha_env",
    "flat_prisoner_env",
    "board_game_captcha_env",
    "flat_pack_compliance_env",
    "specular_lighthouse_relay_env",
    "motion_only_ghost_jigsaw_env",
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SETUP = load_module("controlled_setup_task", BENCHMARK / "shared_scripts" / "setup_task.py")
MATERIALIZER = load_module(
    "controlled_task_materializer", BENCHMARK / "tools" / "materialize_controlled_tasks.py"
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def controls_for(env_name: str) -> dict:
    return read_json(BENCHMARK / "environments" / env_name / "controls.json")


def base_task_for(env_name: str, mechanic: str) -> dict:
    return read_json(
        BENCHMARK
        / "environments"
        / env_name
        / "tasks"
        / f"{mechanic}_seed_0001"
        / "task.json"
    )


def task_for_level(env_name: str, level: int) -> dict:
    controls = controls_for(env_name)
    mechanic = controls["mechanic_id"]
    interaction = controls["baseline"]["interaction"]
    return MATERIALIZER.controlled_task(
        base_task_for(env_name, mechanic),
        mechanic_id=mechanic,
        level=level,
        interaction=interaction,
        profile=controls["difficulty"][str(level)],
        task_dir_name=f"{mechanic}_d{level}_{interaction}_seed_0001",
    )


def generated_levels(env_name: str, seed: str = "controlled-profile-test"):
    return [SETUP.generate_task_state(task_for_level(env_name, level), seed) for level in range(1, 6)]


def without_control_identity(value: dict, *, extra: tuple[str, ...] = ()) -> dict:
    result = copy.deepcopy(value)
    for key in ("task_id", "challenge_id", "control_condition", *extra):
        result.pop(key, None)
    return result


def test_control_files_have_one_baseline_and_five_profiles() -> None:
    for env_name in CONTROLLED_ENVIRONMENTS:
        env_root = BENCHMARK / "environments" / env_name
        controls = controls_for(env_name)
        MATERIALIZER.validate_controls(controls, env_root)
        assert controls["baseline"]["difficulty"] in range(1, 6)
        assert controls["interaction"][controls["baseline"]["interaction"]]["implemented"] is True


def test_materializer_writes_50_deterministic_tasks(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    for env_name in CONTROLLED_ENVIRONMENTS:
        env_root = BENCHMARK / "environments" / env_name
        MATERIALIZER.materialize_environment(env_root, first)
        MATERIALIZER.materialize_environment(env_root, second)
    first_tasks = sorted(first.glob("*_env/tasks/*/task.json"))
    second_tasks = sorted(second.glob("*_env/tasks/*/task.json"))
    assert len(first_tasks) == len(second_tasks) == 50
    for left, right in zip(first_tasks, second_tasks):
        assert left.relative_to(first) == right.relative_to(second)
        assert left.read_bytes() == right.read_bytes()
        task = read_json(left)
        condition = task["metadata"]["control_condition"]
        assert condition["difficulty"] in range(1, 6)
        assert condition["real_time"] == "live"
        assert isinstance(condition["difficulty_parameters"], dict)
        assert Path(task["hooks"]["pre_task"]).parent.name == left.parent.name
        profile = controls_for(left.parents[2].name)["difficulty"][str(condition["difficulty"])]
        if "natural_language" in profile:
            assert task["natural_language"] == profile["natural_language"]


def test_original_tasks_match_their_independently_assigned_baselines() -> None:
    seed = "baseline-preservation"
    for env_name in CONTROLLED_ENVIRONMENTS:
        controls = controls_for(env_name)
        mechanic = controls["mechanic_id"]
        level = int(controls["baseline"]["difficulty"])
        original_public, original_truth = SETUP.generate_task_state(base_task_for(env_name, mechanic), seed)
        baseline_public, baseline_truth = SETUP.generate_task_state(task_for_level(env_name, level), seed)

        if mechanic == "rotating_keyboard":
            original_keyboard = original_public["keyboard"]
            baseline_keyboard = baseline_public["keyboard"]
            for key in ("target", "rows", "direction", "duration_ms"):
                assert baseline_keyboard[key] == original_keyboard[key]
            assert baseline_truth["target"] == original_truth["target"]
        elif mechanic == "input_lag_forklift":
            assert without_control_identity(baseline_public, extra=("queue_visibility",)) == without_control_identity(original_public)
            assert without_control_identity(baseline_truth, extra=("queue_visibility",)) == without_control_identity(original_truth)
        elif mechanic == "rotate_wrong_thing_upright":
            baseline_gimbal = copy.deepcopy(baseline_public["gimbal"])
            baseline_gimbal.pop("active_axes")
            baseline_gimbal.pop("target_needle_width")
            assert baseline_gimbal == original_public["gimbal"]
        elif mechanic == "insider_trading_captcha":
            assert without_control_identity(baseline_public, extra=("visible_chart_ticks",)) == without_control_identity(original_public)
            assert without_control_identity(baseline_truth, extra=("visible_chart_ticks",)) == without_control_identity(original_truth)
        else:
            assert without_control_identity(baseline_public) == without_control_identity(original_public)
            assert without_control_identity(baseline_truth) == without_control_identity(original_truth)


def test_forklift_profiles_match_board_route_and_delay_contracts() -> None:
    generated = generated_levels("input_lag_forklift_env")
    controls = controls_for("input_lag_forklift_env")
    for level, (public, truth) in enumerate(generated, start=1):
        parameters = controls["difficulty"][str(level)]["parameters"]
        assert public["warehouse"]["width"] == parameters["board_width"]
        assert public["warehouse"]["height"] == parameters["board_height"]
        assert len(public["warehouse"]["crates"]) == parameters["crate_count"]
        assert parameters["solution_length_min"] <= len(truth["solution"]) <= parameters["solution_length_max"]
        assert public["control_lag"] == parameters["control_lag"]
        assert truth["solution_issued_commands"][-parameters["control_lag"]:] == ["FLUSH"] * parameters["control_lag"]
        assert public["prompt"] == controls["difficulty"][str(level)]["natural_language"]
        if parameters["control_lag"] == 1:
            assert public["rules"]["flush"] == "EXECUTE QUEUE runs the pending direction without adding another."
        else:
            assert f"queued {parameters['control_lag']} inputs earlier" in public["rules"]["direction"]
            assert public["rules"]["flush"] == "EXECUTE QUEUE runs the oldest queued direction without adding another."


def test_orchard_profiles_match_visual_and_drag_contracts() -> None:
    generated = generated_levels("surreal_apple_on_tree_grid_env")
    controls = controls_for("surreal_apple_on_tree_grid_env")
    for level, (public, truth) in enumerate(generated, start=1):
        parameters = controls["difficulty"][str(level)]["parameters"]
        by_id = {apple["id"]: apple for apple in public["apples"]}
        detached_gaps = [
            abs(branch["points"][-1][2] - by_id[branch["fruit_id"]]["position"][2])
            for branch in public["branches"]
            if branch["fruit_id"] not in truth["attached_ids"]
        ]
        assert len(public["apples"]) == parameters["fruit_count"]
        assert len(truth["attached_ids"]) == parameters["attached_count"]
        assert all(parameters["depth_gap_min"] <= gap <= parameters["depth_gap_max"] for gap in detached_gaps)
        assert public["view_limit_deg"] == parameters["view_limit_deg"]
        assert all(parameters["fruit_radius_min"] <= apple["radius"] <= parameters["fruit_radius_max"] for apple in public["apples"])
        assert public["basket"]["width"] == parameters["basket_width"]
        assert public["basket"]["height"] == parameters["basket_height"]


def test_rotating_keyboard_profiles_match_motion_contracts() -> None:
    generated = generated_levels("rotating_keyboard_env")
    controls = controls_for("rotating_keyboard_env")
    for level, (public, truth) in enumerate(generated, start=1):
        parameters = controls["difficulty"][str(level)]["parameters"]
        keyboard = public["keyboard"]
        assert sum(len(row) for row in keyboard["rows"]) == parameters["key_count"]
        assert len(truth["target"]) == parameters["code_length"]
        assert keyboard["motion_profile"] == parameters["motion_profile"]
        assert keyboard["spin_after_characters"] == parameters["spin_after_characters"]
        if "duration_ms_values" in parameters:
            assert keyboard["duration_ms"] in parameters["duration_ms_values"]
        else:
            assert parameters["duration_ms_min"] <= keyboard["duration_ms"] <= parameters["duration_ms_max"]


def test_gimbal_profiles_match_axis_coupling_and_precision_contracts() -> None:
    generated = generated_levels("rotate_wrong_thing_upright_env")
    controls = controls_for("rotate_wrong_thing_upright_env")
    for level, (public, _truth) in enumerate(generated, start=1):
        parameters = controls["difficulty"][str(level)]["parameters"]
        gimbal = public["gimbal"]
        assert gimbal["active_axes"] == parameters["active_axes"]
        assert len(gimbal["views"]) == parameters["view_count"]
        assert gimbal["coupling"] == parameters["coupling"]
        assert gimbal["tolerance"] == parameters["tolerance"]
        assert gimbal["degrees_per_pixel"] == parameters["degrees_per_pixel"]
        assert gimbal["target_needle_width"] == parameters["target_needle_width"]
        for axis, angle in gimbal["initial"].items():
            if axis in parameters["active_axes"]:
                assert parameters["initial_angle_min"] <= abs(angle) <= parameters["initial_angle_max"]
            else:
                assert angle == 0


def test_market_profiles_match_time_state_and_price_contracts() -> None:
    generated = generated_levels("insider_trading_captcha_env")
    controls = controls_for("insider_trading_captcha_env")
    grader = load_module(
        "controlled_market_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "insider_trading_captcha.py",
    )
    for level, (public, truth) in enumerate(generated, start=1):
        parameters = controls["difficulty"][str(level)]["parameters"]
        assert parameters["tick_count_min"] <= public["tick_count"] <= parameters["tick_count_max"]
        assert public["order_delay_ticks"] == parameters["order_delay_ticks"]
        assert public["max_position"] == parameters["max_position"]
        assert public["target_profit_cents"] >= parameters["target_profit_floor_cents"]
        assert len(truth["causal_reference_ledger"]) >= parameters["reference_settlements_min"]
        assert public["prompt"] == controls["difficulty"][str(level)]["natural_language"]
        if "tick_ms_values" in parameters:
            assert public["tick_ms"] in parameters["tick_ms_values"]
        else:
            assert parameters["tick_ms_min"] <= public["tick_ms"] <= parameters["tick_ms_max"]
        orders = [{"tick": index, "side": side} for index, side in enumerate(truth["solver_actions"])]
        payload = {
            "mechanic_id": public["mechanic_id"],
            "task_id": public["task_id"],
            "challenge_id": public["challenge_id"],
            "orders": orders,
            "settlement_ledger": truth["solver_ledger"],
            "final": {"cash_cents": truth["max_profit_cents"] + truth["initial_cash_cents"], "position": 0},
        }
        assert grader.grade(payload, truth, public)["passed"] is True


def test_flat_prisoner_profiles_match_camera_decoy_and_traversal_contracts() -> None:
    controls = controls_for("flat_prisoner_env")
    for level, (public, truth) in enumerate(generated_levels("flat_prisoner_env"), start=1):
        parameters = controls["difficulty"][str(level)]["parameters"]
        assert len(public["platforms"]) == 5 + parameters["decoy_count"]
        assert math.isclose(public["initial_camera"]["pitch_deg"] - truth["solution"]["camera"]["pitch_deg"], parameters["pitch_offset_deg"])
        assert math.isclose(public["initial_camera"]["distance"] - truth["solution"]["camera"]["distance"], parameters["distance_offset"])
        assert public["controls"]["orbit_step_deg"] == parameters["orbit_step_deg"]
        assert public["controls"]["pan_step"] == parameters["pan_step"]
        assert public["physics"]["move_speed"] == parameters["move_speed"]
        assert public["physics"]["exit_radius"] == parameters["exit_radius"]
        assert public["requirements"]["minimum_camera_events"] == parameters["minimum_camera_events"]
        assert public["requirements"]["minimum_traversal_ticks"] == parameters["minimum_traversal_ticks"]


def test_board_game_profiles_match_lamp_obstacle_and_physics_contracts() -> None:
    controls = controls_for("board_game_captcha_env")
    for level, (public, truth) in enumerate(generated_levels("board_game_captcha_env"), start=1):
        parameters = controls["difficulty"][str(level)]["parameters"]
        assert len(public["switches"]) == parameters["lamp_count"]
        assert len(public["walls"]) == parameters["wall_count"]
        assert len(public["hazards"]) == parameters["hazard_count"]
        assert all(item["radius"] == parameters["lamp_radius"] for item in public["switches"])
        assert public["goal"]["radius"] == parameters["goal_radius"]
        for key in ("tick_ms", "acceleration", "friction", "maximum_speed", "bounce", "ball_radius"):
            assert public["physics"][key] == parameters[key]
        assert len(truth["solver_switch_waypoint_indices"]) == parameters["lamp_count"]


def test_flat_pack_profiles_match_part_socket_and_load_contracts() -> None:
    controls = controls_for("flat_pack_compliance_env")
    for level, (public, truth) in enumerate(generated_levels("flat_pack_compliance_env"), start=1):
        parameters = controls["difficulty"][str(level)]["parameters"]
        assert [item["id"] for item in public["parts"]] == parameters["part_ids"]
        assert len(public["joints"]) == len(parameters["part_ids"]) - 1
        assert len(public["load_steps"]) == parameters["load_step_count"]
        assert public["requirements"]["pose_tolerance"] == parameters["pose_tolerance"]
        assert public["requirements"]["angle_tolerance"] == parameters["angle_tolerance"]
        assert public["requirements"]["strain_limit"] == parameters["strain_limit"]
        assert set(public["compliance_model"]["joint_factors"]) == set(truth["expected_joint_ids"])
        compliance = public["compliance_model"]
        peak_sensor_strain = max(
            (
                abs(step["force_x"]) * compliance["force_x_scale"]
                + abs(step["force_y"]) * compliance["force_y_scale"]
            ) * max(compliance["joint_factors"].values())
            for step in public["load_steps"]
        )
        assert peak_sensor_strain <= public["requirements"]["strain_limit"]


def test_specular_profiles_match_mirror_round_motion_and_tracking_contracts() -> None:
    controls = controls_for("specular_lighthouse_relay_env")
    for level, (public, truth) in enumerate(generated_levels("specular_lighthouse_relay_env"), start=1):
        parameters = controls["difficulty"][str(level)]["parameters"]
        assert len(public["rounds"]) == parameters["round_count"]
        assert public["round_count"] == parameters["round_count"]
        assert truth["angle_tolerance_deg"] == parameters["angle_tolerance_deg"]
        for round_data in public["rounds"]:
            assert len(round_data["mirrors"]) == parameters["mirror_count"]
            assert all(item["length"] == parameters["mirror_length"] for item in round_data["mirrors"])
            assert round_data["receiver"]["radius"] == parameters["receiver_radius"]
            assert round_data["receiver"]["amplitude"] in parameters["receiver_amplitudes"]
            assert round_data["receiver"]["angular_rate"] in parameters["receiver_angular_rates"]
            assert round_data["angle_step_deg"] == parameters["angle_step_deg"]
            assert round_data["tolerance_px"] == parameters["tolerance_px"]
            assert round_data["required_charge_ticks"] == parameters["required_charge_ticks"]
            assert round_data["miss_decay_ticks"] == parameters["miss_decay_ticks"]


def test_ghost_jigsaw_profiles_match_grid_size_and_motion_contracts() -> None:
    controls = controls_for("motion_only_ghost_jigsaw_env")
    for level, (public, truth) in enumerate(generated_levels("motion_only_ghost_jigsaw_env"), start=1):
        parameters = controls["difficulty"][str(level)]["parameters"]
        visual = public["visual"]
        assert len(public["pieces"]) == parameters["piece_count"]
        assert len(truth["expected_positions"]) == parameters["piece_count"]
        assert visual["rows"] == parameters["rows"]
        assert visual["columns"] == parameters["columns"]
        assert visual["frame_count"] == parameters["frame_count"]
        assert visual["fps"] == parameters["fps"]
        assert visual["frame_step"] == parameters["frame_step"]
        assert visual["scroll_speed"] in parameters["scroll_speeds"]


def test_controlled_forklift_grader_replays_every_delay_level() -> None:
    grader = load_module(
        "controlled_forklift_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "input_lag_forklift.py",
    )
    for public, truth in generated_levels("input_lag_forklift_env", "forklift-grader-levels"):
        player, crates, walls, goals = grader._initial(truth)
        lag = int(truth["control_lag"])
        pending: list[str] = []
        events = []

        def pending_snapshot():
            return (pending[0] if pending else None) if lag == 1 else list(pending)

        for issued in truth["solution_issued_commands"]:
            before = grader._snapshot(player, crates)
            pending_before = pending_snapshot()
            executed = None
            if issued == "FLUSH":
                event_type = "flush"
                if pending:
                    executed = pending.pop(0)
                    player, crates, outcome = grader._move(player, crates, walls, executed)
                else:
                    outcome = "flushed_empty"
            else:
                event_type = "direction"
                if len(pending) < lag:
                    outcome = "queued"
                else:
                    executed = pending.pop(0)
                    player, crates, outcome = grader._move(player, crates, walls, executed)
                pending.append(issued)
            events.append({
                "sequence": len(events) + 1,
                "type": event_type,
                "issued": issued,
                "pending_before": pending_before,
                "executed": executed,
                "outcome": outcome,
                "before": before,
                "after": grader._snapshot(player, crates),
                "pending_after": pending_snapshot(),
            })
        payload = {
            "mechanic_id": public["mechanic_id"],
            "task_id": public["task_id"],
            "challenge_id": public["challenge_id"],
            "issued_commands": events,
            "final_state": grader._snapshot(player, crates),
            "pending_command": pending_snapshot(),
            "collisions": sum(event["outcome"].startswith("collision_") for event in events),
            "reset_count": 0,
            "calibration_history": [],
            "completed": not pending and set(crates) == set(goals),
        }
        assert grader.grade(payload, truth, public)["passed"] is True


def test_controlled_orchard_grader_accepts_each_target_count() -> None:
    grader = load_module(
        "controlled_orchard_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "surreal_apple_on_tree_grid.py",
    )
    for public, truth in generated_levels("surreal_apple_on_tree_grid_env", "orchard-grader-levels"):
        events = []

        def record(kind: str, **details) -> None:
            events.append({"sequence": len(events) + 1, "kind": kind, **details})

        limit = float(public["view_limit_deg"])
        start = [480.0, 260.0]
        record("orbit_start", point=start, angle_before=0.0)
        xs = [360, 240, 120, 0, 120, 240, 360, 480, 600, 720, 840, 960]
        xs.extend(950 if index % 2 == 0 else 960 for index in range(8))
        angles = [0.0]
        for x in xs:
            angle = max(-limit, min(limit, (x - start[0]) * 0.24))
            record("orbit_move", point=[float(x), 260.0], angle_after=round(angle, 2))
            angles.append(round(angle, 2))
        record("orbit_end", point=[float(xs[-1]), 260.0], angle=angles[-1])
        apple_by_id = {apple["id"]: apple for apple in truth["apples"]}
        basket = truth["basket"]
        destination = [basket["x"] + basket["width"] / 2, basket["y"] + basket["height"] / 2]
        for apple_id in truth["attached_ids"]:
            center = list(grader._project(apple_by_id[apple_id]["position"], angles[-1]))
            record("pluck_start", apple_id=apple_id, point=center, angle=angles[-1])
            for index in range(1, 5):
                fraction = index / 5
                point = [
                    center[0] + (destination[0] - center[0]) * fraction,
                    center[1] + (destination[1] - center[1]) * fraction,
                ]
                record("pluck_move", apple_id=apple_id, point=point, elapsed_ms=index * 20)
            record(
                "pluck_end",
                apple_id=apple_id,
                point=destination,
                duration_ms=100,
                in_basket=True,
                accepted=True,
            )
        record("seal")
        travel = round(sum(abs(right - left) for left, right in zip(angles, angles[1:])), 2)
        span = round(max(angles) - min(angles), 2)
        sectors = {grader._sector(angle) for angle in angles}
        payload = {
            "mechanic_id": public["mechanic_id"],
            "task_id": public["task_id"],
            "challenge_id": public["challenge_id"],
            "events": events,
            "final_angle_deg": angles[-1],
            "orbit_samples": len(xs),
            "orbit_span_deg": span,
            "orbit_travel_deg": travel,
            "view_sector_count": len(sectors),
            "plucked_ids": sorted(truth["attached_ids"]),
            "invalid_plucks": 0,
            "reset_count": 0,
            "seal_count": 1,
            "completed": True,
        }
        assert grader.grade(payload, truth, public)["passed"] is True


def solve_linear(matrix: list[list[float]], right: list[float]) -> list[float]:
    size = len(matrix)
    work = [row[:] + [right[index]] for index, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(work[row][column]))
        work[column], work[pivot] = work[pivot], work[column]
        scale = work[column][column]
        work[column] = [value / scale for value in work[column]]
        for row in range(size):
            if row == column:
                continue
            amount = work[row][column]
            work[row] = [work[row][index] - amount * work[column][index] for index in range(size + 1)]
    return [work[index][size] for index in range(size)]


def test_controlled_gimbal_grader_accepts_each_axis_and_coupling_profile() -> None:
    grader = load_module(
        "controlled_gimbal_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "rotate_wrong_thing_upright.py",
    )
    for public, truth in generated_levels("rotate_wrong_thing_upright_env", "gimbal-grader-levels"):
        contract = truth["gimbal"]
        axes = contract["active_axes"]
        coupling = contract["coupling"]
        effects = {
            "outer": {"outer": 1.0, "middle": 0.0, "inner": float(coupling["outer_to_inner"])},
            "middle": {"outer": float(coupling["middle_to_outer"]), "middle": 1.0, "inner": 0.0},
            "inner": {"outer": 0.0, "middle": float(coupling["inner_to_middle"]), "inner": 1.0},
        }
        matrix = [[effects[input_axis][output_axis] for input_axis in axes] for output_axis in axes]
        deltas = solve_linear(matrix, [-float(contract["initial"][axis]) for axis in axes])
        events = []
        for view in contract["views"]:
            events.append({"sequence": len(events) + 1, "kind": "view", "view": view})
        maximum = float(contract["max_drag_delta"])
        for axis, delta in zip(axes, deltas):
            remaining = delta
            while abs(remaining) > 1e-8:
                chunk = math.copysign(min(abs(remaining), maximum * 0.9), remaining)
                events.append({"sequence": len(events) + 1, "kind": "drag", "axis": axis, "delta": chunk})
                remaining -= chunk
        payload = {
            "mechanic_id": public["mechanic_id"],
            "challenge_id": public["challenge_id"],
            "events": events,
        }
        assert grader.grade(payload, truth, public)["passed"] is True


def test_every_controlled_generator_is_deterministic_and_binds_the_condition() -> None:
    for env_name in CONTROLLED_ENVIRONMENTS:
        challenge_ids = set()
        for level in range(1, 6):
            task = task_for_level(env_name, level)
            first = SETUP.generate_task_state(task, "controlled-determinism")
            second = SETUP.generate_task_state(task, "controlled-determinism")
            assert first == second
            challenge_ids.add(first[0]["challenge_id"])
            for state in first:
                assert state["control_condition"] == task["metadata"]["control_condition"]
        assert len(challenge_ids) == 5
