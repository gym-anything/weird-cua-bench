from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "ember_mosaic_env"
BASE_TASK_PATH = ENVIRONMENT / "tasks" / "ember_mosaic_seed_0001" / "task.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MATERIALIZER = _load(
    "ember_mosaic_materializer_test",
    BENCHMARK / "tools" / "materialize_controlled_tasks.py",
)
GENERATOR = _load(
    "ember_mosaic_generator_test",
    BENCHMARK / "shared_scripts" / "incubator_generators" / "ember_mosaic.py",
)
GRADER = _load(
    "ember_mosaic_grader_test",
    BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "ember_mosaic.py",
)
CONTROLS = json.loads((ENVIRONMENT / "controls.json").read_text(encoding="utf-8"))
BASE_TASK = json.loads(BASE_TASK_PATH.read_text(encoding="utf-8"))


def _task(level: int, interaction: str, real_time: str = "live") -> dict:
    task = MATERIALIZER.controlled_task(
        BASE_TASK,
        mechanic_id="ember_mosaic",
        level=level,
        interaction=interaction,
        profile=CONTROLS["difficulty"][str(level)],
        task_dir_name=f"ember_mosaic_d{level}_{interaction}_seed_0001",
    )
    task["metadata"]["control_condition"]["real_time"] = real_time
    return task


def _without_identity(value: dict) -> dict:
    copied = copy.deepcopy(value)
    for key in ("task_id", "challenge_id", "control_condition"):
        copied.pop(key, None)
    if isinstance(copied.get("world"), dict):
        copied["world"].pop("control_condition", None)
    return copied


def _event_identity(public: dict, interaction: str) -> dict:
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "control_condition": copy.deepcopy(public["control_condition"]),
        "interaction_mode": interaction,
        "completed": True,
    }


