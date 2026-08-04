from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

from weird_captcha_gym.realtime import load_real_time_settings
from weird_captcha_gym.shared_scripts.setup_task import generate_task_state


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "magnetic_stripe_purgatory_env"
BASE_TASK = ENVIRONMENT / "tasks" / "magnetic_stripe_purgatory_seed_0001" / "task.json"
CONTROLS_PATH = ENVIRONMENT / "controls.json"
MECHANIC_PATH = BENCHMARK / "shared_runtime" / "app" / "mechanics" / "magnetic_stripe_purgatory.js"
ENV_PATH = ENVIRONMENT / "env.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MATERIALIZER = _load("magnetic_stripe_control_materializer", BENCHMARK / "tools" / "materialize_controlled_tasks.py")
GRADER = _load(
    "magnetic_stripe_control_grader",
    BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "magnetic_stripe_purgatory.py",
)
SOLVER = _load(
    "magnetic_stripe_control_solver",
    BENCHMARK / "tools" / "incubator_solvers" / "magnetic_stripe_purgatory.py",
)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


CONTROLS = _read(CONTROLS_PATH)
BASE = _read(BASE_TASK)
ENV = _read(ENV_PATH)


def _task(level: int, interaction: str) -> dict:
    return MATERIALIZER.controlled_task(
        BASE,
        mechanic_id="magnetic_stripe_purgatory",
        level=level,
        interaction=interaction,
        profile=CONTROLS["difficulty"][str(level)],
        task_dir_name=f"magnetic_stripe_purgatory_d{level}_{interaction}_seed_0001",
    )


def _without_control_identity(value: dict) -> dict:
    copied = copy.deepcopy(value)
    for field in ("task_id", "challenge_id", "control_condition"):
        copied.pop(field, None)
    return copied


def _center(rect: dict) -> list[int]:
    return [
        round(int(rect["x"]) + int(rect["width"]) / 2),
        round(int(rect["y"]) + int(rect["height"]) / 2),
    ]


def _passing_payload(truth: dict, interaction: str) -> dict:
    sources = {
        "simplified": {"insert": "card_reader_proxy", "swipe": "timed_swipe_proxy"},
        "full": {"insert": "direct_card_drag", "swipe": "direct_timed_swipe"},
    }[interaction]
    readers = {str(reader["id"]): reader for reader in truth["readers"]}
    events: list[dict] = []

    def record(kind: str, **details) -> None:
        events.append({"sequence": len(events) + 1, "kind": kind, **details})

    reader_states: dict[str, dict] = {}
    card_locations: dict[str, str] = {}
    for card in truth["cards"]:
        card_id = str(card["id"])
        reader_id = str(card["assigned_reader"])
        reader = readers[reader_id]
        start, end = _center(card["initial_rect"]), _center(reader["slot"])
        moves = int(truth["requirements"]["minimum_insert_moves"])
        duration = int(truth["requirements"]["minimum_insert_ms"]) + 40
        record("insert_down", card_id=card_id, point=start, elapsed_ms=0, input_source=sources["insert"])
        for index in range(1, moves + 1):
            point = [
                round(start[0] + (end[0] - start[0]) * index / moves),
                round(start[1] + (end[1] - start[1]) * index / moves),
            ]
            record("insert_move", card_id=card_id, point=point, elapsed_ms=round(duration * index / moves), input_source=sources["insert"])
        record("insert_up", card_id=card_id, reader_id=reader_id, point=end, duration_ms=duration, input_source=sources["insert"])
        track = reader["track"]
        x0 = int(track["x_start"] if track["direction"] == "ltr" else track["x_end"])
        x1 = int(track["x_end"] if track["direction"] == "ltr" else track["x_start"])
        y = int(track["y"])
        samples = int(reader["calibration"]["minimum_samples"])
        swipe_duration = int(reader["calibration"]["solver_ms"])
        record("swipe_down", reader_id=reader_id, card_id=card_id, point=[x0, y], elapsed_ms=0, input_source=sources["swipe"])
        for index in range(1, samples + 1):
            point = [round(x0 + (x1 - x0) * index / samples), y]
            record("swipe_move", reader_id=reader_id, card_id=card_id, point=point, elapsed_ms=round(swipe_duration * index / samples), input_source=sources["swipe"])
        record("swipe_up", reader_id=reader_id, card_id=card_id, point=[x1, y], duration_ms=swipe_duration, input_source=sources["swipe"])
        card_locations[card_id] = reader_id
        reader_states[reader_id] = {"card_id": card_id, "locked": True, "attempts": 1}
    record("audit")
    return {
        "mechanic_id": "magnetic_stripe_purgatory",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "events": events,
        "card_locations": card_locations,
        "reader_states": reader_states,
        "locked_count": len(readers),
        "invalid_insertions": 0,
        "swipe_attempts": len(readers),
        "reset_count": 0,
        "audit_count": 1,
        "interaction": interaction,
        "completed": True,
    }


