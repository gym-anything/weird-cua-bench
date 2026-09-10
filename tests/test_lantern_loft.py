from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "weird_captcha_gym" / "shared_scripts" / "incubator_generators" / "lantern_loft.py"
GRADER_PATH = ROOT / "weird_captcha_gym" / "shared_runtime" / "server" / "incubator_graders" / "lantern_loft.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("lantern_loft_test_generator", GENERATOR_PATH)
GRADER = _load("lantern_loft_test_grader", GRADER_PATH)


def _task(difficulty: int, interaction: str) -> dict:
    return {
        "id": f"lantern-test-d{difficulty}-{interaction}@0.1",
        "_control_condition": {
            "difficulty": difficulty,
            "interaction": interaction,
            "difficulty_parameters": dict(GENERATOR.PROFILES[difficulty]),
        },
    }


def _passing_payload(public: dict, truth: dict) -> dict:
    condition = truth["control_condition"]
    events = []
    sequence = 0
    timestamp = 0
    for move in truth["solution_slides"]:
        sequence += 1
        events.append(
            {
                "seq": sequence,
                "t_ms": timestamp,
                "kind": "slide",
                "module_id": move["module_id"],
                "from_slot": move["from_slot"],
                "to_slot": move["to_slot"],
                "input_source": "drag" if condition["interaction"] == "full" else "proxy_slide",
            }
        )
        timestamp += 1
    for source, target in zip(truth["route_slots"], truth["route_slots"][1:]):
        sequence += 1
        events.append(
            {
                "seq": sequence,
                "t_ms": timestamp,
                "kind": "step",
                "from_slot": source,
                "to_slot": target,
                "input_source": "surface_click" if condition["interaction"] == "full" else "proxy_step",
            }
        )
        timestamp += 1
    sequence += 1
    events.append({"seq": sequence, "t_ms": timestamp, "kind": "finish", "input_source": "physical_contact"})
    return {
        "mechanic_id": "lantern_loft",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "interaction": public["control_condition"]["interaction"],
        "completed": True,
        "events": events,
    }


def test_all_difficulties_and_both_input_surfaces_share_the_world():
    for difficulty in range(1, 6):
        full_public, full_truth = GENERATOR.generate(_task(difficulty, "full"), f"lantern-regression-{difficulty}")
        simple_public, simple_truth = GENERATOR.generate(_task(difficulty, "simplified"), f"lantern-regression-{difficulty}")
        assert full_public["world"] == simple_public["world"]
        assert full_truth["world"] == simple_truth["world"]
        assert len(full_truth["route_slots"]) == GENERATOR.PROFILES[difficulty]["route_count"]
        assert len(full_truth["solution_slides"]) == GENERATOR.PROFILES[difficulty]["slide_count"]
        assert full_public["world"]["rules"]["max_height_delta"] == 1


def test_solution_replays_and_contract_mismatches_fail():
    for interaction in ("full", "simplified"):
        public, truth = GENERATOR.generate(_task(4, interaction), f"lantern-replay-{interaction}")
        payload = _passing_payload(public, truth)
        decision = GRADER.grade(payload, truth, public)
        assert decision["passed"] is True

        wrong_surface = json.loads(json.dumps(payload))
        wrong_surface["events"][0]["input_source"] = "proxy_slide" if interaction == "full" else "drag"
        assert GRADER.grade(wrong_surface, truth, public)["passed"] is False

        missing_surface = json.loads(json.dumps(payload))
        missing_surface.pop("interaction")
        assert GRADER.grade(missing_surface, truth, public)["passed"] is False

        stale = json.loads(json.dumps(payload))
        stale["challenge_id"] = "stale-lantern"
        assert GRADER.grade(stale, truth, public)["passed"] is False

        illegal = json.loads(json.dumps(payload))
        illegal["events"][0]["to_slot"] = (illegal["events"][0]["to_slot"] + 2) % 9
        assert GRADER.grade(illegal, truth, public)["passed"] is False


