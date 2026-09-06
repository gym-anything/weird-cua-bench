from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "weird_captcha_gym"
ENV = BENCH / "environments/charter_of_the_nine_cantons_env"
GENERATOR_PATH = BENCH / "shared_scripts/incubator_generators/charter_of_the_nine_cantons.py"
GRADER_PATH = BENCH / "shared_runtime/server/incubator_graders/charter_of_the_nine_cantons.py"
SOLVER_PATH = BENCH / "tools/incubator_solvers/charter_of_the_nine_cantons.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("nine_canton_generator_test", GENERATOR_PATH)
GRADER = _load("nine_canton_grader_test", GRADER_PATH)
SOLVER = _load("nine_canton_solver_test", SOLVER_PATH)


def _task(level: int, interaction: str, real_time: str = "live") -> dict:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/charter_of_the_nine_cantons_seed_0001/task.json").read_text(encoding="utf-8"))
    task["_control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": copy.deepcopy(controls["difficulty"][str(level)]["parameters"]),
    }
    return task


def _metrics(public: dict, assignment: dict) -> dict:
    parties = {parcel["id"]: parcel["guild"] for parcel in public["parcels"]}
    return GRADER.evaluate_assignment(
        assignment, parties, public["adjacency"], public["ideal_population"],
        public["population_tolerance"], public["target_seat_split"],
    )


def _full_brush_path(public: dict, truth: dict) -> list[str]:
    return SOLVER._required_brush_path(public, truth)


def _centroid(public: dict, parcel_id: str) -> tuple[float, float]:
    parcel = next(item for item in public["parcels"] if item["id"] == parcel_id)
    polygon = parcel["polygon"]
    return (
        sum(point[0] for point in polygon) / len(polygon),
        sum(point[1] for point in polygon) / len(polygon),
    )


def _stroke(public: dict, truth: dict, assignment: dict, path: list[str], sequence: int) -> dict:
    wanted = int(truth["target_assignment"][path[-1]])
    changes = []
    for parcel_id in path:
        if int(assignment[parcel_id]) != wanted:
            changes.append({
                "parcel_id": parcel_id,
                "from_canton": assignment[parcel_id],
                "to_canton": wanted,
            })
            assignment[parcel_id] = wanted
    assert changes
    centers = [_centroid(public, parcel_id) for parcel_id in path]
    travel = sum(
        math.hypot(right[0] - left[0], right[1] - left[1])
        for left, right in zip(centers, centers[1:])
    )
    start, end = centers[0], centers[-1]
    return {
        "sequence": sequence,
        "type": "stroke",
        "brush_canton": wanted,
        "path": path,
        "changes": changes,
        "input_source": "map_brush_drag",
        "gesture": {
            "start_u": start[0] / 1000,
            "start_v": start[1] / 600,
            "end_u": end[0] / 1000,
            "end_v": end[1] / 600,
            "travel_px": max(14.0, travel),
            "sample_count": max(5, len(path) * 5),
        },
    }


def _payload(public: dict, truth: dict, interaction: str, *, cross_border: bool = True) -> dict:
    assignment = copy.deepcopy(public["initial_assignment"])
    events = []
    if interaction == "full" and cross_border:
        path = _full_brush_path(public, truth)
        events.append(_stroke(public, truth, assignment, path, len(events) + 1))
    for parcel in public["parcels"]:
        parcel_id = parcel["id"]
        wanted = int(truth["target_assignment"][parcel_id])
        if assignment[parcel_id] == wanted:
            continue
        if interaction == "simplified":
            event = {
                "sequence": len(events) + 1,
                "type": "assign",
                "parcel_id": parcel_id,
                "from_canton": assignment[parcel_id],
                "to_canton": wanted,
                "input_source": "canton_proxy_button",
            }
        else:
            event = _stroke(public, truth, assignment, [parcel_id], len(events) + 1)
        events.append(event)
        if interaction == "simplified":
            assignment[parcel_id] = wanted
    metrics = _metrics(public, assignment)
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction_mode": interaction,
        "events": events,
        "final_assignment": assignment,
        "metrics": metrics,
        "completed": metrics["completed"],
    }


