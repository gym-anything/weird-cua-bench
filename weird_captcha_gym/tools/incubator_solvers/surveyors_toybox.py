from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "surveyors_toybox"
VIEWS = ("overhead", "front", "side")


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, mechanic: str, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{mechanic}-{name}.png"), full_page=False)


def _wait_new(state_dir: Path, before: str) -> None:
    deadline = time.time() + 8
    while time.time() < deadline:
        if str(_read(state_dir / "ground_truth.json").get("challenge_id")) != before:
            return
        time.sleep(0.05)
    raise AssertionError("Surveyor's Toybox challenge did not regenerate")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(mechanic)
    before = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    page.locator(".survey-submit").click()
    _wait_new(state_dir, before)
    expect(page.locator(".survey-captcha[data-fresh-failure='true']")).to_be_visible(timeout=8_000)
    expect(page.locator(".readout")).to_contain_text("FAIL")
    _shot(page, out_dir, mechanic, "fail-fresh-depot")


def _interaction(page) -> str:
    return str(page.locator(".survey-captcha").get_attribute("data-interaction") or "full")


def _current_box(page, target_id: str) -> dict:
    return page.evaluate("targetId => window.surveyorsToyboxModel.annotations[targetId]", target_id)


def _proxy_adjust(page, field: str, difference: float) -> None:
    step = {"cx": 0.1, "cy": 0.1, "cz": 0.1, "hx": 0.05, "hy": 0.05, "hz": 0.05, "yaw": 5.0}[field]
    tolerance = max(0.03 if field != "yaw" else 2.0, step / 2)
    if abs(difference) <= tolerance:
        return
    selector = ".survey-proxy button[data-field='%s'][data-delta='%s']"
    direction = 1 if difference > 0 else -1
    for _ in range(80):
        if abs(difference) <= tolerance:
            return
        page.locator(selector % (field, f"{direction * step:g}")).click()
        difference -= direction * step
    raise AssertionError(f"proxy adjustment did not settle for {field}: {difference}")


def _proxy_fit(page, truth: dict, target_id: str) -> None:
    page.locator(f".survey-target[data-target-id='{target_id}']").click()
    actual = _current_box(page, target_id)
    expected = truth["target_boxes"][target_id]
    for field, index in (("cx", 0), ("cy", 1), ("cz", 2)):
        _proxy_adjust(page, field, float(expected["center"][index]) - float(actual["center"][index]))
    for field, index in (("hx", 0), ("hy", 1), ("hz", 2)):
        _proxy_adjust(page, field, float(expected["half"][index]) - float(actual["half"][index]))
    _proxy_adjust(page, "yaw", float(expected["yaw"]) - float(actual["yaw"]))


def _screen_point(box: dict, source: list[float], source_width: float = 520, source_height: float = 380) -> tuple[float, float]:
    return (
        box["x"] + source[0] / source_width * box["width"],
        box["y"] + source[1] / source_height * box["height"],
    )


def _drag_handle(page, target_id: str, handle: str, destination: tuple[float, float]) -> None:
    canvas = page.locator(".survey-cloud")
    box = canvas.bounding_box()
    if not box:
        raise AssertionError("missing Surveyor's Toybox point-cloud canvas")
    handles = page.evaluate("targetId => window.surveyorsToyboxModel.cloudHandles(targetId)", target_id)
    start = _screen_point(box, handles[handle])
    page.mouse.move(*start)
    page.mouse.down()
    page.mouse.move(*_screen_point(box, [destination[0], destination[1]]), steps=8)
    page.mouse.up()
    page.wait_for_timeout(25)


