from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path

from weird_captcha_gym.shared_scripts import setup_task as SETUP
from weird_captcha_gym.tools import materialize_controlled_tasks as MATERIALIZER


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "weird_captcha_gym"
ENV = BENCH / "environments" / "silent_colleague_env"
GENERATOR_PATH = BENCH / "shared_scripts" / "incubator_generators" / "silent_colleague.py"
GRADER_PATH = BENCH / "shared_runtime" / "server" / "incubator_graders" / "silent_colleague.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("silent_colleague_generator_test", GENERATOR_PATH)
GRADER = _load("silent_colleague_grader_test", GRADER_PATH)


def _task(level: int, interaction: str, real_time: str = "live") -> dict:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/silent_colleague_seed_0001/task.json").read_text(encoding="utf-8"))
    task["_control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": copy.deepcopy(controls["difficulty"][str(level)]["parameters"]),
    }
    return task


def _winning_payload(public: dict, truth: dict, interaction: str) -> dict:
    sim = GRADER._initial(public)
    events: list[dict] = []
    sources = {"full": {"move": "keyboard_move", "use": "keyboard_action"}, "simplified": {"move": "proxy_step", "use": "proxy_action"}}

    def record(action: str) -> None:
        claim = GRADER.apply_action(sim, action)
        events.append({"sequence": len(events) + 1, "tick": sim["tick"], "input_source": sources[interaction][claim["kind"]], **claim})

    def move_to(target: int) -> None:
        size = int(sim["workshop"]["loop_size"])
        for _ in range(size * 3):
            if sim["player_pos"] == target:
                return
            cw_path = [(sim["player_pos"] + step) % size for step in range(1, (target - sim["player_pos"]) % size + 1)]
            ccw_path = [(sim["player_pos"] - step) % size for step in range(1, (sim["player_pos"] - target) % size + 1)]
            if sim["npc_pos"] not in cw_path and (sim["npc_pos"] in ccw_path or len(cw_path) <= len(ccw_path)):
                direction = 1
            else:
                direction = -1
            record("cw" if direction > 0 else "ccw")
        raise AssertionError(f"could not route to {target}")

    def advance_with_yield(direction: int) -> None:
        GRADER.advance_to(sim, sim["tick"] + 1)
        size = int(sim["workshop"]["loop_size"])
        if sim["npc_phase"] not in {"press_wait"} and (sim["npc_pos"] + direction) % size == sim["player_pos"]:
            record("cw" if direction > 0 else "ccw")

    workshop = truth["workshop"]
    for index, ticket_id in enumerate(workshop["runtime_ticket_sequence"]):
        current = next(item for item in workshop["tickets"] if item["id"] == ticket_id)
        fruit = next(item for item in workshop["fruits"] if item["id"] == current["fruit_id"])
        move_to(int(fruit["station"]))
        record("use")
        move_to(int(workshop["stations"]["handoff"]))
        record("use")
        for _ in range(200):
            if sim["npc_phase"] == "press_wait":
                break
            advance_with_yield(int(current["direction"]))
        else:
            raise AssertionError("colleague did not prime the press")
        move_to(int(workshop["stations"]["player_press"]))
        record("use")
        for _ in range(200):
            if sim["ticket_index"] > index:
                break
            advance_with_yield(int(current["direction"]))
        else:
            raise AssertionError("colleague did not deliver the sealed jar")
    return {
        "mechanic_id": public["mechanic_id"], "task_id": public["task_id"], "challenge_id": public["challenge_id"],
        "interaction_mode": interaction, "events": events, "final_tick": sim["tick"], "final_state": GRADER.snapshot(sim), "completed": True,
    }


def test_all_ten_conditions_share_world_and_grade() -> None:
    for level in range(1, 6):
        worlds = []
        for interaction in ("simplified", "full"):
            public, truth = GENERATOR.generate(_task(level, interaction), "same-world")
            decision = GRADER.grade(_winning_payload(public, truth, interaction), truth, public)
            assert decision["passed"] is True, (level, interaction, decision)
            worlds.append(public["workshop"])
        assert worlds[0] == worlds[1]


def test_original_task_is_the_exact_d4_configuration() -> None:
    task = json.loads((ENV / "tasks/silent_colleague_seed_0001/task.json").read_text(encoding="utf-8"))
    original_public, original_truth = GENERATOR.generate(task, "baseline-preservation")
    baseline_public, baseline_truth = GENERATOR.generate(_task(4, "full"), "baseline-preservation")
    assert original_public["parameters"] == baseline_public["parameters"]
    assert original_public["workshop"] == baseline_public["workshop"]
    assert original_truth["parameters"] == baseline_truth["parameters"]
    assert original_truth["workshop"] == baseline_truth["workshop"]