def _world(public: dict) -> dict:
    return {key: public[key] for key in (
        "parcels", "adjacency", "initial_assignment", "guilds", "canton_colors",
        "target_seat_split", "ideal_population", "population_tolerance", "parameters",
    )}


def test_all_ten_conditions_share_world_and_grade() -> None:
    for level in range(1, 6):
        worlds = []
        for interaction in ("simplified", "full"):
            public, truth = GENERATOR.generate(_task(level, interaction), f"nine-canton-matrix-{level}")
            payload = _payload(public, truth, interaction)
            if interaction == "simplified":
                assert len(payload["events"]) == truth["parameters"]["displaced_parcels"]
            else:
                assert any(
                    len(set(event["path"])) >= int(truth["parameters"].get("minimum_brush_path", 4))
                    and len(event["changes"]) >= int(truth["parameters"].get("minimum_brush_changes", 2))
                    for event in payload["events"]
                )
            assert len(payload["events"]) <= truth["parameters"]["change_budget"]
            assert GRADER.grade(payload, truth, public)["passed"] is True
            worlds.append(_world(public))
        assert worlds[0] == worlds[1]


def test_profiles_are_deterministic_varied_connected_and_initially_unsolved() -> None:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    expected_counts = [54, 81, 135, 135, 162]
    for level, expected_count in enumerate(expected_counts, 1):
        identities = set()
        for index in range(12):
            seed = f"nine-canton-scale-{level}-{index}"
            public, truth = GENERATOR.generate(_task(level, "full"), seed)
            public_again, truth_again = GENERATOR.generate(_task(level, "full"), seed)
            assert public == public_again and truth == truth_again
            assert len(public["parcels"]) == expected_count
            assert len(truth["displaced_parcels"]) == controls["difficulty"][str(level)]["parameters"]["displaced_parcels"]
            assert len({item["parcel_id"] for item in truth["displaced_parcels"]}) == len(truth["displaced_parcels"])
            assert sum(
                public["initial_assignment"][parcel_id] != truth["target_assignment"][parcel_id]
                for parcel_id in public["initial_assignment"]
            ) == len(truth["displaced_parcels"])
            for displaced in truth["displaced_parcels"]:
                parcel_id = displaced["parcel_id"]
                assert displaced["from_canton"] != displaced["to_canton"]
                assert truth["target_assignment"][parcel_id] == displaced["from_canton"]
                assert public["initial_assignment"][parcel_id] == displaced["to_canton"]
            brush_path = _full_brush_path(public, truth)
            assert len(set(brush_path)) >= int(truth["parameters"].get("minimum_brush_path", 4))
            assert sum(
                public["initial_assignment"][parcel_id] != truth["target_assignment"][parcel_id]
                for parcel_id in set(brush_path)
            ) >= int(truth["parameters"].get("minimum_brush_changes", 2))
            assert all(
                right in public["adjacency"][left]
                for left, right in zip(brush_path, brush_path[1:])
            )
            brush_canton = truth["target_assignment"][brush_path[-1]]
            assert all(truth["target_assignment"][parcel_id] == brush_canton for parcel_id in brush_path)
            assert truth["target_stats"]["completed"] is True
            assert _metrics(public, public["initial_assignment"])["completed"] is False
            assert "target_assignment" not in public and "displaced_parcels" not in public
            assert all(item["connected"] for item in truth["target_stats"]["cantons"])
            assert all(item["population"] == public["ideal_population"] for item in truth["target_stats"]["cantons"])
            identities.add(public["challenge_id"])
        assert len(identities) == 12


