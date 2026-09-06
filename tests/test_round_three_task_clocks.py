"""Task-local clocks must preserve elapsed time at paused window boundaries."""
from contextlib import contextmanager
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

import pytest

BENCH = Path(__file__).resolve().parents[1] / "weird_captcha_gym"
CASES = [
    ("ballast_lantern", 600, "ballastLanternModel.sim.tick", 12),
    ("anthill_front", 600, "anthillFrontModel.sim.tick", 6),
    ("confectioners_ink", 600, "confectionersInkModel.tick", 30),
    ("apothecary_dead_reckoning", 1800, "apothecaryDeadReckoningModel.grindStep", 7),
    ("silent_colleague", 3000, None, 5),
]


@contextmanager
def task_browser(tmp_path, mechanic, interaction="full", viewport=(1280, 720), difficulty=None, time_mode="paused"):
    playwright = pytest.importorskip("playwright.sync_api")
    from weird_captcha_gym.tools.materialize_controlled_tasks import materialize_environment

    env = BENCH / "environments" / f"{mechanic}_env"
    if difficulty is None:
        difficulty = json.loads((env / "controls.json").read_text())["baseline"]["difficulty"]
    materialized = materialize_environment(env, tmp_path / "tasks")
    task = next(path for path in materialized if
                (condition := json.loads((path / "task.json").read_text())["metadata"]["control_condition"])
                ["difficulty"] == difficulty and condition["interaction"] == interaction)
    state = tmp_path / "state"
    subprocess.run([sys.executable, str(BENCH / "shared_scripts/setup_task.py"),
                    "--task-json", str(task / "task.json"), "--state-dir", str(state),
                    "--seed", "round-three-clock"], check=True, capture_output=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with (tmp_path / "server.log").open("w") as log:
        server = subprocess.Popen([sys.executable, str(BENCH / "shared_runtime/server/weird_captcha_server.py"),
                                   "--host", "127.0.0.1", "--port", str(port),
                                   "--app-dir", str(BENCH / "shared_runtime/app"), "--state-dir", str(state)],
                                  stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 10
            while True:
                try:
                    urlopen(f"http://127.0.0.1:{port}/health", timeout=.5).close()
                    break
                except OSError:
                    assert server.poll() is None and time.monotonic() < deadline
                    time.sleep(.05)
            with playwright.sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]})
                try:
                    page = context.new_page()
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(f"http://127.0.0.1:{port}/?time_mode={time_mode}", wait_until="networkidle")
                    yield page, state
                    assert not errors
                finally:
                    context.close()
                    browser.close()
        finally:
            server.terminate()
            server.wait(timeout=10)


def advance_window(page, duration, stall=0):
    page.evaluate("""([duration, stall]) => {
        WeirdCaptchaTime.runFor(duration);
        const start = WeirdCaptchaTime.native.performanceNow();
        while (WeirdCaptchaTime.native.performanceNow() - start < stall) {}
    }""", [duration, stall])
    deadline = time.monotonic() + duration / 1000 + 10
    while page.evaluate("WeirdCaptchaTime.status().phase") != "completed":
        assert time.monotonic() < deadline
        time.sleep(.02)


@pytest.mark.parametrize("mechanic,duration,expression,expected", CASES)
@pytest.mark.parametrize("stall", [False, True])
def test_fixed_window_catches_up_and_stays_paused(tmp_path, mechanic, duration, expression, expected, stall):
    with task_browser(tmp_path, mechanic) as (page, state):
        if mechanic == "apothecary_dead_reckoning":
            from weird_captcha_gym.tools.incubator_solvers.apothecary_dead_reckoning import _load
            truth = json.loads((state / "ground_truth.json").read_text())
            _load(page, truth["ingredients"][0]["id"], "full")
            box = page.locator("#apoth-pestle").bounding_box()
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.mouse.down()
        # Split across two windows to cover retained fractions and an existing epoch.
        first = duration // 3 + 7
        advance_window(page, first, first + 250 if stall else 0)
        advance_window(page, duration - first, duration - first + 250 if stall else 0)
        assert page.evaluate("WeirdCaptchaTime.status().task_time_ms") == duration
        time.sleep(.1)
        assert page.evaluate("WeirdCaptchaTime.status().task_time_ms") == duration
        if expression:
            assert page.evaluate(expression) == expected
        if mechanic == "apothecary_dead_reckoning":
            page.mouse.up()
            events = page.evaluate("apothecaryDeadReckoningModel.events")
            assert [e["grind_step"] for e in events if e["type"] == "grind_tick"] == list(range(1, expected + 1))
            assert events[-1]["type"] == "grind_release" and events[-1]["grind_step"] == expected
            advance_window(page, 300, 550 if stall else 0)
            assert page.evaluate(expression) == expected
        elif mechanic == "ballast_lantern":
            page.keyboard.down("Space")
            assert page.evaluate("ballastLanternModel.events.at(-1).tick") == expected
            page.keyboard.up("Space")
        elif mechanic == "anthill_front":
            from weird_captcha_gym.tools.incubator_solvers.anthill_front import _select_full_idle_workers, _canvas_point
            world = json.loads((state / "public_state.json").read_text())["world"]
            _select_full_idle_workers(page, world, 0, [world["workers"][0]["id"]])
            page.keyboard.press("g")
            page.mouse.click(*_canvas_point(page, world, world["seed_pile"]["x"], world["seed_pile"]["y"], 0))
            assert page.evaluate("anthillFrontModel.events.at(-1).tick") == expected
        elif mechanic == "silent_colleague":
            page.keyboard.press("d")
            with page.expect_request("**/result") as request:
                page.locator("#sc-certify").click()
            payload = request.value.post_data_json
            assert payload["final_tick"] == expected
            assert payload["final_state"]["tick"] == expected
            assert payload["events"][-1]["tick"] == expected