def test_fixed_seed_matches_dashboard_and_sorted_materialized_paths(tmp_path: Path) -> None:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    base = json.loads((ENV / "tasks/silent_colleague_seed_0001/task.json").read_text(encoding="utf-8"))
    MATERIALIZER.materialize_environment(ENV, tmp_path)

    for interaction in ("simplified", "full"):
        for level in range(1, 6):
            task_dir_name = f"silent_colleague_d{level}_{interaction}_seed_0001"
            in_memory = MATERIALIZER.controlled_task(
                base,
                mechanic_id="silent_colleague",
                level=level,
                interaction=interaction,
                profile=controls["difficulty"][str(level)],
                task_dir_name=task_dir_name,
            )
            materialized = json.loads(
                (tmp_path / ENV.name / "tasks" / task_dir_name / "task.json").read_text(encoding="utf-8")
            )
            assert in_memory == materialized

            seed = f"canonical-path-d{level}-{interaction}"
            direct_public, direct_truth = SETUP.generate_task_state(in_memory, seed)
            materialized_public, materialized_truth = SETUP.generate_task_state(materialized, seed)
            assert direct_public["challenge_id"] == materialized_public["challenge_id"]
            assert direct_public["workshop"] == materialized_public["workshop"]
            assert direct_truth == materialized_truth


def test_generation_is_deterministic_varied_and_solvable() -> None:
    seen = set()
    for level in range(1, 6):
        for index in range(24):
            seed = f"silent-colleague-{level}-{index}"
            public, truth = GENERATOR.generate(_task(level, "full"), seed)
            again = GENERATOR.generate(_task(level, "full"), seed)
            assert (public, truth) == again
            payload = _winning_payload(public, truth, "full")
            assert GRADER.grade(payload, truth, public)["passed"] is True
            assert payload["final_tick"] * public["parameters"]["tick_ms"] < 180_000
            assert {item["direction"] for item in truth["workshop"]["tickets"]} == {truth["workshop"]["circulation"]}
            seen.add((tuple(truth["workshop"]["runtime_ticket_sequence"]), tuple(item["fruit_id"] for item in truth["workshop"]["tickets"])))
    assert len(seen) >= 80


def test_split_handoff_keeps_wrong_fruit_recoverable() -> None:
    public, _truth = GENERATOR.generate(_task(4, "full", "paused"), "recoverable-handoff")
    stations = public["workshop"]["stations"]
    assert stations["handoff"] != stations["colleague_handoff"]
    sim = GRADER._initial(public)
    current = GRADER._ticket(sim)
    assert current is not None
    wrong = next(item for item in public["workshop"]["fruits"] if item["id"] != current["fruit_id"])
    sim["player_pos"] = int(wrong["station"])
    GRADER.apply_action(sim, "use")
    sim["player_pos"] = int(stations["handoff"])
    GRADER.apply_action(sim, "use")
    sim["player_pos"] = (int(stations["handoff"]) - 1) % int(public["workshop"]["loop_size"])
    sim["npc_phase"] = "handoff"
    sim["npc_pos"] = int(stations["colleague_handoff"])
    GRADER.advance_to(sim, sim["tick"] + 1)
    assert sim["shelf"] == wrong["id"]
    assert sim["npc_pos"] != int(stations["handoff"])
    sim["player_pos"] = int(stations["handoff"])
    effect = GRADER.apply_action(sim, "use")
    assert effect["effect"] == "retrieve_handoff"
    assert sim["shelf"] is None


def test_replay_rejects_stale_wrong_surface_empty_and_forged_claims() -> None:
    public, truth = GENERATOR.generate(_task(4, "full"), "negative-contract")
    good = _winning_payload(public, truth, "full")
    stale = copy.deepcopy(good)
    stale["challenge_id"] = "stale"
    assert GRADER.grade(stale, truth, public)["passed"] is False
    wrong_surface = copy.deepcopy(good)
    wrong_surface["events"][0]["input_source"] = "proxy_step"
    assert "input surface" in GRADER.grade(wrong_surface, truth, public)["feedback"]
    forged = copy.deepcopy(good)
    forged["events"][0]["to"] = 999
    assert "claim disagrees" in GRADER.grade(forged, truth, public)["feedback"]
    empty = copy.deepcopy(good)
    empty["events"] = []
    assert "empty" in GRADER.grade(empty, truth, public)["feedback"]
    wrong_final = copy.deepcopy(good)
    wrong_final["final_state"]["delivered"] = []
    assert "final workshop state" in GRADER.grade(wrong_final, truth, public)["feedback"]


def test_live_and_paused_preserve_world_and_control_parameters() -> None:
    live, _ = GENERATOR.generate(_task(4, "full", "live"), "time-pair")
    paused, _ = GENERATOR.generate(_task(4, "full", "paused"), "time-pair")
    assert live["workshop"] == paused["workshop"]
    assert live["parameters"] == paused["parameters"]
    assert live["control_condition"]["real_time"] == "live"
    assert paused["control_condition"]["real_time"] == "paused"


