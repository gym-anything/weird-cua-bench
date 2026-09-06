from __future__ import annotations

import json
import math
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "unwatched_wing"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, mechanic: str, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{mechanic}-{label}.png"), full_page=True)


def _interaction(page) -> str:
    return str(page.locator(".unwatched-wing").get_attribute("data-interaction") or "full")


def _pose(page) -> tuple[float, float, int]:
    value = page.evaluate("() => [window.unwatchedWingModel.pose.x, window.unwatchedWingModel.pose.y, window.unwatchedWingModel.pose.angle_mdeg]")
    return float(value[0]), float(value[1]), int(value[2])


def _angle_error(target: int, current: int) -> int:
    return int((target - current + 180_000) % 360_000 - 180_000)


def _drag_turn(page, delta_mdeg: int) -> None:
    canvas = page.locator("#uw-world")
    box = canvas.bounding_box()
    if not box:
        raise AssertionError("Unwatched Wing viewport is not visible")
    pixels = max(-115.0, min(115.0, delta_mdeg / 180.0))
    center_x = box["x"] + box["width"] / 2
    center_y = box["y"] + box["height"] / 2
    page.mouse.move(center_x, center_y)
    page.mouse.down()
    page.mouse.move(center_x + pixels, center_y, steps=max(2, round(abs(pixels) / 20)))
    page.mouse.up()


def _turn_to_angle(page, target_mdeg: int) -> None:
    target_mdeg %= 360_000
    for _ in range(40):
        current = _pose(page)[2]
        difference = _angle_error(target_mdeg, current)
        if abs(difference) <= 7_900:
            return
        if _interaction(page) == "full":
            _drag_turn(page, difference)
        else:
            selector = '[data-uw-turn="15000"]' if difference > 0 else '[data-uw-turn="-15000"]'
            page.locator(selector).click()
    raise AssertionError(f"viewport turn did not converge: target={target_mdeg} current={_pose(page)[2]}")


def _turn_to_point(page, point: list[float] | tuple[float, float]) -> None:
    x, y, _ = _pose(page)
    dx, dy = float(point[0]) - x, float(point[1]) - y
    if math.hypot(dx, dy) <= .04:
        return
    target = round(math.degrees(math.atan2(dy, dx)) * 1000) % 360_000
    _turn_to_angle(page, target)


def _step_forward(page) -> None:
    if _interaction(page) == "full":
        page.keyboard.press("w")
    else:
        page.locator('[data-uw-move="1,0"]').click()


def _step_backward(page) -> None:
    if _interaction(page) == "full":
        page.keyboard.press("s")
    else:
        page.locator('[data-uw-move="-1,0"]').click()


def _move_to(page, point: list[float] | tuple[float, float], tolerance: float = .25) -> None:
    target = float(point[0]), float(point[1])
    for _ in range(18):
        x, y, _ = _pose(page)
        remaining = math.dist((x, y), target)
        if remaining <= tolerance:
            return
        _turn_to_point(page, target)
        before = remaining
        _step_forward(page)
        x2, y2, _ = _pose(page)
        if math.dist((x2, y2), target) >= before - .02:
            raise AssertionError(f"museum route step stalled before {target}: pose={(x2, y2)}")
    raise AssertionError(f"museum route did not reach {target}: pose={_pose(page)[:2]}")


def _walk_route(page, route: list[list[float]], first_index: int, last_index: int) -> None:
    for index in range(first_index + 1, last_index + 1):
        _move_to(page, route[index])


def _walk_to_final_plinth(page, route: list[list[float]], first_index: int, last_index: int, final_point: list[float]) -> None:
    for index in range(first_index + 1, last_index + 1):
        if math.dist(tuple(map(float, route[index])), tuple(map(float, final_point))) <= .95:
            _set_lamp(page, True)
        _move_to(page, route[index])


def _press_tool(page, key: str, button: str) -> None:
    if _interaction(page) == "full":
        page.keyboard.press(key)
    else:
        page.locator(button).click()


