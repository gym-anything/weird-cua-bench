from __future__ import annotations

import copy
import importlib.util
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "bureaucratic_signature_trap_env"
MECHANIC = "bureaucratic_signature_trap"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SETUP = _load_module("signature_difficulty_setup", BENCHMARK / "shared_scripts" / "setup_task.py")
MATERIALIZER = _load_module(
    "signature_difficulty_materializer",
    BENCHMARK / "tools" / "materialize_controlled_tasks.py",
)
GRADER = _load_module(
    "signature_difficulty_grader",
    BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{MECHANIC}.py",
)
VERIFIER_HELPERS = _load_module(
    "signature_difficulty_verifier_helpers",
    BENCHMARK / "shared_runtime" / "verifier_helpers.py",
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


CONTROLS = _read_json(ENVIRONMENT / "controls.json")
BASE_TASK = _read_json(
    ENVIRONMENT / "tasks" / f"{MECHANIC}_seed_0001" / "task.json"
)


def _task(level: int, interaction: str = "full") -> dict:
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
    for key in ("task_id", "challenge_id", "control_condition"):
        result.pop(key, None)
    return result


def _polyline_length(points: list[list[float]]) -> float:
    return sum(math.dist(before, after) for before, after in zip(points, points[1:]))


def _events(truth: dict, interaction: str, sheet_source: str) -> list[dict]:
    events: list[dict] = []
    for layer in truth["form"]["layers"]:
        start = [float(layer["initial"]["x"]), float(layer["initial"]["y"])]
        target = [float(layer["target"]["x"]), float(layer["target"]["y"])]
        if interaction == "simplified":
            current = start
            axis_tolerance = float(truth["form"]["alignment_tolerance"]) / math.sqrt(2)
            for axis in (0, 1):
                step = 8.0 if target[axis] > current[axis] else -8.0
                count = math.ceil(max(0, abs(target[axis] - current[axis]) - axis_tolerance) / 8)
                for _ in range(count):
                    after = current.copy()
                    after[axis] += step
                    events.append({
                        "sequence": len(events) + 1,
                        "kind": "sheet_drag",
                        "sheet_id": layer["id"],
                        "input_source": sheet_source,
                        "start": current,
                        "samples": [after],
                        "end": after,
                    })
                    current = after
        else:
            count = max(1, math.ceil(math.dist(start, target) / 40))
            samples = [
                [
                    start[0] + (target[0] - start[0]) * index / count,
                    start[1] + (target[1] - start[1]) * index / count,
                ]
                for index in range(1, count + 1)
            ]
            events.append({
                "sequence": len(events) + 1,
                "kind": "sheet_drag",
                "sheet_id": layer["id"],
                "input_source": sheet_source,
                "start": start,
                "samples": samples,
                "end": samples[-1],
            })
    events.extend([
        {
            "sequence": len(events) + 1,
            "kind": "signature",
            "input_source": "signature_canvas",
            "points": truth["form"]["original_trace"],
        },
        {
            "sequence": len(events) + 2,
            "kind": "certify",
            "input_source": "certify_button",
        },
    ])
    return events


def _payload(public: dict, truth: dict, interaction: str) -> dict:
    source = {
        "simplified": "sheet_nudge_button",
        "full": "fixed_registration_tab",
    }[interaction]
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "events": _events(truth, interaction, source),
    }


def test_signature_controls_materialize_all_conditions_and_keep_other_axes() -> None:
    MATERIALIZER.validate_controls(CONTROLS, ENVIRONMENT)
    assert CONTROLS["baseline"] == {
        "difficulty": 4,
        "interaction": "full",
        "real_time": "live",
    }
    assert CONTROLS["real_time"] == {
        "play_time_seconds": 120,
        "observation_window_ms": 240,
        "frames_per_observation": 1,
    }
    assert {
        name: value["implemented"]
        for name, value in CONTROLS["interaction"].items()
    } == {"simplified": True, "full": True}


def test_signature_materializer_writes_five_levels_for_both_interactions(tmp_path: Path) -> None:
    written = MATERIALIZER.materialize_environment(ENVIRONMENT, tmp_path)
    assert len(written) == 10
    conditions = {
        (
            task["metadata"]["control_condition"]["difficulty"],
            task["metadata"]["control_condition"]["interaction"],
        )
        for task in (_read_json(path / "task.json") for path in written)
    }
    assert conditions == {
        (level, interaction)
        for level in range(1, 6)
        for interaction in ("simplified", "full")
    }


