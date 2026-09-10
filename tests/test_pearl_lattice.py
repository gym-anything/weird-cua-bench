from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

from weird_captcha_gym.shared_scripts import setup_task


ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "weird_captcha_gym" / "environments" / "pearl_lattice_env"
MECHANIC = "pearl_lattice"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("pearl_lattice_generator_test", ROOT / "weird_captcha_gym/shared_scripts/incubator_generators/pearl_lattice.py")
GRADER = _load("pearl_lattice_grader_test", ROOT / "weird_captcha_gym/shared_runtime/server/incubator_graders/pearl_lattice.py")


def _base_task() -> dict:
    return json.loads((ENV / "tasks" / f"{MECHANIC}_seed_0001" / "task.json").read_text())


def _controlled_task(level: int, interaction: str, real_time: str = "live") -> dict:
    controls = json.loads((ENV / "controls.json").read_text())
    task = copy.deepcopy(_base_task())
    task["natural_language"] = controls["difficulty"][str(level)]["natural_language_by_interaction"][interaction]
    task.setdefault("metadata", {})["control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": controls["difficulty"][str(level)]["parameters"],
    }
    return task


def _drop(board: dict[tuple[int, int, int], int], column: tuple[int, int], mark: int) -> int:
    for y in range(4):
        cell = (column[0], y, column[1])
        if cell not in board:
            board[cell] = mark
            return y
    raise AssertionError("test tried to drop into a full column")


def _legal(board: dict[tuple[int, int, int], int]) -> list[tuple[int, int]]:
    return [(x, z) for z in range(4) for x in range(4) if (x, 3, z) not in board]


def _payload(public: dict, truth: dict, interaction: str) -> dict:
    board = {tuple(int(part) for part in key.split(",")): int(value) for key, value in truth["initial_board"].items()}
    pressure = [tuple(column) for column in truth["pressure_columns"]]
    pressure_index = 0
    preview = _legal(board)[0]
    events: list[dict] = []
    sequence = 0

    def line(mark: int) -> bool:
        return any(all(board.get(tuple(cell), 0) == mark for cell in candidate) for candidate in GRADER.ALL_LINES)

    for raw_target in truth["solution_moves"]:
        target = tuple(raw_target)
        legal = _legal(board)
        if preview == target:
            next_preview = legal[(legal.index(preview) + 1) % len(legal)]
            sequence += 1
            events.append({
                "seq": sequence,
                "type": "cycle_preview",
                "input_source": "board_surface" if interaction == "full" else "proxy_next",
                "from_column": list(preview),
                "to_column": list(next_preview),
            })
            preview = next_preview
        while preview != target:
            next_preview = legal[(legal.index(preview) + 1) % len(legal)]
            sequence += 1
            events.append({
                "seq": sequence,
                "type": "cycle_preview",
                "input_source": "board_surface" if interaction == "full" else "proxy_next",
                "from_column": list(preview),
                "to_column": list(next_preview),
            })
            preview = next_preview
        height = _drop(board, target, 1)
        sequence += 1
        events.append({
            "seq": sequence,
            "type": "place",
            "input_source": "confirm_area" if interaction == "full" else "confirm_button",
            "mark": 1,
            "column": list(target),
            "height": height,
        })
        if line(1):
            break
        rival, pressure_index = GENERATOR._opponent_column(board, pressure, pressure_index)
        assert rival is not None
        rival_height = _drop(board, rival, -1)
        sequence += 1
        events.append({
            "seq": sequence,
            "type": "opponent_place",
            "input_source": "opponent_ai",
            "mark": -1,
            "column": list(rival),
            "height": rival_height,
        })
        legal = _legal(board)
        if preview not in legal:
            preview = legal[0]

    sequence += 1
    events.append({"seq": sequence, "type": "submit", "input_source": "certify_button", "completed": line(1)})
    return {
        "mechanic_id": MECHANIC,
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "control_condition": public["control_condition"],
        "events": events,
        "completed": line(1),
    }


def test_all_profiles_are_deterministic_and_keep_the_same_3d_world_across_interaction() -> None:
    for level in range(1, 6):
        full_public, full_truth = setup_task.generate_task_state(_controlled_task(level, "full"), f"pearl-profile-{level}")
        simple_public, simple_truth = setup_task.generate_task_state(_controlled_task(level, "simplified"), f"pearl-profile-{level}")
        assert len(full_public["world"]["cells"]) == 64
        assert full_public["world"] == simple_public["world"]
        assert full_truth["initial_board"] == simple_truth["initial_board"]
        assert full_truth["solution_moves"]
        repeated_public, repeated_truth = setup_task.generate_task_state(_controlled_task(level, "full"), f"pearl-profile-{level}")
        assert repeated_public == full_public
        assert repeated_truth == full_truth