def test_visible_polygons_and_graded_adjacency_share_edges() -> None:
    public, truth = GENERATOR.generate(_task(4, "full"), "shared-border-audit")
    parcels = {parcel["id"]: parcel for parcel in public["parcels"]}
    for parcel_id, neighbors in public["adjacency"].items():
        for neighbor in neighbors:
            assert parcel_id in public["adjacency"][neighbor]
            assert GRADER._shared_edge(parcels[parcel_id]["polygon"], parcels[neighbor]["polygon"])
    decision = GRADER.grade(_payload(public, truth, "full"), truth, public)
    assert decision["passed"] is True


def test_original_135_parcel_configuration_is_preserved_exactly_at_l3() -> None:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    assert controls["baseline"] == {"difficulty": 3, "interaction": "full", "real_time": "live"}
    base_task = json.loads((ENV / "tasks/charter_of_the_nine_cantons_seed_0001/task.json").read_text(encoding="utf-8"))
    original_public, original_truth = GENERATOR.generate(base_task, "baseline-audit")
    public, truth = GENERATOR.generate(_task(3, "full"), "baseline-audit")
    assert _world(public) == _world(original_public)
    assert truth["target_assignment"] == original_truth["target_assignment"]
    assert truth["displaced_parcels"] == original_truth["displaced_parcels"]
    assert public["challenge_id"] == original_public["challenge_id"] == "cn-ff8614f451a12054ab"
    digest = hashlib.sha256(json.dumps(_world(public), sort_keys=True).encode()).hexdigest()
    assert digest == "ce50ab25dfe26af0bdb5bff3bf8a5b527f88882b64066e583eadc22a0b6fad0b"
    assert len(public["parcels"]) == 135
    assert public["ideal_population"] == 15
    assert public["target_seat_split"] == {"gilt": 5, "tide": 2, "plum": 2}
    assert truth["parameters"] == {
        "columns": 15, "rows": 9, "boundary_warp_steps": 12,
        "displaced_parcels": 8, "change_budget": 18,
        "winner_margin": 1, "population_tolerance": 1,
    }
    margins = []
    for canton in truth["target_stats"]["cantons"]:
        counts = sorted(canton["guild_counts"].values(), reverse=True)
        margins.append(counts[0] - counts[1])
    assert margins == [1] * 9


def test_l4_and_l5_use_balanced_multi_canton_exchanges() -> None:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    assert controls["difficulty"]["4"]["parameters"]["population_tolerance"] == 1
    assert controls["difficulty"]["5"]["parameters"]["population_tolerance"] == 0
    assert "exactly 18" in controls["difficulty"]["5"]["natural_language_by_interaction"]["full"]
    for level, exchange_count, bundle_size in ((4, 3, 2), (5, 4, 3)):
        for index in range(20):
            public, truth = GENERATOR.generate(_task(level, "full"), f"balanced-audit-{level}-{index}")
            initial = _metrics(public, public["initial_assignment"])
            assert all(item["population"] == public["ideal_population"] for item in initial["cantons"])
            assert initial["seat_split"] != public["target_seat_split"]
            assert len(truth["exchange_plan"]) == exchange_count
            assert len({item["to_canton"] for item in truth["displaced_parcels"]}) == exchange_count * 2
            assert all(
                len(transfer["parcels"]) == bundle_size
                for exchange in truth["exchange_plan"]
                for transfer in exchange["transfers"]
            )
            center_trim = copy.deepcopy(public["initial_assignment"])
            for displaced in truth["displaced_parcels"]:
                if displaced["to_canton"] == 4:
                    center_trim[displaced["parcel_id"]] = truth["target_assignment"][displaced["parcel_id"]]
            assert _metrics(public, center_trim)["completed"] is False
            for exchange in truth["exchange_plan"]:
                one_exchange = copy.deepcopy(public["initial_assignment"])
                for displaced in truth["displaced_parcels"]:
                    if displaced["exchange_id"] == exchange["exchange_id"]:
                        one_exchange[displaced["parcel_id"]] = truth["target_assignment"][displaced["parcel_id"]]
                assert _metrics(public, one_exchange)["completed"] is False
            assert GRADER.grade(_payload(public, truth, "full"), truth, public)["passed"] is True
    public, truth = GENERATOR.generate(_task(5, "full"), "exact-balance-audit")
    assert public["ideal_population"] == 18 and public["population_tolerance"] == 0
    assert all(item["population"] == 18 for item in truth["target_stats"]["cantons"])


