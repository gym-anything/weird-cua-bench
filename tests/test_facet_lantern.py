from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

from weird_captcha_gym.shared_scripts import setup_task


ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "weird_captcha_gym" / "environments" / "facet_lantern_env"
MECHANIC = "facet_lantern"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("facet_lantern_generator_test", ROOT / "weird_captcha_gym/shared_scripts/incubator_generators/facet_lantern.py")
GRADER = _load("facet_lantern_grader_test", ROOT / "weird_captcha_gym/shared_runtime/server/incubator_graders/facet_lantern.py")


def _base_task() -> dict:
    return json.loads((ENV / "tasks" / f"{MECHANIC}_seed_0001" / "task.json").read_text())


def _controlled_task(level: int, interaction: str) -> dict:
    controls = json.loads((ENV / "controls.json").read_text())
    task = copy.deepcopy(_base_task())
    task["natural_language"] = controls["difficulty"][str(level)]["natural_language_by_interaction"][interaction]
    task.setdefault("metadata", {})["control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": "live",
        "difficulty_parameters": controls["difficulty"][str(level)]["parameters"],
    }
    return task


def _edge(first: str, second: str) -> tuple[str, str]:
    return tuple(sorted((first, second)))


def _visible(vertex: dict, yaw: float, world: dict) -> bool:
    radians = yaw * 3.141592653589793 / 180.0
    depth = float(vertex.get("x", 0)) * __import__("math").sin(radians) + float(vertex.get("z", 0)) * __import__("math").cos(radians)
    return depth >= -float(world.get("occlusion_band", 0.25)) - 1e-7


def _target_yaw(first: dict, second: dict, world: dict, step: float) -> float:
    for index in range(int(360 / step)):
        yaw = index * step
        if _visible(first, yaw, world) and _visible(second, yaw, world):
            return yaw
    raise AssertionError("generated facet edge has no common visible yaw")


def _payload(public: dict, truth: dict, interaction: str) -> dict:
    events = []
    sequence = 0
    current_yaw = float(truth["world"]["initial_yaw"])
    current = {_edge(edge[0], edge[1]) for edge in truth["world"]["connections"]}
    vertices = {str(vertex["id"]): vertex for vertex in truth["world"]["vertices"]}
    for raw_edge in truth["required_connections"]:
        edge = _edge(raw_edge[0], raw_edge[1])
        if edge in current:
            continue
        target_yaw = _target_yaw(vertices[edge[0]], vertices[edge[1]], truth["world"], truth["world"]["rotation_step_degrees"])
        delta = (target_yaw - current_yaw + 180) % 360 - 180
        rotation_deltas = [delta] if interaction == "full" else []
        if interaction == "simplified":
            if abs(delta) < 0.1:
                rotation_deltas = [truth["world"]["rotation_step_degrees"], -truth["world"]["rotation_step_degrees"]]
            else:
                rotation_deltas = [truth["world"]["rotation_step_degrees"] if delta > 0 else -truth["world"]["rotation_step_degrees"]] * int(round(abs(delta) / truth["world"]["rotation_step_degrees"]))
        for per_turn in rotation_deltas:
            sequence += 1
            events.append({
                "seq": sequence,
                "type": "rotate",
                "input_source": "direct_pointer" if interaction == "full" else "proxy_button",
                "from_yaw": current_yaw,
                "to_yaw": current_yaw + per_turn,
                "delta": per_turn,
                **({"path": [[20, 20], [60, 20]]} if interaction == "full" else {"direction": "right" if per_turn > 0 else "left"}),
            })
            current_yaw = (current_yaw + per_turn) % 360
        sequence += 1
        events.extend([
            {"seq": sequence, "type": "select_vertex", "input_source": "vertex_click", "vertex_id": edge[0]},
            {"seq": sequence + 1, "type": "connect", "input_source": "vertex_click", "from_vertex_id": edge[0], "vertex_id": edge[1]},
        ])
        sequence += 1
        current.add(edge)
    return {
        "mechanic_id": MECHANIC,
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "control_condition": public["control_condition"],
        "events": events,
        "completed": True,
        "reported_score": truth["target_score"],
    }


