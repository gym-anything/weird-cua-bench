from __future__ import annotations

import copy
import importlib.util
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
ENV_ROOT = BENCHMARK / "environments" / "cell_gatekeeper_env"
BASE_TASK = ENV_ROOT / "tasks" / "cell_gatekeeper_seed_0001" / "task.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SETUP = load_module("cell_gatekeeper_setup", BENCHMARK / "shared_scripts" / "setup_task.py")
MATERIALIZER = load_module("cell_gatekeeper_materializer", BENCHMARK / "tools" / "materialize_controlled_tasks.py")
GENERATOR = load_module("cell_gatekeeper_generator", BENCHMARK / "shared_scripts" / "incubator_generators" / "cell_gatekeeper.py")
GRADER = load_module("cell_gatekeeper_grader", BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "cell_gatekeeper.py")
VERIFIER = load_module("cell_gatekeeper_verifier", ENV_ROOT / "tasks" / "cell_gatekeeper_seed_0001" / "verifier.py")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def controlled_task(level: int, interaction: str, real_time: str = "live") -> dict:
    base = read_json(BASE_TASK)
    controls = read_json(ENV_ROOT / "controls.json")
    task = MATERIALIZER.controlled_task(
        base,
        mechanic_id="cell_gatekeeper",
        level=level,
        interaction=interaction,
        profile=controls["difficulty"][str(level)],
        task_dir_name=f"cell_gatekeeper_d{level}_{interaction}_seed_0001",
    )
    task["metadata"]["control_condition"]["real_time"] = real_time
    return task


def without_identity(value: dict) -> dict:
    normalized = copy.deepcopy(value)
    for key in ("task_id", "challenge_id", "control_condition"):
        normalized.pop(key, None)
    return normalized


def passing_payload(public: dict, truth: dict, mode: str) -> dict:
    source = {
        "full": {"install": "protein_drag", "remove": "protein_drag", "atp": "atp_drag"},
        "simplified": {"install": "protein_button", "remove": "protein_button", "atp": "atp_button"},
    }[mode]
    events: list[dict] = []

    def add(event_type: str, tick: int, **kwargs) -> None:
        events.append({"seq": len(events) + 1, "type": event_type, "tick": tick, **kwargs})

    slots = list(public["initial_state"]["slots"])
    required = list(public["required_proteins"])
    leaks = [item for item in required if item.endswith("_leak")]
    pumps = [item for item in required if item.endswith("_pump")]
    cursor = 0
    leak_tick = 0
    for leak in leaks:
        add("install", leak_tick, slot=cursor, protein_id=leak, input_source=source["install"])
        leak_tick += int(public["parameters"]["passive_period"])
        add("remove", leak_tick, slot=cursor, input_source=source["remove"])
        cursor += 1
    for pump in pumps:
        add("install", leak_tick, slot=cursor, protein_id=pump, input_source=source["install"])
        cursor += 1
    total_units = len(pumps) * int(public["parameters"]["pump_cycles"])
    batch = int(public["parameters"]["atp_batch"])
    assert total_units % batch == 0
    for _ in range(total_units // batch):
        add("atp", leak_tick, amount=batch, input_source=source["atp"])
    end = int(public["parameters"]["max_ticks"])
    add("certify", end, accepted=True, input_source="lock_button")
    # The browser reports this state.  For the unit-level fixture, replay the
    # event stream once and use the same visible contract rather than trusting
    # a hand-written final count.
    replay = copy.deepcopy(public["initial_state"])
    last = 0
    for event in events:
        target = event["tick"]
        GRADER._advance(replay, public, target - last)
        last = target
        if event["type"] == "install":
            replay["slots"][event["slot"]] = event["protein_id"]
            replay["installed_history"].append(event["protein_id"])
        elif event["type"] == "remove":
            replay["removed_history"].append(replay["slots"][event["slot"]])
            replay["slots"][event["slot"]] = None
        elif event["type"] == "atp":
            replay["atp"] += event["amount"]
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction_mode": mode,
        "events": events,
        "terminal_tick": end,
        "final_state": replay,
        "completed": True,
    }


def test_controls_and_profiles_materialize_ten_tasks() -> None:
    controls = read_json(ENV_ROOT / "controls.json")
    MATERIALIZER.validate_controls(controls, ENV_ROOT)
    assert controls["baseline"] == {"difficulty": 3, "interaction": "full", "real_time": "live"}
    assert controls["real_time"] == {"play_time_seconds": 180, "observation_window_ms": 600, "frames_per_observation": 6}
    assert len(MATERIALIZER.materialize_environment(ENV_ROOT, Path("/tmp/cell-gatekeeper-controlled-test"))) == 10


def test_baseline_and_interaction_pair_preserve_world() -> None:
    base = read_json(BASE_TASK)
    original_public, original_truth = SETUP.generate_task_state(base, "cell-gatekeeper-baseline")
    simplified_public, simplified_truth = SETUP.generate_task_state(controlled_task(3, "simplified"), "cell-gatekeeper-baseline")
    full_public, full_truth = SETUP.generate_task_state(controlled_task(3, "full"), "cell-gatekeeper-baseline")
    assert without_identity(simplified_public) == without_identity(full_public)
    assert without_identity(simplified_truth) == without_identity(full_truth)
    assert without_identity(original_public) == without_identity(full_public)
    assert without_identity(original_truth) == without_identity(full_truth)


