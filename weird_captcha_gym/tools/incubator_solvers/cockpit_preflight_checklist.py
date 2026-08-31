from __future__ import annotations

import io
import json
import math
import re
from pathlib import Path

from PIL import Image


MECHANIC_ID = "cockpit_preflight_checklist"


def _state(state_dir: Path) -> dict:
    return json.loads((state_dir / "public_state.json").read_text(encoding="utf-8"))


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    del state_dir, out_dir
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    page.locator("#cpf-certify").click()
    page.locator('.cpf-verdict.is-fail').wait_for(state="visible")


def _full_range(page, item: dict, value: int, panel: dict | None = None) -> int:
    rail = page.locator(f'[data-range-rail="{item["id"]}"]')
    box = rail.bounding_box()
    if box is None:
        raise AssertionError(f"missing range rail {item['id']}")
    thumb = "low" if value == item["target_low"] else "high"
    start_fraction = (item[thumb] - item["minimum"]) / (item["maximum"] - item["minimum"])
    target_fraction = (value - item["minimum"]) / (item["maximum"] - item["minimum"])
    y = box["y"] + box["height"] / 2
    page.mouse.move(box["x"] + box["width"] * start_fraction, y)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] * target_fraction, y, steps=4)
    page.mouse.up()
    if thumb == "low":
        paired = next((
            coupling for coupling in (panel or {}).get("couplings", [])
            if coupling["source"] == {"id": item["id"], "field": thumb} and coupling["target"]["id"] == item["id"]
        ), None)
        if paired:
            predicted_high = item["high"] + ((value - item[thumb]) // item["step"]) * item["step"] * paired["ratio"]
            predicted_high = max(item["minimum"], min(item["maximum"], predicted_high))
            return min(value, predicted_high - item["step"])
        return min(value, item["high"] - item["step"])
    return max(value, item["low"] + item["step"])


def _full_dial(page, item: dict) -> None:
    node = page.locator(f'[data-dial="{item["id"]}"]')
    box = node.bounding_box()
    if box is None:
        raise AssertionError(f"missing dial {item['id']}")
    start_fraction = (item["value"] - item["minimum"]) / (item["maximum"] - item["minimum"])
    target_fraction = (item["target"] - item["minimum"]) / (item["maximum"] - item["minimum"])
    start_angle = math.radians(-150 + start_fraction * 300 - 90)
    target_angle = math.radians(-150 + target_fraction * 300 - 90)
    radius = min(box["width"], box["height"]) * .39
    center_x, center_y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(center_x + math.cos(start_angle) * radius, center_y + math.sin(start_angle) * radius)
    page.mouse.down()
    page.mouse.move(center_x + math.cos(target_angle) * radius, center_y + math.sin(target_angle) * radius, steps=5)
    page.mouse.up()


def _click_steps(page, selector: str, count: int) -> None:
    for _ in range(count):
        page.locator(selector).click()


def _item(panel: dict, item_id: str) -> dict:
    for item in panel["ranges"] + panel["dials"]:
        if item["id"] == item_id:
            return item
    raise KeyError(item_id)


def _apply_couplings(panel: dict, source: dict, field: str, before: int, after: int) -> None:
    source_steps = (after - before) // source["step"]
    for coupling in panel.get("couplings") or []:
        if coupling["source"] != {"id": source["id"], "field": field}:
            continue
        target = _item(panel, coupling["target"]["id"])
        target_field = coupling["target"]["field"]
        value = target[target_field] + source_steps * target["step"] * coupling["ratio"]
        value = max(target["minimum"], min(target["maximum"], value))
        if target_field == "low":
            value = min(value, target["high"] - target["step"])
        elif target_field == "high":
            value = max(value, target["low"] + target["step"])
        target[target_field] = value


def _commit_local(panel: dict, item: dict, field: str, after: int) -> None:
    before = item[field]
    item[field] = after
    _apply_couplings(panel, item, field, before, after)


def _feeds_locked_target(panel: dict, item: dict, field: str) -> bool:
    return any(coupling["source"] == {"id": item["id"], "field": field} for coupling in panel.get("couplings") or [])


def _detour(panel: dict, item: dict, field: str) -> int:
    value = item[field]
    candidates = (value + item["step"], value - item["step"])
    for candidate in candidates:
        if not item["minimum"] <= candidate <= item["maximum"]:
            continue
        if field in {"low", "high"}:
            paired = next((
                coupling for coupling in panel.get("couplings") or []
                if coupling["source"] == {"id": item["id"], "field": field}
                and coupling["target"]["id"] == item["id"]
            ), None)
            other_field = "high" if field == "low" else "low"
            predicted_other = item[other_field]
            if paired:
                predicted_other += ((candidate - value) // item["step"]) * item["step"] * paired["ratio"]
                predicted_other = max(item["minimum"], min(item["maximum"], predicted_other))
            if field == "low" and candidate > predicted_other - item["step"]:
                continue
            if field == "high" and candidate < predicted_other + item["step"]:
                continue
        return candidate
    raise AssertionError(f"no reversible calibration detour for {item['id']}:{field}")


def _visible_integer(locator) -> int:
    text = locator.inner_text().strip()
    if "BUS LOCK" in text.upper():
        raise AssertionError(f"target is still visibly sealed: {text!r}")
    match = re.search(r"\d+", text)
    if match is None:
        raise AssertionError(f"no visible integer in {text!r}")
    return int(match.group())


def _visible_range_values(page, range_index: int) -> tuple[int, int]:
    unit = page.locator(".cpf-range-unit").nth(range_index)
    rail_box = unit.locator(".cpf-range-rail").bounding_box()
    low_box = unit.locator(".cpf-thumb-low").bounding_box()
    high_box = unit.locator(".cpf-thumb-high").bounding_box()
    if rail_box is None or low_box is None or high_box is None:
        raise AssertionError(f"range {range_index} is not visibly measurable")

    def value(box: dict) -> int:
        center = box["x"] + box["width"] / 2
        fraction = max(0.0, min(1.0, (center - rail_box["x"]) / rail_box["width"]))
        return round(fraction * 20) * 5

    return value(low_box), value(high_box)


def _visible_dial_value(page, dial_index: int) -> int:
    dial = page.locator(".cpf-dial-unit").nth(dial_index).locator(".cpf-dial")
    image = Image.open(io.BytesIO(dial.screenshot())).convert("RGB")
    center_x = (image.width - 1) / 2
    center_y = (image.height - 1) / 2
    pointer_pixels = []
    for y in range(image.height):
        for x in range(image.width):
            red, green, blue = image.getpixel((x, y))
            radius = math.hypot(x - center_x, y - center_y)
            if image.width * .20 < radius < image.width * .46 and red > 120 and green > 70 and red > green * 1.05 and green > blue * 1.15:
                pointer_pixels.append((x, y, red + green - blue))
    if len(pointer_pixels) < 10:
        raise AssertionError(f"dial {dial_index} has no visible amber pointer pixels")
    dx = sum((x - center_x) * weight for x, _y, weight in pointer_pixels)
    dy = sum((y - center_y) * weight for _x, y, weight in pointer_pixels)
    angle = math.degrees(math.atan2(dx, -dy))
    fraction = max(0.0, min(1.0, (angle + 150) / 300))
    return round(fraction * 11)


def _visible_range_target(page, range_index: int, thumb: str) -> int:
    line = page.locator(".cpf-checklist ul").nth(0).locator("li").nth(range_index)
    target = line.locator("strong").locator("b, em").nth(0 if thumb == "low" else 1)
    return _visible_integer(target)


def _visible_dial_target(page, dial_index: int) -> int:
    line = page.locator(".cpf-checklist ul").nth(1).locator("li").nth(dial_index)
    return _visible_integer(line.locator("b, em"))


def _visible_target_is_locked(page, channel_index: int, range_count: int) -> bool:
    if channel_index < range_count * 2:
        range_index, thumb_index = divmod(channel_index, 2)
        line = page.locator(".cpf-checklist ul").nth(0).locator("li").nth(range_index)
        text = line.locator("strong").locator("b, em").nth(thumb_index).inner_text()
    else:
        dial_index = channel_index - range_count * 2
        line = page.locator(".cpf-checklist ul").nth(1).locator("li").nth(dial_index)
        text = line.locator("b, em").inner_text()
    return "BUS LOCK" in text.upper()


def _visible_full_range(page, range_index: int, thumb: str, target: int) -> None:
    unit = page.locator(".cpf-range-unit").nth(range_index)
    rail = unit.locator(".cpf-range-rail")
    rail_box = rail.bounding_box()
    thumb_box = unit.locator(f".cpf-thumb-{thumb}").bounding_box()
    if rail_box is None or thumb_box is None:
        raise AssertionError(f"range {range_index}:{thumb} is not visibly operable")
    start_x = thumb_box["x"] + thumb_box["width"] / 2
    target_x = rail_box["x"] + rail_box["width"] * (target / 100)
    y = rail_box["y"] + rail_box["height"] / 2
    page.mouse.move(start_x, y)
    page.mouse.down()
    page.mouse.move(target_x, y, steps=5)
    page.mouse.up()


def _visible_full_dial(page, dial_index: int, current: int, target: int) -> None:
    dial = page.locator(".cpf-dial-unit").nth(dial_index).locator(".cpf-dial")
    box = dial.bounding_box()
    if box is None:
        raise AssertionError(f"dial {dial_index} is not visibly operable")
    center_x = box["x"] + box["width"] / 2
    center_y = box["y"] + box["height"] / 2
    radius = min(box["width"], box["height"]) * .39

    def point(value: int) -> tuple[float, float]:
        angle = math.radians(-150 + value / 11 * 300 - 90)
        return center_x + math.cos(angle) * radius, center_y + math.sin(angle) * radius

    page.mouse.move(*point(current))
    page.mouse.down()
    page.mouse.move(*point(target), steps=5)
    page.mouse.up()


def _visible_move_range(page, interaction: str, range_index: int, thumb: str, target: int) -> None:
    current = _visible_range_values(page, range_index)[0 if thumb == "low" else 1]
    if current == target:
        return
    if interaction == "full":
        _visible_full_range(page, range_index, thumb, target)
        return
    direction = 1 if target > current else -1
    bank = page.locator(".cpf-range-unit").nth(range_index).locator(".cpf-step-bank > div").nth(0 if thumb == "low" else 1)
    button = bank.locator("button").nth(1 if direction > 0 else 0)
    button.click()


def _visible_move_dial(page, interaction: str, dial_index: int, target: int) -> None:
    current = _visible_dial_value(page, dial_index)
    if current == target:
        return
    if interaction == "full":
        _visible_full_dial(page, dial_index, current, target)
        return
    direction = 1 if target > current else -1
    buttons = page.locator(".cpf-dial-unit").nth(dial_index).locator(".cpf-dial-step button")
    buttons.nth(1 if direction > 0 else 0).click()


def solve_visible_surface(page, interaction: str, *, certify: bool = True) -> dict:
    """Solve from rendered card text and control geometry, without state files.

    This path deliberately avoids ``public_state.json``, numeric ARIA state,
    data-channel identifiers, and generated targets. It is evidence that the
    visible tick/thumb geometry and visible circuit labels are sufficient for
    the automated browser path; it is not a human or model calibration claim.
    """
    if interaction not in {"full", "simplified"}:
        raise AssertionError(f"unexpected interaction {interaction!r}")
    range_count = page.locator(".cpf-range-unit").count()
    dial_count = page.locator(".cpf-dial-unit").count()
    total_channels = range_count * 2 + dial_count
    actions = []

    for channel_index in range(total_channels):
        is_range = channel_index < range_count * 2
        if is_range:
            range_index, thumb_index = divmod(channel_index, 2)
            thumb = "low" if thumb_index == 0 else "high"
            target = _visible_range_target(page, range_index, thumb)
            current = _visible_range_values(page, range_index)[thumb_index]
            if current == target and channel_index + 1 < total_channels and _visible_target_is_locked(page, channel_index + 1, range_count):
                low, high = _visible_range_values(page, range_index)
                if thumb == "low":
                    detour = current + 5 if current + 5 <= high - 5 else current - 5
                else:
                    detour = current + 5 if current + 5 <= 100 else current - 5
                _visible_move_range(page, interaction, range_index, thumb, detour)
                actions.append({"channel": channel_index, "kind": "range-detour", "from": current, "to": detour})
            for _attempt in range(30):
                current = _visible_range_values(page, range_index)[thumb_index]
                if current == target:
                    break
                _visible_move_range(page, interaction, range_index, thumb, target)
                actions.append({"channel": channel_index, "kind": "range", "from": current, "to": target})
            else:
                raise AssertionError(f"visible range did not converge: {range_index}:{thumb}")
        else:
            dial_index = channel_index - range_count * 2
            target = _visible_dial_target(page, dial_index)
            current = _visible_dial_value(page, dial_index)
            if current == target and channel_index + 1 < total_channels and _visible_target_is_locked(page, channel_index + 1, range_count):
                detour = current + 1 if current < 11 else current - 1
                _visible_move_dial(page, interaction, dial_index, detour)
                actions.append({"channel": channel_index, "kind": "dial-detour", "from": current, "to": detour})
            for _attempt in range(30):
                current = _visible_dial_value(page, dial_index)
                if current == target:
                    break
                _visible_move_dial(page, interaction, dial_index, target)
                actions.append({"channel": channel_index, "kind": "dial", "from": current, "to": target})
            else:
                raise AssertionError(f"visible dial did not converge: {dial_index}")
        if channel_index + 1 < total_channels and _visible_target_is_locked(page, channel_index + 1, range_count):
            raise AssertionError(f"visible calibration source {channel_index} did not release channel {channel_index + 1}")

    targets = {}
    for line in page.locator(".cpf-check-tree li").all():
        label = line.locator("span").inner_text().strip()
        targets[label] = line.locator("b").inner_text().strip()

    while True:
        if interaction == "full":
            closed = page.locator(".cpf-tree-head > button:first-child").filter(has_text="▸")
        else:
            closed = page.locator(".cpf-open-proxy").filter(has_text="OPEN")
        if closed.count() == 0:
            break
        closed.first.click()
        actions.append({"kind": "open-visible-branch"})

    row_index = 0
    while row_index < page.locator(".cpf-tree-row").count():
        row = page.locator(".cpf-tree-row").nth(row_index)
        label = row.locator("span").inner_text().strip()
        target = targets[label]
        for _attempt in range(3):
            current = row.locator("button[data-circuit]").inner_text().strip()
            if current == target:
                break
            if interaction == "full":
                row.locator("button[data-circuit]").click()
            else:
                row.locator(".cpf-cycle").click()
            actions.append({"kind": "circuit", "label": label, "from": current, "target": target})
            row = page.locator(".cpf-tree-row").nth(row_index)
        else:
            raise AssertionError(f"visible circuit did not converge: {label}")
        row_index += 1

    if certify:
        page.get_by_role("button", name="CERTIFY PANEL").click()
        page.locator('.cpf-verdict.is-pass').wait_for(state="visible")
    return {
        "state_file_read": False,
        "observation_source": "rendered card text, thumb/indicator geometry, visible tree rows",
        "interaction": interaction,
        "actions": actions,
    }


def solve(page, state_dir: Path, out_dir: Path, mechanic: str, *, certify: bool = True) -> None:
    del out_dir
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    state = _state(state_dir)
    panel = state["panel"]
    mode = (state.get("control_condition") or {}).get("interaction") or "full"
    if mode == "full":
        for item in panel["ranges"]:
            if item["low"] == item["target_low"] and _feeds_locked_target(panel, item, "low"):
                detour = _detour(panel, item, "low")
                actual = _full_range(page, item, detour, panel)
                _commit_local(panel, item, "low", actual)
            for _attempt in range(100):
                if item["low"] == item["target_low"]:
                    break
                actual = _full_range(page, item, item["target_low"], panel)
                if actual == item["low"]:
                    raise AssertionError(f"low thumb cannot reach target for {item['id']}")
                _commit_local(panel, item, "low", actual)
            else:
                raise AssertionError(f"low thumb did not converge for {item['id']}")
            if item["high"] == item["target_high"] and _feeds_locked_target(panel, item, "high"):
                detour = _detour(panel, item, "high")
                actual = _full_range(page, item, detour, panel)
                _commit_local(panel, item, "high", actual)
            for _attempt in range(100):
                if item["high"] == item["target_high"]:
                    break
                actual = _full_range(page, item, item["target_high"], panel)
                if actual == item["high"]:
                    raise AssertionError(f"high thumb cannot reach target for {item['id']}")
                _commit_local(panel, item, "high", actual)
            else:
                raise AssertionError(f"high thumb did not converge for {item['id']}")
        for item in panel["dials"]:
            if item["value"] == item["target"] and _feeds_locked_target(panel, item, "value"):
                detour = _detour(panel, item, "value")
                _full_dial(page, {**item, "target": detour})
                _commit_local(panel, item, "value", detour)
            _full_dial(page, item)
            _commit_local(panel, item, "value", item["target"])
        for branch in panel["branches"]:
            if not branch["expanded"]:
                page.locator(f'[data-branch="{branch["id"]}"]').click()
            for row in branch["rows"]:
                current = row["state"]
                while current != row["target"]:
                    page.locator(f'[data-circuit="{row["id"]}"]').click()
                    current = panel["tree_states"][(panel["tree_states"].index(current) + 1) % len(panel["tree_states"])]
    else:
        for item in panel["ranges"]:
            for thumb, target in (("low", item["target_low"]), ("high", item["target_high"])):
                if item[thumb] == target and _feeds_locked_target(panel, item, thumb):
                    detour = _detour(panel, item, thumb)
                    direction = 1 if detour > item[thumb] else -1
                    page.locator(f'[data-range-step="{item["id"]}:{thumb}:{direction}"]').click()
                    _commit_local(panel, item, thumb, detour)
                direction = 1 if target > item[thumb] else -1
                while item[thumb] != target:
                    after = item[thumb] + direction * item["step"]
                    page.locator(f'[data-range-step="{item["id"]}:{thumb}:{direction}"]').click()
                    _commit_local(panel, item, thumb, after)
        for item in panel["dials"]:
            if item["value"] == item["target"] and _feeds_locked_target(panel, item, "value"):
                detour = _detour(panel, item, "value")
                direction = 1 if detour > item["value"] else -1
                page.locator(f'[data-dial-step="{item["id"]}:{direction}"]').click()
                _commit_local(panel, item, "value", detour)
            for _attempt in range(100):
                if item["value"] == item["target"]:
                    break
                direction = 1 if item["target"] > item["value"] else -1
                after = item["value"] + direction
                page.locator(f'[data-dial-step="{item["id"]}:{direction}"]').click()
                _commit_local(panel, item, "value", after)
            else:
                raise AssertionError(f"dial did not converge for {item['id']}")
        for branch in panel["branches"]:
            if not branch["expanded"]:
                page.locator(f'[data-branch-toggle="{branch["id"]}"]').click()
            for row in branch["rows"]:
                current = row["state"]
                while current != row["target"]:
                    page.locator(f'[data-circuit-cycle="{row["id"]}"]').click()
                    current = panel["tree_states"][(panel["tree_states"].index(current) + 1) % len(panel["tree_states"])]
    if certify:
        page.locator("#cpf-certify").click()
        page.locator('.cpf-verdict.is-pass').wait_for(state="visible")
