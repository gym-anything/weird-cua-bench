from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "fake_desktop_automation_inversion"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _screenshot(page, out_dir: Path, mechanic: str, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{mechanic}-{label}.png"), full_page=True)


def _wait_for_new_challenge(state_dir: Path, previous: str) -> str:
    deadline = time.time() + 8
    while time.time() < deadline:
        current = str(_read_json(state_dir / "ground_truth.json").get("challenge_id") or "")
        if current and current != previous:
            return current
        time.sleep(0.05)
    raise AssertionError("automation-inversion desktop did not regenerate after failure")


def _physical_for_remote(remote: tuple[float, float], mapping: str, width: float, height: float) -> tuple[float, float]:
    x, y = remote
    if mapping == "mirror_x":
        return width - x, y
    if mapping == "mirror_y":
        return x, height - y
    if mapping == "rotate_180":
        return width - x, height - y
    return x, y


def _screen_point(desktop_box: dict, remote: tuple[float, float], mapping: str, width: float, height: float) -> tuple[float, float]:
    physical = _physical_for_remote(remote, mapping, width, height)
    return (
        desktop_box["x"] + physical[0] / width * desktop_box["width"],
        desktop_box["y"] + physical[1] / height * desktop_box["height"],
    )


def _click_remote(page, desktop_box: dict, remote: tuple[float, float], mapping: str, width: float, height: float) -> None:
    x, y = _screen_point(desktop_box, remote, mapping, width, height)
    page.mouse.click(x, y)


def _drag_remote(
    page,
    desktop_box: dict,
    start: tuple[float, float],
    end: tuple[float, float],
    mapping: str,
    width: float,
    height: float,
    *,
    steps: int = 10,
) -> None:
    start_x, start_y = _screen_point(desktop_box, start, mapping, width, height)
    end_x, end_y = _screen_point(desktop_box, end, mapping, width, height)
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(end_x, end_y, steps=steps)
    page.mouse.up()


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read_json(state_dir / "ground_truth.json")
    before = str(truth["challenge_id"])
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    if interaction == "simplified":
        target_ids = {str(item) for item in truth["target_file_ids"]}
        decoy = next(item for item in truth["files"] if str(item["id"]) not in target_ids)
        page.locator("[data-fd-proxy='close_interceptor']").click()
        page.locator(f"[data-fd-proxy-file-id='{decoy['id']}']").click()
        _screenshot(page, out_dir, mechanic, "wrong-file-selected")
        page.locator("[data-fd-proxy='transfer_selected']").click()
    page.locator(".fd-submit").click()
    _wait_for_new_challenge(state_dir, before)
    expect(page.locator(".fake-desktop-captcha[data-fresh-failure='true']")).to_be_visible(timeout=8_000)
    expect(page.locator(".readout")).to_contain_text("FAIL")
    _screenshot(page, out_dir, mechanic, "fail-refresh")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read_json(state_dir / "ground_truth.json")
    desktop_box = page.locator(".fd-desktop").bounding_box()
    if not desktop_box:
        raise AssertionError("transformed desktop is not visible")
    width = float(truth["desktop"]["width"])
    height = float(truth["desktop"]["height"])
    mappings = [str(item) for item in truth["mapping_sequence"]]
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    windows = {item["id"]: dict(item) for item in truth["initial_windows"]}
    geometry = truth["geometry"]
    required_moved = set(str(item) for item in truth["required_moved_window_ids"])

    if interaction == "simplified":
        page.locator("[data-fd-proxy='close_interceptor']").click()
        if "vault" in required_moved:
            page.locator("[data-fd-proxy='move_vault']").click()
        _screenshot(page, out_dir, mechanic, "active-window-reorder")
        for index, target in enumerate(truth["target_file_ids"]):
            page.locator(f"[data-fd-proxy-file-id='{target}']").click()
            if index == 0:
                _screenshot(page, out_dir, mechanic, "active-file-selection")
            page.locator("[data-fd-proxy='transfer_selected']").click()
            page.wait_for_timeout(80)
            if index == 0:
                _screenshot(page, out_dir, mechanic, "active-workflow-remap")
                if "verifier" in required_moved:
                    page.locator("[data-fd-proxy='move_verifier']").click()
            if index == 1:
                _screenshot(page, out_dir, mechanic, "active-second-transfer-remap")
            if len(truth["target_file_ids"]) >= 4 and index == len(truth["target_file_ids"]) - 2:
                _screenshot(page, out_dir, mechanic, "active-fourth-channel")
            if len(truth["target_file_ids"]) >= 4 and index == len(truth["target_file_ids"]) - 1:
                _screenshot(page, out_dir, mechanic, "active-final-remap")
        page.locator("[data-fd-proxy='arm_manual_control']").click()
    else:
        blocker = windows[truth["required_blocker_id"]]
        close_remote = (
            blocker["x"] + blocker["width"] - geometry["close_width"] / 2,
            blocker["y"] + geometry["title_height"] / 2,
        )
        _click_remote(page, desktop_box, close_remote, mappings[0], width, height)
        page.wait_for_timeout(90)

        vault = windows["vault"]
        if "vault" in required_moved:
            title_start = (vault["x"] + 42, vault["y"] + geometry["title_height"] / 2)
            title_end = (title_start[0] + 70, title_start[1] - 20)
            _drag_remote(page, desktop_box, title_start, title_end, mappings[0], width, height, steps=8)
            vault["x"] += 70
            vault["y"] -= 20
        page.wait_for_timeout(90)
        _screenshot(page, out_dir, mechanic, "active-window-reorder")

        target_files = [next(item for item in truth["files"] if item["id"] == target_id) for target_id in truth["target_file_ids"]]
        file_width, file_height = geometry["file_size"]
        verifier = windows["verifier"]
        drop = geometry["drop_zone"]
        gap_x, gap_y = geometry["file_gap"]
        columns = int(geometry["file_columns"])

        def file_remote(file_item: dict) -> tuple[float, float]:
            column, row = int(file_item["slot"]) % columns, int(file_item["slot"]) // columns
            return (
                vault["x"] + geometry["file_origin"][0] + column * (file_width + gap_x) + file_width / 2,
                vault["y"] + geometry["file_origin"][1] + row * (file_height + gap_y) + file_height / 2,
            )

        for index, target_file in enumerate(target_files):
            drop_remote = (verifier["x"] + drop[0] + drop[2] / 2, verifier["y"] + drop[1] + drop[3] / 2)
            _drag_remote(page, desktop_box, file_remote(target_file), drop_remote, mappings[index], width, height, steps=12 + index)
            page.wait_for_timeout(140)
            expect(page.locator(".fd-mapping-badge")).to_contain_text(f"CHANNEL {index + 2}/{len(mappings)}")
            if index == 0:
                _screenshot(page, out_dir, mechanic, "active-workflow-remap")
                if "verifier" in required_moved:
                    verifier_title_start = (verifier["x"] + verifier["width"] - 86, verifier["y"] + geometry["title_height"] / 2)
                    verifier_title_end = (verifier_title_start[0] - 55, verifier_title_start[1] + 28)
                    _drag_remote(page, desktop_box, verifier_title_start, verifier_title_end, mappings[index + 1], width, height, steps=9)
                    verifier["x"] -= 55
                    verifier["y"] += 28
            if index == 1:
                _screenshot(page, out_dir, mechanic, "active-second-transfer-remap")
            if len(target_files) >= 4 and index == len(target_files) - 2:
                _screenshot(page, out_dir, mechanic, "active-fourth-channel")
            if len(target_files) >= 4 and index == len(target_files) - 1:
                _screenshot(page, out_dir, mechanic, "active-final-remap")

        arm = geometry["arm_control"]
        arm_remote = (verifier["x"] + arm[0] + arm[2] / 2, verifier["y"] + arm[1] + arm[3] / 2)
        _click_remote(page, desktop_box, arm_remote, mappings[-1], width, height)
        page.wait_for_timeout(100)

    expect(page.locator(".fd-arm-control.is-armed")).to_be_visible()
    state = page.evaluate("""() => ({
        boundary: window.fakeDesktopInversionModel.boundary,
        loaded: [...window.fakeDesktopInversionModel.loadedFileIds],
        armed: window.fakeDesktopInversionModel.armed,
        move_count: window.fakeDesktopInversionModel.moveCount,
        closed: window.fakeDesktopInversionModel.closedCount,
        z: window.fakeDesktopInversionModel.zOrderChanges,
        moved_ids: [...window.fakeDesktopInversionModel.movedWindowIds].sort(),
    })""")
    if not (
        state["boundary"] == len(truth["target_file_ids"])
        and state["loaded"] == truth["target_file_ids"]
        and state["armed"] is True
        and state["move_count"] >= len(required_moved)
        and state["closed"] >= 1
        and state["z"] >= len(required_moved)
        and set(state["moved_ids"]) >= required_moved
    ):
        raise AssertionError(f"automation-inversion physical workflow ended in unexpected state: {state}")
    _screenshot(page, out_dir, mechanic, "solved")
    page.locator(".fd-submit").click()
    expect(page.locator(".readout")).to_have_text("PASS", timeout=8_000)