def test_all_profiles_are_deterministic_and_pair_worlds_across_interaction() -> None:
    for level in range(1, 6):
        full_public, full_truth = setup_task.generate_task_state(_controlled_task(level, "full"), f"facet-profile-{level}")
        simple_public, simple_truth = setup_task.generate_task_state(_controlled_task(level, "simplified"), f"facet-profile-{level}")
        for public, truth in ((full_public, full_truth), (simple_public, simple_truth)):
            assert len(public["world"]["vertices"]) == {1: 6, 2: 7, 3: 8, 4: 10, 5: 12}[level]
            assert len(truth["targets"]) == {1: 2, 2: 2, 3: 3, 4: 4, 5: 5}[level]
            assert truth["required_connections"]
            assert truth["target_score"] > public["score"]
        public_again, truth_again = setup_task.generate_task_state(_controlled_task(level, "full"), f"facet-profile-{level}")
        assert public_again == full_public
        assert truth_again == full_truth
        assert full_public["world"] == simple_public["world"]
        assert full_truth["world"] == simple_truth["world"]
        assert full_public["targets"] == simple_public["targets"]


def test_baseline_is_the_uncontrolled_medium_full_world() -> None:
    original_public, original_truth = setup_task.generate_task_state(_base_task(), "facet-baseline")
    controlled_public, controlled_truth = setup_task.generate_task_state(_controlled_task(3, "full"), "facet-baseline")
    for public, truth in ((original_public, original_truth), (controlled_public, controlled_truth)):
        assert public["mechanic_id"] == MECHANIC
        assert truth.get("source_does_not_exist") is not True
    assert original_public["world"] == controlled_public["world"]
    assert original_truth["required_connections"] == controlled_truth["required_connections"]
    controls = json.loads((ENV / "controls.json").read_text())
    assert controls["baseline"] == {"difficulty": 3, "interaction": "full", "real_time": "live"}


def test_grader_accepts_both_surfaces_and_rejects_wrong_surface_or_stale_identity() -> None:
    for level in range(1, 6):
        for interaction in ("full", "simplified"):
            public, truth = setup_task.generate_task_state(_controlled_task(level, interaction), f"facet-grade-{level}")
            payload = _payload(public, truth, interaction)
            accepted = GRADER.grade(payload, truth, public)
            assert accepted["passed"] is True, (level, interaction, accepted)

            stale = copy.deepcopy(payload)
            stale["challenge_id"] = "stale-facet-lantern"
            assert GRADER.grade(stale, truth, public)["passed"] is False

            wrong = copy.deepcopy(payload)
            wrong["events"][0]["input_source"] = "proxy_button" if interaction == "full" else "direct_pointer"
            assert GRADER.grade(wrong, truth, public)["passed"] is False


def test_grader_rejects_hidden_vertex_and_incomplete_facet() -> None:
    public, truth = setup_task.generate_task_state(_controlled_task(3, "full"), "facet-hidden-fixture")
    payload = _payload(public, truth, "full")
    hidden = copy.deepcopy(payload)
    hidden["events"][1]["vertex_id"] = next(
        vertex["id"] for vertex in truth["world"]["vertices"]
        if vertex["id"] not in {"v0", "v1", "v2", "v3"}
    )
    assert GRADER.grade(hidden, truth, public)["passed"] is False

    incomplete = copy.deepcopy(payload)
    incomplete["completed"] = False
    assert GRADER.grade(incomplete, truth, public)["passed"] is False


def test_browser_contract_records_the_two_rotation_surfaces() -> None:
    renderer = (ROOT / "weird_captcha_gym/shared_runtime/app/mechanics/facet_lantern.js").read_text()
    assert 'input_source: "direct_pointer"' in renderer
    assert '"proxy_button"' in renderer
    assert 'interaction === "full" ? " hidden aria-hidden=\\"true\\""' in renderer
    assert 'source === "direct_pointer" && model.interaction !== "full"' in renderer
    assert 'source === "proxy_button" && model.interaction !== "simplified"' in renderer
    styles = (ROOT / "weird_captcha_gym/shared_runtime/app/mechanics/facet_lantern.css").read_text()
    assert ".fl-turns[hidden] { display: none; }" in styles
    assert "occlusion_band" in renderer
    assert "fl-turn-left" in renderer and "fl-turn-right" in renderer
