from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "weird_captcha_gym"
ENV = BENCH / "environments" / "letter_rapids_env"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("test_letter_rapids_generator", BENCH / "shared_scripts" / "incubator_generators" / "letter_rapids.py")
GRADER = _load("test_letter_rapids_grader", BENCH / "shared_runtime" / "server" / "incubator_graders" / "letter_rapids.py")
CONTROLS = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
BASE_TASK = json.loads((ENV / "tasks" / "letter_rapids_seed_0001" / "task.json").read_text(encoding="utf-8"))


def _task(level: int, interaction: str, real_time: str = "live") -> dict:
    task = copy.deepcopy(BASE_TASK)
    profile = CONTROLS["difficulty"][str(level)]
    task["_control_condition"] = {
        "difficulty": level,
        "difficulty_label": profile["label"],
        "difficulty_parameters": copy.deepcopy(profile["parameters"]),
        "interaction": interaction,
        "real_time": real_time,
    }
    return task


def _band_midpoint(truth: dict, output: str, symbol: str) -> int:
    row = truth["probability_rows"][output[-1] if output else "^"]
    displayed = GRADER._display_row(row, int(truth["simulation"]["display_band_floor_milli"]))
    _, start, end = next(item for item in displayed if item[0]["symbol"] == symbol)
    return (start + end) // 2


def _delta(truth: dict, tick: int, x_milli: int = 9500) -> int:
    sim = truth["simulation"]
    edge = int(sim["neutral_x_milli"]) + int(sim["dead_zone_half_width_milli"])
    return (
        int(sim["maximum_speed_units_per_second"])
        * int(sim["tick_ms"])
        * (x_milli - edge)
        * int(truth["current_pattern_milli"][tick])
        // (1000 * (10_000 - edge) * 1000)
    )


def _solved_payload(public: dict, truth: dict, interaction: str, x_milli: int = 9500) -> dict:
    events = []
    tick = 0
    travel = 0
    output = ""
    for symbol in truth["target"]:
        events.append(
            {
                "seq": len(events) + 1,
                "tick": tick,
                "type": "pointer",
                "x_milli": x_milli,
                "y_milli": _band_midpoint(truth, output, symbol),
                "input_source": "canyon_pointer" if interaction == "full" else "axis_proxy",
            }
        )
        progress = 0
        while progress < int(truth["simulation"]["commit_units"]):
            amount = _delta(truth, tick, x_milli)
            progress += amount
            travel += amount
            tick += 1
        output += symbol
    return {
        "mechanic_id": "letter_rapids",
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "events": events,
        "interaction_mode": interaction,
        "completed": True,
        "output": output,
        "terminal_reason": "target",
        "terminal_tick": tick,
        "travel_used_units": travel,
        "committed_characters": len(output),
        "rewound_characters": 0,
        "progress_units": 0,
    }


def _world_without_condition(value: dict) -> dict:
    result = copy.deepcopy(value)
    result.pop("control_condition", None)
    result.pop("challenge_id", None)
    return result


