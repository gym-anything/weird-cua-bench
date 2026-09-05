from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

from weird_captcha_gym.tools.materialize_controlled_tasks import controlled_task, materialize_environment


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "weird_captcha_gym"
ENV = BENCH / "environments/crackglaze_crossing_env"
MECHANIC_ID = "crackglaze_crossing"
GENERATOR_PATH = BENCH / "shared_scripts/incubator_generators/crackglaze_crossing.py"
GRADER_PATH = BENCH / "shared_runtime/server/incubator_graders/crackglaze_crossing.py"
SOLVER_PATH = BENCH / "tools/incubator_solvers/crackglaze_crossing.py"
VERIFIER_PATH = ENV / "tasks/crackglaze_crossing_seed_0001/verifier.py"
FRONTEND_PATH = BENCH / "shared_runtime/app/mechanics/crackglaze_crossing.js"
STYLES_PATH = BENCH / "shared_runtime/app/mechanics/crackglaze_crossing.css"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("crackglaze_generator_test", GENERATOR_PATH)
GRADER = _load("crackglaze_grader_test", GRADER_PATH)
SOLVER = _load("crackglaze_solver_test", SOLVER_PATH)
VERIFIER = _load("crackglaze_verifier_test", VERIFIER_PATH)


def _base_task() -> dict:
    return json.loads((ENV / "tasks/crackglaze_crossing_seed_0001/task.json").read_text(encoding="utf-8"))


def _controls() -> dict:
    return json.loads((ENV / "controls.json").read_text(encoding="utf-8"))


def _task(level: int, interaction: str, real_time: str = "live") -> dict:
    task = _base_task()
    task["_control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": copy.deepcopy(_controls()["difficulty"][str(level)]["parameters"]),
    }
    return task


def _direction(cells: dict[str, dict], origin: str, destination: str) -> str:
    first, second = cells[origin], cells[destination]
    delta = (second["row"] - first["row"], second["column"] - first["column"])
    return {(-1, 0): "up", (1, 0): "down", (0, -1): "left", (0, 1): "right"}[delta]


def _payload(public: dict, truth: dict, interaction: str, path: list[str] | None = None) -> dict:
    path = list(path or truth["certified_solution"])
    cells = {cell["id"]: cell for cell in public["cells"]}
    fuses = {cell_id: public["fuse_lengths"][cell["glaze"]] for cell_id, cell in cells.items()}
    events = []
    lit_at: dict[str, int] = {}
    shattered: set[str] = set()
    collected: set[str] = set()
    position = public["start_id"]
    status = "active"
    step = 0
    for destination in path[1:]:
        origin = position
        step += 1
        lit_at.setdefault(origin, step)
        shattered = {cell_id for cell_id, lit_step in lit_at.items() if step - lit_step >= fuses[cell_id]}
        expired = destination in shattered
        event = {
            "sequence": len(events) + 1,
            "type": "move",
            "from": origin,
            "to": destination,
            "direction": _direction(cells, origin, destination),
            "step_index": step,
            "input_source": "tile_click" if interaction == "full" else "direction_button",
            "accepted": not expired,
            "failure": "expired_destination" if expired else None,
        }
        if interaction == "full":
            event["point"] = [
                (cells[destination]["column"] + 0.5) / public["columns"],
                (cells[destination]["row"] + 0.5) / public["rows"],
            ]
        events.append(event)
        position = destination
        if expired:
            status = "failed"
            break
        if destination in public["lantern_ids"]:
            collected.add(destination)
        if destination == public["exit_id"] and collected == set(public["lantern_ids"]):
            status = "passed"
            break
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction_mode": interaction,
        "events": events,
        "final_state": {
            "position": position,
            "step_count": step,
            "collected_lantern_ids": sorted(collected),
            "lit_at": dict(sorted(lit_at.items())),
            "shattered_cell_ids": sorted(shattered),
            "status": status,
        },
        "completed": status == "passed",
    }


