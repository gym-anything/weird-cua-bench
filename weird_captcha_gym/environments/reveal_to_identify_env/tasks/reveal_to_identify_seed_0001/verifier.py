from __future__ import annotations

import importlib.util
import math
import re
from pathlib import Path
from typing import Any


MECHANIC_ID = "reveal_to_identify"
BENCHMARK_ROOT = Path(__file__).resolve().parents[4]
HELPER_PATH = BENCHMARK_ROOT / "shared_runtime" / "verifier_helpers.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _reject(feedback: str) -> dict[str, Any]:
    return {"passed": False, "score": 0, "feedback": f"independent reveal verifier: {feedback}"}


def _normalise_answer(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _finite_number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("non-numeric coordinate")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("non-finite coordinate")
    return number


def verify_exported_bundle(exported: dict[str, Any]) -> dict[str, Any]:
    """Replay one exported result without importing the live server grader."""

    result = exported.get("result") or {}
    truth = exported.get("ground_truth") or {}
    public = exported.get("public_state") or {}
    if not all(isinstance(item, dict) for item in (result, truth, public)):
        return _reject("exported result, truth, or public state is malformed")
    if not result:
        return _reject("no submitted UI result found")
    if any(str(item.get("mechanic_id") or "") != MECHANIC_ID for item in (result, truth, public)):
        return _reject("mechanic identity mismatch")

    challenge_id = str(truth.get("challenge_id") or "")
    task_id = str(truth.get("task_id") or "")
    if not challenge_id or any(str(item.get("challenge_id") or "") != challenge_id for item in (result, public)):
        return _reject("challenge identity mismatch")
    if not task_id or any(str(item.get("task_id") or "") != task_id for item in (result, public)):
        return _reject("task identity mismatch")

    condition = truth.get("control_condition")
    if condition != public.get("control_condition") or not isinstance(condition, dict):
        return _reject("control condition mismatch")
    interaction = str(condition.get("interaction") or "")
    expected_source = {"simplified": "coordinate_reveal", "full": "plate_click"}.get(interaction)
    if expected_source is None or str(result.get("interaction_mode") or "") != interaction:
        return _reject("interaction mode mismatch")

    try:
        stage = truth["stage"]
        reveal = truth["reveal"]
        width = int(stage["width"])
        height = int(stage["height"])
        budget = int(reveal["budget"])
        radius = int(reveal["radius"])
        accepted = {_normalise_answer(value) for value in truth["accepted_answers"]}
    except (KeyError, TypeError, ValueError) as exc:
        return _reject(f"invalid private contract: {exc}")
    if not accepted or "" in accepted:
        return _reject("accepted answer set is empty")
    if any(public.get(key) != truth.get(key) for key in ("stage", "scene", "reveal")):
        return _reject("render contract differs from private truth")

    events = result.get("events")
    if not isinstance(events, list) or not 1 <= len(events) <= budget:
        return _reject("reveal event count is outside the configured budget")
    replayed_centers: list[list[float]] = []
    try:
        for index, event in enumerate(events, start=1):
            if not isinstance(event, dict):
                raise ValueError(f"event {index} is malformed")
            if event.get("sequence") != index or event.get("kind") != "reveal":
                raise ValueError(f"event {index} sequence or kind is invalid")
            if str(event.get("input_source") or "") != expected_source:
                raise ValueError(f"event {index} uses the wrong input surface")
            if _finite_number(event.get("radius")) != radius:
                raise ValueError(f"event {index} radius is invalid")
            if _finite_number(event.get("remaining_after")) != budget - index:
                raise ValueError(f"event {index} budget accounting is invalid")
            point = event.get("point")
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError(f"event {index} point is malformed")
            x, y = (_finite_number(point[0]), _finite_number(point[1]))
            if not 0 <= x <= width or not 0 <= y <= height:
                raise ValueError(f"event {index} point leaves the plate")
            replayed_centers.append([round(x, 2), round(y, 2)])
    except ValueError as exc:
        return _reject(str(exc))

    if result.get("revealed_centers") != replayed_centers:
        return _reject("reported centers differ from event replay")
    if result.get("reveal_count") != len(events):
        return _reject("reported reveal count differs from event replay")
    if result.get("remaining_budget") != budget - len(events):
        return _reject("reported remaining budget differs from event replay")
    if result.get("completed") is not True:
        return _reject("submission is not marked complete")
    raw_answer = str(result.get("answer") or "")
    answer = _normalise_answer(raw_answer)
    if not answer or len(raw_answer) > 32:
        return _reject("identification text is missing or too long")
    if answer not in accepted:
        return _reject("identification does not match the private answer set")
    return {
        "passed": True,
        "score": 100,
        "feedback": f"independent reveal verifier: {len(events)}/{budget} discs replayed; identification accepted",
    }


def verify_task(traj=None, env_info=None, task_info=None):
    del traj, task_info
    try:
        helpers = _load("weird_captcha_verifier_helpers", HELPER_PATH)
        exported, error = helpers.load_exported_result(env_info or {})
    except Exception as exc:
        return {"passed": False, "score": 0, "feedback": f"cannot load verifier dependency: {exc}"}
    if error:
        return {"passed": False, "score": 0, "feedback": error}
    return verify_exported_bundle(exported or {})
