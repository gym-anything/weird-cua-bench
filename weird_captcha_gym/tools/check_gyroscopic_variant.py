"""Exercise the experimental board through browser inputs and independent replay."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright

from weird_captcha_gym.shared_runtime.server.incubator_graders import board_game_captcha as grader
from weird_captcha_gym.tools.incubator_solvers.board_game_captcha import _drive, fail_once
from weird_captcha_gym.tools.materialize_gyroscopic_variant import variant_task
from weird_captcha_gym.tools.smoke_incubator_batch_one_ui import (
    APP_DIR, ROOT, SERVER, SETUP, exported_payload, run_task_verifier,
)


def snapshot(page):
    return page.evaluate("""() => ({position:[...gyroBoardModel.position],
        velocity:[...gyroBoardModel.velocity], tilt:[...gyroBoardModel.tilt],
        external:[...gyroBoardModel.externalTilt], ticks:gyroBoardModel.tickCount})""")


def check_case(browser, output: Path, seed: str, interaction: str) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="gyro-variant-check-") as temporary_name:
        temporary = Path(temporary_name)
        state_dir = temporary / "state"
        task_path = temporary / "task.json"
        task_path.write_text(json.dumps(variant_task(5, interaction)))
        subprocess.run([sys.executable, str(SETUP), "--task-json", str(task_path),
                        "--state-dir", str(state_dir), "--seed", seed],
                       cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        with (output / "server.log").open("w") as log:
            server = subprocess.Popen([sys.executable, str(SERVER), "--host", "127.0.0.1",
                                       "--port", str(port), "--app-dir", str(APP_DIR),
                                       "--state-dir", str(state_dir)],
                                      cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                      env={**os.environ, "WEIRD_CAPTCHA_CHALLENGE_SEED": seed})
            context = browser.new_context(viewport={"width": 1920, "height": 1080},
                                          record_video_dir=str(output / "video"),
                                          record_video_size={"width": 1920, "height": 1080})
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            try:
                deadline = time.monotonic() + 10
                while True:
                    try:
                        urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5).read()
                        break
                    except OSError:
                        if server.poll() is not None or time.monotonic() > deadline:
                            raise RuntimeError("board server failed to start")
                        time.sleep(0.1)
                page.goto(f"http://127.0.0.1:{port}/?time_mode=live&start_paused=1")
                expect(page.locator("#gyro-drift-arrow")).to_be_visible()
                submit_box = page.locator("#gyro-submit").bounding_box()
                assert submit_box and submit_box["y"] + submit_box["height"] <= 1080
                canvas_box = page.locator("#tilt-canvas").bounding_box()
                assert canvas_box and abs(canvas_box["width"] / canvas_box["height"] - 900 / 520) < 0.02
                before = snapshot(page)
                page.screenshot(path=str(output / "initial.png"))
                page.evaluate("() => WeirdCaptchaTime.resume()")
                page.wait_for_timeout(3000)
                page.evaluate("() => WeirdCaptchaTime.pause()")
                after = snapshot(page)
                assert after["tilt"] == [0, 0]
                assert after["ticks"] > before["ticks"] + 50
                assert math.dist(before["position"], after["position"]) > 20, (before, after)
                assert before["external"] != after["external"]
                page.screenshot(path=str(output / "neutral-after-3s.png"))
                page.wait_for_timeout(350)
                assert snapshot(page) == after, "pause must freeze both ball and external tilt"
                page.locator("#gyro-reset").click()
                reset = snapshot(page)
                assert reset["ticks"] == after["ticks"], "reset must preserve external phase"
                assert reset["external"] == after["external"]
                assert reset["position"] == before["position"]
                page.evaluate("() => WeirdCaptchaTime.resume()")
                page.wait_for_timeout(400)
                assert snapshot(page)["position"] != reset["position"]

                # A failed submission must create another usable drifting board.
                fail_once(page, state_dir, output, "board_game_captcha")
                page.wait_for_function("() => document.querySelector('.gyro-board').dataset.freshFailure === 'false'")
                truth = json.loads((state_dir / "ground_truth.json").read_text())
                page.locator("#gyro-reset").click()
                start = time.monotonic()
                _drive(page, truth["solver_waypoints"], truth["solver_switch_waypoint_indices"],
                       interaction, timeout_s=90)
                solve_seconds = time.monotonic() - start
                page.locator("#gyro-submit").click()
                expect(page.locator(".readout")).to_have_text("PASS", timeout=10000)
                page.screenshot(path=str(output / "pass.png"))
                exported = exported_payload(state_dir)
                direct = grader.grade(exported["result"], exported["ground_truth"], exported["public_state"])
                verified = run_task_verifier("board_game_captcha", exported, temporary)
                assert direct["passed"] and verified["passed"], (direct, verified)
                assert not errors, errors
                result = dict(seed=seed, interaction=interaction, solve_seconds=solve_seconds,
                              neutral_before=before, neutral_after=after,
                              server_grade=exported["result"]["server_grade"],
                              direct_grade=direct, verifier=verified)
                (output / "export.json").write_text(json.dumps(exported))
                (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
                print(json.dumps(result), flush=True)
                return result
            except Exception:
                page.screenshot(path=str(output / "failure.png"))
                raise
            finally:
                context.close()
                server.terminate()
                try:
                    server.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--seeds", nargs="+", default=["42", "43", "44"])
    parser.add_argument("--interactions", nargs="+", choices=["full", "simplified"], default=["full"])
    args = parser.parse_args()
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for interaction in args.interactions:
                for seed in args.seeds:
                    results.append(check_case(browser, args.out_dir / f"{interaction}-{seed}", seed, interaction))
        finally:
            browser.close()
    (args.out_dir / "summary.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
