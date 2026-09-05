from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "weird_captcha_gym"
ENV = BENCH / "environments" / "reflow_vitrine_env"
GENERATOR_PATH = BENCH / "shared_scripts" / "incubator_generators" / "reflow_vitrine.py"
GRADER_PATH = BENCH / "shared_runtime" / "server" / "incubator_graders" / "reflow_vitrine.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("reflow_vitrine_generator_test", GENERATOR_PATH)
GRADER = _load("reflow_vitrine_grader_test", GRADER_PATH)


def _assert_contained(boxes: dict) -> None:
    for node_id, box in boxes.items():
        assert float(box["x"]) >= -0.001, (node_id, box)
        assert float(box["y"]) >= -0.001, (node_id, box)
        assert float(box["x"]) + float(box["w"]) <= 360.001, (node_id, box)
        assert float(box["y"]) + float(box["h"]) <= 260.001, (node_id, box)
        assert float(box["w"]) > 0 and float(box["h"]) > 0, (node_id, box)


def _assert_each_corruption_is_visible_and_necessary(public: dict, truth: dict) -> None:
    target_raster = GRADER._raster(public["target_layout"])
    _assert_contained(public["target_layout"])
    _assert_contained(GRADER._layout(public["frames"], public["items"], public["initial_config"]))
    for corruption in truth["corruptions"]:
        single_error = copy.deepcopy(truth["target_config"])
        single_error[corruption["frame_id"]][corruption["property"]] = copy.deepcopy(corruption["initial"])
        boxes = GRADER._layout(public["frames"], public["items"], single_error)
        _assert_contained(boxes)
        raster = GRADER._raster(boxes)
        score = GRADER._ssim(target_raster, raster)
        visible_pixels = sum(abs(left - right) >= 8 for left, right in zip(target_raster, raster))
        assert score < truth["parameters"]["similarity_threshold"] - GENERATOR.MIN_SINGLE_CORRUPTION_SCORE_MARGIN
        assert visible_pixels >= GENERATOR.MIN_SINGLE_CORRUPTION_PIXELS
        assert round(score, 8) == corruption["single_error_similarity"]
        assert visible_pixels == corruption["visible_pixel_difference"]


def _task(level: int, interaction: str, real_time: str = "live") -> dict:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/reflow_vitrine_seed_0001/task.json").read_text(encoding="utf-8"))
    task["_control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": copy.deepcopy(controls["difficulty"][str(level)]["parameters"]),
    }
    return task


def _payload(public: dict, truth: dict, interaction: str) -> dict:
    current = copy.deepcopy(public["initial_config"])
    target = truth["target_config"]
    events = []
    for frame in public["frames"]:
        frame_id = frame["id"]
        for prop in public["mutable_properties"]:
            if prop == "order" or (prop == "grow" and frame_id == "window"):
                continue
            if current[frame_id][prop] == target[frame_id][prop]:
                continue
            source = "value_button" if interaction == "simplified" else "inspector_fader_drag" if prop in {"gap", "padding", "grow"} else "inspector_dropdown"
            event = {
                "sequence": len(events) + 1, "type": "set", "frame_id": frame_id, "property": prop,
                "value": target[frame_id][prop], "input_source": source,
            }
            if source == "inspector_fader_drag":
                event["gesture"] = {"start_u": .25, "start_v": .4, "end_u": .75, "end_v": .4, "travel_px": 120.0, "sample_count": 6}
            events.append(event)
            current[frame_id][prop] = target[frame_id][prop]
        while current[frame_id]["order"] != target[frame_id]["order"]:
            wanted = next(index for index, value in enumerate(target[frame_id]["order"]) if current[frame_id]["order"][index] != value)
            source_index = current[frame_id]["order"].index(target[frame_id]["order"][wanted])
            child_id = current[frame_id]["order"][source_index]
            source = "order_nudge_button" if interaction == "simplified" else "child_strip_drag"
            event = {
                "sequence": len(events) + 1, "type": "reorder", "frame_id": frame_id, "property": "order",
                "child_id": child_id, "from_index": source_index, "to_index": wanted, "input_source": source,
            }
            if source == "child_strip_drag":
                event["gesture"] = {"start_u": .5, "start_v": .5, "end_u": .5, "end_v": .5, "travel_px": 90.0, "sample_count": 5}
            events.append(event)
            current[frame_id]["order"].insert(wanted, current[frame_id]["order"].pop(source_index))
    score = GRADER._ssim(GRADER._raster(public["target_layout"]), GRADER._raster(GRADER._layout(public["frames"], public["items"], current)))
    return {
        "mechanic_id": public["mechanic_id"], "task_id": public["task_id"], "challenge_id": public["challenge_id"],
        "interaction_mode": interaction, "events": events, "final_config": current,
        "similarity": round(score, 8), "completed": score >= truth["parameters"]["similarity_threshold"],
    }


