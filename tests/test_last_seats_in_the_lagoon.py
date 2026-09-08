from __future__ import annotations

import copy
import importlib.util
import itertools
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "weird_captcha_gym" / "environments" / "last_seats_in_the_lagoon_env"
MECHANIC = "last_seats_in_the_lagoon"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load(
    "last_seats_in_the_lagoon_generator_test",
    ROOT / "weird_captcha_gym/shared_scripts/incubator_generators/last_seats_in_the_lagoon.py",
)
GRADER = _load(
    "last_seats_in_the_lagoon_grader_test",
    ROOT / "weird_captcha_gym/shared_runtime/server/incubator_graders/last_seats_in_the_lagoon.py",
)
MATERIALIZER = _load(
    "last_seats_in_the_lagoon_materializer_test",
    ROOT / "weird_captcha_gym/tools/materialize_controlled_tasks.py",
)


CONTROLS = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
BASE_TASK = json.loads(
    (ENV / "tasks" / f"{MECHANIC}_seed_0001" / "task.json").read_text(encoding="utf-8")
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


def _generate(level: int, interaction: str, seed: str = "lagoon-test") -> tuple[dict, dict]:
    return GENERATOR.generate(_task(level, interaction), seed)


def _events(public: dict, truth: dict, input_source: str) -> list[dict]:
    boats = copy.deepcopy(truth["initial_boats"])
    passengers = copy.deepcopy(truth["initial_passengers"])
    reefs = {tuple(item) for item in truth["reefs"]}
    columns = int(truth["board"]["columns"])
    rows = int(truth["board"]["rows"])
    events = []
    for step in truth["solution_path"]:
        boat = next(item for item in boats if item["id"] == step["boat_id"])
        before = [boat["x"], boat["y"]]
        accepted, boarded = GENERATOR._apply_move(
            boats,
            passengers,
            step["boat_id"],
            step["direction"],
            reefs,
            columns,
            rows,
        )
        assert accepted
        events.append(
            {
                "boat_id": step["boat_id"],
                "direction": step["direction"],
                "from": before,
                "to": [boat["x"], boat["y"]],
                "input_source": input_source,
                "accepted": True,
                "boarded": boarded,
            }
        )
    return events


def test_controls_have_five_profiles_and_both_surfaces() -> None:
    assert CONTROLS["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    assert set(CONTROLS["difficulty"]) == {"1", "2", "3", "4", "5"}
    assert all(CONTROLS["interaction"][mode]["implemented"] for mode in ("full", "simplified"))
    assert set(CONTROLS["real_time"]) == {
        "play_time_seconds",
        "observation_window_ms",
        "frames_per_observation",
    }


def test_shared_registration_uses_the_mechanic_id() -> None:
    manifest = json.loads((ROOT / "weird_captcha_gym/benchmark_manifest.json").read_text(encoding="utf-8"))
    real_time = json.loads((ROOT / "weird_captcha_gym/real_time.json").read_text(encoding="utf-8"))
    assert "last_seats_in_the_lagoon_env" in manifest["environments"]
    assert real_time["environments"][MECHANIC] == CONTROLS["real_time"]
    assert "last_seats_in_the_lagoon_env" not in real_time["environments"]


def test_all_ten_conditions_generate_shared_world_and_legal_solution() -> None:
    expected_routes = {1: 8, 2: 24, 3: 24, 4: 48, 5: 120}
    for level in range(1, 6):
        full_public, full_truth = _generate(level, "full", f"level-{level}")
        simple_public, simple_truth = _generate(level, "simplified", f"level-{level}")
        for public, truth, source in (
            (full_public, full_truth, "drag"),
            (simple_public, simple_truth, "direction_buttons"),
        ):
            assert len(truth["solution_path"]) == expected_routes[level]
            decision = GRADER.grade(
                {
                    "mechanic_id": MECHANIC,
                    "task_id": public["task_id"],
                    "challenge_id": public["challenge_id"],
                    "completed": True,
                    "interaction_mode": (truth.get("control_condition") or {}).get("interaction"),
                    "actions": _events(public, truth, source),
                },
                truth,
                public,
            )
            assert decision["passed"], decision
        for key in ("board", "boats", "passengers", "reefs", "rules", "palette"):
            assert full_public[key] == simple_public[key], key
        assert full_truth["solution_path"] == simple_truth["solution_path"]


def _successful_boat_orders(level: int, seed: str) -> set[tuple[int, ...]]:
    profile = CONTROLS["difficulty"][str(level)]["parameters"]
    _public, truth = _generate(level, "full", seed)
    routes = [
        GENERATOR._route(boat["orientation"], int(profile["route_span"]), int(profile["route_cycles"]))
        for boat in truth["initial_boats"]
    ]
    boat_ids = [str(boat["id"]) for boat in truth["initial_boats"]]
    successful: set[tuple[int, ...]] = set()
    for order in itertools.permutations(range(len(boat_ids))):
        boats = copy.deepcopy(truth["initial_boats"])
        passengers = copy.deepcopy(truth["initial_passengers"])
        reefs = {tuple(item) for item in truth["reefs"]}
        valid = True
        for boat_index in order:
            for direction in routes[boat_index]:
                accepted, _boarded = GENERATOR._apply_move(
                    boats,
                    passengers,
                    boat_ids[boat_index],
                    direction,
                    reefs,
                    int(truth["board"]["columns"]),
                    int(truth["board"]["rows"]),
                )
                if not accepted:
                    valid = False
                    break
            if not valid:
                break
        if valid and all(item.get("boarded") for item in passengers):
            successful.add(tuple(order))
    return successful


def test_l2_to_l3_changes_the_active_order_problem() -> None:
    level2 = CONTROLS["difficulty"]["2"]["parameters"]
    level3 = CONTROLS["difficulty"]["3"]["parameters"]
    assert level2["boat_count"] == 2
    assert level3["boat_count"] == 3
    assert level3["route_span"] == 4
    assert level3["route_cycles"] == 1
    assert _successful_boat_orders(2, "order-2-0") == {(0, 1), (1, 0)}
    # L3's additional boat and crossing rope lanes make some orderings fail
    # through the actual collision/automatic-pickup replay, not a metadata
    # quota or an extra post-goal loop.
    assert len(_successful_boat_orders(3, "order-3-0")) == 3


def test_generated_passenger_cells_are_globally_distinct() -> None:
    for level in range(1, 6):
        for seed_index in range(12):
            public, _truth = _generate(level, "full", f"distinct-{level}-{seed_index}")
            positions = [tuple(item["position"]) for item in public["passengers"]]
            assert len(positions) == len(set(positions)), (level, seed_index, positions)


def test_base_d4_world_is_the_uncontrolled_reference_configuration() -> None:
    base_public, base_truth = GENERATOR.generate(BASE_TASK, "reference-seed")
    controlled_public, controlled_truth = _generate(4, "full", "reference-seed")
    for key in ("board", "boats", "passengers", "reefs", "rules", "palette"):
        assert base_public[key] == controlled_public[key], key
    assert base_truth["solution_path"] == controlled_truth["solution_path"]
    assert "control_condition" not in base_public
    assert controlled_public["control_condition"]["difficulty"] == 4


def test_grader_rejects_wrong_surface_stale_position_and_forged_pickup() -> None:
    public, truth = _generate(4, "full", "grader-negative")
    events = _events(public, truth, "drag")
    valid = {
        "mechanic_id": MECHANIC,
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "completed": True,
        "interaction_mode": "full",
        "actions": events,
    }
    assert GRADER.grade(valid, truth, public)["passed"] is True
    wrong_surface = copy.deepcopy(valid)
    wrong_surface["actions"][0]["input_source"] = "direction_buttons"
    assert GRADER.grade(wrong_surface, truth, public)["passed"] is False
    stale = copy.deepcopy(valid)
    stale["actions"][0]["from"] = [999, 999]
    assert GRADER.grade(stale, truth, public)["passed"] is False
    forged = copy.deepcopy(valid)
    forged["actions"][0]["boarded"] = ["passenger-forged"]
    assert GRADER.grade(forged, truth, public)["passed"] is False

    rejected = copy.deepcopy(valid)
    blocked = None
    reefs = {tuple(item) for item in truth["reefs"]}
    for boat in truth["initial_boats"]:
        for direction, (dx, dy) in GENERATOR.DIRS.items():
            target = (int(boat["x"]) + dx, int(boat["y"]) + dy)
            if not GENERATOR._candidate_clear(
                boat,
                target,
                truth["initial_boats"],
                reefs,
                int(truth["board"]["columns"]),
                int(truth["board"]["rows"]),
                ignore_id=str(boat["id"]),
            ):
                blocked = {
                    "boat_id": boat["id"],
                    "direction": direction,
                    "from": [boat["x"], boat["y"]],
                    "to": [target[0], target[1]],
                    "input_source": "drag",
                    "accepted": False,
                    "boarded": [],
                }
                break
        if blocked is not None:
            break
    assert blocked is not None
    rejected["actions"].insert(0, blocked)
    assert GRADER.grade(rejected, truth, public)["passed"] is False


def test_materialized_task_dirs_cover_each_level_and_surface(tmp_path) -> None:
    from weird_captcha_gym.tools.materialize_controlled_tasks import materialize_environment
    written = materialize_environment(ENV, tmp_path)
    assert len(written) == 10
    task_root = tmp_path / ENV.name / "tasks"
    for level in range(1, 6):
        for interaction in ("full", "simplified"):
            name = f"{MECHANIC}_d{level}_{interaction}_seed_0001"
            task_path = task_root / name / "task.json"
            assert task_path.is_file()
            task = json.loads(task_path.read_text(encoding="utf-8"))
            condition = task["metadata"]["control_condition"]
            assert condition["difficulty"] == level
            assert condition["interaction"] == interaction
            if level == 3:
                assert condition["difficulty_parameters"]["boat_count"] == 3
                assert condition["difficulty_parameters"]["route_span"] == 4
                assert condition["difficulty_parameters"]["route_cycles"] == 1
            assert task["hooks"]["pre_task"].endswith(f"/tasks/{name}/setup_task.sh")
            assert task["hooks"]["post_task"].endswith(f"/tasks/{name}/export_result.sh")


def test_split_advertises_both_execution_schedules() -> None:
    split = json.loads((ROOT / "weird_captcha_gym/splits/last_seats_in_the_lagoon_split.json").read_text())
    expected = {f"{MECHANIC}_d{level}_{mode}_seed_0001{suffix}" for level in range(1, 6) for mode in ("full", "simplified") for suffix in ("", "_tpaused")}
    assert set(split["variations_tasks"]) == expected
    assert len(split["variations_tasks"]) == 20
    for names in (split["train_tasks"], split["test_tasks"], split["all_tasks"]):
        assert all((ENV / "tasks" / name / "task.json").is_file() for name in names)


def test_malformed_ledgers_fail_without_coercion_or_exceptions() -> None:
    public, truth = _generate(4, "full", "malformed-ledger")
    valid = {"task_id": public["task_id"], "challenge_id": public["challenge_id"],
             "completed": True, "actions": _events(public, truth, "drag")}
    final_boats = [{"id": boat["id"], "x": boat["x"], "y": boat["y"]} for boat in truth["initial_boats"]]
    # The witness returns every boat to its initial anchor.
    valid["final"] = {"boats": final_boats}
    assert GRADER.grade(valid, truth, public)["passed"]
    for ledger in (1, "passenger-1", {}, [None]):
        malformed = copy.deepcopy(valid)
        malformed["actions"][0]["boarded"] = ledger
        assert GRADER.grade(malformed, truth, public)["passed"] is False
    for final in ([1], None, {"boats": 1}, {"boats": [None]}, {"boarded": 1}, {"boarded": [None]},
                  {"boats": final_boats + [final_boats[0]]}):
        malformed = copy.deepcopy(valid)
        malformed["final"] = final
        assert GRADER.grade(malformed, truth, public)["passed"] is False
    for coordinate in (final_boats[0]["x"] + 0.5, str(final_boats[0]["x"]), True, None):
        malformed = copy.deepcopy(valid)
        malformed["final"]["boats"][0]["x"] = coordinate
        assert GRADER.grade(malformed, truth, public)["passed"] is False


def test_exported_verifiers_bind_requested_task_without_current_task_id() -> None:
    public, truth = _generate(4, "full", "export-binding")
    payload = {"task_id": public["task_id"], "challenge_id": public["challenge_id"],
               "completed": True, "actions": _events(public, truth, "drag")}
    exported = {"result": payload, "public_state": public, "ground_truth": truth,
                "current_task": {"challenge_index": 0, "last_reason": "setup"}}
    def copy_from_env(source, destination):
        assert source == "/tmp/task_result.json"
        Path(destination).write_text(json.dumps(exported))
    for verifier_path in (ENV / "tasks").glob("*/verifier.py"):
        verifier = _load("lagoon_export_binding_test", verifier_path)
        assert verifier.verify_task(env_info={"copy_from_env": copy_from_env},
                                    task_info={"id": public["task_id"]})["passed"]
        assert not verifier.verify_task(env_info={"copy_from_env": copy_from_env},
                                        task_info={"id": "unrelated-task@0.1"})["passed"]
        payload["actions"][0]["boarded"] = 1
        assert not verifier.verify_task(env_info={"copy_from_env": copy_from_env},
                                        task_info={"id": public["task_id"]})["passed"]
        payload["actions"] = _events(public, truth, "drag")
