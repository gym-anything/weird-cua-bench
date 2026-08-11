#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from weird_captcha_gym.shared_runtime.server.weird_captcha_server import PuzzleServer


ROOT = REPO_ROOT / "weird_captcha_gym"


class QuietPuzzleServer(PuzzleServer):
    def log_message(self, _format: str, *_args: object) -> None:
        return


def post(base: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{base}/time-control",
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def status(base: str) -> dict:
    with urllib.request.urlopen(f"{base}/time-control/status") as response:
        return json.load(response)


def post_input(base: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{base}/input-control",
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def input_status(base: str) -> dict:
    with urllib.request.urlopen(f"{base}/input-control/status") as response:
        return json.load(response)


def wait_status(base: str, predicate, timeout: float = 5) -> dict:
    deadline = time.monotonic() + timeout
    last = {}
    while time.monotonic() < deadline:
        try:
            last = status(base)
            if predicate(last):
                return last
        except Exception:
            pass
        time.sleep(0.02)
    raise TimeoutError(last)


def wait_input_status(base: str, predicate, timeout: float = 5) -> dict:
    deadline = time.monotonic() + timeout
    last = {}
    while time.monotonic() < deadline:
        try:
            last = input_status(base)
            if predicate(last):
                return last
        except Exception:
            pass
        time.sleep(0.02)
    raise TimeoutError(last)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="weird-cua-time-control-") as temporary:
        root = Path(temporary)
        app_dir = root / "app"
        state_dir = root / "state"
        app_dir.mkdir()
        state_dir.mkdir()
        shutil.copy2(ROOT / "shared_runtime" / "app" / "time_controller.js", app_dir)
        (app_dir / "index.html").write_text(
            """<!doctype html><html><head>
            <script src="/time_controller.js"></script>
            <style>@keyframes drift {from {transform:translateX(0)} to {transform:translateX(100px)}}
            #box {animation: drift 1s linear infinite}
            @keyframes late-drift {from {transform:translateX(0)} to {transform:translateX(100px)}}
            #late.animated {animation: late-drift 1s linear infinite}
            #drag {width:160px;height:80px;background:#ddd;touch-action:none}</style></head><body>
            <div id="box">box</div><button id="spawn">spawn animation</button><div id="late">late</div>
            <input id="field"><div id="drag">drag</div>
            <script>
            window.timerTicks = 0; window.rafTicks = 0; window.trustedClicks = 0;
            window.trustedKeys = 0; window.dragEvents = [];
            setInterval(() => window.timerTicks++, 20);
            function frame(){ window.rafTicks++; requestAnimationFrame(frame); }
            document.getElementById('spawn').addEventListener('click', event => {
              if (event.isTrusted) trustedClicks++;
              document.getElementById('late').classList.add('animated');
            });
            document.getElementById('field').addEventListener('keydown', event => {
              if (event.isTrusted) trustedKeys++;
            });
            for (const type of ['pointerdown', 'pointermove', 'pointerup']) {
              document.getElementById('drag').addEventListener(type, event => {
                if (event.isTrusted) dragEvents.push(type);
                if (type === 'pointerdown') event.currentTarget.setPointerCapture(event.pointerId);
              });
            }
            requestAnimationFrame(frame); WeirdCaptchaTime.markReady();
            </script></body></html>""",
            encoding="utf-8",
        )

        PuzzleServer.app_dir = app_dir
        PuzzleServer.state_dir = state_dir
        server = ThreadingHTTPServer(("127.0.0.1", 0), QuietPuzzleServer)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(f"{base}/?time_mode=paused&start_paused=1&time_control=1")
                wait_status(base, lambda item: item.get("ready") is True)
                page.wait_for_timeout(100)

                before = page.evaluate("""() => ({
                  task: WeirdCaptchaTime.status().task_time_ms,
                  timers: timerTicks,
                  raf: rafTicks,
                  animation: document.getElementById('box').getAnimations()[0].currentTime
                })""")
                page.wait_for_timeout(250)
                frozen = page.evaluate("""() => ({
                  task: WeirdCaptchaTime.status().task_time_ms,
                  timers: timerTicks,
                  raf: rafTicks,
                  animation: document.getElementById('box').getAnimations()[0].currentTime
                })""")
                if frozen != before:
                    raise AssertionError(f"paused state advanced: before={before}, after={frozen}")

                armed = post_input(base, {
                    "command": "arm",
                    "category": "mouse",
                    "required": True,
                })
                wait_input_status(
                    base,
                    lambda item: item.get("command_sequence") == armed["sequence"]
                    and item.get("phase") == "armed",
                )
                action_task_before = page.evaluate("WeirdCaptchaTime.status().task_time_ms")
                page.click("#spawn")
                completed_input_command = post_input(base, {
                    "command": "complete",
                    "arm_sequence": armed["arm_sequence"],
                })
                input_delivery = wait_input_status(
                    base,
                    lambda item: item.get("command_sequence") == completed_input_command["sequence"]
                    and item.get("phase") in {"completed", "missing"},
                )
                if not input_delivery.get("receipt_confirmed"):
                    raise AssertionError(f"browser did not confirm paused click: {input_delivery}")
                action_state = page.evaluate("""() => ({
                  task: WeirdCaptchaTime.status().task_time_ms,
                  clicks: trustedClicks,
                  animation: document.getElementById('late').getAnimations()[0]?.currentTime,
                  playState: document.getElementById('late').getAnimations()[0]?.playState,
                })""")
                page.wait_for_timeout(120)
                action_frozen = page.evaluate("""() => ({
                  task: WeirdCaptchaTime.status().task_time_ms,
                  clicks: trustedClicks,
                  animation: document.getElementById('late').getAnimations()[0]?.currentTime,
                  playState: document.getElementById('late').getAnimations()[0]?.playState,
                })""")
                if action_state != action_frozen or action_state["task"] != action_task_before:
                    raise AssertionError(
                        f"paused action or new animation advanced: {action_state} -> {action_frozen}"
                    )
                if action_state["clicks"] != 1 or action_state["playState"] != "paused":
                    raise AssertionError(f"paused handler/animation state is wrong: {action_state}")

                keyboard_arm = post_input(base, {
                    "command": "arm",
                    "category": "keyboard",
                    "required": True,
                })
                wait_input_status(
                    base,
                    lambda item: item.get("command_sequence") == keyboard_arm["sequence"]
                    and item.get("phase") == "armed",
                )
                page.focus("#field")
                page.keyboard.type("K")
                keyboard_complete = post_input(base, {
                    "command": "complete",
                    "arm_sequence": keyboard_arm["arm_sequence"],
                })
                keyboard_delivery = wait_input_status(
                    base,
                    lambda item: item.get("command_sequence") == keyboard_complete["sequence"]
                    and item.get("phase") in {"completed", "missing"},
                )
                keyboard_state = page.evaluate("""() => ({
                  task: WeirdCaptchaTime.status().task_time_ms,
                  keys: trustedKeys,
                  value: document.getElementById('field').value,
                })""")
                if (
                    not keyboard_delivery.get("receipt_confirmed")
                    or keyboard_state != {"task": action_task_before, "keys": 1, "value": "K"}
                ):
                    raise AssertionError(
                        f"paused keyboard delivery failed: {keyboard_delivery}, {keyboard_state}"
                    )

                drag_arm = post_input(base, {
                    "command": "arm",
                    "category": "mouse",
                    "required": True,
                })
                wait_input_status(
                    base,
                    lambda item: item.get("command_sequence") == drag_arm["sequence"]
                    and item.get("phase") == "armed",
                )
                drag_box = page.locator("#drag").bounding_box()
                if drag_box is None:
                    raise AssertionError("drag target has no geometry")
                page.mouse.move(drag_box["x"] + 20, drag_box["y"] + 20)
                page.mouse.down()
                page.mouse.move(drag_box["x"] + 120, drag_box["y"] + 50, steps=4)
                page.mouse.up()
                drag_complete = post_input(base, {
                    "command": "complete",
                    "arm_sequence": drag_arm["arm_sequence"],
                })
                drag_delivery = wait_input_status(
                    base,
                    lambda item: item.get("command_sequence") == drag_complete["sequence"]
                    and item.get("phase") in {"completed", "missing"},
                )
                drag_state = page.evaluate("""() => ({
                  task: WeirdCaptchaTime.status().task_time_ms,
                  events: [...dragEvents],
                })""")
                if (
                    not drag_delivery.get("receipt_confirmed")
                    or drag_state["task"] != action_task_before
                    or "pointerdown" not in drag_state["events"]
                    or "pointermove" not in drag_state["events"]
                    or "pointerup" not in drag_state["events"]
                ):
                    raise AssertionError(
                        f"paused drag delivery failed: {drag_delivery}, {drag_state}"
                    )

                command = post(base, {"command": "run_for", "milliseconds": 200, "start_delay_ms": 50})
                completed = wait_status(
                    base,
                    lambda item: item.get("sequence") == command["sequence"]
                    and item.get("phase") == "completed",
                )
                advanced = page.evaluate("""() => ({
                  task: WeirdCaptchaTime.status().task_time_ms,
                  timers: timerTicks,
                  raf: rafTicks,
                  animation: document.getElementById('box').getAnimations()[0].currentTime,
                  lateAnimation: document.getElementById('late').getAnimations()[0].currentTime
                })""")
                expected_task = action_task_before + 200
                if abs(advanced["task"] - expected_task) > 0.001:
                    raise AssertionError(
                        f"virtual task endpoint was {advanced['task']}, expected {expected_task}"
                    )
                if advanced["timers"] <= before["timers"] or advanced["raf"] <= before["raf"]:
                    raise AssertionError(f"timers did not advance: {before} -> {advanced}")
                if advanced["animation"] <= before["animation"]:
                    raise AssertionError(f"CSS animation did not advance: {before} -> {advanced}")
                if advanced["lateAnimation"] <= action_state["animation"]:
                    raise AssertionError(
                        f"action-created animation did not advance in the window: {action_state} -> {advanced}"
                    )
                if completed.get("window_started_wall_ms") is None or completed.get("window_completed_wall_ms") is None:
                    raise AssertionError(f"observation boundaries were not reported: {completed}")

                page.wait_for_timeout(200)
                refrozen = page.evaluate("WeirdCaptchaTime.status().task_time_ms")
                if abs(refrozen - advanced["task"]) > 1:
                    raise AssertionError(f"clock did not refreeze: {advanced['task']} -> {refrozen}")
                switched_live = page.evaluate("WeirdCaptchaTime.setMode('live')")
                page.wait_for_timeout(100)
                live_task_time = page.evaluate("WeirdCaptchaTime.status().task_time_ms")
                if switched_live["mode"] != "live" or live_task_time <= refrozen:
                    raise AssertionError(f"browser mode switch did not resume task time: {switched_live}")
                switched_paused = page.evaluate("WeirdCaptchaTime.setMode('paused')")
                if switched_paused["mode"] != "paused" or switched_paused["state"] != "paused":
                    raise AssertionError(f"browser mode switch did not pause task time: {switched_paused}")
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    print(json.dumps({
        "ok": True,
        "paused": True,
        "advance_ms": 200,
        "paused_input_receipt": True,
        "paused_keyboard_receipt": True,
        "paused_drag_receipt": True,
        "action_created_animation_refrozen": True,
        "exact_virtual_endpoint": True,
        "refrozen": True,
        "browser_mode_switch": True,
    }))


if __name__ == "__main__":
    main()