def test_stale_identity_wrong_surface_and_forged_outcomes_are_rejected() -> None:
    public, truth = GENERATOR.generate(_task(4, "full"), "negative-contract")
    payload = _payload(public, truth, "full")
    payload["challenge_id"] = "stale"
    assert "stale" in GRADER.grade(payload, truth, public)["feedback"]

    payload = _payload(public, truth, "full")
    payload["events"][0]["input_source"] = "canton_proxy_button"
    assert "input surface" in GRADER.grade(payload, truth, public)["feedback"]

    simplified_public, simplified_truth = GENERATOR.generate(
        _task(4, "simplified"), "negative-contract-simplified"
    )
    simplified_payload = _payload(simplified_public, simplified_truth, "simplified")
    simplified_payload["events"][0]["input_source"] = "map_brush_drag"
    assert "input surface" in GRADER.grade(
        simplified_payload, simplified_truth, simplified_public
    )["feedback"]

    payload = _payload(public, truth, "full")
    payload["final_assignment"][next(iter(payload["final_assignment"]))] = 8
    assert "differs" in GRADER.grade(payload, truth, public)["feedback"]

    payload = _payload(public, truth, "full")
    payload["metrics"]["seat_split"]["gilt"] = 9
    assert "metrics" in GRADER.grade(payload, truth, public)["feedback"]

    payload = _payload(public, truth, "full", cross_border=False)
    assert "active brush stroke" in GRADER.grade(payload, truth, public)["feedback"]


def test_undone_border_stroke_does_not_satisfy_full_interaction() -> None:
    public, truth = GENERATOR.generate(_task(4, "full"), "undone-border-contract")
    grouped = _payload(public, truth, "full")
    singles = _payload(public, truth, "full", cross_border=False)
    events = [copy.deepcopy(grouped["events"][0]), {
        "sequence": 2,
        "type": "undo",
        "input_source": "undo_button",
    }]
    for event in singles["events"]:
        event = copy.deepcopy(event)
        event["sequence"] = len(events) + 1
        events.append(event)
    singles["events"] = events
    decision = GRADER.grade(singles, truth, public)
    assert decision["passed"] is False
    assert "active brush stroke" in decision["feedback"]


