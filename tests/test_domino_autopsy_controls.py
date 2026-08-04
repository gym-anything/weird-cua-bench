from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
ENV_ROOT = BENCHMARK / "environments" / "domino_autopsy_env"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


SETUP = _load("domino_control_setup", BENCHMARK / "shared_scripts" / "setup_task.py")
MATERIALIZER = _load(
    "domino_control_materializer",
    BENCHMARK / "tools" / "materialize_controlled_tasks.py",
)
GRADER = _load(
    "domino_control_grader",
    BENCHMARK / "shared_runtime" / "server" / "legacy_browser_grader.py",
)
VERIFIERS = _load(
    "domino_control_verifiers",
    BENCHMARK / "shared_runtime" / "verifier_helpers.py",
)


def _task(level: int, interaction: str) -> dict:
    controls = _read(ENV_ROOT / "controls.json")
    base = _read(ENV_ROOT / "tasks" / "domino_autopsy_seed_0001" / "task.json")
    return MATERIALIZER.controlled_task(
        base,
        mechanic_id="domino_autopsy",
        level=level,
        interaction=interaction,
        profile=controls["difficulty"][str(level)],
        task_dir_name=f"domino_autopsy_d{level}_{interaction}_seed_0001",
    )


def _without_identity(value: dict) -> dict:
    result = copy.deepcopy(value)
    for key in ("task_id", "challenge_id", "control_condition"):
        result.pop(key, None)
    return result


def _passing_payload(truth: dict, interaction: str) -> dict:
    bell = str(truth["bell_body_id"])
    source = {"simplified": "domino_click_place", "full": "domino_drag"}[interaction]
    placements = {
        str(domino_id): {
            "x": float(target["x"]),
            "y": float(target["y"]),
            "angle": float(target["angle"]),
        }
        for domino_id, target in zip(truth["loose_ids"], truth["target_slots"])
    }
    ordered = sorted(
        [
            *[
                (str(item["id"]), float(item["x"]))
                for item in truth["fixed_dominoes"]
            ],
            *[
                (str(domino_id), float(placements[str(domino_id)]["x"]))
                for domino_id in truth["loose_ids"]
            ],
        ],
        key=lambda item: item[1],
    )
    return {
        "mechanic_id": "domino_autopsy",
        "challenge_id": truth["challenge_id"],
        "placements": placements,
        "placement_sources": {
            str(domino_id): source for domino_id in truth["loose_ids"]
        },
        "physics_engine": "matter-js@0.20.0",
        "bell_hit": True,
        "bell_peak_angle": 0.6,
        "run_completed": True,
        "collision_pairs": [
            *[[left[0], right[0]] for left, right in zip(ordered, ordered[1:])],
            [ordered[-1][0], bell],
        ],
    }


def test_domino_controls_validate_and_materialize_ten_tasks(tmp_path: Path) -> None:
    controls = _read(ENV_ROOT / "controls.json")
    MATERIALIZER.validate_controls(controls, ENV_ROOT)
    assert _read(BENCHMARK / "real_time.json")["environments"]["domino_autopsy"] == controls["real_time"]
    written = MATERIALIZER.materialize_environment(ENV_ROOT, tmp_path)
    assert len(written) == 10
    assert {
        (
            _read(path / "task.json")["metadata"]["control_condition"]["difficulty"],
            _read(path / "task.json")["metadata"]["control_condition"]["interaction"],
        )
        for path in written
    } == {(level, interaction) for level in range(1, 6) for interaction in ("simplified", "full")}


def test_domino_level_three_preserves_the_original_world() -> None:
    base = _read(ENV_ROOT / "tasks" / "domino_autopsy_seed_0001" / "task.json")
    original_public, original_truth = SETUP.generate_task_state(base, "domino-baseline")
    controlled_public, controlled_truth = SETUP.generate_task_state(
        _task(3, "full"),
        "domino-baseline",
    )
    assert _without_identity(controlled_public) == _without_identity(original_public)
    assert _without_identity(controlled_truth) == _without_identity(original_truth)