def _direct_fit(page, truth: dict, target_id: str) -> None:
    page.locator(f".survey-target[data-target-id='{target_id}']").click()
    expected = truth["target_boxes"][target_id]
    for _ in range(2):
        actual = _current_box(page, target_id)
        dx = (float(expected["center"][0]) - float(actual["center"][0])) * 52
        dy = -(float(expected["center"][2]) - float(actual["center"][2])) * 42
        if abs(dx) > 1 or abs(dy) > 1:
            handles = page.evaluate("targetId => window.surveyorsToyboxModel.cloudHandles(targetId)", target_id)
            _drag_handle(page, target_id, "center", (handles["center"][0] + dx, handles["center"][1] + dy))
    actual = _current_box(page, target_id)
    dy = -(float(expected["center"][1]) - float(actual["center"][1])) * 42
    if abs(dy) > 1:
        handles = page.evaluate("targetId => window.surveyorsToyboxModel.cloudHandles(targetId)", target_id)
        _drag_handle(page, target_id, "cy", (handles["cy"][0], handles["cy"][1] + dy))
    for field, handle, index in (("hx", "hx", 0), ("hy", "hy", 1), ("hz", "hz", 2)):
        actual = _current_box(page, target_id)
        delta = float(expected["half"][index]) - float(actual["half"][index])
        if abs(delta) > 0.01:
            handles = page.evaluate("targetId => window.surveyorsToyboxModel.cloudHandles(targetId)", target_id)
            if field == "hy": destination = (handles[handle][0], handles[handle][1] - delta * 80)
            else: destination = (handles[handle][0] + delta * 80, handles[handle][1])
            _drag_handle(page, target_id, handle, destination)
    actual = _current_box(page, target_id)
    delta_yaw = float(expected["yaw"]) - float(actual["yaw"])
    if abs(delta_yaw) > 0.2:
        handles = page.evaluate("targetId => window.surveyorsToyboxModel.cloudHandles(targetId)", target_id)
        _drag_handle(page, target_id, "yaw", (handles["yaw"][0] + delta_yaw * 2, handles["yaw"][1]))


def _link_all(page, truth: dict) -> None:
    interaction = _interaction(page)
    for frame in range(int(truth["requirements"]["frame_count"])):
        page.locator(f".survey-frame[data-frame='{frame}']").click()
        for target_id in truth["target_ids"]:
            page.locator(f".survey-target[data-target-id='{target_id}']").click()
            for view in VIEWS:
                mark_id = truth["expected_links"][f"{frame}:{view}:{target_id}"]
                if interaction == "simplified":
                    page.locator(f".survey-mark-choice[data-view='{view}'][data-mark-id='{mark_id}']").click()
                else:
                    mark = next(
                        item for item in truth["camera_frames"][frame]["views"][view]["marks"] if item["id"] == mark_id
                    )
                    canvas = page.locator(f".survey-camera[data-view='{view}']")
                    box = canvas.bounding_box()
                    if not box:
                        raise AssertionError(f"missing {view} camera canvas")
                    rect = mark["rect"]
                    page.mouse.click(*_screen_point(box, [rect["x"] + rect["w"] / 2, rect["y"] + rect["h"] / 2], 340, 230))
                page.locator(".survey-link-button").click()


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(mechanic)
    truth = _read(state_dir / "ground_truth.json")
    # Exercise the visible pan/zoom controls while returning to the initial
    # view, so the clean film demonstrates the complete navigation surface.
    for action in ("zoom-in", "pan-right", "pan-left", "zoom-out"):
        page.locator(f".survey-view-tool[data-view-action='{action}']").click()
    if _interaction(page) == "full":
        cloud = page.locator(".survey-cloud")
        bounds = cloud.bounding_box()
        if not bounds:
            raise AssertionError("missing Surveyor's Toybox point-cloud canvas")
        page.keyboard.down("Shift")
        page.mouse.move(bounds["x"] + 26, bounds["y"] + 26)
        page.mouse.down()
        page.mouse.move(bounds["x"] + 46, bounds["y"] + 38, steps=4)
        page.mouse.up()
        page.keyboard.up("Shift")
        cloud.hover()
        page.mouse.wheel(0, -100)
        page.mouse.wheel(0, 100)
    if _interaction(page) == "simplified":
        for target_id in truth["target_ids"]:
            _proxy_fit(page, truth, target_id)
    else:
        for target_id in truth["target_ids"]:
            _direct_fit(page, truth, target_id)
            _shot(page, out_dir, mechanic, f"fitted-{target_id}")
    _shot(page, out_dir, mechanic, "cross-view-fit-before-links")
    _link_all(page, truth)
    expect(page.locator(".survey-links")).to_have_text(
        f"{truth['requirements']['required_links']}/{truth['requirements']['required_links']}"
    )
    _shot(page, out_dir, mechanic, "all-synchronized-links")
    page.locator(".survey-submit").click()
    expect(page.locator(".readout")).to_have_text("PASS", timeout=8_000)
    expect(page.locator(".survey-verdict")).to_be_visible(timeout=8_000)
    _shot(page, out_dir, mechanic, "pass-verdict")