def test_undo_restores_the_prior_partition_and_budget() -> None:
    public, truth = GENERATOR.generate(_task(2, "simplified"), "undo-contract")
    parcel_id = public["parcels"][0]["id"]
    before = public["initial_assignment"][parcel_id]
    destination = (before + 1) % 9
    metrics = _metrics(public, public["initial_assignment"])
    payload = {
        "mechanic_id": public["mechanic_id"], "task_id": public["task_id"], "challenge_id": public["challenge_id"],
        "interaction_mode": "simplified",
        "events": [
            {"sequence": 1, "type": "assign", "parcel_id": parcel_id, "from_canton": before, "to_canton": destination, "input_source": "canton_proxy_button"},
            {"sequence": 2, "type": "undo", "input_source": "undo_button"},
        ],
        "final_assignment": public["initial_assignment"], "metrics": metrics, "completed": metrics["completed"],
    }
    decision = GRADER.grade(payload, truth, public)
    assert decision["graded"] is True
    assert "0/" in decision["feedback"]

    public, truth = GENERATOR.generate(_task(2, "full"), "undo-contract-full")
    parcel = public["parcels"][0]
    parcel_id = parcel["id"]
    before = public["initial_assignment"][parcel_id]
    destination = (before + 1) % 9
    x = sum(point[0] for point in parcel["polygon"]) / len(parcel["polygon"]) / 1000
    y = sum(point[1] for point in parcel["polygon"]) / len(parcel["polygon"]) / 600
    metrics = _metrics(public, public["initial_assignment"])
    payload = {
        "mechanic_id": public["mechanic_id"], "task_id": public["task_id"], "challenge_id": public["challenge_id"],
        "interaction_mode": "full",
        "events": [
            {
                "sequence": 1,
                "type": "stroke",
                "brush_canton": destination,
                "path": [parcel_id],
                "changes": [{"parcel_id": parcel_id, "from_canton": before, "to_canton": destination}],
                "input_source": "map_brush_drag",
                "gesture": {"start_u": x, "start_v": y, "end_u": x, "end_v": y, "travel_px": 14.0, "sample_count": 5},
            },
            {"sequence": 2, "type": "undo", "input_source": "undo_button"},
        ],
        "final_assignment": public["initial_assignment"], "metrics": metrics, "completed": metrics["completed"],
    }
    decision = GRADER.grade(payload, truth, public)
    assert decision["graded"] is True
    assert "0/" in decision["feedback"]


def test_live_and_paused_share_the_same_static_world() -> None:
    live, _ = GENERATOR.generate(_task(5, "full", "live"), "time-equivalence")
    paused, _ = GENERATOR.generate(_task(5, "full", "paused"), "time-equivalence")
    assert _world(live) == _world(paused)
    assert live["control_condition"]["real_time"] == "live"
    assert paused["control_condition"]["real_time"] == "paused"


def test_registration_sources_and_bounded_observation_settings() -> None:
    env = json.loads((ENV / "env.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/charter_of_the_nine_cantons_seed_0001/task.json").read_text(encoding="utf-8"))
    split = json.loads((BENCH / "splits/charter_of_the_nine_cantons_split.json").read_text(encoding="utf-8"))
    manifest = json.loads((BENCH / "benchmark_manifest.json").read_text(encoding="utf-8"))
    real_time = json.loads((BENCH / "real_time.json").read_text(encoding="utf-8"))["environments"]
    assert env["runner_options"] == {"observation_window_ms": 0, "frames_per_observation": 1, "play_time_seconds": 240}
    assert task["name"] == "Charter of the Nine Cantons"
    assert task["metadata"]["source_anchors"] == ["WEB-320", "TRW-161"]
    assert len(split["variations_tasks"]) == 20
    assert manifest["environment_count"] == len(manifest["environments"])
    assert manifest["environments"].count("charter_of_the_nine_cantons_env") == 1
    assert real_time["charter_of_the_nine_cantons"] == env["runner_options"]


def test_browser_module_exposes_distinct_bound_interaction_surfaces() -> None:
    source = (BENCH / "shared_runtime/app/mechanics/charter_of_the_nine_cantons.js").read_text(encoding="utf-8")
    styles = (BENCH / "shared_runtime/app/mechanics/charter_of_the_nine_cantons.css").read_text(encoding="utf-8")
    assert "canton_proxy_button" in source
    assert "map_brush_drag" in source
    assert "setPointerCapture" in source and "sampleBrush" in source
    assert "target_assignment" not in source
    assert "cn-boundaries" in source and "cn-boundaries" in styles
    for prohibited in (
        "CURRENT HOLDINGS / CHARTER", "ACTIVE PARCEL CHANGES", "LINKED", "SPLIT",
        "Cross a parcel border in one stroke", "0 / 1", "SEALED",
        "THICK LINES ARE CANTON BORDERS",
    ):
        assert prohibited not in source
    for script in [*ENV.glob("scripts/*.sh"), *ENV.glob("tasks/*/*.sh")]:
        assert os.access(script, os.X_OK), script
