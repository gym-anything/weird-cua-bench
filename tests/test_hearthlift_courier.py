from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
from collections import deque
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "weird_captcha_gym"
ENV = BENCH / "environments" / "hearthlift_courier_env"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("hearthlift_test_generator", BENCH / "shared_scripts/incubator_generators/hearthlift_courier.py")
GRADER = _load("hearthlift_test_grader", BENCH / "shared_runtime/server/incubator_graders/hearthlift_courier.py")


def _task(level: int, interaction: str) -> dict:
    base = json.loads((ENV / "tasks/hearthlift_courier_seed_0001/task.json").read_text())
    controls = json.loads((ENV / "controls.json").read_text())
    base["id"] = f"hearthlift_courier_d{level}_{interaction}_seed_0001@0.2"
    base["_control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": "live",
        "difficulty_parameters": controls["difficulty"][str(level)]["parameters"],
    }
    return base


def test_generator_materializes_all_levels_and_preserves_world_across_interaction_modes():
    controls = json.loads((ENV / "controls.json").read_text())
    assert controls["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    assert controls["capabilities"]["visual_understanding"] == "3D"
    assert controls["capabilities"]["temporal_understanding_and_memory"] is False
    assert controls["capabilities"]["reasoning_and_planning"] is True
    assert controls["capabilities"]["exploration_and_interface_understanding"] is True
    for level in range(1, 6):
        full_public, full_truth = GENERATOR.generate(_task(level, "full"), f"hearth-seed-{level}")
        simple_public, simple_truth = GENERATOR.generate(_task(level, "simplified"), f"hearth-seed-{level}")
        assert full_public["world"] == simple_public["world"]
        assert full_truth["world"] == simple_truth["world"]
        assert len(full_truth["solution_events"]) > 10
        full_result = GRADER.grade(
            {"mechanic_id": full_truth["mechanic_id"], "task_id": full_truth["task_id"], "challenge_id": full_truth["challenge_id"], "events": full_truth["solution_events"], "completed": True},
            full_truth,
            full_public,
        )
        simple_result = GRADER.grade(
            {"mechanic_id": simple_truth["mechanic_id"], "task_id": simple_truth["task_id"], "challenge_id": simple_truth["challenge_id"], "events": simple_truth["solution_events"], "completed": True},
            simple_truth,
            simple_public,
        )
        assert full_result["passed"] is True, full_result
        assert simple_result["passed"] is True, simple_result


def test_replay_rejects_stale_challenge_wrong_surface_and_missing_transport():
    public, truth = GENERATOR.generate(_task(4, "full"), "hearth-adversarial")
    payload = {"mechanic_id": truth["mechanic_id"], "task_id": truth["task_id"], "challenge_id": truth["challenge_id"], "events": truth["solution_events"], "completed": True}
    stale = copy.deepcopy(payload)
    stale["challenge_id"] = "old-challenge"
    assert GRADER.grade(stale, truth, public)["passed"] is False

    wrong_surface = copy.deepcopy(payload)
    wrong_surface["events"][0]["input_source"] = "camera_button"
    assert GRADER.grade(wrong_surface, truth, public)["passed"] is False

    empty = {**payload, "events": [], "completed": True}
    assert GRADER.grade(empty, truth, public)["passed"] is False


def test_declared_visual_controls_change_the_same_seed_decision_surface():
    base = _task(4, "full")
    base["_control_condition"]["difficulty_parameters"] = {
        **base["_control_condition"]["difficulty_parameters"],
        "cargo_detour": 0,
    }
    near_public, _ = GENERATOR.generate(base, "hearth-control-seed")
    base["_control_condition"]["difficulty_parameters"]["cargo_detour"] = 1
    far_public, _ = GENERATOR.generate(base, "hearth-control-seed")
    near_cargo = next(box for box in near_public["world"]["boxes"] if box["kind"] == "cargo")
    far_cargo = next(box for box in far_public["world"]["boxes"] if box["kind"] == "cargo")
    assert (near_cargo["x"], near_cargo["y"]) != (far_cargo["x"], far_cargo["y"])

    low_visibility = _task(4, "full")
    low_visibility["_control_condition"]["difficulty_parameters"] = {
        **low_visibility["_control_condition"]["difficulty_parameters"],
        "camera_obscurity": 0.42,
    }
    low_public, _ = GENERATOR.generate(low_visibility, "hearth-control-seed")
    high_visibility = _task(4, "full")
    high_visibility["_control_condition"]["difficulty_parameters"] = {
        **high_visibility["_control_condition"]["difficulty_parameters"],
        "camera_obscurity": 0.82,
    }
    high_public, _ = GENERATOR.generate(high_visibility, "hearth-control-seed")
    assert low_public["world"]["camera"]["obscurity"] == 0.42
    assert high_public["world"]["camera"]["obscurity"] == 0.82
    assert low_public["world"]["cells"] == high_public["world"]["cells"]
    assert low_public["world"]["camera"]["obscurity"] != high_public["world"]["camera"]["obscurity"]
    assert sum(box["kind"] == "helper" for box in near_public["world"]["boxes"]) == 4


def test_registry_split_and_task_provenance_are_task_bound():
    manifest = json.loads((BENCH / "benchmark_manifest.json").read_text())
    assert "hearthlift_courier_env" in manifest["environments"]
    assert manifest["environment_count"] == len(manifest["environments"])
    realtime = json.loads((BENCH / "real_time.json").read_text())
    assert realtime["environments"]["hearthlift_courier"] == {"play_time_seconds": 240, "observation_window_ms": 0, "frames_per_observation": 1}
    split = json.loads((BENCH / "splits/hearthlift_courier_split.json").read_text())
    assert len(split["variations_tasks"]) == 10
    task = json.loads((ENV / "tasks/hearthlift_courier_seed_0001/task.json").read_text())
    assert task["metadata"]["source_anchors"] == ["IND-068"]
    assert "Use only screenshots and visible controls" in task["natural_language"]
    assert "Developer Tools" in task["description"]
    assert (BENCH / "shared_runtime/assets/provenance/hearthlift_courier_v0.json").is_file()


def test_unchanged_helper_positions_cannot_deliver_cargo():
    # Exhaust the movement/climb state graph after pickup, not a push quota.
    for level in range(1, 6):
        for seed in range(20):
            _, truth = GENERATOR.generate(_task(level, "full"), str(seed))
            world = truth["world"]
            start = copy.deepcopy(truth["initial_state"])
            cargo = next(box for box in start["boxes"] if box["kind"] == "cargo")
            start["boxes"].remove(cargo)
            start["held"] = cargo["id"]
            queue = deque([start])
            seen = set()
            reached_hearth = False
            while queue:
                state = queue.popleft()
                pos = tuple(state["avatar"][key] for key in ("x", "y", "z"))
                if pos in seen:
                    continue
                seen.add(pos)
                if pos == tuple(world["hearth"][key] for key in ("x", "y", "height")):
                    reached_hearth = True
                    break
                for action_type in ("move", "climb"):
                    for direction in GENERATOR.DIRECTIONS:
                        candidate = copy.deepcopy(state)
                        try:
                            GRADER._apply_action(world, candidate, {"type": action_type, "direction": direction})
                        except ValueError:
                            continue
                        assert candidate["boxes"] == start["boxes"]
                        queue.append(candidate)
            assert not reached_hearth, (level, seed)


def test_browser_geometry_and_movement_match_the_independent_voxel_replay():
    rows = []
    for level in range(1, 6):
        for seed in range(10):
            public, truth = GENERATOR.generate(_task(level, "full"), str(seed))
            assert "stack_height" not in truth["control_condition"]["difficulty_parameters"]
            assert all(world_stage["height_before"] == 2*index for index, world_stage in enumerate(truth["world"]["stages"]))
            rows.append({"world": public["world"], "events": truth["solution_events"]})
    source = (BENCH / "shared_runtime/app/mechanics/hearthlift_courier.js").read_text()
    source = source.replace("  window.WeirdCaptchaMechanics.hearthlift_courier =", "  globalThis.testApi = {applyAction,snapshot,project,footprint};\n  window.WeirdCaptchaMechanics.hearthlift_courier =")
    script = """
const vm=require('vm'), fs=require('fs');
const {source,rows} = JSON.parse(fs.readFileSync(0,'utf8'));
const context={window:{}}; vm.createContext(context); vm.runInContext(source,context);
const {applyAction,snapshot,project,footprint}=context.testApi;
for (const {world,events} of rows) {
  const model={world,current:{avatar:structuredClone(world.avatar_start),boxes:structuredClone(world.boxes),held:null,delivered:false},cells:new Map(world.cells.map(c=>[`${c.x},${c.y}`,c]))};
  for (const event of events) {
    if (!['camera','certify'].includes(event.type)) applyAction(model,event);
    if (JSON.stringify(snapshot(model)) !== JSON.stringify(event.after)) throw Error('browser voxel replay mismatch');
  }
  for (let angle=0;angle<360;angle+=15) {
    model.cameraYaw=angle*Math.PI/180;
    model.projection={scale:0.7,centerX:0,centerY:0};
    const a=footprint(model,3,2,4,0.5), b=footprint(model,4,2,4,0.5);
    for (const [first,second] of [[a[1],b[0]],[a[2],b[3]]]) {
      if (Math.hypot(first.x-second.x,first.y-second.y)>1e-9) throw Error('projected neighbors do not share an edge');
    }
    const high=project(model,3,2,4), low=project(model,3,2,2);
    if (Math.abs((low.y-high.y)-2*32*0.7)>1e-9) throw Error('visible height differs from two-voxel ledge');
  }
}
"""
    result = subprocess.run(["node", "-e", script], input=json.dumps({"source": source, "rows": rows}), text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