def test_baseline_is_exact_l4_full_world() -> None:
    uncontrolled_public, uncontrolled_truth = GENERATOR.generate(BASE_TASK, "letter-rapids-baseline")
    controlled_public, controlled_truth = GENERATOR.generate(_task(4, "full"), "letter-rapids-baseline")
    assert _world_without_condition(uncontrolled_public) == _world_without_condition(controlled_public)
    hidden_a = _world_without_condition(uncontrolled_truth)
    hidden_b = _world_without_condition(controlled_truth)
    assert hidden_a == hidden_b
    assert CONTROLS["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}


def test_all_twenty_control_conditions_preserve_world_across_interaction_and_clock_and_grade() -> None:
    for level in range(1, 6):
        seed = f"letter-rapids-matrix-{level}"
        reference = None
        for real_time in ("live", "paused"):
            for interaction in ("full", "simplified"):
                public, truth = GENERATOR.generate(_task(level, interaction, real_time), seed)
                world = _world_without_condition(public)
                if reference is None:
                    reference = world
                else:
                    assert world == reference
                grade = GRADER.grade(_solved_payload(public, truth, interaction), truth, public)
                assert grade["passed"] is True, grade


def test_probability_rows_are_gapless_and_profiles_change_active_control_problem() -> None:
    snapshots = []
    for level in range(1, 6):
        public, truth = GENERATOR.generate(_task(level, "full"), f"letter-rapids-profile-{level}")
        for row in public["probability_rows"].values():
            assert row[0]["start_milli"] == 0
            assert row[-1]["end_milli"] == 10_000
            assert all(first["end_milli"] == second["start_milli"] for first, second in zip(row, row[1:]))
            assert {item["symbol"] for item in row} == set(public["alphabet"])
            displayed = GRADER._display_row(row, int(truth["simulation"]["display_band_floor_milli"]))
            assert displayed[0][1] == 0 and displayed[-1][2] == 10_000
            assert all(first[2] == second[1] for first, second in zip(displayed, displayed[1:]))
            assert min(end - start for _, start, end in displayed) >= 340
        params = CONTROLS["difficulty"][str(level)]["parameters"]
        snapshots.append(
            (
                len(public["alphabet"]),
                min(item["end_milli"] - item["start_milli"] for item in public["probability_rows"]["^"]),
                int(truth["simulation"]["dead_zone_half_width_milli"]),
                int(truth["simulation"]["maximum_speed_units_per_second"]),
                int(params["current_amplitude_milli"]),
                max(len(target) for target in params["target_pool"]),
            )
        )
    assert [item[0] for item in snapshots] == [8, 12, 20, 27, 27]
    assert [item[2] for item in snapshots] == sorted((item[2] for item in snapshots), reverse=True)
    assert [item[3] for item in snapshots] == sorted(item[3] for item in snapshots)
    assert [item[4] for item in snapshots] == sorted(item[4] for item in snapshots)
    assert snapshots[-1][-1] > snapshots[-2][-1]


def test_required_l4_l5_display_channels_are_not_tiny_targets() -> None:
    canyon_height = 538
    for level in (4, 5):
        for seed_index in range(250):
            _, truth = GENERATOR.generate(_task(level, "full"), f"letter-rapids-target-size-{level}-{seed_index}")
            output = ""
            for symbol in truth["target"]:
                row = truth["probability_rows"][output[-1] if output else "^"]
                displayed = GRADER._display_row(row, int(truth["simulation"]["display_band_floor_milli"]))
                _, start, end = next(item for item in displayed if item[0]["symbol"] == symbol)
                assert (end - start) / 10_000 * canyon_height >= 18
                output += symbol


def test_grader_rejects_wrong_surface_stale_identity_and_tampering() -> None:
    public, truth = GENERATOR.generate(_task(4, "full"), "letter-rapids-adversarial")
    payload = _solved_payload(public, truth, "full")
    wrong_surface = copy.deepcopy(payload)
    wrong_surface["events"][0]["input_source"] = "axis_proxy"
    assert "wrong interaction input" in GRADER.grade(wrong_surface, truth, public)["feedback"]
    stale = copy.deepcopy(payload)
    stale["challenge_id"] = "stale"
    assert "challenge identity" in GRADER.grade(stale, truth, public)["feedback"]
    tampered = copy.deepcopy(payload)
    tampered["travel_used_units"] -= 1
    assert "travel used" in GRADER.grade(tampered, truth, public)["feedback"]
    truncated = copy.deepcopy(payload)
    truncated["terminal_tick"] -= 1
    assert GRADER.grade(truncated, truth, public)["passed"] is False

    baseline_public, baseline_truth = GENERATOR.generate(BASE_TASK, "letter-rapids-uncontrolled-binding")
    baseline_payload = _solved_payload(baseline_public, baseline_truth, "full")
    assert GRADER.grade(baseline_payload, baseline_truth, baseline_public)["passed"] is True
    baseline_payload["events"][0]["input_source"] = "axis_proxy"
    assert "wrong interaction input" in GRADER.grade(baseline_payload, baseline_truth, baseline_public)["feedback"]


def test_both_interaction_modes_expose_the_same_intermediate_flow_effect() -> None:
    for interaction in ("full", "simplified"):
        public, truth = GENERATOR.generate(_task(4, interaction), "letter-rapids-continuous-flow")
        payload = _solved_payload(public, truth, interaction, x_milli=7200)
        assert {event["x_milli"] for event in payload["events"]} == {7200}
        assert GRADER.grade(payload, truth, public)["passed"] is True


def test_recent_frames_expose_current_trend_and_action_value_expires() -> None:
    _, truth = GENERATOR.generate(_task(4, "full"), "letter-rapids-realtime-witness")
    pattern = truth["current_pattern_milli"]
    window = 12  # 600 ms at the 50 ms simulation tick.
    rising = next(index for index in range(window, len(pattern) - window) if pattern[index] - pattern[index - window] > 130)
    falling = next(index for index in range(window, len(pattern) - window) if pattern[index - window] - pattern[index] > 130)
    rising_travel = sum(_delta(truth, tick) for tick in range(rising, rising + 8))
    falling_travel = sum(_delta(truth, tick) for tick in range(falling, falling + 8))
    assert abs(rising_travel - falling_travel) > 500
    assert len(set(pattern[rising - window:rising + 1])) > 6
    assert len(set(pattern[falling - window:falling + 1])) > 6


def test_repository_registration_and_interaction_surface_contract() -> None:
    manifest = json.loads((BENCH / "benchmark_manifest.json").read_text(encoding="utf-8"))
    settings = json.loads((BENCH / "real_time.json").read_text(encoding="utf-8"))
    split = json.loads((BENCH / "splits" / "letter_rapids_split.json").read_text(encoding="utf-8"))
    frontend = (BENCH / "shared_runtime" / "app" / "mechanics" / "letter_rapids.js").read_text(encoding="utf-8")
    assert "letter_rapids_env" in manifest["environments"]
    assert manifest["environment_count"] == len(manifest["environments"])
    assert settings["environments"]["letter_rapids"] == CONTROLS["real_time"]
    assert len(split["variations_tasks"]) == 20
    assert 'input_source = inputSource' in frontend
    assert '"canyon_pointer"' in frontend and '"axis_proxy"' in frontend
    assert 'id="rapids-flow" type="range" min="0" max="10000" step="1"' in frontend
    assert "NEXT WANTED" not in frontend and "data-state" not in frontend
    assert "legacy_agent_sample_population" in BASE_TASK["metadata"]
    assert BASE_TASK["metadata"]["legacy_agent_sample_population"] is False
    assert "x === model.pointer.x && y === model.pointer.y) return" in frontend
