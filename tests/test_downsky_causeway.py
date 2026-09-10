from __future__ import annotations

import copy
import importlib.util
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
GENERATOR_PATH = BENCHMARK / "shared_scripts" / "incubator_generators" / "downsky_causeway.py"
GRADER_PATH = BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "downsky_causeway.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = load_module("downsky_test_generator", GENERATOR_PATH)
GRADER = load_module("downsky_test_grader", GRADER_PATH)


def condition(level: int, interaction: str) -> dict:
    controls = json.loads((BENCHMARK / "environments" / "downsky_causeway_env" / "controls.json").read_text())
    return {
        "difficulty": level,
        "interaction": interaction,
        "real_time": "live",
        "difficulty_parameters": copy.deepcopy(controls["difficulty"][str(level)]["parameters"]),
    }


def task_for(level: int, interaction: str) -> dict:
    return {
        "id": f"downsky_causeway_d{level}_{interaction}_seed_0001@0.2",
        "natural_language": "Reach the illuminated pavilion.",
        "_control_condition": condition(level, interaction),
    }


def passing_events(world: dict, interaction: str) -> list[dict]:
    # Oracle wiring fixture: center on each route terrace using the selected
    # surface's real look increments, then approach the same finish disc.
    events = []
    state, error = GRADER.replay_events([], world, interaction)
    assert error is None
    movement = "keyboard" if interaction == "full" else "control_button"
    look = "viewport_drag" if interaction == "full" else "look_button"

    def emit(kind, **fields):
        nonlocal state
        events.append(dict(seq=len(events) + 1, t_ms=(len(events) + 1) * 40, kind=kind, **fields))
        state, error = GRADER.replay_events(events, world, interaction)
        assert error is None and not state["failed"], (error, state)

    ordered = [p for p in world["platforms"] if str(p["id"]).startswith("terrace-")]
    for target in ordered[1:]:
        emit("key_down", control="forward", input_source=movement)
        for _ in range(160):
            dx = target["center"][0] - state["x"]
            dy = target["center"][1] - state["y"]
            if state["platform_id"] == target["id"] and math.hypot(dx, dy) <= 0.26:
                break
            angle = (math.atan2(dy, dx) - state["heading"] + math.pi) % (2 * math.pi) - math.pi
            pixels = angle / world["rules"]["look_sensitivity"]
            looks = [pixels] if interaction == "full" else [math.copysign(8, pixels)] * round(abs(pixels) / 8)
            for delta in looks:
                if abs(delta) > 1e-9:
                    emit("look", dx=delta, dy=0, input_source=look)
            emit("tick", dt_ms=world["rules"]["tick_ms"], input_source="physics")
            if target["id"] == world["exit_platform_id"] and math.hypot(target["center"][0] - state["x"], target["center"][1] - state["y"]) <= world["rules"]["finish_radius"]:
                emit("finish", input_source="physical_contact")
                return events
        else:
            raise AssertionError(f"oracle did not reach {target['id']}")
        emit("key_up", control="forward", input_source=movement)
    raise AssertionError("oracle did not contact the exit")


def test_downsky_profiles_are_deterministic_and_interaction_invariant() -> None:
    expected_branch_counts = {1: 0, 2: 1, 3: 2, 4: 4, 5: 5}
    for level in range(1, 6):
        full_public, full_truth = GENERATOR.generate(task_for(level, "full"), "downsky-test-seed")
        simple_public, simple_truth = GENERATOR.generate(task_for(level, "simplified"), "downsky-test-seed")
        assert full_public["world"] == simple_public["world"]
        assert full_truth["world"] == simple_truth["world"]
        assert full_truth["route_platform_ids"] == simple_truth["route_platform_ids"]
        assert len(full_truth["route_platform_ids"]) == full_public["control_condition"]["difficulty_parameters"]["route_count"]
        parameters = full_public["control_condition"]["difficulty_parameters"]
        assert len(full_truth["branch_platform_ids"]) == expected_branch_counts[level]
        assert len(full_truth["branch_platform_ids"]) == parameters["branch_count"]
        assert len(full_truth["branch_platform_ids"]) == parameters["regular_branch_count"] + int(parameters["terminal_shelf"])
        repeated_public, repeated_truth = GENERATOR.generate(task_for(level, "full"), "downsky-test-seed")
        assert repeated_public == full_public
        assert repeated_truth == full_truth


