"""Measure realized Lantern Loft structure, using frozen generated worlds.

Search is a bounded implementation diagnostic, not a screenshot-only solver.
"""

from collections import deque
import importlib.util
import json
from pathlib import Path
import sys


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent


def shortest_actions(world, grader, node_limit=100000):
    initial = (tuple(world["board"]), world["carrier_slot"])
    queue = deque([(initial, 0, 0)])
    seen = {initial}
    while queue:
        (board, carrier), actions, slides = queue.popleft()
        if carrier == world["exit_slot"]:
            return {"minimum_actions": actions, "slides_in_one_shortest_action_solution": slides, "states_seen": len(seen), "exhausted": False}
        if len(seen) >= node_limit:
            return {"minimum_actions": None, "states_seen": len(seen), "node_limit": node_limit, "exhausted": True}
        empty = board.index(None)
        for target in range(9):
            if grader._connected(world, list(board), carrier, target):
                successor = (board, target)
                if successor not in seen:
                    seen.add(successor)
                    queue.append((successor, actions + 1, slides))
            if target != carrier and board[target] is not None and grader._adjacent(target, empty, 3)[0]:
                changed = list(board)
                changed[empty], changed[target] = changed[target], None
                successor = (tuple(changed), carrier)
                if successor not in seen:
                    seen.add(successor)
                    queue.append((successor, actions + 1, slides + 1))
    return {"minimum_actions": None, "states_seen": len(seen), "unreachable": True}


def main():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    source = Path(manifest["source_root"])
    path = source / "weird_captcha_gym/shared_runtime/server/incubator_graders/lantern_loft.py"
    spec = importlib.util.spec_from_file_location("loft_primary_grader", path)
    grader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(grader)
    rows = []
    for folder in sorted((ROOT / "outputs/generation/lantern_loft").glob("d*_full_seed*")):
        public = json.loads((folder / "public_state.json").read_text())
        truth = json.loads((folder / "ground_truth.json").read_text())
        world = public["world"]
        modules = {m["id"]: m for m in world["modules"]}
        heights = [modules[mid]["height"] for mid in truth["route_module_ids"]]
        rows.append({
            "configuration": folder.name,
            "parameters": public["control_condition"]["difficulty_parameters"],
            "realized_route_heights": heights,
            "realized_route_height_transitions": sum(a != b for a, b in zip(heights, heights[1:])),
            "decoy_count": sum(mid.startswith("decoy-") for mid in modules),
            "construction_slide_witness_length": len(truth["solution_slides"]),
            "shortest_action_diagnostic": shortest_actions(world, grader),
        })
    result = {"schema_version": 1, "source_revision": manifest["source_revision"],
              "scope": "15 frozen worlds, one per difficulty/seed; Full/Simplified worlds already compared separately. Exact BFS under existing grader transitions until the stated node limit. Does not establish screenshot difficulty or minimum slide count among non-shortest solutions.", "rows": rows}
    (ROOT / "lantern_loft_structure_checks.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