def _cut_nearby_light(page) -> None:
    light_id = page.evaluate("() => { const lights = window.unwatchedWingModel.state.wall_lights; const on = window.unwatchedWingModel.lights; const pose = window.unwatchedWingModel.pose; const reach = window.unwatchedWingModel.state.controls.breaker_range; const candidates = lights.map((item) => ({id:item.id, d:Math.hypot(item.center[0]-pose.x,item.center[1]-pose.y)})).filter((item) => item.d <= reach && on[item.id]).sort((a,b)=>a.d-b.d); return candidates[0]?.id || null; }")
    if not light_id:
        return
    _press_tool(page, "e", "#uw-breaker")
    page.wait_for_function("id => window.unwatchedWingModel.lights[id] === false", arg=light_id)


def _deploy_probe(page, point: list[float]) -> None:
    x, y, _ = _pose(page)
    if math.dist((x, y), (float(point[0]), float(point[1]))) < .45:
        _step_backward(page)
    expected_id = page.evaluate(
        """point => window.unwatchedWingModel.state.plinths.find(
          item => Math.hypot(item.center[0] - point[0], item.center[1] - point[1]) < .01
        )?.id || null""",
        point,
    )
    if not expected_id:
        raise AssertionError(f"no plinth exists at probe target {point}")

    def fire() -> bool:
        if _interaction(page) == "full":
            canvas = page.locator("#uw-world")
            box = canvas.bounding_box()
            if not box:
                raise AssertionError("Unwatched Wing viewport is not visible")
            page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        else:
            page.locator("#uw-probe").click()
        page.wait_for_function("() => window.unwatchedWingModel.probePlinthId !== null")
        if page.evaluate("id => window.unwatchedWingModel.probePlinthId === id", expected_id):
            return True
        _recall(page)
        return False

    for offset in range(5):
        _turn_to_point(page, point)
        if fire():
            return
        if _interaction(page) == "simplified":
            x, y, angle = _pose(page)
            target_angle = round(math.degrees(math.atan2(float(point[1]) - y, float(point[0]) - x)) * 1000) % 360_000
            error = _angle_error(target_angle, angle)
            if abs(error) >= 6_900:
                turn = '[data-uw-turn="15000"]' if error > 0 else '[data-uw-turn="-15000"]'
                page.locator(turn).click()
                if fire():
                    return
                reverse = '[data-uw-turn="-15000"]' if error > 0 else '[data-uw-turn="15000"]'
                page.locator(reverse).click()
            if offset < 4:
                page.locator('[data-uw-move="0,-1"]').click()
        else:
            break
    raise AssertionError(f"visible probe controls could not select {expected_id} at {point}")


def _set_viewer(page, open_value: bool) -> None:
    current = bool(page.evaluate("() => window.unwatchedWingModel.viewerOpen"))
    if current != open_value:
        _press_tool(page, "v", "#uw-viewer")
    page.wait_for_function("value => window.unwatchedWingModel.viewerOpen === value", arg=open_value)


def _assert_probe_feed_visible(page) -> None:
    surface = page.evaluate(
        """() => {
          const view = document.querySelector('.uw-probe-view');
          const feed = document.querySelector('#uw-probe-feed');
          const style = getComputedStyle(view);
          const pixels = feed.getContext('2d').getImageData(0, 0, feed.width, feed.height).data;
          let coloredPixels = 0;
          for (let index = 0; index < pixels.length; index += 4) {
            if (pixels[index] > 35 || pixels[index + 1] > 45 || pixels[index + 2] > 45) coloredPixels += 1;
          }
          return {
            viewer_open: window.unwatchedWingModel.viewerOpen,
            probe_plinth_id: window.unwatchedWingModel.probePlinthId,
            opacity: style.opacity,
            visibility: style.visibility,
            transform: style.transform,
            animations: view.getAnimations({subtree: true}).length,
            colored_pixels: coloredPixels,
          };
        }"""
    )
    if not (
        surface["viewer_open"] is True
        and surface["probe_plinth_id"]
        and surface["opacity"] == "1"
        and surface["visibility"] == "visible"
        and surface["transform"] == "none"
        and surface["animations"] == 0
        and int(surface["colored_pixels"]) >= 100
    ):
        raise AssertionError(f"opened probe is absent from the visible frame: {surface}")