def test_downsky_oracle_transcript_replays_for_all_ten_variants() -> None:
    for level in range(1, 6):
        for interaction in ("full", "simplified"):
            public_state, ground_truth = GENERATOR.generate(task_for(level, interaction), "downsky-oracle-seed")
            events = passing_events(ground_truth["world"], interaction)
            payload = {
                "mechanic_id": "downsky_causeway",
                "task_id": ground_truth["task_id"],
                "challenge_id": ground_truth["challenge_id"],
                "interaction": interaction,
                "completed": True,
                "events": events,
            }
            result = GRADER.grade(payload, ground_truth, public_state)
            assert result["passed"] is True, (level, interaction, result)


def test_downsky_rejects_wrong_input_surface_and_stale_challenge() -> None:
    public_state, ground_truth = GENERATOR.generate(task_for(4, "full"), "downsky-rejection-seed")
    events = passing_events(ground_truth["world"], "full")
    wrong_surface = {
        "mechanic_id": "downsky_causeway",
        "task_id": ground_truth["task_id"],
        "challenge_id": ground_truth["challenge_id"],
        "interaction": "simplified",
        "completed": True,
        "events": events,
    }
    stale = dict(wrong_surface, interaction="full", challenge_id="stale-challenge")
    assert GRADER.grade(wrong_surface, ground_truth, public_state)["passed"] is False
    assert GRADER.grade(stale, ground_truth, public_state)["passed"] is False


def test_exit_contact_tolerance_contract_has_positive_and_negative_boundaries() -> None:
    public_state, ground_truth = GENERATOR.generate(task_for(4, "full"), "downsky-contact-boundary-seed")
    world = copy.deepcopy(ground_truth["world"])
    exit_platform = next(item for item in world["platforms"] if item["id"] == world["exit_platform_id"])
    radius = float(world["rules"]["finish_radius"])
    assert radius == 0.3
    assert "finish_guard_radius" not in world["rules"]

    def finish_at(offset: float) -> tuple[dict, str | None]:
        centered = copy.deepcopy(world)
        center_x, center_y, center_z = map(float, exit_platform["center"])
        centered["start"] = {
            "platform_id": exit_platform["id"],
            "position": [center_x + offset, center_y, center_z],
            "heading": 0.0,
            "pitch": 0.0,
        }
        return GRADER.replay_events(
            [{"seq": 1, "t_ms": 0, "kind": "finish", "input_source": "physical_contact"}],
            centered,
            "full",
        )

    inside, inside_error = finish_at(radius - 1e-6)
    outside, outside_error = finish_at(radius + 1e-6)
    assert inside_error is None and inside["finished"] is True
    assert outside["finished"] is False
    assert outside_error == "event 1 certifies outside the pavilion contact region"


def test_discrete_look_and_legacy_contact_contract_are_rejected() -> None:
    public, truth = GENERATOR.generate(task_for(4, "simplified"), "downsky-contract")
    events = passing_events(truth["world"], "simplified")
    payload = {"mechanic_id": "downsky_causeway", "task_id": truth["task_id"],
               "challenge_id": truth["challenge_id"], "interaction": "simplified",
               "completed": True, "events": events}
    altered = copy.deepcopy(payload)
    next(e for e in altered["events"] if e["kind"] == "look")["dx"] = 4
    assert "discrete look" in GRADER.grade(altered, truth, public)["feedback"]
    legacy_truth = copy.deepcopy(truth)
    legacy_public = copy.deepcopy(public)
    for document in (legacy_truth, legacy_public):
        document["world"]["rules"].update(finish_radius=1.728, finish_guard_radius=0.3)
    assert "contact contract" in GRADER.grade(payload, legacy_truth, legacy_public)["feedback"]


def test_baseline_and_split_preserve_materialization_contract(tmp_path) -> None:
    materializer = load_module("downsky_materializer", BENCHMARK / "tools/materialize_controlled_tasks.py")
    env = BENCHMARK / "environments/downsky_causeway_env"
    paths = materializer.materialize_environment(env, tmp_path)
    assert len(paths) == 10
    split = json.loads((BENCHMARK / "splits/downsky_causeway_split.json").read_text())
    assert set(split["variations_tasks"]) == {p.name for p in paths}
    assert split["all_tasks"] == ["downsky_causeway_seed_0001"]
    baseline = json.loads((env / "tasks/downsky_causeway_seed_0001/task.json").read_text())
    for seed in ("baseline-a", "baseline-b", "baseline-c"):
        original, _ = GENERATOR.generate(baseline, seed)
        controlled, _ = GENERATOR.generate(task_for(4, "full"), seed)
        assert original["world"] == controlled["world"]
