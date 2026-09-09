from __future__ import annotations

import copy
import importlib.util
import itertools
import json
from pathlib import Path

from weird_captcha_gym.shared_scripts import setup_task


ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "weird_captcha_gym" / "environments" / "polycube_parcel_env"
MECHANIC = "polycube_parcel"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("polycube_parcel_generator_test", ROOT / "weird_captcha_gym/shared_scripts/incubator_generators/polycube_parcel.py")
GRADER = _load("polycube_parcel_grader_test", ROOT / "weird_captcha_gym/shared_runtime/server/incubator_graders/polycube_parcel.py")


def _base_task() -> dict:
    return json.loads((ENV / "tasks" / f"{MECHANIC}_seed_0001" / "task.json").read_text(encoding="utf-8"))


def _task(level: int, interaction: str, real_time: str = "live") -> dict:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    task = copy.deepcopy(_base_task())
    task["natural_language"] = controls["difficulty"][str(level)]["natural_language_by_interaction"][interaction]
    task.setdefault("metadata", {})["control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": controls["difficulty"][str(level)]["parameters"],
    }
    return task


def _mul(a: list[list[int]], b: list[list[int]]) -> list[list[int]]:
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


ROTATIONS = {
    ("x", 1): [[1, 0, 0], [0, 0, -1], [0, 1, 0]],
    ("x", -1): [[1, 0, 0], [0, 0, 1], [0, -1, 0]],
    ("y", 1): [[0, 0, 1], [0, 1, 0], [-1, 0, 0]],
    ("y", -1): [[0, 0, -1], [0, 1, 0], [1, 0, 0]],
    ("z", 1): [[0, -1, 0], [1, 0, 0], [0, 0, 1]],
    ("z", -1): [[0, 1, 0], [-1, 0, 0], [0, 0, 1]],
}


def _payload(public: dict, truth: dict, interaction: str) -> dict:
    events = [{"seq": 1, "type": "camera_orbit", "input_source": "direct_camera_drag" if interaction == "full" else "camera_proxy_button", "before": {"yaw": 0, "pitch": 0.48}, "after": {"yaw": 24, "pitch": 0.50}, **({"path": [[800, 480], [850, 490]]} if interaction == "full" else {"direction": "right"})}]
    sequence = 1
    for piece in truth["world"]["pieces"]:
        if piece["locked"]:
            continue
        sequence += 1
        events.append({"seq": sequence, "type": "select_piece", "input_source": "piece_click", "piece_id": piece["id"]})
        current = copy.deepcopy(piece["orientation"])
        target = truth["solution_placements"][piece["id"]]["orientation"]
        # A valid path in the 24-element rotation group is found by a short
        # bounded search, which keeps this test independent of the solver.
        queue = [(current, [])]
        seen = {json.dumps(current, sort_keys=True)}
        while queue:
            matrix, path = queue.pop(0)
            if matrix == target:
                break
            for action, rotation in ROTATIONS.items():
                candidate = _mul(rotation, matrix)
                key = json.dumps(candidate, sort_keys=True)
                if key not in seen:
                    seen.add(key)
                    queue.append((candidate, path + [action]))
        else:
            raise AssertionError("no orientation path")
        for axis, direction in path:
            sequence += 1
            before = copy.deepcopy(current)
            current = _mul(ROTATIONS[(axis, direction)], current)
            events.append({"seq": sequence, "type": "rotate_piece", "input_source": "axis_rotation_button", "piece_id": piece["id"], "axis": axis, "direction": direction, "before_orientation": before, "after_orientation": current})
        sequence += 1
        place = {"seq": sequence, "type": "place_piece", "input_source": "piece_drag" if interaction == "full" else "placement_proxy", "piece_id": piece["id"], "before_origin": piece["origin"], "after_origin": truth["solution_placements"][piece["id"]]["origin"], "orientation": current}
        if interaction == "full":
            place.update({"path": [[200, 300], [500, 300]], "drop_path": [[500, 300]]})
        else:
            place["proxy"] = {"surface": "axis_cell_selectors", "origin": truth["solution_placements"][piece["id"]]["origin"]}
        events.append(place)
        sequence += 1
        events.append({"seq": sequence, "type": "clear_selection", "input_source": "piece_click", "piece_id": piece["id"]})
    sequence += 1
    events.append({"seq": sequence, "type": "submit", "input_source": "certify_button", "completed": True})
    return {"mechanic_id": MECHANIC, "task_id": public["task_id"], "challenge_id": public["challenge_id"], "control_condition": public["control_condition"], "events": events, "completed": True}