def test_controls_define_l4_full_reference_and_shared_real_time_settings() -> None:
    MATERIALIZER.validate_controls(CONTROLS, ENVIRONMENT)
    assert CONTROLS["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    assert CONTROLS["real_time"] == load_real_time_settings("magnetic_stripe_purgatory").__dict__
    assert ENV["observation"] == [{"type": "frame_window", "fps": 10, "resolution": [1280, 720], "inline": False}]


def test_baseline_materializes_all_ten_and_preserves_the_original_world(tmp_path: Path) -> None:
    written = MATERIALIZER.materialize_environment(ENVIRONMENT, tmp_path)
    assert len(written) == 10
    assert {
        (_read(path / "task.json")["metadata"]["control_condition"]["difficulty"], _read(path / "task.json")["metadata"]["control_condition"]["interaction"])
        for path in written
    } == {(level, interaction) for level in range(1, 6) for interaction in ("simplified", "full")}
    for seed_index in range(64):
        seed = f"magnetic-stripe-baseline-{seed_index}"
        original_public, original_truth = generate_task_state(BASE, seed)
        baseline_public, baseline_truth = generate_task_state(_task(4, "full"), seed)
        assert baseline_public["challenge_id"] == original_public["challenge_id"]
        assert baseline_truth["challenge_id"] == original_truth["challenge_id"]
        assert _without_control_identity(baseline_public) == _without_control_identity(original_public)
        assert _without_control_identity(baseline_truth) == _without_control_identity(original_truth)


def test_profiles_change_the_active_problem_and_interaction_preserves_each_world() -> None:
    expected_counts = [1, 2, 3, 3, 4]
    expected_zones = [0, 0, 0, 2, 3]
    expected_samples = [8, 10, 11, 14, 18]
    for level, count, zones, samples in zip(range(1, 6), expected_counts, expected_zones, expected_samples):
        simple_public, simple_truth = generate_task_state(_task(level, "simplified"), "magnetic-stripe-profile")
        full_public, full_truth = generate_task_state(_task(level, "full"), "magnetic-stripe-profile")
        assert simple_public["challenge_id"] == full_public["challenge_id"]
        assert _without_control_identity(simple_public) == _without_control_identity(full_public)
        assert _without_control_identity(simple_truth) == _without_control_identity(full_truth)
        assert len(simple_truth["readers"]) == len(simple_truth["cards"]) == count
        assert {len(reader["interference_zones"]) for reader in simple_truth["readers"]} == {zones}
        assert {reader["calibration"]["minimum_samples"] for reader in simple_truth["readers"]} == {samples}
        assert simple_public["control_condition"] == simple_truth["control_condition"]


def test_lane_blocking_fields_create_a_feasible_noncentral_route() -> None:
    expected_fields = {5: 3}
    for level, field_count in expected_fields.items():
        _, truth = generate_task_state(_task(level, "full"), f"magnetic-stripe-fields-{level}")
        for reader in truth["readers"]:
            blocking = SOLVER._blocking_fields(reader)
            assert len(blocking) == field_count
            track = reader["track"]
            start_x = int(track["x_start"] if track["direction"] == "ltr" else track["x_end"])
            end_x = int(track["x_end"] if track["direction"] == "ltr" else track["x_start"])
            center_y = int(track["y"])
            samples = int(reader["calibration"]["minimum_samples"])
            center_path = [
                (round(start_x + (end_x - start_x) * index / samples), center_y)
                for index in range(samples + 1)
            ]
            blocked = GRADER._evaluate_swipe(reader, center_path, int(reader["calibration"]["solver_ms"]))
            assert blocked["feedback"] == "BAD READ"
            assert blocked["zone_hits"] > 0
            clearance_path = [tuple(round(value) for value in point) for point in SOLVER._clearance_points(reader)]
            cleared = GRADER._evaluate_swipe(reader, clearance_path, int(reader["calibration"]["solver_ms"]))
            assert cleared["feedback"] == "ACCEPTED"
            assert cleared["zone_hits"] == 0
            assert cleared["maximum_deviation"] <= int(reader["calibration"]["straightness_px"])


def test_grader_accepts_each_surface_and_rejects_the_other_mode_transcript() -> None:
    simple_public, simple_truth = generate_task_state(_task(4, "simplified"), "magnetic-stripe-replay")
    full_public, full_truth = generate_task_state(_task(4, "full"), "magnetic-stripe-replay")
    simple_payload = _passing_payload(simple_truth, "simplified")
    full_payload = _passing_payload(full_truth, "full")
    assert GRADER.grade(simple_payload, simple_truth, simple_public)["passed"] is True
    assert GRADER.grade(full_payload, full_truth, full_public)["passed"] is True
    wrong_surface = copy.deepcopy(full_payload)
    wrong_surface["task_id"] = simple_truth["task_id"]
    wrong_surface["challenge_id"] = simple_truth["challenge_id"]
    rejected = GRADER.grade(wrong_surface, simple_truth, simple_public)
    assert rejected["passed"] is False
    assert "wrong insertion interaction input" in rejected["feedback"]


def test_browser_feedback_uses_each_profile_geometry_contract() -> None:
    source = MECHANIC_PATH.read_text(encoding="utf-8")
    assert "function swipeRequirements(reader)" in source
    assert "function segmentHitsZone(first, second, zone)" in source
    assert "function pathHitsZone(points, zones)" in source
    assert "STATIC FIELD" in source
    for parameter in (
        "minimum_coverage_milli",
        "maximum_sample_gap_px",
        "maximum_backtrack_px",
        "straightness_px",
    ):
        assert parameter in source
    assert "points.length - 1 < 14" not in source
    assert "coverage < 920" not in source
    assert "backtrack > 18" not in source
    assert "maximumGap > 58" not in source