def test_signature_level_four_preserves_the_legacy_seeded_form_exactly() -> None:
    for index in range(12):
        seed = f"signature-baseline-preservation-{index:02d}"
        original_public, original_truth = SETUP.generate_task_state(BASE_TASK, seed)
        baseline_public, baseline_truth = SETUP.generate_task_state(_task(4), seed)
        assert baseline_public["challenge_id"] == original_public["challenge_id"]
        assert baseline_truth["challenge_id"] == original_truth["challenge_id"]
        assert baseline_public["form"] == original_public["form"]
        assert baseline_truth["form"] == original_truth["form"]
        assert _without_control_identity(baseline_public) == _without_control_identity(original_public)
        assert _without_control_identity(baseline_truth) == _without_control_identity(original_truth)


def test_signature_profiles_change_and_order_the_visible_problem() -> None:
    expected_layers = [1, 2, 3, 4, 5]
    expected_apertures = [96, 88, 80, 72, 64]
    expected_alignment = [18, 14, 11, 8, 6]
    expected_trace_points = [73, 85, 97, 109, 145]
    for seed_index in range(16):
        generated = [
            SETUP.generate_task_state(_task(level), f"signature-profile-order-{seed_index:02d}")[0]
            for level in range(1, 6)
        ]
        forms = [public["form"] for public in generated]
        assert [len(form["layers"]) for form in forms] == expected_layers
        assert [form["aperture"]["radius"] for form in forms] == expected_apertures
        assert [form["alignment_tolerance"] for form in forms] == expected_alignment
        assert [len(form["original_trace"]) for form in forms] == expected_trace_points
        assert all(
            left < right
            for left, right in zip(
                map(lambda form: _polyline_length(form["original_trace"]), forms),
                map(lambda form: _polyline_length(form["original_trace"]), forms[1:]),
            )
        )
        assert [
            form["signature"]["minimum_coverage"]
            for form in forms
        ] == [0.65, 0.72, 0.78, 0.84, 0.92]
        assert [
            form["signature"]["mean_deviation"]
            for form in forms
        ] == [22, 19, 16.5, 14, 10]


def test_signature_interaction_pair_preserves_every_difficulty_world() -> None:
    for level in range(1, 6):
        for seed_index in range(4):
            seed = f"signature-paired-d{level}-{seed_index}"
            simplified_public, simplified_truth = SETUP.generate_task_state(
                _task(level, "simplified"), seed
            )
            full_public, full_truth = SETUP.generate_task_state(
                _task(level, "full"), seed
            )
            assert simplified_public["challenge_id"] == full_public["challenge_id"]
            assert simplified_public["form"] == full_public["form"]
            assert simplified_truth["form"] == full_truth["form"]
            assert _without_control_identity(simplified_public) == _without_control_identity(full_public)
            assert _without_control_identity(simplified_truth) == _without_control_identity(full_truth)


def test_signature_grader_and_export_verifier_accept_all_ten_conditions() -> None:
    for level in range(1, 6):
        for interaction in ("simplified", "full"):
            public, truth = SETUP.generate_task_state(
                _task(level, interaction),
                f"signature-grade-d{level}-{interaction}",
            )
            payload = _payload(public, truth, interaction)
            grade = GRADER.grade(payload, truth, public)
            assert grade["passed"] is True, grade
            verified = VERIFIER_HELPERS.verify_bureaucratic_signature_trap({
                "result": payload,
                "ground_truth": truth,
                "public_state": public,
            })
            assert verified == {
                "passed": True,
                "score": 100,
                "feedback": grade["feedback"],
            }


def test_signature_grader_rejects_cross_axis_and_profile_tampering() -> None:
    public, truth = SETUP.generate_task_state(
        _task(5, "simplified"),
        "signature-profile-tamper",
    )
    payload = _payload(public, truth, "simplified")

    wrong_source = copy.deepcopy(payload)
    wrong_source["events"][0]["input_source"] = "fixed_registration_tab"
    assert GRADER.grade(wrong_source, truth, public)["feedback"] == (
        "sheet drag uses the wrong interaction input"
    )

    wrong_task = copy.deepcopy(payload)
    wrong_task["task_id"] = "stale-task"
    assert GRADER.grade(wrong_task, truth, public)["feedback"] == (
        "stale task or challenge"
    )

    wrong_mechanic = copy.deepcopy(public)
    wrong_mechanic["mechanic_id"] = "different_mechanic"
    assert GRADER.grade(payload, truth, wrong_mechanic)["feedback"] == (
        "mechanic mismatch"
    )

    skewed_public = copy.deepcopy(public)
    skewed_public["form"]["alignment_tolerance"] = 8
    assert GRADER.grade(payload, truth, skewed_public)["feedback"] == (
        "public/private carbon contract mismatch"
    )

    skewed_truth = copy.deepcopy(truth)
    skewed_state = copy.deepcopy(public)
    skewed_truth["control_condition"]["difficulty_parameters"]["layer_count"] = 4
    skewed_state["control_condition"]["difficulty_parameters"]["layer_count"] = 4
    assert GRADER.grade(payload, skewed_truth, skewed_state)["feedback"] == (
        "carbon difficulty profile differs from form contract"
    )
