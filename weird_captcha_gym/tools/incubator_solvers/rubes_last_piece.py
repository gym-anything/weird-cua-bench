from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "rubes_last_piece"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, mechanic: str, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{mechanic}-{name}.png"), full_page=True)


def _wait_new(state_dir: Path, previous: str) -> None:
    deadline = time.time() + 8
    while time.time() < deadline:
        if str(_read(state_dir / "public_state.json").get("challenge_id")) != previous:
            return
        time.sleep(0.05)
    raise AssertionError("Rube challenge did not regenerate after rejection")


def _grader():
    path = Path(__file__).resolve().parents[2] / "shared_runtime/server/incubator_graders/rubes_last_piece.py"
    spec = importlib.util.spec_from_file_location("rubes_last_piece_solver_replay", path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _public_solution(state: dict) -> dict[str, dict]:
    replay = _grader()
    tools = state["tools"]
    angles = [float(value) for value in state["contract"]["allowed_angles_deg"]]
    candidates: dict[str, list[dict]] = {}
    for bay in state["bays"]:
        rows = []
        for tool in tools:
            for angle in angles:
                pose = [float(bay["anchor"][0]), float(bay["anchor"][1]), float(angle)]
                if replay.replay_lane(state, bay, tool, pose)["passed"]:
                    rows.append({"tool_id": tool["id"], "pose": pose})
        if not rows:
            raise AssertionError(f"no visible-state physical solution for {bay['id']}")
        candidates[bay["id"]] = rows

    chosen: dict[str, dict] = {}

    def search(index: int, used: set[str]) -> bool:
        if index == len(state["bays"]):
            return True
        bay_id = state["bays"][index]["id"]
        for candidate in candidates[bay_id]:
            if candidate["tool_id"] in used:
                continue
            chosen[bay_id] = candidate
            if search(index + 1, used | {candidate["tool_id"]}):
                return True
        chosen.pop(bay_id, None)
        return False

    if not search(0, set()):
        raise AssertionError("no non-reusing visible-state deflector assignment")
    return chosen


def _solution(state: dict) -> dict[str, dict]:
    return _public_solution(state)


def _screen(box: dict, stage: dict, point: list[float]) -> tuple[float, float]:
    return (
        box["x"] + point[0] / stage["width"] * box["width"],
        box["y"] + point[1] / stage["height"] * box["height"],
    )


def _place_full(page, tool_id: str, anchor: list[float], box: dict, stage: dict) -> None:
    chip = page.locator(f'.rube-tool[data-tool-id="{tool_id}"]')
    chip_box = chip.bounding_box()
    if chip_box is None:
        raise AssertionError(f"Rube rack deflector {tool_id} is not visible")
    page.mouse.move(chip_box["x"] + chip_box["width"] / 2, chip_box["y"] + chip_box["height"] / 2)
    page.mouse.down()
    page.mouse.move(*_screen(box, stage, anchor), steps=8)
    page.mouse.up()


def _move_full(page, start: list[float], target: list[float], box: dict, stage: dict) -> None:
    page.mouse.move(*_screen(box, stage, start))
    page.mouse.down()
    page.mouse.move(*_screen(box, stage, target), steps=8)
    page.mouse.up()


def _exercise_full_drop_rejections(page, state: dict, out_dir: Path, mechanic: str) -> None:
    box = page.locator(".rube-canvas").bounding_box()
    if box is None:
        raise AssertionError("Rube flight canvas is missing")
    tool_id = state["tools"][0]["id"]
    for name, point in (("off-station-drop-rejected", [40.0, state["stage"]["height"] / 2]), ("canvas-edge-drop-rejected", [1.0, 1.0])):
        _place_full(page, tool_id, point, box, state["stage"])
        expect(page.locator(".rube-placed-count")).to_have_text(f"0/{len(state['bays'])}")
        expect(page.locator(".readout")).to_contain_text("DASHED FLIGHT STATION")
        _shot(page, out_dir, mechanic, name)


def _exercise_full_station_move(page, state: dict, solution: dict[str, dict], out_dir: Path, mechanic: str) -> None:
    if len(state["bays"]) < 2:
        return
    box = page.locator(".rube-canvas").bounding_box()
    if box is None:
        raise AssertionError("Rube flight canvas is missing")
    first, second = state["bays"][:2]
    first_tool = solution[first["id"]]["tool_id"]
    second_tool = solution[second["id"]]["tool_id"]
    _move_full(page, first["anchor"], second["anchor"], box, state["stage"])
    _move_full(page, second["anchor"], first["anchor"], box, state["stage"])
    _place_full(page, second_tool, second["anchor"], box, state["stage"])
    expect(page.locator(".rube-placed-count")).to_have_text(f"{len(state['bays'])}/{len(state['bays'])}")
    _shot(page, out_dir, mechanic, "full-moved-between-stations")


def _exercise_material_swap(page, state: dict, solution: dict[str, dict], out_dir: Path, mechanic: str) -> bool:
    used = {candidate["tool_id"] for candidate in solution.values()}
    first = state["bays"][0]
    replay = _grader()
    mismatch = None
    for tool in state["tools"]:
        if tool["id"] in used:
            continue
        for angle in state["contract"]["allowed_angles_deg"]:
            pose = [float(first["anchor"][0]), float(first["anchor"][1]), float(angle)]
            result = replay.replay_lane(state, first, tool, pose)
            if not result["passed"] and result["impact_error"] is not None:
                mismatch = {"tool_id": tool["id"], "angle": float(angle)}
                break
        if mismatch:
            break
    if mismatch is None:
        return False

    interaction = str((state.get("control_condition") or {}).get("interaction") or "full")
    box = page.locator(".rube-canvas").bounding_box()
    if box is None:
        raise AssertionError("Rube flight canvas is missing")
    if interaction == "simplified":
        page.locator(f'.rube-tool[data-tool-id="{mismatch["tool_id"]}"]').click()
        page.locator(f'[data-place-bay="{first["id"]}"]').click()
    else:
        _place_full(page, mismatch["tool_id"], first["anchor"], box, state["stage"])
    _rotate_to(page, interaction, _screen(box, state["stage"], first["anchor"]), mismatch["angle"])
    page.locator(".rube-run").click()
    expect(page.locator(".rube-machine[data-outcome='fail']")).to_be_visible(timeout=10_000)
    _shot(page, out_dir, mechanic, "material-mismatch-stall")
    page.locator(".rube-rewind").click()

    correct_tool = solution[first["id"]]["tool_id"]
    if interaction == "simplified":
        page.locator(f'.rube-tool[data-tool-id="{correct_tool}"]').click()
        page.locator(f'[data-place-bay="{first["id"]}"]').click()
    else:
        _place_full(page, correct_tool, first["anchor"], box, state["stage"])
    expect(page.locator(".rube-placed-count")).to_have_text(f"{len(state['bays'])}/{len(state['bays'])}")
    _shot(page, out_dir, mechanic, "material-swap-repair")
    return True


def _rotate_to(page, interaction: str, point: tuple[float, float], target: float) -> None:
    turns = int(round(((float(target) - 45.0) % 180.0) / 5.0))
    for _ in range(turns):
        if interaction == "simplified":
            page.locator('[data-rotate="5"]').click()
        else:
            page.mouse.click(*point, button="right")


def _place_solution(page, state: dict, solution: dict[str, dict]) -> None:
    interaction = str((state.get("control_condition") or {}).get("interaction") or "full")
    stage = state["stage"]
    box = page.locator(".rube-canvas").bounding_box()
    if box is None:
        raise AssertionError("Rube flight canvas is missing")
    for bay in state["bays"]:
        candidate = solution[bay["id"]]
        tool_id = candidate["tool_id"]
        if interaction == "simplified":
            page.locator(f'.rube-tool[data-tool-id="{tool_id}"]').click()
            page.locator(f'[data-place-bay="{bay["id"]}"]').click()
        else:
            _place_full(page, tool_id, bay["anchor"], box, stage)
        _rotate_to(page, interaction, _screen(box, stage, bay["anchor"]), candidate["pose"][2])


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(mechanic)
    state = _read(state_dir / "public_state.json")
    interaction = str((state.get("control_condition") or {}).get("interaction") or "full")
    solution = _solution(state)
    if interaction == "full":
        _exercise_full_drop_rejections(page, state, out_dir, mechanic)
    _place_solution(page, state, solution)
    first = state["bays"][0]
    first_tool = solution[first["id"]]["tool_id"]
    page.locator(f'.rube-tool[data-tool-id="{first_tool}"]').click() if interaction == "simplified" else None
    box = page.locator(".rube-canvas").bounding_box()
    if box is None:
        raise AssertionError("Rube flight canvas is missing")
    replay = _grader()
    tool = next(item for item in state["tools"] if item["id"] == first_tool)
    failure_angle = 90.0
    visible_misses = []
    for candidate_angle in state["contract"]["allowed_angles_deg"]:
        candidate_pose = [float(first["anchor"][0]), float(first["anchor"][1]), float(candidate_angle)]
        candidate = replay.replay_lane(state, first, tool, candidate_pose)
        if not candidate["passed"] and candidate["miss_offset"] is not None:
            visible_misses.append((abs(float(candidate["miss_offset"])), float(candidate_angle)))
    if visible_misses:
        failure_angle = min(visible_misses)[1]
    current = float(solution[first["id"]]["pose"][2])
    turns = int(round(((failure_angle - current) % 180.0) / 5.0))
    for _ in range(turns):
        if interaction == "simplified":
            page.locator('[data-rotate="5"]').click()
        else:
            page.mouse.click(*_screen(box, state["stage"], first["anchor"]), button="right")
    page.locator(".rube-run").click()
    expect(page.locator(".rube-machine[data-outcome='fail']")).to_be_visible(timeout=10_000)
    expect(page.locator(".readout[data-status='error']")).to_be_visible()
    _shot(page, out_dir, mechanic, "physical-stall")
    page.locator(".rube-rewind").click()
    expect(page.locator(".rube-machine[data-outcome='edit']")).to_be_visible()
    expect(page.locator(".readout")).to_contain_text("REWOUND")
    _shot(page, out_dir, mechanic, "rewound-for-repair")
    before = str(state["challenge_id"])
    with page.expect_response(lambda response: response.url.endswith("/result")):
        page.locator(".rube-submit").click()
    _wait_new(state_dir, before)
    expect(page.locator(".rube-machine[data-fresh-failure='true']")).to_be_visible(timeout=8_000)
    expect(page.locator(".readout")).to_contain_text("FAIL")
    _shot(page, out_dir, mechanic, "failure-fresh-bench")
    page.wait_for_timeout(1200)


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(mechanic)
    state = _read(state_dir / "public_state.json")
    solution = _solution(state)
    _place_solution(page, state, solution)
    interaction = str((state.get("control_condition") or {}).get("interaction") or "full")
    if interaction == "full":
        _exercise_full_station_move(page, state, solution, out_dir, mechanic)
    _exercise_material_swap(page, state, solution, out_dir, mechanic)
    expect(page.locator(".rube-placed-count")).to_have_text(f"{len(state['bays'])}/{len(state['bays'])}")
    _shot(page, out_dir, mechanic, "deflectors-aimed")
    page.locator(".rube-run").click()
    page.wait_for_function("() => ['running','pass','fail'].includes(document.querySelector('.rube-machine')?.dataset.outcome)", timeout=5_000)
    page.wait_for_timeout(420)
    _shot(page, out_dir, mechanic, "rollout-live")
    page.wait_for_function("() => ['pass','fail'].includes(document.querySelector('.rube-machine')?.dataset.outcome)", timeout=14_000)
    outcome_state = page.locator(".rube-machine").get_attribute("data-outcome")
    if outcome_state != "pass":
        diagnostic = page.evaluate("() => ({mode:window.rubesLastPieceModel?.mode,releaseIndex:window.rubesLastPieceModel?.releaseIndex,tick:window.rubesLastPieceModel?.tick,placements:window.rubesLastPieceModel?.placements,balls:window.rubesLastPieceModel?.balls?.map(ball=>({x:ball.x,y:ball.y,vx:ball.vx,vy:ball.vy,tick:ball.tick,bounced:ball.bounced,crossing:ball.crossing}))})")
        raise AssertionError(f"physical Rube flight stalled: {diagnostic}")
    expect(page.locator(".readout")).to_contain_text("BELL RANG")
    physical = page.evaluate("() => ({releaseIndex:window.rubesLastPieceModel.releaseIndex,tick:window.rubesLastPieceModel.tick,bell:window.rubesLastPieceModel.bellRung,sequence:window.rubesLastPieceModel.lastSequence})")
    expected_sequence = state.get("expected_release_sequence") or [f"release:{bay['id']}" for bay in state["bays"]] + ["bell:ring"]
    if not physical["bell"] or physical["releaseIndex"] != len(state["bays"]) or physical["sequence"] != expected_sequence:
        raise AssertionError(f"physical Rube rollout incomplete: {physical}")
    _shot(page, out_dir, mechanic, "bell-rang-pre-certify")
    page.locator(".rube-submit").click()
    expect(page.locator(".rube-verdict")).to_be_visible(timeout=90_000)
    expect(page.locator(".readout")).to_have_text("PASS", timeout=8_000)
    _shot(page, out_dir, mechanic, "pass")
