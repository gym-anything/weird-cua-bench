from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "weird_captcha_gym" / "environments" / "cloudstep_caddie_env"
GENERATOR_PATH = ROOT / "weird_captcha_gym" / "shared_scripts" / "incubator_generators" / "cloudstep_caddie.py"
GRADER_PATH = ROOT / "weird_captcha_gym" / "shared_runtime" / "server" / "incubator_graders" / "cloudstep_caddie.py"
MATERIALIZER_PATH = ROOT / "weird_captcha_gym" / "tools" / "materialize_controlled_tasks.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generator = _load("cloudstep_test_generator", GENERATOR_PATH)
grader = _load("cloudstep_test_grader", GRADER_PATH)
materializer = _load("cloudstep_test_materializer", MATERIALIZER_PATH)


def _controls() -> dict:
    return json.loads((ENV / "controls.json").read_text(encoding="utf-8"))


def _state_pair(level: int, interaction: str, seed: str = "cloudstep-test-seed") -> tuple[dict, dict]:
    controls = _controls()
    profile = copy.deepcopy(controls["difficulty"][str(level)])
    task = {
        "id": "cloudstep_caddie_diagnostic@0.2",
        "natural_language": "test",
        "_control_condition": {
            "difficulty": level,
            "interaction": interaction,
            "real_time": "live",
            "difficulty_parameters": profile["parameters"],
        },
    }
    return generator.generate(task, seed)


def _winning_payload(public: dict, truth: dict) -> dict:
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "simplified")
    tile_map = grader._tile_map(public["course"])
    cards = {str(card["id"]): card for card in public["cards"]}
    current = grader._state(public["course"]["start"], [], tile_map)
    events = []
    for sequence, step in enumerate(truth["solution"], 1):
        card_id = str(step["card_id"])
        before = copy.deepcopy(current)
        after, error = grader._transition(current, cards[card_id], str(step["direction"]), public["course"], tile_map)
        assert error is None and after is not None
        after["used_card_ids"] = [*current["used_card_ids"], card_id]
        events.append({
            "seq": sequence,
            "type": "stroke",
            "card_id": card_id,
            "direction": step["direction"],
            "before": before,
            "after": after,
            "input_source": "card_drag_to_compass" if interaction == "full" else "card_then_direction_buttons",
        })
        current = after
    events.append({
        "seq": len(events) + 1,
        "type": "certify",
        "ball": current,
        "used_card_ids": current["used_card_ids"],
        "accepted": True,
        "input_source": "certify_button",
    })
    return {
        "mechanic_id": "cloudstep_caddie",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "interaction_mode": interaction,
        "events": events,
        "completed": True,
    }


def test_controls_have_five_profiles_and_both_surfaces() -> None:
    controls = _controls()
    materializer.validate_controls(controls, ENV)
    assert controls["baseline"] == {"difficulty": 4, "interaction": "simplified", "real_time": "live"}
    assert controls["interaction"]["simplified"]["implemented"] is True
    assert controls["interaction"]["full"]["implemented"] is True


def test_all_levels_and_both_interactions_are_solvable_and_same_world() -> None:
    for level in range(1, 6):
        simplified, simple_truth = _state_pair(level, "simplified")
        full, full_truth = _state_pair(level, "full")
        assert simplified["challenge_id"] == full["challenge_id"]
        assert {key: value for key, value in simplified.items() if key != "control_condition"} == {key: value for key, value in full.items() if key != "control_condition"}
        assert len(simple_truth["solution"]) == {1: 3, 2: 4, 3: 5, 4: 7, 5: 9}[level]
        assert len(simplified["cards"]) == len(simple_truth["solution"])
        assert grader.grade(_winning_payload(simplified, simple_truth), simple_truth, simplified)["passed"] is True
        assert grader.grade(_winning_payload(full, full_truth), full_truth, full)["passed"] is True


def test_fresh_seeds_change_visible_course_but_preserve_replay_contract() -> None:
    first, first_truth = _state_pair(4, "simplified", "cloudstep-seed-a")
    second, second_truth = _state_pair(4, "simplified", "cloudstep-seed-b")
    assert first["challenge_id"] != second["challenge_id"]
    assert first["course"] != second["course"] or first["palette"] != second["palette"]
    assert grader.grade(_winning_payload(first, first_truth), first_truth, first)["passed"] is True
    assert grader.grade(_winning_payload(second, second_truth), second_truth, second)["passed"] is True