def test_difficulty_profiles_change_information_ambiguity_and_timing() -> None:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    profiles = [controls["difficulty"][str(level)]["parameters"] for level in range(1, 6)]
    assert [item["ticket_count"] for item in profiles] == [1, 2, 3, 4, 5]
    assert [item["label_count"] for item in profiles] == [2, 3, 3, 4, 5]
    assert [item["intent_mode"] for item in profiles] == ["fruit_badge", "label_badge", "hover_badge", "position_only", "position_only"]
    assert [item["signal_ticks"] for item in profiles] == [8, 7, 5, 5, 4]
    assert [item["press_window_ticks"] for item in profiles] == [7, 6, 5, 4, 4]
    assert [item["tick_ms"] for item in profiles] == [800, 720, 650, 600, 520]
    assert all(item["tick_ms"] <= controls["real_time"]["observation_window_ms"] for item in profiles)


def test_timing_parameters_count_exact_visible_states() -> None:
    for level in range(1, 6):
        public, _truth = GENERATOR.generate(_task(level, "full"), f"exact-timing-{level}")
        sim = GRADER._initial(public)
        current = GRADER._ticket(sim)
        assert current is not None
        rack = int(GRADER._label(sim, current["label_id"])["station"])
        sim["player_pos"] = (rack + 5) % int(sim["workshop"]["loop_size"])
        visible_rack_states = 0
        for _ in range(100):
            GRADER.advance_to(sim, sim["tick"] + 1)
            if sim["npc_pos"] == rack and sim["npc_phase"] == "signal":
                visible_rack_states += 1
            if sim["npc_phase"] == "jar":
                break
        assert visible_rack_states == public["parameters"]["signal_ticks"]
        assert sim["npc_pos"] != rack

        sim["npc_phase"] = "press"
        sim["npc_pos"] = int(sim["workshop"]["stations"]["colleague_press"])
        GRADER.advance_to(sim, sim["tick"] + 1)
        accepted_states = 0
        while sim["npc_phase"] == "press_wait":
            accepted_states += 1
            assert sim["prime_until"] - sim["tick"] + 1 == public["parameters"]["press_window_ticks"] - accepted_states + 1
            GRADER.advance_to(sim, sim["tick"] + 1)
        assert accepted_states == public["parameters"]["press_window_ticks"]


def test_registration_metadata_files_and_browser_surfaces() -> None:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    env = json.loads((ENV / "env.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/silent_colleague_seed_0001/task.json").read_text(encoding="utf-8"))
    split = json.loads((BENCH / "splits/silent_colleague_split.json").read_text(encoding="utf-8"))
    manifest = json.loads((BENCH / "benchmark_manifest.json").read_text(encoding="utf-8"))
    real_time = json.loads((BENCH / "real_time.json").read_text(encoding="utf-8"))["environments"]
    assert controls["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    assert task["name"] == "The Silent Colleague"
    assert task["difficulty"] == "hard"
    assert task["metadata"]["source_anchors"] == ["XAGT-208", "XAGT-209", "XAGT-212", "XAGT-213", "XAGT-202"]
    assert task["metadata"]["status"] == "prototype_visual_candidate"
    assert len(split["variations_tasks"]) == 20
    assert manifest["environment_count"] == len(manifest["environments"])
    assert manifest["environments"].count("silent_colleague_env") == 1
    assert real_time["silent_colleague"] == env["runner_options"] == controls["real_time"]
    source = (BENCH / "shared_runtime/app/mechanics/silent_colleague.js").read_text(encoding="utf-8")
    assert "keyboard_move" in source and "proxy_step" in source
    assert "keyboard_action" in source and "proxy_action" in source
    assert "setInterval(advance" in source
    assert "event.repeat" in source
    assert "runtime_ticket_sequence" in source
    assert "is-current" not in source
    assert "READ THE NEXT ROUTE" not in source
    assert "wordless worker" not in GENERATOR_PATH.read_text(encoding="utf-8")
    assert "unrelated" in task["description"]
    assert "browser-settings" in task["natural_language"]
    assert task["natural_language"].endswith("Fill all four preservation tickets before the shift ends.")
    for profile in controls["difficulty"].values():
        assert "visible controls in the task webpage" in profile["natural_language"]
        assert "browser-settings" in profile["natural_language"]
    for path in (
        ENV / "scripts/install_puzzle_runtime.sh", ENV / "scripts/setup_puzzle_runtime.sh",
        ENV / "tasks/silent_colleague_seed_0001/setup_task.sh", ENV / "tasks/silent_colleague_seed_0001/export_result.sh",
    ):
        assert os.access(path, os.X_OK)