def test_all_ten_conditions_share_world_and_grade() -> None:
    for level in range(1, 6):
        worlds = []
        for interaction in ("simplified", "full"):
            public, truth = GENERATOR.generate(_task(level, interaction), f"matrix-{level}")
            payload = _payload(public, truth, interaction)
            assert len(payload["events"]) <= truth["parameters"]["edit_budget"]
            assert GRADER.grade(payload, truth, public)["passed"] is True
            worlds.append((public["frames"], public["items"], public["initial_config"], public["target_layout"]))
        assert worlds[0] == worlds[1]


def test_generation_is_deterministic_varied_and_visibly_corrupted() -> None:
    for level in range(1, 6):
        identities = set()
        for index in range(20):
            seed = f"reflow-scale-{level}-{index}"
            public, truth = GENERATOR.generate(_task(level, "full"), seed)
            public_again, truth_again = GENERATOR.generate(_task(level, "full"), seed)
            assert public == public_again and truth == truth_again
            assert len(truth["corruptions"]) == level
            assert truth["initial_similarity"] < truth["parameters"]["similarity_threshold"] - .004
            assert "target_config" not in public and "corruptions" not in public
            _assert_each_corruption_is_visible_and_necessary(public, truth)
            assert GRADER.grade(_payload(public, truth, "full"), truth, public)["passed"] is True
            identities.add(public["challenge_id"])
        assert len(identities) == 20


def test_baseline_spans_three_frames_and_preserves_declared_contract() -> None:
    public, truth = GENERATOR.generate(_task(4, "full"), "baseline-audit")
    assert len(public["frames"]) == 6
    assert len(truth["corruptions"]) == 4
    assert len({entry["frame_id"] for entry in truth["corruptions"]}) >= 3
    assert public["parameters"] == {
        "frame_count": 6, "corruption_count": 4, "edit_budget": 11, "property_set": "complete",
        "diagnostic_mode": "none", "show_frame_guides": False, "similarity_threshold": .997,
    }
    _assert_each_corruption_is_visible_and_necessary(public, truth)


def test_fully_clipped_geometry_contributes_no_raster_pixels() -> None:
    blank = GRADER._raster({})
    for box in (
        {"x": 400, "y": 20, "w": 30, "h": 30, "kind": "card", "tone": 224},
        {"x": -40, "y": 20, "w": 30, "h": 30, "kind": "card", "tone": 224},
        {"x": 20, "y": 280, "w": 30, "h": 30, "kind": "card", "tone": 224},
        {"x": 20, "y": -40, "w": 30, "h": 30, "kind": "frame"},
    ):
        assert GRADER._raster({"outside": box}) == blank
    assert GRADER._raster({"edge": {"x": 359, "y": 20, "w": 30, "h": 30, "kind": "card", "tone": 224}}) != blank


def test_reported_hidden_geometry_seed_is_now_visible_and_necessary() -> None:
    public, truth = GENERATOR.generate(_task(4, "full"), "audit-authoritative-hidden-4-27")
    _assert_each_corruption_is_visible_and_necessary(public, truth)


def test_stale_identity_wrong_surface_forged_score_and_overbudget_are_rejected() -> None:
    public, truth = GENERATOR.generate(_task(4, "full"), "negative-contract")
    payload = _payload(public, truth, "full")
    payload["challenge_id"] = "stale"
    assert "stale" in GRADER.grade(payload, truth, public)["feedback"]

    payload = _payload(public, truth, "full")
    payload["events"][0]["input_source"] = "value_button"
    assert "input surface" in GRADER.grade(payload, truth, public)["feedback"]

    payload = _payload(public, truth, "full")
    payload["similarity"] = 1.0 if payload["similarity"] != 1.0 else 0.0
    assert "similarity" in GRADER.grade(payload, truth, public)["feedback"]

    payload = _payload(public, truth, "full")
    payload["events"] = payload["events"] * 4
    assert "ledger" in GRADER.grade(payload, truth, public)["feedback"]


