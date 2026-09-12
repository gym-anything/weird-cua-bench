from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_ROOT = ROOT / "weird_captcha_gym" / "environments" / "pocket_radio_repair_env"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generator = _load("pocket_radio_repair_test_generator", ROOT / "weird_captcha_gym/shared_scripts/incubator_generators/pocket_radio_repair.py")
grader = _load("pocket_radio_repair_test_grader", ROOT / "weird_captcha_gym/shared_runtime/server/incubator_graders/pocket_radio_repair.py")
materializer = _load("pocket_radio_repair_test_materializer", ROOT / "weird_captcha_gym/tools/materialize_controlled_tasks.py")
BASE = json.loads((ENV_ROOT / "tasks/pocket_radio_repair_seed_0001/task.json").read_text())
CONTROLS = json.loads((ENV_ROOT / "controls.json").read_text())


def _task(level: int, interaction: str) -> dict:
    task = copy.deepcopy(BASE)
    task["id"] = f"pocket_radio_repair_d{level}_{interaction}_seed_0001@0.2"
    task["_control_condition"] = {"difficulty": level, "interaction": interaction, "real_time": "live", "difficulty_parameters": copy.deepcopy(CONTROLS["difficulty"][str(level)]["parameters"])}
    task["metadata"]["mechanic_id"] = "pocket_radio_repair"
    return task


def _success(public: dict, truth: dict, interaction: str) -> dict:
    events = []
    def add(kind: str, **details):
        events.append({"seq": len(events) + 1, "type": kind, **details})
    for cover in sorted(truth["covers"], key=lambda item: item["layer"]):
        for screw in [item for item in truth["screws"] if item["cover_id"] == cover["id"]]:
            if interaction == "simplified":
                add("select_tool", tool_id=screw["tool_id"], input_source="tool_button")
                add("loosen_screw", screw_id=screw["id"], tool_id=screw["tool_id"], turn_degrees=truth["turn_degrees"], input_source="screw_button")
            else:
                add("tool_drag", tool_id=screw["tool_id"], screw_id=screw["id"], start=[70, 470], end=[screw["x"], screw["y"]], input_source="tool_drag")
                add("screw_rotate", screw_id=screw["id"], tool_id=screw["tool_id"], turn_degrees=truth["turn_degrees"], start=[screw["x"], screw["y"]], end=[screw["x"] + 20, screw["y"] + 20], input_source="screw_rotate")
        if interaction == "simplified":
            add("open_cover", cover_id=cover["id"], input_source="cover_button")
        else:
            add("lift_cover", cover_id=cover["id"], start=[cover["x"] + 110, cover["y"] + 100], end=[cover["x"] + 110, cover["y"] + 25], input_source="cover_drag")
        for part in [item for item in truth["components"] if item["cover_id"] == cover["id"]]:
            if part["condition"] == "dirty":
                if interaction == "simplified": add("clean_component", component_id=part["id"], stroke_count=truth["clean_strokes"], input_source="clean_button")
                else: add("clean_gesture", component_id=part["id"], stroke_length=truth["clean_strokes"] * 22 + 10, start=[part["x"], part["y"]], end=[part["x"] + part["w"], part["y"]], input_source="clean_gesture")
            elif part["condition"] == "missing":
                add("replace_component", component_id=part["id"], **({"input_source": "replace_button"} if interaction == "simplified" else {"start": [part["tray_x"], part["tray_y"]], "end": [part["x"], part["y"]], "input_source": "component_drag"}))
    for cover in sorted(truth["covers"], key=lambda item: item["layer"], reverse=True):
        if interaction == "simplified": add("install_cover", cover_id=cover["id"], input_source="cover_button")
        else: add("install_cover", cover_id=cover["id"], start=[160, 115 + cover["layer"] * 55], end=[cover["x"], cover["y"]], input_source="cover_drag")
        for screw in [item for item in truth["screws"] if item["cover_id"] == cover["id"]]:
            if interaction == "simplified":
                add("select_tool", tool_id=screw["tool_id"], input_source="tool_button")
                add("install_screw", screw_id=screw["id"], tool_id=screw["tool_id"], input_source="screw_button")
            else:
                loose_y = 170 + truth["screws"].index(screw) * 30
                add("tool_drag", tool_id=screw["tool_id"], screw_id=screw["id"], start=[70, 470], end=[770, loose_y], input_source="tool_drag")
                add("install_screw", screw_id=screw["id"], tool_id=screw["tool_id"], start=[770, loose_y], end=[screw["x"], screw["y"]], input_source="screw_drag")
    add("test", accepted=True, input_source="test_button")
    return {"mechanic_id": "pocket_radio_repair", "task_id": truth["task_id"], "challenge_id": truth["challenge_id"], "events": events, "completed": True}


def test_controls_and_materialization(tmp_path):
    materializer.validate_controls(CONTROLS, ENV_ROOT)
    written = materializer.materialize_environment(ENV_ROOT, tmp_path)
    assert len(written) == 10
    assert {path.name for path in written} == {f"pocket_radio_repair_d{level}_{interaction}_seed_0001" for level in range(1, 6) for interaction in ("simplified", "full")}


def test_pairs_share_generated_world_and_all_targets_are_reachable():
    for level in range(1, 6):
        simple, simple_truth = generator.generate(_task(level, "simplified"), "radio-pair-seed")
        full, full_truth = generator.generate(_task(level, "full"), "radio-pair-seed")
        parameters = CONTROLS["difficulty"][str(level)]["parameters"]
        assert len(simple_truth["covers"]) == parameters["cover_count"]
        assert len(simple_truth["screws"]) == parameters["cover_count"] * parameters["screws_per_cover"]
        assert len(simple_truth["components"]) == parameters["component_count"]
        assert simple["radio"] == full["radio"]
        assert simple_truth["covers"] == full_truth["covers"]
        assert simple_truth["screws"] == full_truth["screws"]
        assert simple_truth["components"] == full_truth["components"]
        assert grader.grade(_success(simple, simple_truth, "simplified"), simple_truth, simple)["passed"] is True
        assert grader.grade(_success(full, full_truth, "full"), full_truth, full)["passed"] is True


def test_wrong_surface_and_forged_completion_fail():
    public, truth = generator.generate(_task(4, "simplified"), "radio-negative-seed")
    payload = _success(public, truth, "simplified")
    wrong = copy.deepcopy(payload)
    wrong["events"][0]["input_source"] = "tool_drag"
    assert grader.grade(wrong, truth, public)["passed"] is False
    forged = {"mechanic_id": "pocket_radio_repair", "task_id": truth["task_id"], "challenge_id": truth["challenge_id"], "events":[{"seq":1,"type":"test","accepted":True,"input_source":"test_button"}], "completed":True}
    assert grader.grade(forged, truth, public)["passed"] is False