def _gate_sweep_payload(public: dict, truth: dict, interaction: str) -> dict:
    width = int(truth["world"]["width"])
    source = "freehand_brush" if interaction == "full" else "stamp_controls"
    max_tick = max(1, (150_000 + int(truth["world"]["parameters"]["tick_ms"]) - 1) // int(truth["world"]["parameters"]["tick_ms"]))
    events = []
    for tick in range(0, max_tick + 1, 3):
        for cell in truth["gate_cells"]:
            events.append({
                "seq": len(events) + 1,
                "type": "brush",
                "material": "stone",
                "points": [{"x": int(cell) % width, "y": int(cell) // width}],
                "input_source": source,
                "tick": tick,
            })
    events.append({
        "seq": len(events) + 1,
        "type": "submit",
        "input_source": "certify_button",
        "completed": True,
        "tick": max_tick,
    })
    payload = _event_identity(public, interaction)
    payload.update({"events": events, "final_tick": max_tick})
    return payload


def _hot_fires(state: dict, oil_cells: set[int]) -> list[int]:
    width, height = int(state["width"]), int(state["height"])
    fires: set[int] = set()
    for oil in oil_cells:
        x, y = oil % width, oil // width
        for dx, dy in GRADER.NEIGHBOURS:
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height:
                neighbour = ny * width + nx
                if state["grid"][neighbour] == "f":
                    fires.add(neighbour)
    return sorted(fires)


def _adaptive_payload(public: dict, truth: dict, interaction: str) -> dict:
    width = int(truth["world"]["width"])
    source = "freehand_brush" if interaction == "full" else "stamp_controls"
    max_tick = max(1, (150_000 + int(truth["world"]["parameters"]["tick_ms"]) - 1) // int(truth["world"]["parameters"]["tick_ms"]))
    replay = GRADER._new_state(truth)
    oil_cells = {int(cell) for pocket in truth["world"]["oil_pockets"] for cell in pocket["cells"]}
    events: list[dict] = []

    def brush(cell: int, material: str, tick: int) -> None:
        events.append({
            "seq": len(events) + 1,
            "type": "brush",
            "material": material,
            "points": [{"x": int(cell) % width, "y": int(cell) // width}],
            "input_source": source,
            "tick": tick,
        })
        GRADER._apply_brush(replay, material, events[-1]["points"], int(truth["world"]["parameters"]["brush_radius"]))

    while replay["tick"] <= max_tick:
        tick = replay["tick"]
        if tick % 3 == 0:
            for gate in truth["gate_cells"]:
                brush(int(gate), "stone", tick)
        for fire in _hot_fires(replay, oil_cells):
            brush(fire, "water", tick)
        if replay["oil_ignited"]:
            raise AssertionError("adaptive fixture ignited oil before certification")
        if replay["burned"] >= replay["target_cells"] and not _hot_fires(replay, oil_cells):
            break
        GRADER._step(replay)
    else:
        raise AssertionError("adaptive fixture did not finish within the replay horizon")

    events.append({
        "seq": len(events) + 1,
        "type": "submit",
        "input_source": "certify_button",
        "completed": True,
        "tick": replay["tick"],
    })
    payload = _event_identity(public, interaction)
    payload.update({"events": events, "final_tick": replay["tick"]})
    return payload


def test_controls_materialize_the_ten_conditions_and_share_the_live_world(tmp_path: Path) -> None:
    MATERIALIZER.validate_controls(CONTROLS, ENVIRONMENT)
    assert CONTROLS["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    assert CONTROLS["real_time"] == {
        "play_time_seconds": 150,
        "observation_window_ms": 600,
        "frames_per_observation": 6,
    }

    written = MATERIALIZER.materialize_environment(ENVIRONMENT, tmp_path)
    assert len(written) == 10
    assert {
        (
            json.loads((path / "task.json").read_text(encoding="utf-8"))["metadata"]["control_condition"]["difficulty"],
            json.loads((path / "task.json").read_text(encoding="utf-8"))["metadata"]["control_condition"]["interaction"],
        )
        for path in written
    } == {(level, interaction) for level in range(1, 6) for interaction in ("full", "simplified")}

    for level in range(1, 6):
        full, full_truth = GENERATOR.generate(_task(level, "full"), f"matrix-{level}")
        simplified, simplified_truth = GENERATOR.generate(_task(level, "simplified"), f"matrix-{level}")
        paused, _ = GENERATOR.generate(_task(level, "full", "paused"), f"matrix-{level}")
        assert _without_identity(full) == _without_identity(simplified)
        assert _without_identity(full_truth) == _without_identity(simplified_truth)
        assert _without_identity(full) == _without_identity(paused)
        assert len(full["target_cells"]) > 0
        assert len(full["oil_pockets"]) == CONTROLS["difficulty"][str(level)]["parameters"]["oil_pocket_count"]
        assert full["parameters"]["oil_heat_ticks"] == 3


def test_full_stroke_raster_is_explicit_integer_bresenham() -> None:
    assert list(GRADER._raster_segment((0, 0), (2, 1))) == [(0, 0), (1, 1), (2, 1)]
    assert list(GRADER._raster_segment((10, 10), (11, 12))) == [(10, 10), (11, 11), (11, 12)]


@pytest.mark.parametrize("interaction", ["full", "simplified"])
def test_independent_replay_accepts_adaptive_cooling_and_rejects_surface_tampering(interaction: str) -> None:
    public, truth = GENERATOR.generate(_task(4, interaction), f"grade-{interaction}")
    payload = _adaptive_payload(public, truth, interaction)
    decision = GRADER.grade(payload, truth, public)
    assert decision["passed"] is True, decision

    wrong_surface = copy.deepcopy(payload)
    wrong_surface["events"][0]["input_source"] = "stamp_controls" if interaction == "full" else "freehand_brush"
    assert GRADER.grade(wrong_surface, truth, public)["passed"] is False

    stale = copy.deepcopy(payload)
    stale["challenge_id"] = "stale-challenge"
    assert GRADER.grade(stale, truth, public)["passed"] is False


@pytest.mark.parametrize("level", [1, 2, 3, 4, 5])
@pytest.mark.parametrize("interaction", ["full", "simplified"])
def test_visible_gate_sweep_alone_cannot_certify_any_level(level: int, interaction: str) -> None:
    public, truth = GENERATOR.generate(_task(level, interaction), f"fixed-gate-{level}-{interaction}")
    decision = GRADER.grade(_gate_sweep_payload(public, truth, interaction), truth, public)
    assert decision["passed"] is False, decision
    assert decision["oil_ignited"] is True


def test_simplified_stamp_rejects_a_forged_multi_point_stroke() -> None:
    public, truth = GENERATOR.generate(_task(4, "simplified"), "stamp-path-binding")
    payload = _adaptive_payload(public, truth, "simplified")
    assert GRADER.grade(payload, truth, public)["passed"]
    payload["events"][0]["points"].append(dict(payload["events"][0]["points"][0]))
    decision = GRADER.grade(payload, truth, public)
    assert not decision["passed"]
    assert "exactly one point" in decision["feedback"]