def test_revert_replays_the_prior_configuration() -> None:
    public, truth = GENERATOR.generate(_task(2, "simplified"), "revert-contract")
    prop = next(prop for prop in public["mutable_properties"] if prop not in {"order", "grow"})
    frame_id = public["frames"][0]["id"]
    current = public["initial_config"][frame_id][prop]
    value = next(value for value in public["allowed_values"][prop] if value != current)
    config = copy.deepcopy(public["initial_config"])
    score = GRADER._ssim(GRADER._raster(public["target_layout"]), GRADER._raster(GRADER._layout(public["frames"], public["items"], config)))
    payload = {
        "mechanic_id": public["mechanic_id"], "task_id": public["task_id"], "challenge_id": public["challenge_id"],
        "interaction_mode": "simplified",
        "events": [
            {"sequence": 1, "type": "set", "frame_id": frame_id, "property": prop, "value": value, "input_source": "value_button"},
            {"sequence": 2, "type": "revert", "input_source": "revert_button"},
        ],
        "final_config": config, "similarity": round(score, 8), "completed": score >= truth["parameters"]["similarity_threshold"],
    }
    decision = GRADER.grade(payload, truth, public)
    assert decision["graded"] is True
    assert "replayed 2/" in decision["feedback"]


def test_live_and_paused_share_the_same_static_decision_world() -> None:
    live, _ = GENERATOR.generate(_task(5, "full", "live"), "time-equivalence")
    paused, _ = GENERATOR.generate(_task(5, "full", "paused"), "time-equivalence")
    for key in ("frames", "items", "initial_config", "target_layout", "parameters"):
        assert live[key] == paused[key]
    assert live["control_condition"]["real_time"] == "live"
    assert paused["control_condition"]["real_time"] == "paused"


def test_registration_sources_and_static_observation_settings() -> None:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    env = json.loads((ENV / "env.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/reflow_vitrine_seed_0001/task.json").read_text(encoding="utf-8"))
    split = json.loads((BENCH / "splits/reflow_vitrine_split.json").read_text(encoding="utf-8"))
    manifest = json.loads((BENCH / "benchmark_manifest.json").read_text(encoding="utf-8"))
    real_time = json.loads((BENCH / "real_time.json").read_text(encoding="utf-8"))["environments"]
    assert controls["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    assert env["runner_options"] == {"observation_window_ms": 0, "frames_per_observation": 1, "play_time_seconds": 180}
    assert task["name"] == "Reflow Vitrine"
    assert task["metadata"]["source_anchors"] == ["XAGT-056", "XAGT-046", "XAGT-072"]
    assert len(split["variations_tasks"]) == 20
    assert manifest["environments"].count("reflow_vitrine_env") == 1
    assert real_time["reflow_vitrine"] == env["runner_options"]
    assert all(profile["parameters"]["diagnostic_mode"] == "none" for profile in controls["difficulty"].values())
    assert all(profile["parameters"]["show_frame_guides"] is False for profile in controls["difficulty"].values())


def test_browser_module_exposes_bound_surfaces_and_no_object_drag() -> None:
    source = (BENCH / "shared_runtime/app/mechanics/reflow_vitrine.js").read_text(encoding="utf-8")
    styles = (BENCH / "shared_runtime/app/mechanics/reflow_vitrine.css").read_text(encoding="utf-8")
    for token in ("inspector_dropdown", "inspector_fader_drag", "child_strip_drag", "value_button", "order_nudge_button", "revert_button"):
        assert token in source
    assert "data-order-chip" in source and "data-fader-frame" in source
    assert "rv-prop" in styles and "pointer-events: none" in styles
    for prohibited in (
        "STRUCTURAL SIMILARITY", "LAST REFLOW DIRECTION", "CLOSER ↑", "FARTHER ↓",
        "MATCH FOUND", "TARGET THRESHOLD REACHED", "ALIGNED", "CERTIFY THE VITRINE",
        "REFLOW COMPLETE", "INSPECT BOTH PLATES", "DRAG TO REFLOW",
        "Editing a frame re-solves every descendant", "DISPLAY OBJECTS ARE LOCKED",
    ):
        assert prohibited not in source
    solver = (BENCH / "tools/incubator_solvers/reflow_vitrine.py").read_text(encoding="utf-8")
    assert "select_option" not in solver
    assert "page.keyboard.type(str(target))" in solver
