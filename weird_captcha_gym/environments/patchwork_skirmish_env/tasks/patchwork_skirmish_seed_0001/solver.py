from __future__ import annotations

from pathlib import Path
import importlib.util


GRADER_PATH = Path(__file__).resolve().parents[4] / "shared_runtime" / "server" / "incubator_graders" / "patchwork_skirmish.py"


def _grader():
    spec = importlib.util.spec_from_file_location("patchwork_skirmish_grader", GRADER_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load grader from {GRADER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def solve(public_state, ground_truth):
    return _grader().plan(ground_truth["world"])