def test_baseline_is_level_three_full_live_and_source_anchored() -> None:
    public, truth = setup_task.generate_task_state(_base_task(), "pearl-baseline")
    assert public["control_condition"] == json.loads((ENV / "controls.json").read_text())["baseline"] | {
        "difficulty_parameters": public["control_condition"]["difficulty_parameters"]
    }
    assert public["world"]["size"] == 4
    assert len(truth["target_lines"]) == 2
    assert _base_task()["metadata"]["source_anchors"] == ["ART-336"]


def test_independent_grader_accepts_both_surfaces_and_rejects_tampering() -> None:
    for level in range(1, 6):
        for interaction in ("full", "simplified"):
            public, truth = setup_task.generate_task_state(_controlled_task(level, interaction), f"pearl-grade-{level}")
            payload = _payload(public, truth, interaction)
            decision = GRADER.grade(payload, truth, public)
            assert decision["passed"] is True, (level, interaction, decision)

            stale = copy.deepcopy(payload)
            stale["challenge_id"] = "stale-pearl-lattice"
            assert GRADER.grade(stale, truth, public)["passed"] is False

            wrong_surface = copy.deepcopy(payload)
            wrong_surface["events"][0]["input_source"] = "proxy_next" if interaction == "full" else "board_surface"
            assert GRADER.grade(wrong_surface, truth, public)["passed"] is False


def test_player_move_ceiling_is_an_active_grader_rule() -> None:
    controls = json.loads((ENV / "controls.json").read_text())
    for interaction in ("full", "simplified"):
        task = _controlled_task(2, interaction)
        public = truth = None
        for index in range(64):
            candidate_public, candidate_truth = setup_task.generate_task_state(task, f"pearl-ceiling-{interaction}-{index}")
            if len(candidate_truth["solution_moves"]) > 1:
                public, truth = candidate_public, candidate_truth
                break
        assert public is not None and truth is not None
        payload = _payload(public, truth, interaction)
        assert len(truth["solution_moves"]) > 1

        limited_condition = copy.deepcopy(public["control_condition"])
        limited_condition["difficulty_parameters"]["max_player_moves"] = 1
        public["control_condition"] = copy.deepcopy(limited_condition)
        truth["control_condition"] = copy.deepcopy(limited_condition)
        payload["control_condition"] = copy.deepcopy(limited_condition)
        decision = GRADER.grade(payload, truth, public)
        assert decision["passed"] is False
        assert "ceiling" in decision["feedback"]
    assert controls["difficulty"]["2"]["parameters"]["max_player_moves"] == 6


def test_controls_split_and_browser_contract_are_complete() -> None:
    controls = json.loads((ENV / "controls.json").read_text())
    assert controls["baseline"] == {"difficulty": 3, "interaction": "full", "real_time": "live"}
    assert controls["real_time_diagnostic"]["classification"] == "not_real_time_under_settled_definition"
    assert controls["capabilities"] == {
        "visual_understanding": "3D",
        "temporal_understanding_and_memory": False,
        "reasoning_and_planning": True,
        "exploration_and_interface_understanding": False,
    }
    split = json.loads((ROOT / "weird_captcha_gym/splits/pearl_lattice_split.json").read_text())
    assert len(split["variations_tasks"]) == 10
    renderer = (ROOT / "weird_captcha_gym/shared_runtime/app/mechanics/pearl_lattice.js").read_text()
    assert 'cycle("board_surface")' in renderer
    assert 'cycle("proxy_next")' in renderer
    assert 'place("confirm_area")' in renderer
    assert 'place("confirm_button")' in renderer
    assert "4×4×4" in renderer
    assert "requestAnimationFrame" in renderer
    assert "previewLabelDetail" in renderer
    assert "rotationStepDegrees" in renderer
    assert "maxPlayerMoves" in renderer

    for level, expected_step in ((1, 18.0), (2, 15.0), (3, 12.0), (4, 10.0), (5, 8.0)):
        public, _ = setup_task.generate_task_state(_controlled_task(level, "full"), f"pearl-contract-{level}")
        assert public["world"]["rotation_step_degrees"] == expected_step
        assert public["world"]["max_player_moves"] == json.loads((ENV / "controls.json").read_text())["difficulty"][str(level)]["parameters"]["max_player_moves"]
    l5_public, _ = setup_task.generate_task_state(_controlled_task(5, "full"), "pearl-contract-l5")
    assert l5_public["world"]["preview_label_detail"] == "layer"