def _bounce_to_failure(public: dict, truth: dict, interaction: str) -> dict:
    start = public["start_id"]
    neighbor = public["neighbors"][start][0]
    path = [start]
    current = start
    for _ in range(max(public["fuse_lengths"].values()) * 3):
        current = neighbor if current == start else start
        path.append(current)
        payload = _payload(public, truth, interaction, path)
        if payload["final_state"]["status"] == "failed":
            return payload
    raise AssertionError("bounce route did not fail")


def _counterfactual_world(public: dict, truth: dict) -> tuple[dict, dict]:
    counter_public = copy.deepcopy(public)
    counter_truth = copy.deepcopy(truth)
    mapping = truth["search_certificate"]["counterfactual"]["fuse_lengths"]
    counter_public["fuse_lengths"] = copy.deepcopy(mapping)
    counter_truth["fuse_lengths"] = copy.deepcopy(mapping)
    return counter_public, counter_truth


def test_all_ten_conditions_grade_and_preserve_interaction_world() -> None:
    for level in range(1, 6):
        worlds = []
        for interaction in ("simplified", "full"):
            public, truth = GENERATOR.generate(_task(level, interaction), "condition-parity")
            outcome = GRADER.grade(_payload(public, truth, interaction), truth, public)
            assert outcome["passed"] is True, (level, interaction, outcome)
            assert truth["search_certificate"]["requires_revisit"] is True
            assert truth["search_certificate"]["counterfactual"]["same_geometry"] is True
            worlds.append({key: public[key] for key in (
                "challenge_id", "rows", "columns", "cells", "neighbors", "start_id", "exit_id",
                "lantern_ids", "glazes", "fuse_lengths", "parameters",
            )})
        assert worlds[0] == worlds[1]


def test_geometry_only_policy_fails_and_same_geometry_fuse_swap_changes_route() -> None:
    for level in range(1, 6):
        for index in range(12):
            public, truth = GENERATOR.generate(_task(level, "simplified"), f"ablation-{level}-{index}")
            intended = GRADER.grade(_payload(public, truth, "simplified"), truth, public)
            geometry = GRADER.grade(
                _payload(public, truth, "simplified", truth["geometry_only_paths"][0]), truth, public
            )
            assert intended["passed"] is True
            assert geometry["passed"] is False
            assert truth["search_certificate"]["geometry_only_ablations"][0]["passed"] is False

            counter_public, counter_truth = _counterfactual_world(public, truth)
            counter_path = truth["search_certificate"]["counterfactual"]["certified_solution"]
            counter_pass = GRADER.grade(
                _payload(counter_public, counter_truth, "simplified", counter_path),
                counter_truth,
                counter_public,
            )
            actual_path_in_counterfactual = GRADER.grade(
                _payload(counter_public, counter_truth, "simplified", truth["certified_solution"]),
                counter_truth,
                counter_public,
            )
            counter_path_in_actual = GRADER.grade(
                _payload(public, truth, "simplified", counter_path), truth, public
            )
            assert counter_pass["passed"] is True
            assert actual_path_in_counterfactual["passed"] is False
            assert counter_path_in_actual["passed"] is False


def test_opening_walk_exposes_every_fuse_before_the_generated_core() -> None:
    for level in range(1, 6):
        public, truth = GENERATOR.generate(_task(level, "full"), f"witness-{level}")
        cells = {cell["id"]: cell for cell in public["cells"]}
        witnesses = truth["calibration_cell_ids"]
        assert len(witnesses) == public["parameters"]["glaze_count"]
        assert len({cells[cell_id]["glaze"] for cell_id in witnesses}) == len(witnesses)
        first_core_index = next(
            index for index, cell_id in enumerate(truth["certified_solution"])
            if cells[cell_id]["row"] >= 4
        )
        core_entry_step = first_core_index
        for leave_step, cell_id in enumerate(witnesses, 1):
            fuse = public["fuse_lengths"][cells[cell_id]["glaze"]]
            assert core_entry_step - leave_step >= fuse


def test_live_and_paused_conditions_do_not_change_the_turn_driven_world() -> None:
    for level in range(1, 6):
        live, _ = GENERATOR.generate(_task(level, "full", "live"), "clock-parity")
        paused, _ = GENERATOR.generate(_task(level, "full", "paused"), "clock-parity")
        for key in ("challenge_id", "cells", "neighbors", "fuse_lengths", "lantern_ids", "reference_steps"):
            assert live[key] == paused[key]


