from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "craftcha_alchemy_bench_env"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SETUP = _load("craftcha_control_setup", BENCHMARK / "shared_scripts" / "setup_task.py")
MATERIALIZER = _load("craftcha_control_materializer", BENCHMARK / "tools" / "materialize_controlled_tasks.py")
GRADER = _load(
    "craftcha_control_grader",
    BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "craftcha_alchemy_bench.py",
)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


CONTROLS = _read(ENVIRONMENT / "controls.json")
BASE = _read(ENVIRONMENT / "tasks" / "craftcha_alchemy_bench_seed_0001" / "task.json")


def _task(level: int, interaction: str) -> dict:
    return MATERIALIZER.controlled_task(
        BASE,
        mechanic_id="craftcha_alchemy_bench",
        level=level,
        interaction=interaction,
        profile=CONTROLS["difficulty"][str(level)],
        task_dir_name=f"craftcha_alchemy_bench_d{level}_{interaction}_seed_0001",
    )


def _without_control_identity(value: dict) -> dict:
    copied = copy.deepcopy(value)
    for field in ("task_id", "challenge_id", "control_condition"):
        copied.pop(field, None)
    return copied


def _center(rect: dict) -> dict[str, float]:
    return {
        "x": (float(rect["x1"]) + float(rect["x2"])) / 2,
        "y": (float(rect["y1"]) + float(rect["y2"])) / 2,
    }


def _midpoint(left: dict[str, float], right: dict[str, float], ratio: float) -> dict[str, float]:
    return {
        "x": left["x"] + (right["x"] - left["x"]) * ratio,
        "y": left["y"] + (right["y"] - left["y"]) * ratio,
    }


def _passing_payload(truth: dict, interaction: str) -> dict:
    geometry = truth["geometry"]
    recipe = truth["recipe"]
    inventory = list(truth["initial_inventory"])
    stations = {station: None for station in ("grind", "heat", "infuse", "press", "assemble")}
    assembly: list[str] = []
    delivery = None
    events: list[dict] = []
    time_ms = int(truth["recipe_window_ms"])

    def record(kind: str, **details) -> None:
        events.append({"seq": len(events) + 1, "t_ms": time_ms, "kind": kind, **details})

    record("recipe_seal", reason="initial", recipe_hash=truth["recipe_hash"])

    def transfer(slot: int, destination: str) -> str:
        nonlocal time_ms, delivery
        state = inventory[slot]
        assert state is not None
        source = _center(geometry["inventory_slots"][slot])
        target = _center(geometry["delivery"] if destination == "delivery" else geometry["stations"][destination])
        time_ms += 120
        if interaction == "full":
            record(
                "drag",
                start=source,
                end=target,
                samples=[source, _midpoint(source, target, .33), _midpoint(source, target, .67), target],
                duration_ms=120,
                source_slot=slot,
                destination=destination,
                state_id=state,
                input_surface="physical_drag",
            )
        else:
            record(
                "proxy_transfer",
                source_point=source,
                destination_point=target,
                source_slot=slot,
                destination=destination,
                state_id=state,
                input_surface="click_to_place_proxy",
            )
        inventory[slot] = None
        if destination == "delivery":
            delivery = state
        elif destination == "assemble":
            assembly.append(state)
        else:
            stations[destination] = state
        return state

    transform_count = 0
    for branch_index, branch in enumerate(recipe["branches"]):
        for step in branch["steps"]:
            station = step["station_id"]
            input_state = transfer(branch_index, station)
            assert input_state == step["input_state_id"]
            time_ms += 420
            output_slot = inventory.index(None)
            record(
                "cycle",
                point=_center(geometry["cycle_buttons"][station]),
                duration_ms=410,
                cycle_pulses=[1, 2, 3, 4],
                station_id=station,
                input_state_ids=[input_state],
                output_state_id=step["output_state_id"],
                output_slot=output_slot,
                input_surface="machine_cycle_button",
            )
            stations[station] = None
            inventory[output_slot] = step["output_state_id"]
            transform_count += 1

    for branch_index, branch in enumerate(recipe["branches"]):
        assert inventory[branch_index] == branch["terminal_state_id"]
        transfer(branch_index, "assemble")
    time_ms += 420
    output_slot = inventory.index(None)
    record(
        "cycle",
        point=_center(geometry["cycle_buttons"]["assemble"]),
        duration_ms=410,
        cycle_pulses=[1, 2, 3, 4],
        station_id="assemble",
        input_state_ids=list(assembly),
        output_state_id=recipe["device_state_id"],
        output_slot=output_slot,
        input_surface="machine_cycle_button",
    )
    assembly = []
    inventory[output_slot] = recipe["device_state_id"]
    transform_count += 1
    transfer(output_slot, "delivery")
    time_ms += 120
    record("submit", point=_center(geometry["verify_button"]), certified=True)

    return {
        "mechanic_id": "craftcha_alchemy_bench",
        "challenge_id": truth["challenge_id"],
        "interaction": interaction,
        "events": events,
        "final_state": {
            "inventory": inventory,
            "stations": stations,
            "assembly": assembly,
            "delivery": delivery,
            "recipe_sealed": True,
            "memory_charge": truth["memory_charge_initial"],
            "replay_count": 0,
            "reset_count": 0,
            "transform_count": transform_count,
            "discard_count": 0,
            "drag_count": len(recipe["branches"]) + 1 + sum(len(branch["steps"]) for branch in recipe["branches"]),
            "submitted": True,
        },
    }