def test_domino_profiles_change_the_coupled_physics_problem() -> None:
    expected_counts = [1, 2, 3, 4, 5]
    expected_fixed_counts = [8, 8, 8, 7, 6]
    expected_spacings = [40, 40, 40, 50, 54]
    expected_swings = [0.02, 0.03, 0.03, 0.25, 0.4]
    for level, count, fixed_count, spacing, swing in zip(
        range(1, 6),
        expected_counts,
        expected_fixed_counts,
        expected_spacings,
        expected_swings,
    ):
        public, truth = SETUP.generate_task_state(_task(level, "full"), "domino-profiles")
        assert len(public["board"]["loose"]) == count
        assert len(public["board"]["fixed"]) == fixed_count
        assert len(truth["target_slots"]) == count
        assert (
            truth["target_slots"][1]["x"] - truth["target_slots"][0]["x"]
            if count > 1
            else spacing
        ) == spacing
        assert truth["minimum_bell_swing_radians"] == swing
        assert len(truth["expected_body_ids"]) == fixed_count + count
        assert bool(public["board"].get("target_guides")) is (level <= 2)


def test_domino_interactions_share_world_and_enforce_input_surface() -> None:
    for level in range(1, 6):
        simple_public, simple_truth = SETUP.generate_task_state(
            _task(level, "simplified"),
            f"domino-pair-{level}",
        )
        full_public, full_truth = SETUP.generate_task_state(
            _task(level, "full"),
            f"domino-pair-{level}",
        )
        assert _without_identity(simple_public) == _without_identity(full_public)
        assert _without_identity(simple_truth) == _without_identity(full_truth)

        for interaction, public, truth in (
            ("simplified", simple_public, simple_truth),
            ("full", full_public, full_truth),
        ):
            payload = _passing_payload(truth, interaction)
            assert GRADER.grade(payload, truth, public)["passed"] is True
            exported = {
                "result": payload,
                "ground_truth": truth,
                "public_state": public,
            }
            assert VERIFIERS.verify_domino_autopsy(exported)["passed"] is True

            wrong = copy.deepcopy(payload)
            wrong_source = "domino_drag" if interaction == "simplified" else "domino_click_place"
            wrong["placement_sources"] = {
                domino_id: wrong_source for domino_id in wrong["placement_sources"]
            }
            assert GRADER.grade(wrong, truth, public)["passed"] is False
            assert VERIFIERS.verify_domino_autopsy(
                {**exported, "result": wrong}
            )["passed"] is False

            stale = copy.deepcopy(payload)
            stale["challenge_id"] = "stale-challenge"
            assert GRADER.grade(stale, truth, public)["passed"] is False
            assert VERIFIERS.verify_domino_autopsy(
                {**exported, "result": stale}
            )["passed"] is False


def test_domino_replay_rejects_fabricated_physics_and_impossible_poses() -> None:
    public, truth = SETUP.generate_task_state(
        _task(5, "full"),
        "domino-adversarial-replay",
    )
    passing = _passing_payload(truth, "full")
    grade = GRADER.grade(passing, truth, public)
    assert grade["passed"] is True
    assert "independent pose replay" in grade["feedback"]

    exported = {
        "result": passing,
        "ground_truth": truth,
        "public_state": public,
    }
    assert VERIFIERS.verify_domino_autopsy(exported)["passed"] is True

    first_id = str(truth["loose_ids"][0])
    cases = []

    outside_board = copy.deepcopy(passing)
    outside_board["placements"][first_id]["x"] = -500
    cases.append(outside_board)

    floating = copy.deepcopy(passing)
    floating["placements"][first_id]["y"] = 100
    cases.append(floating)

    non_finite = copy.deepcopy(passing)
    non_finite["placements"][first_id]["angle"] = float("nan")
    cases.append(non_finite)

    fabricated_graph = copy.deepcopy(passing)
    fabricated_graph["collision_pairs"] = [
        [truth["first_body_id"], truth["bell_body_id"]]
    ]
    cases.append(fabricated_graph)

    impossible_swing = copy.deepcopy(passing)
    impossible_swing["bell_peak_angle"] = 99
    cases.append(impossible_swing)

    for payload in cases:
        assert GRADER.grade(payload, truth, public)["passed"] is False
        assert VERIFIERS.verify_domino_autopsy(
            {**exported, "result": payload}
        )["passed"] is False
