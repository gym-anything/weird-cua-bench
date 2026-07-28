from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import types


ROOT = Path(__file__).resolve().parents[1]
GRADER_PATH = ROOT / "benchmarks" / "weird_captcha_gym" / "shared_runtime" / "server" / "incubator_graders" / "microgame_gauntlet.py"
BENCH = ROOT / "benchmarks" / "weird_captcha_gym"
ENVIRONMENT = BENCH / "environments" / "microgame_gauntlet_env"


def _grader():
    spec = importlib.util.spec_from_file_location("microgame_gauntlet_contract_grader", GRADER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _normalized(value: dict) -> dict:
    result = copy.deepcopy(value)
    for key in ("task_id", "challenge_id", "control_condition"):
        result.pop(key, None)
    return result


def test_dial_replay_accepts_equivalent_zero_and_360_degree_telemetry() -> None:
    grader = _grader()
    round_data = {"friction": 0.96, "target_angle": 0, "target_tolerance": 8}
    events = [
        {"action": "drag_start", "angle": 315},
        {"action": "drag_move", "angle": 330, "delta": 15},
        {"action": "drag_move", "angle": 345, "delta": 15},
        {"action": "drag_end", "angle": 345, "velocity": 15},
        # A historical browser rounding edge could serialize this equivalent
        # position as 360. The replay must use circular angular equality.
        {"action": "dial_tick", "angle": 360, "velocity": 14.4},
        {"action": "brake", "angle": 0},
    ]
    assert grader._grade_dial(round_data, events) is None


def test_route_replay_rejects_teleported_checkpoints_and_accepts_sampled_corridor() -> None:
    grader = _grader()
    round_data = {
        "points": [
            {"x": 10, "y": 50},
            {"x": 30, "y": 50},
            {"x": 50, "y": 50},
            {"x": 70, "y": 50},
        ],
        "checkpoint_radius": 5,
        "corridor_radius": 6,
    }
    teleported = [
        {"action": "route_start", "x": 10, "y": 50},
        {"action": "route_move", "x": 30, "y": 50},
        {"action": "route_move", "x": 50, "y": 50},
        {"action": "route_move", "x": 70, "y": 50},
        {"action": "route_end", "x": 70, "y": 50},
    ]
    assert grader._grade_route(round_data, teleported) == "route transcript skips unsampled corridor geometry"

    sampled = [{"action": "route_start", "x": 10, "y": 50}]
    for x in range(12, 71, 2):
        sampled.append({"action": "route_move", "x": x, "y": 50})
    sampled.append({"action": "route_end", "x": 70, "y": 50})
    assert grader._grade_route(round_data, sampled) is None


def test_l4_full_preserves_the_precontrol_head_generator_output_exactly() -> None:
    """Keep L4/full tied to the literal historical generator, not equivalents."""
    source = subprocess.run(
        ["git", "show", "HEAD:benchmarks/weird_captcha_gym/shared_scripts/incubator_generators/microgame_gauntlet.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    historical_generator = types.ModuleType("microgame_gauntlet_head_generator")
    exec(compile(source, "HEAD:microgame_gauntlet.py", "exec"), historical_generator.__dict__)
    historical_task = json.loads(
        subprocess.run(
            ["git", "show", "HEAD:benchmarks/weird_captcha_gym/environments/microgame_gauntlet_env/tasks/microgame_gauntlet_seed_0001/task.json"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    setup = _module("microgame_gauntlet_current_setup", BENCH / "shared_scripts" / "setup_task.py")
    materializer = _module("microgame_gauntlet_control_materializer", BENCH / "tools" / "materialize_controlled_tasks.py")
    with tempfile.TemporaryDirectory(prefix="microgame-gauntlet-head-contract-") as temporary:
        root = Path(temporary) / "materialized"
        materializer.materialize_environment(ENVIRONMENT, root)
        controlled_task = json.loads(
            (root / ENVIRONMENT.name / "tasks" / "microgame_gauntlet_d4_full_seed_0001" / "task.json").read_text(encoding="utf-8")
        )
    historical_public, historical_truth = historical_generator.generate(historical_task, "head-baseline-contract")
    controlled_public, controlled_truth = setup.generate_task_state(controlled_task, "head-baseline-contract")
    for historical, controlled in ((historical_public, controlled_public), (historical_truth, controlled_truth)):
        assert json.dumps(_normalized(historical), sort_keys=True, separators=(",", ":")) == json.dumps(
            _normalized(controlled), sort_keys=True, separators=(",", ":")
        )