def test_each_adjacent_profile_changes_the_running_problem() -> None:
    controls = read_json(ENV_ROOT / "controls.json")
    worlds = [SETUP.generate_task_state(controlled_task(level, "full"), "cell-gatekeeper-profile") for level in range(1, 6)]
    assert [len(public["species"]) for public, _ in worlds] == [1, 2, 2, 3, 3]
    assert [public["parameters"]["pump_cycles"] for public, _ in worlds] == [3, 3, 4, 5, 6]
    assert [public["parameters"]["goal_width"] for public, _ in worlds] == [4, 3, 2, 2, 1]
    assert [len(public["protein_catalog"]) for public, _ in worlds] == [2, 4, 4, 8, 8]
    for level in range(1, 6):
        assert worlds[level - 1][0]["parameters"] == controls["difficulty"][str(level)]["parameters"]


def test_both_interaction_transcripts_pass_and_wrong_surface_fails() -> None:
    for level in range(1, 6):
        for mode in ("simplified", "full"):
            public, truth = SETUP.generate_task_state(controlled_task(level, mode), f"cell-gatekeeper-d{level}-{mode}")
            payload = passing_payload(public, truth, mode)
            decision = GRADER.grade(payload, truth, public)
            assert decision["passed"] is True, (level, mode, decision)
            wrong = copy.deepcopy(payload)
            wrong["interaction_mode"] = "full" if mode == "simplified" else "simplified"
            assert GRADER.grade(wrong, truth, public)["passed"] is False
            forged = copy.deepcopy(payload)
            forged["final_state"]["counts"][public["species"][0]["id"]]["outside"] += 1
            assert GRADER.grade(forged, truth, public)["passed"] is False


def test_paused_identity_is_time_setting_only_and_verifier_replays_export(tmp_path: Path) -> None:
    public, truth = SETUP.generate_task_state(controlled_task(3, "full", "paused"), "cell-gatekeeper-paused")
    assert public["control_condition"]["real_time"] == "paused"
    payload = passing_payload(public, truth, "full")
    export = tmp_path / "task_result.json"
    export.write_text(json.dumps({"result": payload, "ground_truth": truth, "public_state": public}), encoding="utf-8")

    def copy_from_env(_source: str, destination: str) -> None:
        Path(destination).write_bytes(export.read_bytes())

    checked = VERIFIER.verify_task(env_info={"copy_from_env": copy_from_env}, task_info={"id": public["task_id"]})
    assert checked["passed"] is True


def test_final_bands_must_hold_for_the_observation_window() -> None:
    public, truth = SETUP.generate_task_state(controlled_task(3, "full"), "cell-gatekeeper-hold")
    payload = passing_payload(public, truth, "full")
    assert payload["final_state"]["stable_ticks"] >= public["parameters"]["observation_ticks"]
    short_hold = copy.deepcopy(payload)
    short_hold["final_state"]["stable_ticks"] = public["parameters"]["observation_ticks"] - 1
    decision = GRADER.grade(short_hold, truth, public)
    assert decision["passed"] is False


def test_atp_burst_effect_is_identical_across_input_surfaces() -> None:
    for mode in ("full", "simplified"):
        public, truth = SETUP.generate_task_state(controlled_task(3, mode), f"cell-gatekeeper-atp-{mode}")
        payload = passing_payload(public, truth, mode)
        atp_events = [event for event in payload["events"] if event["type"] == "atp"]
        assert atp_events
        assert {event["amount"] for event in atp_events} == {public["parameters"]["atp_batch"]}
        wrong = copy.deepcopy(payload)
        wrong_event = next(event for event in wrong["events"] if event["type"] == "atp")
        wrong_event["amount"] = 1
        if public["parameters"]["atp_batch"] == 1:
            wrong_event["amount"] = 2
        assert GRADER.grade(wrong, truth, public)["passed"] is False


def test_manual_calibration_can_finish_after_transport_stops_without_skipping_crossings() -> None:
    for level in range(1, 6):
        for mode in ("full", "simplified"):
            public, truth = SETUP.generate_task_state(controlled_task(level, mode), "manual-calibration")
            reference = passing_payload(public, truth, mode)
            sim = copy.deepcopy(public["initial_state"])
            events = []

            def apply(event):
                GRADER._advance(sim, public, event["tick"] - sim["tick"])
                assert GRADER._apply_event(sim, event, public, mode) is None
                events.append({**event, "seq": len(events) + 1})

            for event in reference["events"][:-1]:
                apply(event)
            GRADER._advance(sim, public, 40 - sim["tick"])
            for slot, protein in enumerate(list(sim["slots"])):
                if protein:
                    apply({"type": "remove", "tick": sim["tick"], "slot": slot,
                           "input_source": "protein_drag" if mode == "full" else "protein_button"})
            sid = public["species"][0]["id"]
            low, high = public["goal"][sid]["outside"]
            for target in (high + 2, low):
                while sim["counts"][sid]["outside"] != target:
                    delta = 1 if sim["counts"][sid]["outside"] < target else -1
                    apply({"type": "solute", "tick": sim["tick"], "species": sid, "side": "outside", "delta": delta,
                           "input_source": "solute_drag" if mode == "full" else "solute_button"})
                assert GRADER._base_goal_ok(sim, public) is (target == low)
            GRADER._advance(sim, public, public["parameters"]["observation_ticks"])
            events.append({"seq": len(events) + 1, "type": "certify", "tick": sim["tick"], "accepted": True, "input_source": "lock_button"})
            payload = {**reference, "events": events, "terminal_tick": sim["tick"], "final_state": sim}
            assert GRADER.grade(payload, truth, public)["passed"] is True
            assert all(sim["crossings"]["active"].get(pid, 0) >= public["parameters"]["pump_cycles"]
                       for pid in public["required_proteins"] if pid.endswith("_pump"))