def test_target_metadata_and_registry_are_present():
    controls = json.loads((ROOT / "weird_captcha_gym" / "environments" / "lantern_loft_env" / "controls.json").read_text())
    task = json.loads((ROOT / "weird_captcha_gym" / "environments" / "lantern_loft_env" / "tasks" / "lantern_loft_seed_0001" / "task.json").read_text())
    manifest = json.loads((ROOT / "weird_captcha_gym" / "benchmark_manifest.json").read_text())
    real_time = json.loads((ROOT / "weird_captcha_gym" / "real_time.json").read_text())
    assert controls["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    assert task["metadata"]["source_anchors"] == ["PHY-059"]
    assert task["metadata"]["capabilities"] == ["visual understanding (3D)", "reasoning and planning"]
    assert "lantern_loft_env" in manifest["environments"]
    assert real_time["environments"]["lantern_loft"]["observation_window_ms"] == 0
    assert real_time["environments"]["lantern_loft"]["frames_per_observation"] == 1


def test_profiles_require_reconfiguration_and_real_elevation_changes():
    for level in range(1, 6):
        for seed in range(100):
            public, truth = GENERATOR.generate(_task(level, "full"), str(seed))
            world = public["world"]
            modules = GRADER._module_map(world)
            heights = [modules[mid]["height"] for mid in truth["route_module_ids"]]
            assert sum(a != b for a, b in zip(heights, heights[1:])) == GENERATOR.PROFILES[level]["elevation_changes"], (level,seed)
            seen = {world["carrier_slot"]}
            pending = list(seen)
            while pending:
                source = pending.pop()
                for target in range(9):
                    if target not in seen and GRADER._connected(world, world["board"], source, target):
                        seen.add(target)
                        pending.append(target)
            assert world["exit_slot"] not in seen, (level,seed)
            # Each authored connection has two openings; remaining openings
            # are the exact additional, potentially misleading choices.
            opening_count = sum(sum(m["openings"].values()) for m in modules.values())
            assert opening_count == 2*(len(heights)-1) + GENERATOR.PROFILES[level]["decoy_openings"]
            assert GRADER.grade(_passing_payload(public,truth),truth,public)["passed"]


def test_browser_replay_draw_coordinates_and_unfiltered_proxies():
    rows = []
    for level in range(1, 6):
        for seed in range(10):
            public, truth = GENERATOR.generate(_task(level, "simplified"), str(seed))
            rows.append({"public": public,"payload": _passing_payload(public,truth)})
    source = (ROOT / "weird_captcha_gym/shared_runtime/app/mechanics/lantern_loft.js").read_text()
    source = source.replace("  window.WeirdCaptchaMechanics =", "  globalThis.testApi={polygon,connected,drawScene,updateProxy,hitSlot,setModel: value=>{model=value;}};\n  window.WeirdCaptchaMechanics =")
    script = """
const vm=require('vm'),fs=require('fs');
const {rows,source}=JSON.parse(fs.readFileSync(0,'utf8'));
const slide={innerHTML:'',querySelectorAll:()=>[]},step={innerHTML:'',querySelectorAll:()=>[]};
const drawing=new Proxy({}, {get:(_,key)=>key==='createLinearGradient'?(()=>({addColorStop(){}})):(...args)=>{for(const a of args) if(typeof a==='number'&&!Number.isFinite(a)) throw Error(`non-finite drawing coordinate: ${key}`);},set:()=>true});
const canvas={width:900,height:560,getContext:()=>drawing};
const context={window:{},document:{querySelector:s=>({'#lantern-slide-proxy':slide,'#lantern-step-proxy':step,'#lantern-loft-canvas':canvas}[s]||null)}};
vm.createContext(context);vm.runInContext(source,context);
const api=context.testApi;
for (const row of rows) {
  const world=row.public.world;
  const model={state:row.public,board:[...world.board],modules:Object.fromEntries(world.modules.map(m=>[m.id,m])),emptySlot:world.empty_slot,carrierSlot:world.carrier_slot,exitSlot:world.exit_slot,helpers:{text:String}};
  api.setModel(model);
  for(const event of row.payload.events) {
    api.drawScene(); api.updateProxy();
    if ((slide.innerHTML.match(/data-slide-module=/g)||[]).length!==8 || (step.innerHTML.match(/data-step-slot=/g)||[]).length!==9 || /disabled/.test(slide.innerHTML+step.innerHTML)) throw Error('proxies expose move legality');
    if(event.kind==='slide') {model.board[event.to_slot]=model.board[event.from_slot];model.board[event.from_slot]=null;model.emptySlot=event.from_slot;}
    if(event.kind==='step') {if(!api.connected(model.carrierSlot,event.to_slot)) throw Error('browser/Python connectivity mismatch');model.carrierSlot=event.to_slot;}
  }
  const a=api.polygon(0,1), b=api.polygon(1,1);
  if(JSON.stringify(a[1])!==JSON.stringify(b[0]) || JSON.stringify(a[2])!==JSON.stringify(b[3])) throw Error('adjacent top surfaces do not share their projected edge');
}
"""
    result = subprocess.run(["node", "-e", script], input=json.dumps({"source": source, "rows": rows}), text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