def test_wrong_surface_stale_transcript_and_incomplete_hand_fail() -> None:
    public, truth = _state_pair(4, "full")
    winning = _winning_payload(public, truth)
    wrong_surface = copy.deepcopy(winning)
    wrong_surface["events"][0]["input_source"] = "card_then_direction_buttons"
    assert grader.grade(wrong_surface, truth, public)["passed"] is False
    stale = copy.deepcopy(winning)
    stale["challenge_id"] = "stale-challenge"
    assert grader.grade(stale, truth, public)["passed"] is False
    incomplete = copy.deepcopy(winning)
    incomplete["events"] = [incomplete["events"][-1]]
    incomplete["events"][0]["seq"] = 1
    incomplete["events"][0]["ball"]["used_card_ids"] = []
    incomplete["events"][0]["used_card_ids"] = []
    incomplete["events"][0]["accepted"] = False
    assert grader.grade(incomplete, truth, public)["passed"] is False


def test_materialized_task_matrix_and_verifier_files_exist(tmp_path) -> None:
    generated = materializer.materialize_environment(ENV, tmp_path)
    task_root = generated[0].parent
    names = {path.name for path in generated}
    for level in range(1, 6):
        for interaction in ("simplified", "full"):
            name = f"cloudstep_caddie_d{level}_{interaction}_seed_0001"
            assert name in names
            task = json.loads((task_root / name / "task.json").read_text(encoding="utf-8"))
            condition = task["metadata"]["control_condition"]
            assert condition["difficulty"] == level
            assert condition["interaction"] == interaction
            assert (task_root / name / "verifier.py").is_file()
            assert (task_root / name / "setup_task.sh").is_file()
            assert (task_root / name / "export_result.sh").is_file()


def test_cup_sand_and_ramp_geometry_agree_across_generated_worlds() -> None:
    for level in range(1, 6):
        for seed in range(40):
            public, truth = _state_pair(level, "full", str(seed))
            course = public["course"]
            tiles = grader._tile_map(course)
            cup = course["cup"]
            assert tiles[(cup["x"], cup["y"])]["surface"] == "cup"
            assert sum(tile["surface"] == "cup" for tile in tiles.values()) == 1
            events = _winning_payload(public, truth)["events"][:-1]
            assert sum(event["after"]["surface"] == "sand" for event in events) == {1: 0, 2: 1, 3: 1, 4: 2, 5: 3}[level]
            assert sum(event["after"]["z"] != event["before"]["z"] for event in events) == (1 if level < 3 else 2)
            for tile in tiles.values():
                if tile["surface"] == "ramp":
                    canonical = generator._transform_direction(tile["ramp_direction"], course["transform"])
                    assert canonical in grader._DIRECTIONS


def test_ramp_direction_and_drawn_cell_edges_match_independent_replay() -> None:
    rows = []
    for direction, (dx, dy) in grader._DIRECTIONS.items():
        for heading in grader._DIRECTIONS:
            course = {"width": 7, "height": 6, "tiles": [
                {"x": 2, "y": 2, "z": 0, "surface": "fairway"},
                {"x": 2 + dx, "y": 2 + dy, "z": 1, "surface": "ramp", "ramp_direction": heading},
            ], "rules": {"roll_max_step_height": 1}}
            before = {"x": 2, "y": 2, "z": 0, "surface": "fairway", "used_card_ids": []}
            card = {"kind": "roll", "distance": 1}
            after, error = grader._transition(before, card, direction, course, grader._tile_map(course))
            assert (error is None) is (direction == heading)
            rows.append({"course": course, "before": before, "card": card, "direction": direction, "legal": after is not None})
    script = r'''
const fs = require('fs'), vm = require('vm');
let source = fs.readFileSync(process.argv[1], 'utf8');
source = source.replace('registry.cloudstep_caddie =', 'window.testApi = {transition, project, diamond, setCourse(course) {model = {state: {course}, tiles: tileMap(course)};}}; registry.cloudstep_caddie =');
const sandbox = {window: {}};
vm.runInNewContext(source, sandbox);
const api = sandbox.window.testApi;
const rows = JSON.parse(fs.readFileSync(0, 'utf8'));
for (const row of rows) {api.setCourse(row.course); if (!api.transition(row.before,row.card,row.direction).error !== row.legal) throw Error('browser/replay ramp mismatch');}
const scales = [];
for (const [width,height] of [[7,6],[8,7],[9,8],[11,9],[12,9]]) {
  api.setCourse({width,height});
  const p = api.project(2,2,0), q = api.project(3,2,0);
  const a = api.diamond(null,p), b = api.diamond(null,q);
  for (const [i,j] of [[1,0],[2,3]]) for (const axis of [0,1]) if (Math.abs(a[i][axis]-b[j][axis]) > 1e-8) throw Error('neighboring tile edges overlap or separate');
  scales.push(p.tileW);
}
if (!scales.every((scale,index) => index === 0 || scale < scales[index-1])) throw Error('claimed scale progression is inactive');
'''
    frontend = ROOT / "weird_captcha_gym/shared_runtime/app/mechanics/cloudstep_caddie.js"
    subprocess.run(["node", "-e", script, str(frontend)], input=json.dumps(rows), text=True, check=True, capture_output=True)
