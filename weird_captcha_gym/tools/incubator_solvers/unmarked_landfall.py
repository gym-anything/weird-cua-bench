from __future__ import annotations

import json
import math
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "unmarked_landfall"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, mechanic: str, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{mechanic}-{label}.png"), full_page=True)


def _wait_new(state_dir: Path, old: str) -> None:
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            current = str(_read(state_dir / "ground_truth.json").get("challenge_id") or "")
        except (FileNotFoundError, json.JSONDecodeError):
            current = old
        if current and current != old:
            return
        time.sleep(0.05)
    raise AssertionError("Unmarked Landfall did not issue a fresh challenge")


def _canvas_box(page) -> dict:
    box = page.locator("#landfall-panorama").bounding_box()
    if not box:
        raise AssertionError("landfall panorama is not visible")
    return box


def _map_box(page) -> dict:
    box = page.locator("#landfall-map").bounding_box()
    if not box:
        raise AssertionError("landfall map is not visible")
    return box


def _canvas_screen(box: dict, point: tuple[float, float]) -> tuple[float, float]:
    return (
        box["x"] + point[0] / 960 * box["width"],
        box["y"] + point[1] / 540 * box["height"],
    )


def _map_screen(page, point: tuple[float, float]) -> tuple[float, float]:
    mapped = page.evaluate(
        """([x, y]) => {
          const svg = document.getElementById("landfall-map");
          const point = svg.createSVGPoint();
          point.x = x;
          point.y = y;
          const result = point.matrixTransform(svg.getScreenCTM());
          return [result.x, result.y];
        }""",
        [float(point[0]), float(point[1])],
    )
    return float(mapped[0]), float(mapped[1])


def _delta(angle: float) -> float:
    return (angle + 180) % 360 - 180


def _pan_to(page, bearing: float) -> None:
    for _ in range(5):
        yaw = float(page.evaluate("() => unmarkedLandfallModel.yaw"))
        difference = _delta(bearing - yaw)
        if abs(difference) <= 4:
            return
        change = max(-105.0, min(105.0, difference))
        stage_dx = -change / 0.32
        start_x = 480.0
        end_x = start_x + stage_dx
        if end_x < 75:
            start_x += 75 - end_x
            end_x = 75
        if end_x > 885:
            start_x -= end_x - 885
            end_x = 885
        box = _canvas_box(page)
        page.mouse.move(*_canvas_screen(box, (start_x, 250)))
        page.mouse.down()
        page.mouse.move(*_canvas_screen(box, (end_x, 250)), steps=14)
        page.mouse.up()
    yaw = float(page.evaluate("() => unmarkedLandfallModel.yaw"))
    if abs(_delta(bearing - yaw)) > 8:
        raise AssertionError(f"could not pan to bearing {bearing}; stopped at {yaw}")


def _turn_to_visible(page, bearing: float) -> None:
    for _ in range(12):
        yaw = float(page.evaluate("() => unmarkedLandfallModel.yaw"))
        difference = _delta(bearing - yaw)
        if abs(difference) <= 42:
            return
        page.locator("#landfall-turn-right" if difference > 0 else "#landfall-turn-left").click()
    raise AssertionError(f"road bearing {bearing} never entered the simplified view")


def _observe_bearing(page, interaction: str, bearing: float) -> None:
    if interaction == "full":
        _pan_to(page, bearing)
    else:
        _turn_to_visible(page, bearing)


def _observe_node(
    page,
    node: dict,
    interaction: str,
    observed_features: set[str],
    observed_landmark: list[bool],
    out_dir: Path,
    mechanic: str,
) -> None:
    clue = node.get("clue")
    if clue and clue["feature"] not in observed_features:
        _observe_bearing(page, interaction, float(clue["bearing"]))
        page.wait_for_timeout(140)
        _shot(page, out_dir, mechanic, f"evidence-{clue['feature']}")
        observed_features.add(str(clue["feature"]))
    landmark = node.get("landmark")
    if landmark and not observed_landmark[0]:
        _observe_bearing(page, interaction, float(landmark["bearing"]))
        page.wait_for_timeout(140)
        _shot(page, out_dir, mechanic, "localization-landmark")
        observed_landmark[0] = True


