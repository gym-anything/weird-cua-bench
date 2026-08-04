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
            #box {animation: drift 1s linear infinite}</style></head><body><div id="box">box</div>
            <script>
            window.timerTicks = 0; window.rafTicks = 0;
            setInterval(() => window.timerTicks++, 20);
            function frame(){ window.rafTicks++; requestAnimationFrame(frame); }
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
                  animation: document.getElementById('box').getAnimations()[0].currentTime
                })""")
                if not 170 <= advanced["task"] <= 260:
                    raise AssertionError(f"virtual task time advanced by {advanced['task']} ms")
                if advanced["timers"] <= before["timers"] or advanced["raf"] <= before["raf"]:
                    raise AssertionError(f"timers did not advance: {before} -> {advanced}")
                if advanced["animation"] <= before["animation"]:
                    raise AssertionError(f"CSS animation did not advance: {before} -> {advanced}")
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
        "refrozen": True,
        "browser_mode_switch": True,
    }))


if __name__ == "__main__":
    main()