def _set_lamp(page, enabled: bool) -> None:
    current = bool(page.evaluate("() => window.unwatchedWingModel.lampOn"))
    if current != enabled:
        _press_tool(page, "f", "#uw-lamp")
    page.wait_for_function("value => window.unwatchedWingModel.lampOn === value", arg=enabled)


def _recall(page) -> None:
    if page.evaluate("() => window.unwatchedWingModel.probePlinthId !== null"):
        _press_tool(page, "r", "#uw-recall")
    page.wait_for_function("() => window.unwatchedWingModel.probePlinthId === null")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    expect(page.locator(".unwatched-wing")).to_be_visible(timeout=6_000)
    page.locator("#uw-abandon").click()
    expect(page.locator(".uw-verdict.is-fail")).to_be_visible(timeout=7_000)
    deadline = time.time() + 7
    while time.time() < deadline:
        if str(_read(state_dir / "ground_truth.json")["challenge_id"]) != before:
            break
        time.sleep(.05)
    else:
        raise AssertionError("aborted museum did not issue a fresh challenge")
    _shot(page, out_dir, mechanic, "failure-fresh-wing")
    _step_forward(page)
    expect(page.locator(".uw-verdict.is-fail")).to_be_hidden(timeout=3_000)


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    expect(page.locator(".unwatched-wing")).to_be_visible(timeout=7_000)
    truth = _read(state_dir / "ground_truth.json")
    route = [[float(value) for value in point] for point in truth["solution"]["route_points"]]
    target_indices = [int(value) for value in truth["solution"]["target_route_indices"]]
    path = list(truth["target_path"])
    required = set(map(int, truth["required_pin_steps"]))
    ambient_plinths = {str(item["plinth_id"]) for item in truth["wall_lights"]}
    if len(target_indices) != len(path) or target_indices != sorted(target_indices):
        raise AssertionError("hidden museum route violates its ordered-plinth contract")

    _shot(page, out_dir, mechanic, "initial-consignment")
    route_cursor = 0
    _walk_route(page, route, route_cursor, target_indices[0])
    route_cursor = target_indices[0]

    for step in range(len(path) - 1):
        if path[step] in ambient_plinths:
            _cut_nearby_light(page)
        before_cursor = int(page.evaluate("() => window.unwatchedWingModel.targetCursor"))
        if before_cursor != step:
            raise AssertionError(f"target path diverged before step {step}: cursor={before_cursor}")
        if step in required:
            _deploy_probe(page, truth["plinths"][step]["center"])
            _set_viewer(page, True)
            _assert_probe_feed_visible(page)
            _set_lamp(page, False)
            _walk_route(page, route, route_cursor, target_indices[step + 1])
            route_cursor = target_indices[step + 1]
            if step == min(required):
                _shot(page, out_dir, mechanic, "probe-held-blind-turn")
            old = truth["plinths"][step]["center"]
            x, y, _ = _pose(page)
            away = round(math.degrees(math.atan2(y - float(old[1]), x - float(old[0]))) * 1000) % 360_000
            _turn_to_angle(page, away)
            try:
                page.wait_for_function("step => window.unwatchedWingModel.pinReady.has(step)", arg=step)
            except Exception as error:
                snapshot = page.evaluate(
                    """step => {
                      const model = window.unwatchedWingModel;
                      const next = model.state.plinths[step + 1].center;
                      return {
                        step,
                        pose: {...model.pose},
                        target_cursor: model.targetCursor,
                        probe_plinth_id: model.probePlinthId,
                        expected_probe_plinth_id: model.state.target_path[step],
                        lamp_on: model.lampOn,
                        viewer_open: model.viewerOpen,
                        observation: window.unwatchedWingPublicMath.targetObservation(),
                        distance_to_release: Math.hypot(next[0] - model.pose.x, next[1] - model.pose.y),
                        pin_ready_steps: [...model.pinReady],
                      };
                    }""",
                    step,
                )
                raise AssertionError(f"probe handoff did not arm: {snapshot}") from error
            _set_viewer(page, False)
            page.wait_for_function("next => window.unwatchedWingModel.targetCursor === next", arg=step + 1)
            _recall(page)
            _set_lamp(page, True)
        else:
            _set_lamp(page, False)
            if step == 0:
                _shot(page, out_dir, mechanic, "hand-lamp-off-jump")
            page.wait_for_function("next => window.unwatchedWingModel.targetCursor === next", arg=step + 1)
            if step + 1 == len(path) - 1:
                _walk_to_final_plinth(
                    page,
                    route,
                    route_cursor,
                    target_indices[step + 1],
                    truth["plinths"][step + 1]["center"],
                )
            else:
                _walk_route(page, route, route_cursor, target_indices[step + 1])
            route_cursor = target_indices[step + 1]
            # Leave the frame dark while approaching the new plinth.  The
            # exhibit cannot re-arm and bounce during a cornering movement
            # until the hand lamp deliberately observes it at the destination.
            _set_lamp(page, True)
        if step == 0:
            _shot(page, out_dir, mechanic, "first-unwatched-jump")

    if path[-1] in ambient_plinths:
        _cut_nearby_light(page)
    _set_viewer(page, False)
    _recall(page)
    final_point = next(
        item["center"] for item in truth["plinths"] if str(item["id"]) == str(path[-1])
    )
    _set_lamp(page, True)
    _move_to(page, final_point, tolerance=.28)
    # Establish a deliberate visible observation at the final pedestal. The
    # target can arrive on the last walking input and remain disarmed until a
    # subsequent input settles the new current plinth.
    if _interaction(page) == "full":
        _drag_turn(page, 9_000)
    else:
        page.locator('[data-uw-turn="15000"]').click()
    _turn_to_angle(page, (_pose(page)[2] + 180_000) % 360_000)
    _set_lamp(page, False)
    # If the lamp was already off at the exact arrival boundary, _set_lamp is
    # intentionally a no-op and therefore does not create the final settle
    # edge. A small ordinary look supplies that physical action while keeping
    # the authored dark/equipment state unchanged.
    if not page.evaluate("() => window.unwatchedWingModel.entangled === true"):
        if _interaction(page) == "full":
            _drag_turn(page, 9_000)
        else:
            page.locator('[data-uw-turn="15000"]').click()
    try:
        page.wait_for_function("() => window.unwatchedWingModel.entangled === true", timeout=3_000)
    except Exception as error:
        snapshot = page.evaluate(
            """() => {
                      const model = window.unwatchedWingModel;
                      const currentId = model.state.target_path[model.targetCursor];
                      const current = model.state.plinths.find(item => item.id === currentId)?.center || null;
                      const finalId = model.state.target_path[model.state.target_path.length - 1];
                      const final = model.state.plinths.find(item => item.id === finalId)?.center || null;
                      return {
                        pose: {...model.pose},
                        target_cursor: model.targetCursor,
                        target_path_length: model.state.target_path.length,
                        target_armed: model.targetArmed,
                        current_target_id: currentId,
                        current_target: current,
                        final_target_id: finalId,
                        final_target: final,
                        distance_to_current: current ? Math.hypot(current[0] - model.pose.x, current[1] - model.pose.y) : null,
                        distance_to_final: final ? Math.hypot(final[0] - model.pose.x, final[1] - model.pose.y) : null,
                        entangle_radius: model.state.controls.entangle_radius,
                        entangled: model.entangled,
                        dock_occupied: model.dockOccupied,
                        submitting: model.submitting,
                        terminal: model.terminal,
                        force_reveal: model.forceReveal,
                        lamp_on: model.lampOn,
                        viewer_open: model.viewerOpen,
                        probe_plinth_id: model.probePlinthId,
                lights: {...model.lights},
                observation: window.unwatchedWingPublicMath.targetObservation(),
              };
            }"""
        )
        raise AssertionError(f"final darkness did not entangle: {snapshot}") from error
    expect(page.locator(".uw-verdict.is-pass")).to_be_visible(timeout=8_000)
    expect(page.locator(".uw-foot .readout")).to_have_attribute("data-status", "passed")
    _shot(page, out_dir, mechanic, "dock-00-pass")