def test_controlled_baseline_materializes_all_ten_and_preserves_original_generation(tmp_path: Path) -> None:
    MATERIALIZER.validate_controls(CONTROLS, ENVIRONMENT)
    written = MATERIALIZER.materialize_environment(ENVIRONMENT, tmp_path)
    assert len(written) == 10
    assert {
        (
            _read(path / "task.json")["metadata"]["control_condition"]["difficulty"],
            _read(path / "task.json")["metadata"]["control_condition"]["interaction"],
        )
        for path in written
    } == {(level, interaction) for level in range(1, 6) for interaction in ("simplified", "full")}
    original_public, original_truth = SETUP.generate_task_state(BASE, "craftcha-baseline-preservation")
    controlled_public, controlled_truth = SETUP.generate_task_state(_task(4, "full"), "craftcha-baseline-preservation")
    assert _without_control_identity(original_public) == _without_control_identity(controlled_public)
    assert _without_control_identity(original_truth) == _without_control_identity(controlled_truth)


def test_profiles_change_the_generated_problem_and_interaction_preserves_the_world() -> None:
    expected_process_counts = [2, 2, 3, 3, 4]
    expected_steps = [(4, 4), (5, 6), (6, 7), (6, 9), (10, 11)]
    for level, expected_station_count, (minimum, maximum) in zip(range(1, 6), expected_process_counts, expected_steps):
        public, truth = SETUP.generate_task_state(_task(level, "simplified"), "craftcha-profile-contract")
        assert public["control_condition"] == truth["control_condition"]
        assert len(truth["active_station_ids"]) == expected_station_count + 1
        assert minimum <= truth["recipe"]["step_count"] <= maximum
        assert truth["inventory_capacity"] == 4
    simple_public, simple_truth = SETUP.generate_task_state(_task(4, "simplified"), "craftcha-interaction-pair")
    full_public, full_truth = SETUP.generate_task_state(_task(4, "full"), "craftcha-interaction-pair")
    assert simple_public["challenge_id"] == full_public["challenge_id"]
    assert _without_control_identity(simple_public) == _without_control_identity(full_public)
    assert _without_control_identity(simple_truth) == _without_control_identity(full_truth)


def test_grader_accepts_each_surface_and_rejects_a_transcript_from_the_other_mode() -> None:
    simple_public, simple_truth = SETUP.generate_task_state(_task(4, "simplified"), "craftcha-interaction-replay")
    full_public, full_truth = SETUP.generate_task_state(_task(4, "full"), "craftcha-interaction-replay")
    simple_payload = _passing_payload(simple_truth, "simplified")
    full_payload = _passing_payload(full_truth, "full")
    assert GRADER.grade(simple_payload, simple_truth, simple_public)["passed"] is True
    assert GRADER.grade(full_payload, full_truth, full_public)["passed"] is True
    rejected = copy.deepcopy(full_payload)
    rejected["interaction"] = "simplified"
    decision = GRADER.grade(rejected, simple_truth, simple_public)
    assert decision["passed"] is False
    assert "wrong interaction surface" in decision["feedback"]
