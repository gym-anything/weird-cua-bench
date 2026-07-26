#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from benchmarks.weird_captcha_gym.dashboard.export_static import export_dashboard


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export and exercise every static browser-play puzzle, including a real WebAssembly grade."
    )
    parser.add_argument("--out-dir", type=Path, help="Optional directory for dashboard and pass screenshots")
    return parser.parse_args()


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


def main() -> None:
    args = parse_args()
    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="weird-cua-static-browser-") as temporary:
        site = Path(temporary) / "site"
        manifest = export_dashboard(site, copy_media=False)
        handler = partial(QuietHandler, directory=str(site))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"

        failures: list[dict[str, str]] = []
        active_environment = ["dashboard"]
        dashboard_requests: list[str] = []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 1440, "height": 1000})
                context.add_init_script(
                    """(() => {
                      const canvas = document.createElement('canvas');
                      canvas.width = 1280;
                      canvas.height = 720;
                      const context = canvas.getContext('2d');
                      let frame = 0;
                      setInterval(() => {
                        frame += 1;
                        context.fillStyle = frame % 2 ? '#102418' : '#182d3a';
                        context.fillRect(0, 0, canvas.width, canvas.height);
                        context.fillStyle = '#c7ff35';
                        context.font = '48px monospace';
                        context.fillText(`CAPTURE ${frame}`, 80, 120);
                      }, 32);
                      window.__WEIRD_CAPTURE_TEST_CANVAS = canvas;
                      const mediaDevices = navigator.mediaDevices || {};
                      Object.defineProperty(mediaDevices, 'getDisplayMedia', {
                        configurable: true,
                        value: async () => canvas.captureStream(30),
                      });
                      if (!navigator.mediaDevices) {
                        Object.defineProperty(navigator, 'mediaDevices', {configurable: true, value: mediaDevices});
                      }
                    })()"""
                )
                dashboard = context.new_page()
                dashboard.on("request", lambda request: dashboard_requests.append(request.url))
                dashboard.on(
                    "pageerror",
                    lambda error: failures.append({
                        "environment": active_environment[0],
                        "kind": "pageerror",
                        "error": str(error),
                    }),
                )
                dashboard.goto(
                    f"{base_url}/#/environment/rotating_keyboard_env",
                    wait_until="networkidle",
                )
                expect(dashboard.get_by_role("button", name="Try in browser")).to_be_visible()
                if args.out_dir:
                    dashboard.screenshot(path=str(args.out_dir / "dashboard-browser-play.png"), full_page=True)
                with context.expect_page() as opened:
                    dashboard.get_by_role("button", name="Try in browser").click()
                puzzle = opened.value
                if "environment=rotating_keyboard_env" not in puzzle.url:
                    raise AssertionError(f"one-click launch opened the wrong URL: {puzzle.url}")
                if any(url.startswith("http://127.0.0.1:8767") for url in dashboard_requests):
                    raise AssertionError("the shared dashboard contacted the loopback companion before opt-in")

                puzzle.on(
                    "pageerror",
                    lambda error: failures.append({
                        "environment": active_environment[0],
                        "kind": "pageerror",
                        "error": str(error),
                    }),
                )
                puzzle.goto(
                    f"{base_url}/play/?environment=rotating_keyboard_env&attempt=0",
                    wait_until="networkidle",
                )
                puzzle.wait_for_selector(".rotating-captcha")
                puzzle.get_by_role("button", name="Expand observation controls").click()
                expect(puzzle.get_by_role("button", name="Capture model observation")).to_be_visible()
                puzzle.get_by_role("button", name="Paused").click()
                puzzle.wait_for_function("WeirdCaptchaTime.status().state === 'paused'")
                paused_before = puzzle.evaluate("WeirdCaptchaTime.status().task_time_ms")
                puzzle.wait_for_timeout(180)
                paused_after = puzzle.evaluate("WeirdCaptchaTime.status().task_time_ms")
                if abs(paused_after - paused_before) > 1:
                    raise AssertionError(f"public paused clock advanced: {paused_before} -> {paused_after}")
                puzzle.get_by_role("button", name="Capture model observation").click()
                expect(puzzle.locator(".weird-demo-observation")).to_have_attribute("data-open", "true", timeout=10_000)
                expect(puzzle.locator(".weird-demo-frame")).to_have_count(6)
                expect(puzzle.locator("[data-demo-screen-label]")).to_contain_text("obs.screen")
                if args.out_dir:
                    puzzle.screenshot(path=str(args.out_dir / "browser-observation-viewer.png"), full_page=True)
                if puzzle.evaluate("WeirdCaptchaTime.status().state") != "paused":
                    raise AssertionError("paused browser observation did not stop after frame capture")
                puzzle.get_by_role("button", name="Close").click()
                puzzle.get_by_role("button", name="Live").click()
                puzzle.wait_for_function("WeirdCaptchaTime.status().state === 'running'")
                first_challenge = puzzle.locator(".rotating-captcha").get_attribute("data-challenge-id")
                puzzle.locator("#submit-rotating").click()
                expect(puzzle.locator(".readout")).to_have_text("FAIL", timeout=60_000)
                second_challenge = puzzle.locator(".rotating-captcha").get_attribute("data-challenge-id")
                if first_challenge == second_challenge:
                    raise AssertionError("failed browser play did not issue a fresh challenge")
                target = puzzle.locator(".rotating-fixed strong").inner_text()
                puzzle.evaluate(
                    """target => {
                        for (const key of target) {
                          document.querySelector(`.rotating-key[data-key="${CSS.escape(key)}"]`).click();
                        }
                    }""",
                    target,
                )
                puzzle.locator("#submit-rotating").click()
                expect(puzzle.locator(".readout")).to_have_text("PASS", timeout=30_000)
                if args.out_dir:
                    puzzle.screenshot(path=str(args.out_dir / "browser-play-pyodide-pass.png"), full_page=True)

                challenge_root = site / "play" / "challenges"
                environment_ids = sorted(path.stem for path in challenge_root.glob("*.json"))
                for environment_id in environment_ids:
                    active_environment[0] = environment_id
                    try:
                        puzzle.goto(
                            f"{base_url}/play/?environment={environment_id}&attempt=0",
                            wait_until="domcontentloaded",
                            timeout=15_000,
                        )
                        puzzle.wait_for_function(
                            "document.body.dataset.mechanic && document.body.dataset.mechanic !== 'waiting'",
                            timeout=10_000,
                        )
                        if not puzzle.locator("#app").inner_text().strip():
                            raise AssertionError("rendered app is empty")
                        bundle = json.loads((challenge_root / f"{environment_id}.json").read_text(encoding="utf-8"))
                        for level in sorted(bundle.get("difficulty_profiles") or {}, key=int):
                            puzzle.goto(
                                f"{base_url}/play/?environment={environment_id}&attempt=0&difficulty={level}",
                                wait_until="domcontentloaded",
                                timeout=15_000,
                            )
                            puzzle.wait_for_function(
                                "document.body.dataset.mechanic && document.body.dataset.mechanic !== 'waiting'",
                                timeout=10_000,
                            )
                            selected = puzzle.evaluate(
                                "async () => (await (await fetch(`/state?ts=${Date.now()}`)).json()).control_condition?.difficulty"
                            )
                            if int(selected or 0) != int(level):
                                raise AssertionError(f"requested difficulty {level} rendered difficulty {selected}")
                            if not puzzle.locator("#app").inner_text().strip():
                                raise AssertionError(f"difficulty {level} rendered an empty app")
                    except Exception as error:  # noqa: BLE001 - aggregate all environments before failing.
                        failures.append({
                            "environment": environment_id,
                            "kind": "render",
                            "error": str(error).splitlines()[0],
                        })
                active_environment[0] = "all-browser-graders"
                grader_sweep = puzzle.evaluate(
                    """async () => {
                      const catalog = await (await fetch('/data/catalog.json')).json();
                      const ids = catalog.environments.filter(item => item.stage === 'built').map(item => item.id);
                      const worker = new Worker('runtime/grader_worker.js', {type: 'module'});
                      let nextId = 0;
                      const pending = new Map();
                      worker.onmessage = event => {
                        const slot = pending.get(event.data.id);
                        if (!slot) return;
                        pending.delete(event.data.id);
                        if (event.data.ok) slot.resolve(event.data.grade);
                        else slot.reject(new Error(event.data.error));
                      };
                      worker.onerror = event => {
                        for (const slot of pending.values()) slot.reject(new Error(event.message));
                        pending.clear();
                      };
                      const grade = data => new Promise((resolve, reject) => {
                        const id = ++nextId;
                        pending.set(id, {resolve, reject});
                        worker.postMessage({id, ...data});
                      });
                      const failures = [];
                      for (const environmentId of ids) {
                        try {
                          const bundle = await (await fetch(`challenges/${environmentId}.json`)).json();
                          const challenge = bundle.challenges[0];
                          const output = await grade({
                            graderUrl: new URL(bundle.grader, location.href).href,
                            payload: {
                              mechanic_id: bundle.mechanic_id,
                              challenge_id: challenge.ground_truth.challenge_id,
                            },
                            groundTruth: challenge.ground_truth,
                            publicState: challenge.public_state,
                          });
                          if (output?.graded !== true || typeof output?.passed !== 'boolean') {
                            failures.push({environmentId, output});
                          }
                        } catch (error) {
                          failures.push({environmentId, error: error.message});
                        }
                      }
                      worker.terminate();
                      return {executed: ids.length, failures};
                    }"""
                )
                failures.extend({
                    "environment": item.get("environmentId", "unknown"),
                    "kind": "pyodide-grader",
                    "error": item.get("error", json.dumps(item.get("output"))),
                } for item in grader_sweep["failures"])
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

        summary = {
            "ok": not failures,
            "dashboard_one_click": True,
            "loopback_contact_before_opt_in": False,
            "fresh_failure_challenge": True,
            "browser_time_conditions": ["live", "paused"],
            "browser_observation_frames": 6,
            "pyodide_grade": "PASS",
            "pyodide_graders_executed": grader_sweep["executed"],
            "rendered_environments": manifest["browser_play"]["environments"] - len({item["environment"] for item in failures}),
            "total_environments": manifest["browser_play"]["environments"],
            "failures": failures,
        }
        print(json.dumps(summary, indent=2))
        if failures:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
