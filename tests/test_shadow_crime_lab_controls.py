from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "shadow_crime_lab_env"
MECHANIC = "shadow_crime_lab"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SETUP = _load("shadow_crime_control_setup", BENCHMARK / "shared_scripts" / "setup_task.py")
MATERIALIZER = _load("shadow_crime_control_materializer", BENCHMARK / "tools" / "materialize_controlled_tasks.py")
GRADER = _load(
    "shadow_crime_control_grader",
    BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{MECHANIC}.py",
)
VERIFIER = _load(
    "shadow_crime_control_verifier",
    ENVIRONMENT / "tasks" / f"{MECHANIC}_seed_0001" / "verifier.py",
)
CONTROLS = json.loads((ENVIRONMENT / "controls.json").read_text(encoding="utf-8"))
BASE_TASK = json.loads(
    (ENVIRONMENT / "tasks" / f"{MECHANIC}_seed_0001" / "task.json").read_text(encoding="utf-8")
)


def _task(level: int, interaction: str) -> dict:
    return MATERIALIZER.controlled_task(
        BASE_TASK,
        mechanic_id=MECHANIC,
        level=level,
        interaction=interaction,
        profile=CONTROLS["difficulty"][str(level)],
        task_dir_name=f"{MECHANIC}_d{level}_{interaction}_seed_0001",
    )


def _without_control_identity(value: dict) -> dict:
    result = copy.deepcopy(value)
    for key in ("task_id", "challenge_id", "control_condition", "prompt"):
        result.pop(key, None)
    return result


def _responses(truth: dict, lamp: tuple[float, float]) -> list[dict]:
    contract = GRADER._derive_contract(truth["challenge_id"], truth["objects"])
    initial = (float(truth["lamp"]["x"]), float(truth["lamp"]["y"]))
    polygons = GRADER._polygons(truth["objects"], lamp, initial, float(truth["lamp"]["area_radius"]), contract)
    return [
        {
            "object_id": object_id,
            "centroid": {"x": round(GRADER._centroid(polygon)[0], 2), "y": round(GRADER._centroid(polygon)[1], 2)},
            "area": round(GRADER._polygon_area(polygon), 2),
        }
        for object_id, polygon in polygons
    ]


def _event(events: list[dict], **payload: object) -> None:
    payload["seq"] = len(events) + 1
    payload["t_ms"] = (len(events) + 1) * 10
    events.append(payload)


def _full_payload(public: dict, truth: dict) -> dict:
    events: list[dict] = []
    lamp = (float(truth["lamp"]["x"]), float(truth["lamp"]["y"]))
    _event(
        events,
        type="lamp_start",
        input_surface="direct_lamp_drag",
        pointer={"x": lamp[0], "y": lamp[1]},
        lamp={"x": lamp[0], "y": lamp[1]},
        drag_offset={"x": 0, "y": 0},
    )
    visited: list[str] = []
    for probe in truth["solution"]["probe_path"]:
        target = (float(probe["x"]), float(probe["y"]))
        zone_id = str(probe["zone_id"])
        _event(
            events,
            type="lamp_move",
            input_surface="direct_lamp_drag",
            pointer={"x": target[0], "y": target[1]},
            **{"from": {"x": lamp[0], "y": lamp[1]}},
            to={"x": target[0], "y": target[1]},
            zone_id=zone_id,
        )
        lamp = target
        visited.append(zone_id)
        _event(
            events,
            type="probe_sample",
            input_surface="direct_lamp_drag",
            zone_id=zone_id,
            lamp={"x": lamp[0], "y": lamp[1]},
            responses=_responses(truth, lamp),
        )
    _event(events, type="lamp_end", input_surface="direct_lamp_drag", pointer={"x": lamp[0], "y": lamp[1]}, lamp={"x": lamp[0], "y": lamp[1]})
    tag_point = truth["solution"]["expected_tag_point"]
    _event(events, type="tag_start", input_surface="direct_tag_drag", dock="evidence_tag")
    _event(
        events,
        type="tag_end",
        input_surface="direct_tag_drag",
        point=tag_point,
        object_id=truth["forged_object_id"],
    )
    return {
        "mechanic_id": MECHANIC,
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "interaction_mode": "full",
        "events": events,
        "final_state": {
            "lamp_position": {"x": round(lamp[0], 2), "y": round(lamp[1], 2)},
            "visited_zone_ids": visited,
            "sample_count": len(visited),
            "tagged_object_id": truth["forged_object_id"],
            "reset_count": 0,
            "proxy_tag_armed": False,
        },
    }


def _simplified_payload(public: dict, truth: dict) -> dict:
    events: list[dict] = []
    lamp = (float(truth["lamp"]["x"]), float(truth["lamp"]["y"]))
    visited: list[str] = []
    for probe in truth["solution"]["probe_path"]:
        lamp = (float(probe["x"]), float(probe["y"]))
        zone_id = str(probe["zone_id"])
        visited.append(zone_id)
        _event(
            events,
            type="proxy_probe",
            input_surface="probe_zone_button",
            zone_id=zone_id,
            **{"from": {"x": lamp[0], "y": lamp[1]}},
            lamp={"x": lamp[0], "y": lamp[1]},
            responses=_responses(truth, lamp),
        )
    _event(events, type="proxy_tag_arm", input_surface="armed_tag_button", dock="evidence_tag")
    _event(
        events,
        type="proxy_tag_place",
        input_surface="armed_tag_click",
        point=truth["solution"]["expected_tag_point"],
        object_id=truth["forged_object_id"],
    )
    return {
        "mechanic_id": MECHANIC,
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "interaction_mode": "simplified",
        "events": events,
        "final_state": {
            "lamp_position": {"x": round(lamp[0], 2), "y": round(lamp[1], 2)},
            "visited_zone_ids": visited,
            "sample_count": len(visited),
            "tagged_object_id": truth["forged_object_id"],
            "reset_count": 0,
            "proxy_tag_armed": False,
        },
    }