def test_first_built_configuration_is_the_l3_full_baseline() -> None:
    controls = _controls()
    assert controls["baseline"] == {"difficulty": 3, "interaction": "full", "real_time": "live"}
    assert controls["difficulty"]["3"]["parameters"] == GENERATOR.BASELINE_PARAMETERS
    original_public, original_truth = GENERATOR.generate(_base_task(), "fixed-baseline")
    l3_public, l3_truth = GENERATOR.generate(_task(3, "full"), "fixed-baseline")
    keys = ("challenge_id", "rows", "columns", "cells", "neighbors", "fuse_lengths", "lantern_ids")
    assert {key: original_public[key] for key in keys} == {key: l3_public[key] for key in keys}
    assert original_truth["certified_solution"] == l3_truth["certified_solution"]


def test_failure_partial_credit_cross_mode_stale_and_forged_state_are_rejected() -> None:
    for interaction in ("simplified", "full"):
        public, truth = GENERATOR.generate(_task(3, interaction), f"failure-{interaction}")
        failed = _bounce_to_failure(public, truth, interaction)
        outcome = GRADER.grade(failed, truth, public)
        assert outcome["passed"] is False
        assert outcome["graded"] is True
        assert failed["final_state"]["status"] == "failed"

    public, truth = GENERATOR.generate(_task(3, "full"), "tamper")
    payload = _payload(public, truth, "full")
    wrong_mode = copy.deepcopy(payload)
    wrong_mode["interaction_mode"] = "simplified"
    assert GRADER.grade(wrong_mode, truth, public)["passed"] is False
    stale = copy.deepcopy(payload)
    stale["challenge_id"] = "glaze-stale"
    assert "stale" in GRADER.grade(stale, truth, public)["feedback"]
    forged = copy.deepcopy(payload)
    forged["final_state"]["shattered_cell_ids"] = []
    assert "final floor state" in GRADER.grade(forged, truth, public)["feedback"]
    teleport = copy.deepcopy(payload)
    teleport["events"][0]["to"] = public["exit_id"]
    assert "adjacent" in GRADER.grade(teleport, truth, public)["feedback"]
    proxy = copy.deepcopy(payload)
    proxy["events"][0]["input_source"] = "direction_button"
    assert "destination tile" in GRADER.grade(proxy, truth, public)["feedback"]


def test_seeded_generation_varies_active_topology_and_remains_reachable() -> None:
    challenges = set()
    topologies = set()
    lantern_sets = set()
    fuse_maps = set()
    for index in range(50):
        public, truth = GENERATOR.generate(_task(5, "full"), f"scale-{index}")
        challenges.add(public["challenge_id"])
        topologies.add(truth["search_certificate"]["topology_hash"])
        lantern_sets.add(tuple(public["lantern_ids"]))
        fuse_maps.add(tuple(sorted(public["fuse_lengths"].items())))
        assert GRADER.grade(_payload(public, truth, "full"), truth, public)["passed"] is True
        assert GRADER.grade(
            _payload(public, truth, "full", truth["geometry_only_paths"][0]), truth, public
        )["passed"] is False
        for cell in public["cells"]:
            assert 0 <= cell["row"] < public["rows"]
            assert 0 <= cell["column"] < public["columns"]
            for neighbor in public["neighbors"][cell["id"]]:
                assert cell["id"] in public["neighbors"][neighbor]
    assert len(challenges) == 50
    assert len(topologies) >= 45
    assert len(lantern_sets) >= 35
    assert len(fuse_maps) >= 12