def test_all_profiles_are_deterministic_and_share_world_between_interaction_modes() -> None:
    for level in range(1, 6):
        full_public, full_truth = setup_task.generate_task_state(_task(level, "full"), f"polycube-profile-{level}")
        simple_public, simple_truth = setup_task.generate_task_state(_task(level, "simplified"), f"polycube-profile-{level}")
        assert full_public["world"] == simple_public["world"]
        assert full_truth["world"] == simple_truth["world"]
        assert full_public["challenge_id"] == simple_public["challenge_id"]
        assert len(full_public["world"]["pieces"]) == 7
        assert full_public["preplaced_count"] == {1: 5, 2: 4, 3: 2, 4: 0, 5: 0}[level]
        assert full_truth["exact_cover_cells"] == [list(cell) for cell in itertools.product(range(3), repeat=3)]
        again, again_truth = setup_task.generate_task_state(_task(level, "full"), f"polycube-profile-{level}")
        assert again == full_public
        assert again_truth == full_truth


def test_uncontrolled_task_is_the_approved_l4_full_reference() -> None:
    base_public, base_truth = setup_task.generate_task_state(_base_task(), "polycube-baseline")
    controlled_public, controlled_truth = setup_task.generate_task_state(_task(4, "full"), "polycube-baseline")
    assert base_public["mechanic_id"] == MECHANIC
    assert base_public["world"] == controlled_public["world"]
    assert base_truth["solution_placements"] == controlled_truth["solution_placements"]
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    assert controls["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}


def test_grader_accepts_both_modes_and_rejects_wrong_surface_or_stale_identity() -> None:
    for interaction in ("full", "simplified"):
        public, truth = setup_task.generate_task_state(_task(4, interaction), f"polycube-grade-{interaction}")
        payload = _payload(public, truth, interaction)
        assert GRADER.grade(payload, truth, public)["passed"] is True
        wrong = copy.deepcopy(payload)
        wrong["events"][0]["input_source"] = "camera_proxy_button" if interaction == "full" else "direct_camera_drag"
        assert GRADER.grade(wrong, truth, public)["passed"] is False
        stale = copy.deepcopy(payload)
        stale["challenge_id"] = "stale-parcel"
        assert GRADER.grade(stale, truth, public)["passed"] is False


def test_grader_rejects_overlap_and_incomplete_submission() -> None:
    public, truth = setup_task.generate_task_state(_task(4, "full"), "polycube-negative")
    payload = _payload(public, truth, "full")
    broken = copy.deepcopy(payload)
    place = next(event for event in broken["events"] if event["type"] == "place_piece")
    place["after_origin"] = [0, 0, 0]
    assert GRADER.grade(broken, truth, public)["passed"] is False
    incomplete = copy.deepcopy(payload)
    incomplete["completed"] = False
    assert GRADER.grade(incomplete, truth, public)["passed"] is False


def test_registry_controls_realtime_provenance_and_browser_contract() -> None:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    assert set(controls["difficulty"]) == {"1", "2", "3", "4", "5"}
    assert controls["interaction"]["full"]["implemented"] and controls["interaction"]["simplified"]["implemented"]
    assert controls["real_time"] == {"play_time_seconds": 180, "observation_window_ms": 0, "frames_per_observation": 1}
    realtime = json.loads((ROOT / "weird_captcha_gym/real_time.json").read_text(encoding="utf-8"))
    assert realtime["environments"][MECHANIC] == controls["real_time"]
    manifest = json.loads((ROOT / "weird_captcha_gym/benchmark_manifest.json").read_text(encoding="utf-8"))
    assert "polycube_parcel_env" in manifest["environments"]
    renderer = (ROOT / "weird_captcha_gym/shared_runtime/app/mechanics/polycube_parcel.js").read_text(encoding="utf-8")
    assert '"piece_drag"' in renderer
    assert '"placement_proxy"' in renderer
    assert "transformedCells" in renderer and "pp-parcel-face" in renderer