def test_shadow_crime_controls_materialize_and_l4_preserves_the_original() -> None:
    MATERIALIZER.validate_controls(CONTROLS, ENVIRONMENT)
    assert CONTROLS["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    assert CONTROLS["real_time"] == {"play_time_seconds": 150, "observation_window_ms": 0, "frames_per_observation": 1}
    assert BASE_TASK["natural_language"] == CONTROLS["difficulty"]["4"]["natural_language"]
    for seed in ("shadow-baseline-a", "shadow-baseline-b"):
        original_public, original_truth = SETUP.generate_task_state(BASE_TASK, seed)
        baseline_public, baseline_truth = SETUP.generate_task_state(_task(4, "full"), seed)
        assert _without_control_identity(original_public) == _without_control_identity(baseline_public)
        assert _without_control_identity(original_truth) == _without_control_identity(baseline_truth)


def test_shadow_crime_profiles_change_causal_problem_and_keep_pairs_world_equal() -> None:
    expected_shapes = [(3, 2), (3, 3), (4, 3), (5, 4), (6, 5)]
    for level, expected in zip(range(1, 6), expected_shapes):
        simplified_public, simplified_truth = SETUP.generate_task_state(_task(level, "simplified"), f"shadow-profile-{level}")
        full_public, full_truth = SETUP.generate_task_state(_task(level, "full"), f"shadow-profile-{level}")
        assert simplified_public["challenge_id"] == full_public["challenge_id"]
        assert _without_control_identity(simplified_public) == _without_control_identity(full_public)
        assert _without_control_identity(simplified_truth) == _without_control_identity(full_truth)
        assert (len(simplified_public["objects"]), len(simplified_public["probe_zones"])) == expected
        parameters = CONTROLS["difficulty"][str(level)]["parameters"]
        assert all(zone["radius"] == parameters["zone_radius"] for zone in simplified_public["probe_zones"])


def test_shadow_crime_grader_accepts_every_controlled_condition_and_rejects_cross_surface() -> None:
    for level in range(1, 6):
        for interaction in ("simplified", "full"):
            public, truth = SETUP.generate_task_state(_task(level, interaction), f"shadow-grade-{level}-{interaction}")
            payload = _simplified_payload(public, truth) if interaction == "simplified" else _full_payload(public, truth)
            outcome = GRADER.grade(payload, truth, public)
            assert outcome["passed"] is True, outcome
            if interaction == "full":
                assert sum(event["type"] == "lamp_move" for event in payload["events"]) == len(truth["probe_zones"])
                assert not any(event["type"] == "tag_move" for event in payload["events"])
            wrong_mode = copy.deepcopy(payload)
            wrong_mode["interaction_mode"] = "full" if interaction == "simplified" else "simplified"
            assert GRADER.grade(wrong_mode, truth, public)["feedback"] == "wrong interaction mode"
            stale = copy.deepcopy(payload)
            stale["challenge_id"] = "stale-shadow-challenge"
            assert GRADER.grade(stale, truth, public)["feedback"] == "stale challenge"


def test_shadow_crime_sparse_full_drag_has_the_same_effect_contract_as_simplified() -> None:
    for level in range(1, 6):
        simplified_public, simplified_truth = SETUP.generate_task_state(
            _task(level, "simplified"), f"shadow-same-effect-{level}"
        )
        full_public, full_truth = SETUP.generate_task_state(
            _task(level, "full"), f"shadow-same-effect-{level}"
        )
        assert _without_control_identity(simplified_truth) == _without_control_identity(full_truth)
        simplified = _simplified_payload(simplified_public, simplified_truth)
        full = _full_payload(full_public, full_truth)
        assert GRADER.grade(simplified, simplified_truth, simplified_public)["passed"] is True
        assert GRADER.grade(full, full_truth, full_public)["passed"] is True
        assert sum(event["type"] == "lamp_move" for event in full["events"]) == len(full_truth["probe_zones"])
        assert not any(event["type"] == "tag_move" for event in full["events"])
        assert not {"minimum_lamp_moves", "minimum_travel"} & set(
            full_public["control_condition"]["difficulty_parameters"]
        )


def test_shadow_crime_exported_task_verifier_accepts_every_controlled_condition(tmp_path: Path) -> None:
    for level in range(1, 6):
        for interaction in ("simplified", "full"):
            public, truth = SETUP.generate_task_state(_task(level, interaction), f"shadow-export-{level}-{interaction}")
            result = _simplified_payload(public, truth) if interaction == "simplified" else _full_payload(public, truth)
            result["server_grade"] = GRADER.grade(result, truth, public)
            assert result["server_grade"]["passed"] is True
            exported = {"result": result, "ground_truth": truth, "public_state": public}
            source = tmp_path / f"d{level}-{interaction}.json"
            source.write_text(json.dumps(exported), encoding="utf-8")

            def copy_from_env(remote: str, destination: str) -> None:
                assert remote == "/tmp/task_result.json"
                Path(destination).write_bytes(source.read_bytes())

            verified = VERIFIER.verify_task(env_info={"copy_from_env": copy_from_env})
            assert verified["passed"] is True, verified
            assert verified["score"] == 100
