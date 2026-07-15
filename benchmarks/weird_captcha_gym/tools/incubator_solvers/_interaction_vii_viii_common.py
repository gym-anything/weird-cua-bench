from __future__ import annotations

import json
import math
import time
from pathlib import Path

from playwright.sync_api import expect


ABANDON = {
    "specular_lighthouse_relay": "#specular-abandon",
    "wind_tunnel_seed_courier": "#wind-abandon",
    "hologram_silhouette_foundry": "#holo-abandon",
    "orbital_docking_customs": "#orbital-abandon",
    "gravity_room_freight": "#gravity-abandon",
    "floodgate_archive_rescue": "#flood-abandon",
    "elastic_membrane_sorter": "#membrane-abandon",
    "pheromone_dispatch": "#pheromone-abandon",
    "clockwork_clutch_safe": "#clutch-abandon",
    "marionette_checkpoint": "#marionette-abandon",
}


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, mechanic: str, label: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_dir / f"{mechanic}-{label}.png"), full_page=True)


def fail_once(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    before = str(_read(state_dir / "ground_truth.json")["challenge_id"])
    page.locator(ABANDON[mechanic]).click()
    expect(page.locator(".ivv-verdict.is-fresh")).to_be_visible(timeout=8_000)
    deadline = time.time() + 8
    while time.time() < deadline:
        if str(_read(state_dir / "ground_truth.json")["challenge_id"]) != before:
            break
        time.sleep(.05)
    else:
        raise AssertionError(f"{mechanic} failure did not issue a fresh challenge")
    _shot(page, out_dir, mechanic, "fail-fresh")
    expect(page.locator(".ivv-verdict.is-fresh")).to_be_hidden(timeout=3_000)


def _click_many(locator, count: int) -> None:
    for _ in range(max(0, count)):
        locator.click()


def _set_range(page, selector: str, target: int, minimum: int = 0) -> None:
    control = page.locator(selector)
    control.focus()
    page.keyboard.press("Home")
    for _ in range(int(target) - int(minimum)):
        page.keyboard.press("ArrowRight")
    expect(control).to_have_value(str(int(target)))


def _adjust_range(page, selector: str, target: int) -> None:
    control = page.locator(selector)
    current = int(float(control.input_value()))
    target = int(target)
    if current == target:
        return
    control.focus()
    key = "ArrowRight" if target > current else "ArrowLeft"
    for _ in range(abs(target - current)):
        page.keyboard.press(key)


def _specular(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    truth = _read(state_dir / "ground_truth.json")
    _shot(page, out_dir, mechanic, "initial-fresh-optical-bench")
    def aim(mirror_index: int, target: float) -> None:
        current = float(page.evaluate("i => window.specularLighthouseRelayModel.angles[i]", mirror_index))
        plus_steps = round((float(target) - current) % 180)
        minus_steps = round((current - float(target)) % 180)
        selector = f'[data-mirror="{mirror_index}"][data-delta="{1 if plus_steps <= minus_steps else -1}"]'
        _click_many(page.locator(selector), min(plus_steps, minus_steps))

    for round_index, solution in enumerate(truth["solutions"]):
        for mirror_index, target in enumerate(solution["angles"]):
            aim(mirror_index, float(target))
        if round_index == 0:
            _shot(page, out_dir, mechanic, "three-mirror-beam-aligned")
        page.locator("#specular-charge").click()
        deadline = time.time() + 22
        photographed = False
        while time.time() < deadline:
            if page.locator(".ivv-verdict.is-pass").count() and page.locator(".ivv-verdict.is-pass").is_visible():
                break
            snapshot = page.evaluate("() => ({roundIndex:window.specularLighthouseRelayModel.roundIndex,tick:window.specularLighthouseRelayModel.tick,charge:window.specularLighthouseRelayModel.charge})")
            if int(snapshot["roundIndex"]) > round_index:
                break
            round_data = truth["rounds"][round_index]
            receiver = round_data["receiver"]
            receiver_y = float(receiver["center"][1]) + float(receiver["amplitude"]) * math.sin(int(snapshot["tick"]) * float(receiver["angular_rate"]) + float(receiver["phase"]))
            previous = round_data["mirrors"][1]["center"]
            center = round_data["mirrors"][2]["center"]
            incoming = math.atan2(float(center[1]) - float(previous[1]), float(center[0]) - float(previous[0]))
            outgoing = math.atan2(receiver_y - float(center[1]), float(receiver["center"][0]) - float(center[0]))
            target = (math.degrees((incoming + outgoing) / 2 + math.pi / 2) + 90) % 180
            aim(2, target)
            if round_index == 0 and int(snapshot["charge"]) > 18 and not photographed:
                _shot(page, out_dir, mechanic, "live-moving-receiver-track")
                photographed = True
            page.wait_for_timeout(24)
        else:
            raise AssertionError(f"moving receiver {round_index + 1} did not charge")
    expect(page.locator(".ivv-verdict.is-pass")).to_be_visible(timeout=10_000)


def _wind(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    truth = _read(state_dir / "ground_truth.json")
    page.locator("#wind-launch").click()
    for event_index, item in enumerate(truth["plan"]):
        page.wait_for_function("tick => window.windTunnelSeedCourierModel.tick >= tick", arg=int(item["tick"]), timeout=8_000)
        page.locator(f'[data-fan="{int(item["fan"])}"][data-power="{int(item["power"])}"]').click()
        if event_index == 0:
            _shot(page, out_dir, mechanic, "fan-field-armed")
    page.wait_for_function("() => window.windTunnelSeedCourierModel.tick > 245", timeout=12_000)
    _shot(page, out_dir, mechanic, "active-gate-flight")
    expect(page.locator(".ivv-verdict.is-pass")).to_be_visible(timeout=20_000)


def _hologram(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    truth = _read(state_dir / "ground_truth.json")
    _shot(page, out_dir, mechanic, "initial-three-view-foundry")
    for target in truth["solution_objects"]:
        page.locator(f'[data-rod="{target["id"]}"]').click()
        current = page.evaluate("id => window.hologramSilhouetteFoundryModel.objects.find(item => item.id === id)", target["id"])
        for axis_index, axis in enumerate("xyz"):
            delta = int(target["center"][axis_index]) - int(current["center"][axis_index])
            button = page.locator(f'[data-move="{axis}{"+" if delta > 0 else "-"}"]')
            _click_many(button, abs(delta))
        current_axis = str(page.evaluate("id => window.hologramSilhouetteFoundryModel.objects.find(item => item.id === id).axis", target["id"]))
        turns = ("xyz".index(target["axis"]) - "xyz".index(current_axis)) % 3
        _click_many(page.locator("#holo-rotate"), turns)
    _shot(page, out_dir, mechanic, "three-shadow-dies-coincident")
    page.locator("#holo-cast").click()


def _orbital(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    truth = _read(state_dir / "ground_truth.json")
    plan = truth["reference_plan"]
    _shot(page, out_dir, mechanic, "initial-rendezvous")
    coast_seen = 0
    for item in plan:
        action = str(item["action"])
        if action in {"thrust", "retro", "strafe-up", "strafe-down"}:
            _click_many(page.locator(f'[data-orbit="{action}"]'), int(item["count"]))
        elif action == "coast":
            ticks = int(item["ticks"])
            _click_many(page.locator('[data-orbit="coast-long"]'), ticks // 30)
            _click_many(page.locator('[data-orbit="coast"]'), ticks % 30 // 10)
            coast_seen += 1
            if coast_seen == 2:
                _shot(page, out_dir, mechanic, "first-scan-s-corridor")
        elif action == "rotate":
            target = int(round(float(item["target_deg"]))) % 360
            current = int(round(float(page.evaluate("() => window.orbitalDockingCustomsModel.ship.angle_deg")))) % 360
            right = ((target - current) % 360) // 15
            left = ((current - target) % 360) // 15
            _click_many(page.locator(f'[data-orbit="rotate-{"right" if right <= left else "left"}"]'), min(right, left))
        elif action == "dock":
            page.locator("#orbital-dock").click()
        else:
            raise AssertionError(f"unknown orbital reference action: {action}")


def _gravity(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    truth = _read(state_dir / "ground_truth.json")
    _shot(page, out_dir, mechanic, "initial-gravity-room")
    for index, action in enumerate(truth["solution"]):
        page.locator(f'[data-gravity="{action}"]').click()
        page.wait_for_timeout(680)
        if index == len(truth["solution"]) // 2:
            _shot(page, out_dir, mechanic, "mid-rotation-airlocks")
    page.locator("#gravity-certify").click()


def _flood(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    truth = _read(state_dir / "ground_truth.json")
    _shot(page, out_dir, mechanic, "initial-unequal-vaults")
    for index, action in enumerate(truth["reference_plan"]):
        if action["action"] == "pump":
            page.locator(f'[data-circuit="{action["circuit"]}"][data-direction="{action["direction"]}"]').click()
        elif action["action"] == "gate":
            page.locator(f'[data-lock="{action["gate"]}"]').click()
        else:
            page.locator("#flood-flow").click()
        if index == len(truth["reference_plan"]) // 2:
            _shot(page, out_dir, mechanic, "active-lock-transfer")
    page.locator("#flood-certify").click()


def _membrane(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    truth = _read(state_dir / "ground_truth.json")
    _shot(page, out_dir, mechanic, "initial-live-membrane")
    for index, round_data in enumerate(truth["rounds"]):
        first = round_data["checkpoints"][0]
        fx = max(-.048, min(.048, .004 * (float(first[0]) - 450)))
        fy = max(-.048, min(.048, .004 * (float(first[1]) - 230)))
        hx, hy = fx / .2, fy / .2
        initial = [max(0, min(100, round(100 * value))) for value in (.5 + hx + hy, .5 - hx + hy, .5 + hx - hy, .5 - hx - hy)]
        for post, value in enumerate(initial):
            _adjust_range(page, f'[data-post="{post}"]', value)
        page.locator("#membrane-release").click()
        last_control = -10
        photographed = False
        deadline = time.time() + 32
        while time.time() < deadline:
            if page.locator(".ivv-verdict.is-pass").count() and page.locator(".ivv-verdict.is-pass").is_visible():
                break
            snapshot = page.evaluate("() => {const m=window.elasticMembraneSorterModel;return {roundIndex:m.roundIndex,ticks:m.ticks,checkpoint:m.checkpoint,ball:{...m.ball},running:m.running}}")
            if int(snapshot["roundIndex"]) > index:
                break
            if not snapshot["running"] and int(snapshot["ticks"]) >= int(truth["physics"]["max_ticks"]):
                raise AssertionError("closed-loop membrane controller reached the visible simulation limit")
            if int(snapshot["ticks"]) - last_control >= 6:
                checkpoint = int(snapshot["checkpoint"])
                target = round_data["checkpoints"][checkpoint] if checkpoint < len(round_data["checkpoints"]) else round_data["wells"][round_data["target_well"]]
                ball = snapshot["ball"]
                fx = max(-.048, min(.048, .004 * (float(target[0]) - float(ball["x"])) - .09 * float(ball["vx"])))
                fy = max(-.048, min(.048, .004 * (float(target[1]) - float(ball["y"])) - .09 * float(ball["vy"])))
                hx, hy = fx / .2, fy / .2
                targets = [max(0, min(100, round(100 * value))) for value in (.5 + hx + hy, .5 - hx + hy, .5 + hx - hy, .5 - hx - hy)]
                for post, value in enumerate(targets):
                    _adjust_range(page, f'[data-post="{post}"]', value)
                last_control = int(snapshot["ticks"])
            if index == 0 and int(snapshot["checkpoint"]) == 1 and not photographed:
                _shot(page, out_dir, mechanic, "live-steering-between-rings")
                photographed = True
            page.wait_for_timeout(28)
        else:
            raise AssertionError(f"membrane round {index + 1} did not capture")
    expect(page.locator(".ivv-verdict.is-pass")).to_be_visible(timeout=10_000)


def _pheromone(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    truth = _read(state_dir / "ground_truth.json")
    public = _read(state_dir / "public_state.json")
    canvas = page.locator("#pheromone-canvas")
    box = canvas.bounding_box()
    if not box: raise AssertionError("pheromone habitat has no pointer geometry")
    def screen(point): return box["x"] + point[0] / 900 * box["width"], box["y"] + point[1] / 480 * box["height"]
    def paint_route(field_id: str) -> None:
        page.locator(f'[data-field="{field_id}"]').click()
        path = truth["reference_paths"][field_id]
        page.mouse.move(*screen(path[0])); page.mouse.down()
        try:
            for first, second in zip(path, path[1:]):
                for step in range(1, 13):
                    amount = step / 12
                    page.mouse.move(*screen([first[0] + (second[0] - first[0]) * amount, first[1] + (second[1] - first[1]) * amount]))
        finally:
            page.mouse.up()
    for field_id in truth["reference_paths"]:
        paint_route(field_id)
    _shot(page, out_dir, mechanic, "two-fields-painted")
    page.locator("#pheromone-dispatch").click()
    photographed = False
    deadline = time.time() + 38
    while time.time() < deadline:
        if page.locator(".ivv-verdict.is-pass").count() and page.locator(".ivv-verdict.is-pass").is_visible():
            break
        snapshot = page.evaluate("() => {const m=window.pheromoneDispatchModel;return {tick:m.tick,lastRefresh:{...m.lastRefresh},delivered:{...m.delivered},carrying:Object.values(m.ants).flat().some(a=>a.carrying)}}")
        for field in truth["reference_paths"]:
            spec = next(item for item in public["fields"] if item["id"] == field)
            if int(snapshot["tick"]) - int(snapshot["lastRefresh"][field]) >= int(spec["trail_ttl_ticks"]) - 28:
                paint_route(field)
        if snapshot["carrying"] and not photographed:
            _shot(page, out_dir, mechanic, "two-active-cache-carrier-swarms")
            photographed = True
        page.wait_for_timeout(100)
    else:
        raise AssertionError("dual pheromone teams did not complete")
    expect(page.locator(".ivv-verdict.is-pass")).to_be_visible(timeout=10_000)


def _clutch(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    truth = _read(state_dir / "ground_truth.json")
    _shot(page, out_dir, mechanic, "initial-coupled-train")
    page.locator("#clutch-drive").click()
    for schedule_index, item in enumerate(truth["release_schedule"]):
        page.wait_for_function("tick => window.clockworkClutchSafeModel.tick >= tick", arg=int(item["tick"]), timeout=12_000)
        page.locator(f'[data-clutch="{int(item["shaft"])}"]').click()
        if schedule_index == 0:
            _shot(page, out_dir, mechanic, "first-release-load-redistributed")
    page.locator("#clutch-brake").click()
    _shot(page, out_dir, mechanic, "four-phases-braked")
    page.locator("#clutch-unlock").click()


def _marionette(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    truth = _read(state_dir / "ground_truth.json")
    _shot(page, out_dir, mechanic, "initial-coupled-puppet")
    for pose_index, pose in enumerate(truth["poses"]):
        photographed = False
        deadline = time.time() + 18
        while time.time() < deadline:
            if page.locator(".ivv-verdict.is-pass").count() and page.locator(".ivv-verdict.is-pass").is_visible():
                break
            snapshot = page.evaluate("() => {const m=window.marionetteCheckpointModel;return {poseIndex:m.poseIndex,tick:m.tick,progress:m.progress}}")
            if int(snapshot["poseIndex"]) > pose_index:
                break
            future_tick = int(snapshot["tick"]) + 2
            targets = [round(float(base) + float(pose["amplitudes"][index]) * math.sin(future_tick * float(pose["angular_rate"]) + float(pose["phases"][index]))) for index, base in enumerate(pose["base_lengths"])]
            for string, length in enumerate(targets):
                _adjust_range(page, f'[data-string="{string}"]', int(length))
            if pose_index == 0 and int(snapshot["progress"]) > 22 and not photographed:
                _shot(page, out_dir, mechanic, "live-four-limb-tracking")
                photographed = True
            page.wait_for_timeout(85)
        else:
            raise AssertionError(f"moving marionette act {pose_index + 1} did not clear")
    expect(page.locator(".ivv-verdict.is-pass")).to_be_visible(timeout=10_000)


SOLVERS = {
    "specular_lighthouse_relay": _specular,
    "wind_tunnel_seed_courier": _wind,
    "hologram_silhouette_foundry": _hologram,
    "orbital_docking_customs": _orbital,
    "gravity_room_freight": _gravity,
    "floodgate_archive_rescue": _flood,
    "elastic_membrane_sorter": _membrane,
    "pheromone_dispatch": _pheromone,
    "clockwork_clutch_safe": _clutch,
    "marionette_checkpoint": _marionette,
}


def solve(page, state_dir: Path, out_dir: Path, mechanic: str) -> None:
    expect(page.locator(f'.ivv-{mechanic.replace("_", "-")}')).to_be_visible(timeout=6_000)
    SOLVERS[mechanic](page, state_dir, out_dir, mechanic)
