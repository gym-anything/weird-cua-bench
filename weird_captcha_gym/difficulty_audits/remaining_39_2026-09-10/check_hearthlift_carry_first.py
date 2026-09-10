"""Test whether Hearthlift requires its advertised prepare/return/carry route."""

import copy
import importlib.util
import json
from pathlib import Path
import sys


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent


def carry_first_actions(truth):
    actions = [{"type": "camera", "delta": 0.34}, {"type": "pickup"}]
    for stage in truth["world"]["stages"]:
        actions.append({"type": "climb", "direction": "E"})
        actions.extend({"type": "move", "direction": "E"} for _ in range(3))
        if stage.get("turn"):
            actions.append({"type": "move", "direction": stage["turn"]["direction"]})
    actions.append({"type": "drop"})
    return actions


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    bench = Path(manifest["source_root"]) / "weird_captcha_gym"
    generator = load(bench / "shared_scripts/incubator_generators/hearthlift_courier.py", "carry_first_generator")
    grader = load(bench / "shared_runtime/server/incubator_graders/hearthlift_courier.py", "carry_first_grader")
    rows = []
    for folder in sorted((ROOT / "outputs/generation/hearthlift_courier").glob("d*_*_seed*")):
        public = json.loads((folder / "public_state.json").read_text())
        truth = json.loads((folder / "ground_truth.json").read_text())
        actions = carry_first_actions(truth)
        mode = truth["control_condition"]["interaction"]
        events = generator._event_transcript(truth["world"], actions, mode)
        payload = {k: truth[k] for k in ("mechanic_id", "task_id", "challenge_id")}
        payload.update({"control_condition": truth["control_condition"], "completed": True, "events": events, "final_state": events[-1]["after"]})
        decision = grader.grade(payload, truth, public)
        original_helpers = [box for box in truth["world"]["boxes"] if box["kind"] != "cargo"]
        rows.append({"configuration": folder.name, "action_count": len(actions), "canonical_action_count": len(truth["solution_actions"]),
                     "helper_and_decoy_boxes_unchanged": events[-1]["after"]["boxes"] == original_helpers,
                     "grade": decision, "actions": actions})
    result = {"schema_version": 1, "source_revision": manifest["source_revision"],
              "scope": "Privileged replay diagnostic of 30 frozen configurations. Uses existing generator event construction and independently grades the carry-first route. Not human or screenshot-agent evidence.", "rows": rows}
    (ROOT / "hearthlift_carry_first_checks.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"configurations": len(rows), "passing_carry_first_routes": sum(row["grade"]["passed"] for row in rows),
                      "unchanged_helper_boxes": sum(row["helper_and_decoy_boxes_unchanged"] for row in rows)}, indent=2))


if __name__ == "__main__":
    main()
