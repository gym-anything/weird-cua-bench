from __future__ import annotations

import copy
import importlib.util
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
GENERATOR_PATH = BENCHMARK / "shared_scripts" / "incubator_generators" / "rising_causeway.py"
GRADER_PATH = BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "rising_causeway.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = load_module("rising_causeway_test_generator", GENERATOR_PATH)
GRADER = load_module("rising_causeway_test_grader", GRADER_PATH)
CONTROLS = json.loads((BENCHMARK / "environments" / "rising_causeway_env" / "controls.json").read_text())


def task_for(level: int, interaction: str) -> dict:
    return {
        "id": f"rising_causeway_d{level}_{interaction}_seed_0001@0.2",
        "natural_language": "Read the chamber and reach the terminal.",
        "_control_condition": {
            "difficulty": level,
            "interaction": interaction,
            "real_time": "live",
            "difficulty_parameters": copy.deepcopy(CONTROLS["difficulty"][str(level)]["parameters"]),
        },
    }


def passing_events(truth: dict, interaction: str) -> list[dict]:
    source = "viewport_click" if interaction == "full" else "proxy_button"
    movement = "keyboard" if interaction == "full" else "control_button"
    events: list[dict] = []
    clock = [0.0]

    def add(kind: str, **fields) -> None:
        events.append({"seq": len(events) + 1, "t_ms": clock[0], "kind": kind, **fields})

    for stage in range(int(truth["required_red_stage"])):
        add("red_actuator", target_id="red-main", before_stage=stage, after_stage=stage + 1, input_source=source)
    add("stair_actuator", target_id="yellow-triple", high_end=truth["required_stair_end"], input_source=source)
    add("launcher_prime", launcher_id=truth["required_launcher_id"], input_source=source)
    launcher = next(item for item in truth["world"]["chamber"]["launchers"] if item["id"] == truth["required_launcher_id"])
    contact = launcher["contact"]
    move_speed = float(truth["world"]["chamber"]["rules"]["move_speed"])
    if abs(float(contact[1])) > 0.05:
        add("key_down", control="strafe_right" if float(contact[1]) > 0 else "strafe_left", input_source=movement)
        for _ in range(max(1, math.ceil(abs(float(contact[1])) / move_speed * 1000 / 40))):
            clock[0] += 40
            add("tick", dt_ms=40, input_source="physics")
        add("key_up", control="strafe_right" if float(contact[1]) > 0 else "strafe_left", input_source=movement)
    add("key_down", control="forward", input_source=movement)
    start_x = float(truth["world"]["chamber"]["start"]["position"][0])
    for _ in range(max(1, math.ceil((float(contact[0]) - start_x) / move_speed * 1000 / 40))):
        clock[0] += 40
        add("tick", dt_ms=40, input_source="physics")
    add("launch_start", launcher_id=truth["required_launcher_id"], contact=contact, velocity=launcher["launch_velocity"], input_source="contact_physics")
    flight_ms = float(truth["world"]["chamber"]["rules"]["flight_duration_ms"])
    for _ in range(int(flight_ms // 40)):
        clock[0] += 40
        add("tick", dt_ms=40, input_source="physics")
    target = truth["launch_target"]
    add("launch_land", launcher_id=truth["required_launcher_id"], x=target[0], y=target[1], z=target[2], flight_time_ms=flight_ms, input_source="contact_physics")
    terminal = truth["world"]["chamber"]["terminal"]["position"]
    speed = float(truth["world"]["chamber"]["rules"]["move_speed"])
    steps = max(1, math.ceil((float(terminal[0]) - float(target[0])) / speed * 1000 / 40))
    for _ in range(steps):
        clock[0] += 40
        add("tick", dt_ms=40, input_source="physics")
    add("key_up", control="forward", input_source=movement)
    clock[0] += 1
    add("terminal_activate", input_source=source)
    return events


def test_rising_profiles_are_deterministic_and_interaction_invariant() -> None:
    for level in range(1, 6):
        full_public, full_truth = GENERATOR.generate(task_for(level, "full"), "rising-profile-seed")
        simple_public, simple_truth = GENERATOR.generate(task_for(level, "simplified"), "rising-profile-seed")
        assert full_public["world"] == simple_public["world"]
        assert {key: value for key, value in full_truth.items() if key not in {"task_id", "control_condition"}} == {
            key: value for key, value in simple_truth.items() if key not in {"task_id", "control_condition"}
        }
        repeated_public, repeated_truth = GENERATOR.generate(task_for(level, "full"), "rising-profile-seed")
        assert repeated_public == full_public
        assert repeated_truth == full_truth
        assert len(full_truth["world"]["chamber"]["launchers"]) == int(CONTROLS["difficulty"][str(level)]["parameters"]["launcher_count"])


def test_rising_profile_contracts_match_required_launcher_orientation() -> None:
    _, level_one = GENERATOR.generate(task_for(1, "full"), "rising-orientation-seed")
    _, level_two = GENERATOR.generate(task_for(2, "full"), "rising-orientation-seed")
    assert level_one["world"]["chamber"]["launchers"][0]["kind"] == "floor"
    assert level_two["world"]["chamber"]["launchers"][0]["kind"] == "wall"


def test_rising_oracle_replays_all_ten_variants() -> None:
    for level in range(1, 6):
        for interaction in ("full", "simplified"):
            public, truth = GENERATOR.generate(task_for(level, interaction), f"rising-oracle-{level}")
            payload = {
                "mechanic_id": "rising_causeway",
                "task_id": truth["task_id"],
                "challenge_id": truth["challenge_id"],
                "interaction": interaction,
                "completed": True,
                "events": passing_events(truth, interaction),
            }
            result = GRADER.grade(payload, truth, public)
            assert result["passed"] is True, (level, interaction, result)


def test_rising_rejects_wrong_surface_stale_challenge_and_tampered_geometry() -> None:
    public, truth = GENERATOR.generate(task_for(4, "full"), "rising-rejection-seed")
    events = passing_events(truth, "full")
    wrong_surface = {
        "mechanic_id": "rising_causeway",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "interaction": "simplified",
        "completed": True,
        "events": events,
    }
    stale = dict(wrong_surface, interaction="full", challenge_id="stale")
    tampered_public = copy.deepcopy(public)
    tampered_public["world"]["chamber"]["terminal"]["position"][0] += 0.5
    assert GRADER.grade(wrong_surface, truth, public)["passed"] is False
    assert GRADER.grade(stale, truth, public)["passed"] is False
    assert GRADER.grade(dict(stale, challenge_id=truth["challenge_id"]), truth, tampered_public)["passed"] is False


def test_rising_rejects_a_short_contact_arc() -> None:
    public, truth = GENERATOR.generate(task_for(4, "full"), "rising-arc-seed")
    events = passing_events(truth, "full")
    landing = next(event for event in events if event["kind"] == "launch_land")
    landing["t_ms"] -= 300
    payload = {
        "mechanic_id": "rising_causeway",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "interaction": "full",
        "completed": True,
        "events": events,
    }
    assert GRADER.grade(payload, truth, public)["passed"] is False


def payload_for(public: dict, truth: dict, interaction: str = "full") -> dict:
    return {
        "mechanic_id": "rising_causeway", "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"], "interaction": interaction,
        "completed": True, "events": passing_events(truth, interaction),
    }


def test_rising_split_matches_materialized_conditions(tmp_path) -> None:
    env = BENCHMARK / "environments" / "rising_causeway_env"
    materializer = load_module("rising_materializer_test", BENCHMARK / "tools" / "materialize_controlled_tasks.py")
    generated = materializer.materialize_environment(env, tmp_path)
    split = json.loads((BENCHMARK / "splits" / "rising_causeway_split.json").read_text())
    assert set(split["variations_tasks"]) == {p.name for p in generated}
    assert len(generated) == 10
    # Generated variants are ignored: a fresh checkout has only the baseline.
    repeated = materializer.materialize_environment(env, tmp_path / "repeat")
    assert [task.name for task in generated] == [task.name for task in repeated]
    for task, repeated_task in zip(generated, repeated):
        assert json.loads((repeated_task / "task.json").read_text()) == json.loads((task / "task.json").read_text())
        assert (repeated_task / "verifier.py").read_bytes() == (task / "verifier.py").read_bytes()


def test_rising_accepts_thinking_time_within_play_budget() -> None:
    public, truth = GENERATOR.generate(task_for(4, "full"), "rising-long-run")
    payload = payload_for(public, truth)
    idle = [{"kind": "tick", "dt_ms": 40, "t_ms": (i + 1) * 40, "input_source": "physics"} for i in range(2500)]
    for event in payload["events"]:
        event["t_ms"] += 100000
    payload["events"] = idle + payload["events"]
    for i, event in enumerate(payload["events"], 1):
        event["seq"] = i
    assert payload["events"][-1]["t_ms"] < 180000
    assert GRADER.grade(payload, truth, public)["passed"] is True


def test_rising_grader_matches_active_browser_control_limits() -> None:
    public, truth = GENERATOR.generate(task_for(1, "full"), "rising-control-limits")
    original = payload_for(public, truth)
    # Browser red extension stops at the active profile maximum.
    extra_red = copy.deepcopy(original)
    extra_red["events"][1:1] = [
        {"kind": "red_actuator", "target_id": "red-main", "before_stage": before,
         "after_stage": after, "input_source": "viewport_click", "t_ms": 0}
        for before, after in ((1, 2), (2, 3), (3, 0), (0, 1))
    ]
    for i, event in enumerate(extra_red["events"], 1):
        event["seq"] = i
    assert GRADER.grade(extra_red, truth, public)["passed"] is False
    wrong_tick = copy.deepcopy(original)
    next(e for e in wrong_tick["events"] if e["kind"] == "tick")["dt_ms"] = 80
    assert GRADER.grade(wrong_tick, truth, public)["passed"] is False
    in_flight = copy.deepcopy(original)
    idx = next(i for i, e in enumerate(in_flight["events"]) if e["kind"] == "launch_start")
    in_flight["events"].insert(idx + 1, {
        "kind": "launcher_prime", "launcher_id": truth["required_launcher_id"],
        "input_source": "viewport_click", "t_ms": in_flight["events"][idx]["t_ms"],
    })
    for i, event in enumerate(in_flight["events"], 1):
        event["seq"] = i
    assert GRADER.grade(in_flight, truth, public)["passed"] is False
    overflow = copy.deepcopy(original)
    overflow["events"][0]["seq"] = float("inf")
    assert GRADER.grade(overflow, truth, public)["passed"] is False


def test_rising_exported_verifier_replays_without_trusting_server_grade() -> None:
    import shutil
    verifier = load_module("rising_exported_verifier_test", BENCHMARK / "environments" / "rising_causeway_env" / "tasks" / "rising_causeway_seed_0001" / "verifier.py")
    for interaction in ("full", "simplified"):
        public, truth = GENERATOR.generate(task_for(4, interaction), "rising-verifier")
        payload = payload_for(public, truth, interaction)
        exported = {"public_state": public, "ground_truth": truth, "result": payload}

        def copy_from_env(source: str, target: str) -> None:
            assert source == "/tmp/task_result.json"
            Path(target).write_text(json.dumps(exported))

        assert verifier.verify_task(env_info={"copy_from_env": copy_from_env})["passed"] is True
        payload["challenge_id"] = "stale"
        payload["server_grade"] = {"passed": True, "score": 100}
        assert verifier.verify_task(env_info={"copy_from_env": copy_from_env})["passed"] is False
