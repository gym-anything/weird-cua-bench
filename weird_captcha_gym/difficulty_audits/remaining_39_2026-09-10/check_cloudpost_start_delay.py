"""Read-only ideal-control replay and first-input delay analysis, not CUA evidence."""

import importlib.util
import json
import math
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def replay(public, truth, solver, grader, delay):
    plane = dict(public["initial_plane"])
    physics = public["physics"]
    events, collected = [], []
    control = [0.0, 0.0]
    def record(kind, tick, **details):
        events.append({"seq": len(events) + 1, "type": kind, "tick": tick, **details})
    for tick in range(3000):
        if tick:
            grader._step_plane(plane, control, physics)
        for target in public["targets"]:
            distance = math.dist([plane[k] for k in ("x", "y", "z")], [target[k] for k in ("x", "y", "z")])
            if target["id"] not in collected and distance <= physics["contact_radius"]:
                collected.append(target["id"])
                record("contact", tick, target_id=target["id"], distance=round(distance, 4), plane={k: round(v, 4) for k, v in plane.items()})
        done = len(collected) == len(public["targets"])
        lost = abs(plane["x"]) > physics["world_x"] or abs(plane["y"]) > physics["world_y"] or plane["z"] > physics["world_z"]
        if done or lost:
            record("terminal", tick, completed=done, collected=collected, plane={k: round(v, 4) for k, v in plane.items()})
            payload = {k: truth[k] for k in ("mechanic_id", "task_id", "challenge_id")}
            payload.update(interaction="full", completed=done, events=events)
            return {"initial_neutral_ticks": delay, "terminal_tick": tick, "contacts": len(collected), "grade": grader.grade(payload, truth, public)}
        if tick >= delay:
            target = next(target for target in public["targets"] if target["id"] not in collected)
            control = solver._control_for(plane, target, physics)
            record("steer", tick, yaw=control[0], pitch=control[1], input_source="pointer_steer")
    return {"initial_neutral_ticks": delay, "error": "3000-tick replay limit"}


def main():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    bench = Path(manifest["source_root"]) / "weird_captcha_gym"
    solver = load(bench / "tools/incubator_solvers/cloudpost_circuit.py", "cloudpost_delay_solver")
    grader = load(bench / "shared_runtime/server/incubator_graders/cloudpost_circuit.py", "cloudpost_delay_grader")
    rows = []
    for folder in sorted((ROOT / "outputs/generation/cloudpost_circuit").glob("d*_full_seed*")):
        public = json.loads((folder / "public_state.json").read_text())
        truth = json.loads((folder / "ground_truth.json").read_text())
        rows.append({"configuration": folder.name, "replays": [replay(public, truth, solver, grader, delay) for delay in (0, 16)]})
    attempts = []
    for path in sorted((ROOT / "outputs/browser").glob("018_cloudpost_circuit_d[45]_*_seed1_solve/state/attempts.jsonl")):
        attempt = json.loads(path.read_text().splitlines()[0])
        first = next(event for event in attempt["events"] if event["type"] == "steer")
        name = path.parent.parent.name
        config = name.removeprefix("018_cloudpost_circuit_").removesuffix("_solve")
        public = json.loads((ROOT / "outputs/generation/cloudpost_circuit" / config / "public_state.json").read_text())
        target, physics = public["targets"][0], public["physics"]
        z_before_input = first["tick"] * physics["flight_speed"]
        # All future headings have |yaw| <= max_yaw and forward z velocity.
        # Distance to the reachable x-z half-plane is a conservative lower
        # bound: it ignores turn ramp, pitch, discrete time and input latency.
        lower_bound = max(0.0, abs(target["x"]) * math.cos(physics["max_yaw"]) - (target["z"] - z_before_input) * math.sin(physics["max_yaw"]))
        attempts.append({"original_record": name, "first_steer_tick": first["tick"], "neutral_seconds": first["tick"] * physics["tick_ms"] / 1000,
            "first_target": target, "z_before_first_steer": z_before_input, "xz_reachability_distance_lower_bound": lower_bound,
            "radius": physics["contact_radius"], "first_target_already_unreachable_by_bound": lower_bound > physics["contact_radius"],
            "server_grade": attempt.get("server_grade"), "source_attempt": str(path.relative_to(ROOT))})
    result = {"source_revision": manifest["source_revision"], "scope": __doc__,
        "limitations": "Ideal replay uses exact private pose, continuous controls and zero control latency. It does not prove screenshot-only or Simplified button feasibility. Original browser failures are not upgraded.", "rows": rows, "original_failed_attempts": attempts}
    (ROOT / "cloudpost_start_delay_checks.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"worlds": len(rows), "tick_zero_passes": sum(row["replays"][0].get("grade", {}).get("passed") is True for row in rows),
        "tick_16_passes": sum(row["replays"][1].get("grade", {}).get("passed") is True for row in rows), "failed_attempts": attempts}))


if __name__ == "__main__":
    main()