def _walk(page, truth: dict, out_dir: Path, mechanic: str) -> None:
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    nodes = {node["id"]: node for node in truth["journey"]["nodes"]}
    route = list(truth["target"]["solution_route"])
    observed_features: set[str] = set()
    observed_landmark = [False]
    if route[0] != truth["journey"]["landing_node"]:
        raise AssertionError("solution route does not begin at the landing node")
    for index, (source, destination) in enumerate(zip(route, route[1:]), start=1):
        _observe_node(
            page,
            nodes[source],
            interaction,
            observed_features,
            observed_landmark,
            out_dir,
            mechanic,
        )
        road = next(item for item in nodes[source]["roads"] if item["to"] == destination)
        if interaction == "full":
            _pan_to(page, float(road["bearing"]))
            box = _canvas_box(page)
            page.mouse.click(*_canvas_screen(box, (480, 421.2)))
        else:
            _turn_to_visible(page, float(road["bearing"]))
            page.locator(f'[data-road-target="{destination}"]').click()
        page.wait_for_function("node => unmarkedLandfallModel.currentNode === node", arg=destination)
        if index == max(1, len(route) // 2):
            _shot(page, out_dir, mechanic, "active-road-evidence")
    _observe_node(
        page,
        nodes[route[-1]],
        interaction,
        observed_features,
        observed_landmark,
        out_dir,
        mechanic,
    )
    actual_steps = int(page.evaluate("() => unmarkedLandfallModel.steps"))
    if actual_steps != len(route) - 1 or actual_steps > int(truth["journey"]["step_budget"]):
        raise AssertionError(f"unexpected route length {actual_steps}")
    if observed_features != set(truth["active_features"]):
        raise AssertionError(
            "solution did not visibly inspect every evidence class: "
            f"{sorted(observed_features)}"
        )
    if not observed_landmark[0]:
        raise AssertionError("solution did not visibly inspect the localization landmark")


def _file_deposition(page, truth: dict, out_dir: Path, mechanic: str) -> None:
    page.locator('[data-landfall-tab="guide"]').click()
    if len(truth["guide"]["provinces"]) > int(truth["guide"]["page_size"]):
        page.locator("#landfall-guide-next").click()
    _shot(page, out_dir, mechanic, "guide-after-fieldwork")
    page.locator('[data-landfall-tab="deposition"]').click()
    for feature in truth["active_features"]:
        value = truth["target"]["signature"][feature]
        page.locator(f'[data-feature="{feature}"][data-value="{value}"]').click()
    _shot(page, out_dir, mechanic, "deposition-complete-selection")


def _pin_landing(
    page,
    truth: dict,
    out_dir: Path,
    mechanic: str,
    *,
    exercise_map_controls: bool = True,
) -> None:
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    page.locator('[data-landfall-tab="map"]').click()
    point = truth["target"]["landing_point"]
    width = float(truth["map"]["width"])
    height = float(truth["map"]["height"])
    box = _map_box(page)
    if interaction == "full" and exercise_map_controls:
        target_screen = _map_screen(page, (float(point["x"]), float(point["y"])))
        page.mouse.move(*target_screen)
        page.mouse.wheel(0, -480)
        page.mouse.wheel(0, -480)
        _shot(page, out_dir, mechanic, "map-before-moved-pan")
        # Exercise the direct manipulation surface as an actual pan rather than
        # counting the pointer-down/up pair from a pin click as a map drag.
        drag_start = _map_screen(page, (width / 2, height / 2))
        drag_end = _map_screen(page, (width / 2 + 36, height / 2 + 24))
        page.mouse.move(*drag_start)
        page.mouse.down()
        page.mouse.move(*drag_end, steps=12)
        page.mouse.up()
        _shot(page, out_dir, mechanic, "map-after-moved-pan")
    elif interaction == "simplified" and exercise_map_controls:
        page.locator('[data-map-zoom="1"]').click()
        page.locator('[data-map-zoom="1"]').click()
        page.locator('[data-map-zoom="-1"]').click()
        page.locator('[data-map-zoom="-1"]').click()
    transform = page.evaluate("() => ({zoom:unmarkedLandfallModel.mapZoom,pan:unmarkedLandfallModel.mapPan})")
    view_point = (
        float(transform["pan"][0]) + float(point["x"]) * float(transform["zoom"]),
        float(transform["pan"][1]) + float(point["y"]) * float(transform["zoom"]),
    )
    page.mouse.click(*_map_screen(page, view_point))
    page.wait_for_function("() => Boolean(unmarkedLandfallModel.pin)")
    _shot(page, out_dir, mechanic, "map-original-drop-pin")


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    before = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    page.locator("#landfall-submit").click()
    _wait_new(state_dir, before)
    expect(page.locator('.unmarked-landfall[data-fresh-failure="true"]')).to_be_visible(timeout=10_000)
    expect(page.locator(".readout")).to_have_text("FAIL")
    _shot(page, out_dir, mechanic, "failure-fresh-country")


def attempt_one_step_shortcut(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    """Submit correct private truth after one road step; the grader must reject it."""

    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    before = str(truth["challenge_id"])
    interaction = str((truth.get("control_condition") or {}).get("interaction") or "full")
    node_id = str(truth["journey"]["landing_node"])
    node = next(item for item in truth["journey"]["nodes"] if item["id"] == node_id)
    road = node["roads"][0]
    if interaction == "full":
        box = _canvas_box(page)
        page.mouse.move(*_canvas_screen(box, (480, 250)))
        page.mouse.down()
        page.mouse.move(*_canvas_screen(box, (470, 250)), steps=4)
        page.mouse.up()
        _pan_to(page, float(road["bearing"]))
        box = _canvas_box(page)
        page.mouse.click(*_canvas_screen(box, (480, 421.2)))
    else:
        page.locator("#landfall-turn-right").click()
        _turn_to_visible(page, float(road["bearing"]))
        page.locator(f'[data-road-target="{road["to"]}"]').click()
    page.wait_for_function(
        "destination => unmarkedLandfallModel.currentNode === destination",
        arg=str(road["to"]),
    )
    _file_deposition(page, truth, out_dir, mechanic)
    _pin_landing(
        page,
        truth,
        out_dir,
        mechanic,
        exercise_map_controls=False,
    )
    expect(page.locator('#landfall-submit[data-ready="true"]')).to_be_visible()
    page.locator("#landfall-submit").click()
    _wait_new(state_dir, before)
    expect(page.locator('.unmarked-landfall[data-fresh-failure="true"]')).to_be_visible(
        timeout=10_000
    )
    expect(page.locator(".readout")).to_have_text("FAIL")
    _shot(page, out_dir, mechanic, "one-step-shortcut-rejected")


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    page.locator(".unmarked-landfall").wait_for(state="visible")
    truth = _read(state_dir / "ground_truth.json")
    _walk(page, truth, out_dir, mechanic)
    _file_deposition(page, truth, out_dir, mechanic)
    _pin_landing(page, truth, out_dir, mechanic)
    expect(page.locator('#landfall-submit[data-ready="true"]')).to_be_visible()
    page.locator("#landfall-submit").click()
    expect(page.locator(".readout")).to_have_text("PASS", timeout=10_000)
    expect(page.locator('.unmarked-landfall[data-verdict="pass"]')).to_be_visible()
    _shot(page, out_dir, mechanic, "pass")


def solve_with_corrections(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    if mechanic != MECHANIC_ID:
        raise AssertionError(f"unexpected mechanic {mechanic!r}")
    truth = _read(state_dir / "ground_truth.json")
    _walk(page, truth, out_dir, mechanic)

    page.locator('[data-landfall-tab="deposition"]').click()
    first_feature = truth["active_features"][0]
    first_correct = truth["target"]["signature"][first_feature]
    first_wrong = next(
        value
        for value in truth["feature_values"][first_feature]
        if value != first_correct
    )
    page.locator(
        f'[data-feature="{first_feature}"][data-value="{first_wrong}"]'
    ).click()
    _shot(page, out_dir, mechanic, "corrective-wrong-convention")
    page.locator(
        f'[data-feature="{first_feature}"][data-value="{first_correct}"]'
    ).click()
    for feature in truth["active_features"][1:]:
        value = truth["target"]["signature"][feature]
        page.locator(f'[data-feature="{feature}"][data-value="{value}"]').click()

    page.locator('[data-landfall-tab="map"]').click()
    box = _map_box(page)
    point = truth["target"]["landing_point"]
    width = float(truth["map"]["width"])
    height = float(truth["map"]["height"])
    wrong = (
        width - 18 if float(point["x"]) < width / 2 else 18,
        height - 18 if float(point["y"]) < height / 2 else 18,
    )
    page.mouse.click(*_map_screen(page, wrong))
    _shot(page, out_dir, mechanic, "corrective-wrong-pin")
    page.mouse.click(
        *_map_screen(page, (float(point["x"]), float(point["y"])))
    )
    _shot(page, out_dir, mechanic, "corrective-repaired-pin")

    expect(page.locator('#landfall-submit[data-ready="true"]')).to_be_visible()
    page.locator("#landfall-submit").click()
    expect(page.locator(".readout")).to_have_text("PASS", timeout=10_000)
    expect(page.locator('.unmarked-landfall[data-verdict="pass"]')).to_be_visible()
    _shot(page, out_dir, mechanic, "corrective-pass")