def test_profiles_change_the_active_decision_and_memory_problem() -> None:
    profiles = _controls()["difficulty"]
    assert [profiles[str(level)]["parameters"]["glaze_count"] for level in range(1, 6)] == [2, 3, 3, 4, 4]
    assert [profiles[str(level)]["parameters"]["gallery_cells"] for level in range(1, 6)] == [0, 0, 2, 4, 6]
    assert [profiles[str(level)]["parameters"]["lantern_count"] for level in range(1, 6)] == [3, 3, 3, 3, 4]
    assert [profiles[str(level)]["parameters"]["minimum_policy_failures"] for level in range(1, 6)] == [2, 3, 4, 5, 6]
    for level in range(1, 6):
        public, truth = GENERATOR.generate(_task(level, "full"), "profile-evidence")
        assert sum(not item["passed"] for item in truth["search_certificate"]["geometry_only_ablations"]) >= profiles[str(level)]["parameters"]["minimum_policy_failures"]
        assert sum(cell["under_gallery"] for cell in public["cells"]) == profiles[str(level)]["parameters"]["gallery_cells"]
        hidden = {cell["id"] for cell in public["cells"] if cell["under_gallery"]}
        assert all(truth["certified_solution"].count(cell_id) > 1 for cell_id in hidden)


def test_materialization_registration_capabilities_and_terse_ui_boundary(tmp_path: Path) -> None:
    written = materialize_environment(ENV, tmp_path)
    assert len(written) == 10
    task = _base_task()
    controls = _controls()
    required = (
        "code", "scripts", "automation", "developer tools", "console", "debugger", "inspector",
        "network", "source", "dom", "page-state inspection", "terminal", "shell", "python",
        "address-bar", "url edits", "reload", "navigation", "extensions", "external applications", "unrelated tabs",
    )
    assert task["metadata"]["source_anchors"] == ["IND-021", "VGE-250", "VGE-489"]
    assert task["metadata"]["capabilities"] == [
        "visual understanding: 2D", "temporal understanding and memory", "reasoning and planning"
    ]
    for field in (task["description"], task["natural_language"]):
        for term in required:
            assert term in field.lower()
    for level, profile in controls["difficulty"].items():
        for term in required:
            assert term in profile["natural_language"].lower()
        generated = controlled_task(
            task,
            mechanic_id=MECHANIC_ID,
            level=int(level),
            interaction="full",
            profile=profile,
            task_dir_name=f"crackglaze-test-d{level}-full",
        )
        assert generated["metadata"]["control_condition"]["difficulty_parameters"] == profile["parameters"]
    manifest = json.loads((BENCH / "benchmark_manifest.json").read_text(encoding="utf-8"))
    real_time = json.loads((BENCH / "real_time.json").read_text(encoding="utf-8"))
    assert "crackglaze_crossing_env" in manifest["environments"]
    assert real_time["environments"][MECHANIC_ID] == {
        "play_time_seconds": 180, "observation_window_ms": 0, "frames_per_observation": 1
    }
    frontend = FRONTEND_PATH.read_text(encoding="utf-8")
    forbidden_visible_copy = (
        "LEAVING LIGHTS", "LANTERNS", "MOVES", "FLOOR LOST", "DARK GALLERY",
        "KILN SAMPLES", "CURRENT REGISTER", "CLICK AN ADJACENT", "USE THE STEP",
        "HAIRLINE", "CRAZED", "GONE", "FRESH CROSSING", "GLAZE GAVE WAY",
        "CROSSING ACTIVE", "DOOR UNSEALED",
    )
    assert all(value not in frontend for value in forbidden_visible_copy)
    assert '<div class="crack-fresh-failure">FAIL</div>' in frontend
    assert controls["real_time"] == real_time["environments"][MECHANIC_ID]
    assert SOLVER.MECHANIC_ID == GENERATOR.MECHANIC_ID == GRADER.MECHANIC_ID == MECHANIC_ID
    assert callable(VERIFIER.verify_task)


def test_full_mode_keeps_expired_ground_targetable_for_the_real_failure_path() -> None:
    frontend = FRONTEND_PATH.read_text(encoding="utf-8")
    styles = STYLES_PATH.read_text(encoding="utf-8")
    assert 'if (interaction() === "full")' in frontend
    assert 'interaction() === "full" && stage !== "shattered"' not in frontend
    assert ".stage-shattered:not(button) { pointer-events: none; }" in styles
    assert ".stage-shattered { pointer-events: none; }" not in styles
