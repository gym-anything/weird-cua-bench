#!/usr/bin/env python3
"""Capture visible controllability evidence for Thirty-Year Time Wheel.

The full interaction smoke owns the exhaustive solve matrix. This companion
records comparable starting screens for the preserved baseline, representative
profiles, both L3 interaction surfaces, and the browser runtime's actual live
and paused observation viewer. It deliberately launches only an isolated
headless Chromium with temporary state and a loopback server.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import sys
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from weird_captcha_gym.dashboard.export_static import export_dashboard
from weird_captcha_gym.shared_scripts.setup_task import generate_task_state, load_task
from weird_captcha_gym.tools import materialize_controlled_tasks as materializer
from weird_captcha_gym.tools import smoke_controlled_interaction_ui as browser_smoke


ENVIRONMENT = "thirty_year_time_wheel_env"
MECHANIC = "thirty_year_time_wheel"
ENV_ROOT = ROOT / "weird_captcha_gym" / "environments" / ENVIRONMENT
LOCAL_VIEWPORT = browser_smoke.observation_viewport(ENV_ROOT)
STATIC_VIEWPORT = {"width": 1280, "height": 720}
EVIDENCE_SEED = "thirty-year-time-wheel-controllability-evidence-v1"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture visible Time Wheel controllability evidence.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ENV_ROOT / "evidence_docs",
        help="Evidence directory (defaults to the environment evidence_docs directory).",
    )
    return parser.parse_args()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def without_identity(value: dict[str, Any]) -> dict[str, Any]:
    stripped = copy.deepcopy(value)
    for key in ("task_id", "challenge_id", "control_condition"):
        stripped.pop(key, None)
    return stripped


def fingerprint(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(without_identity(value), sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def controlled_task(tasks_root: Path, difficulty: int, interaction: str) -> Path:
    return browser_smoke.controlled_task(tasks_root, difficulty, interaction)


def start_capture_server(task_path: Path, interaction: str, state_dir: Path) -> tuple[Any, int]:
    """Start a locally isolated task server with the capture's fixed seed."""

    return browser_smoke.start_server(
        task_path,
        MECHANIC,
        interaction,
        state_dir,
        EVIDENCE_SEED,
    )


def capture_local_screens(
    browser: Any,
    *,
    original_task: Path,
    tasks_root: Path,
    work_root: Path,
    output: Path,
) -> dict[str, dict[str, Any]]:
    from playwright.sync_api import expect

    output.mkdir(parents=True, exist_ok=True)
    selected = [
        ("original-l3-uncontrolled", original_task),
        ("d2-full", controlled_task(tasks_root, 2, "full")),
        ("d3-simplified", controlled_task(tasks_root, 3, "simplified")),
        ("d3-full", controlled_task(tasks_root, 3, "full")),
        ("d4-full", controlled_task(tasks_root, 4, "full")),
        ("d5-full", controlled_task(tasks_root, 5, "full")),
    ]
    records: dict[str, dict[str, Any]] = {}
    for label, task_path in selected:
        state_dir = work_root / label
        state_dir.mkdir(parents=True, exist_ok=True)
        expected_interaction = "simplified" if label == "d3-simplified" else "full"
        process, port = start_capture_server(task_path, expected_interaction, state_dir)
        page = browser.new_page(viewport=LOCAL_VIEWPORT, device_scale_factor=1)
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            current_task_path = state_dir / "current_task.json"
            current_task_text = current_task_path.read_text(encoding="utf-8")
            current_task_path.unlink()
            try:
                page.goto(f"http://127.0.0.1:{port}/?time_mode=live", wait_until="networkidle")
            finally:
                current_task_path.write_text(current_task_text, encoding="utf-8")
            expect(page.locator(".time-wheel-captcha")).to_be_visible()
            expect(page.locator(".time-wheel-captcha")).to_have_attribute("data-interaction", expected_interaction)
            if expected_interaction == "simplified":
                expect(page.locator("[data-time-proxy-component]").first).to_be_visible()
            else:
                expect(page.locator("#time-wheel-dial")).to_be_visible()
            page.screenshot(path=str(output / f"{label}.png"), full_page=True)
            public = browser_smoke.read_json(state_dir / "public_state.json")
            records[label] = {
                "challenge_id": public["challenge_id"],
                "task_id": public["task_id"],
                "difficulty": (public.get("control_condition") or {}).get("difficulty", 3),
                "interaction": page.locator(".time-wheel-captcha").get_attribute("data-interaction"),
                "required_components": public.get("required_components", ["month", "year", "day"]),
                "detent_degrees": public["detent_degrees"],
                "target_presentation": public.get("target_presentation", "direct"),
                "world_fingerprint_without_identity": fingerprint(public),
                "page_errors": errors,
            }
        finally:
            page.close()
            process.terminate()
            try:
                process.wait(timeout=3)
            except Exception:
                process.kill()
    if records["original-l3-uncontrolled"]["world_fingerprint_without_identity"] != records["d3-full"]["world_fingerprint_without_identity"]:
        raise AssertionError("visible controlled L3 no longer preserves the uncontrolled world")
    if records["d3-simplified"]["world_fingerprint_without_identity"] != records["d3-full"]["world_fingerprint_without_identity"]:
        raise AssertionError("visible L3 interaction pair generated different worlds")
    if any(record["page_errors"] for record in records.values()):
        raise AssertionError(f"browser errors during visible capture: {records}")
    write_json(output / "visible-states.json", records)
    return records


def install_page_snapshot_capture(page: Any) -> None:
    """Provide a headless-only screen stream to the browser observation viewer."""

    page.evaluate("document.documentElement.dataset.agentCapture = 'true'")
    png = page.screenshot()
    page.evaluate("delete document.documentElement.dataset.agentCapture")
    encoded = base64.b64encode(png).decode("ascii")
    page.evaluate(
        """async encoded => {
          const image = new Image();
          await new Promise((resolve, reject) => {
            image.onload = resolve;
            image.onerror = reject;
            image.src = `data:image/png;base64,${encoded}`;
          });
          const canvas = document.createElement('canvas');
          canvas.width = 1280;
          canvas.height = 720;
          const context = canvas.getContext('2d');
          context.drawImage(image, 0, 0, canvas.width, canvas.height);
          let pulse = false;
          const native = window.WeirdCaptchaTime?.native || window;
          native.setInterval(() => {
            pulse = !pulse;
            context.fillStyle = pulse ? '#000001' : '#000000';
            context.fillRect(canvas.width - 1, canvas.height - 1, 1, 1);
          }, 32);
          const mediaDevices = navigator.mediaDevices || {};
          Object.defineProperty(mediaDevices, 'getDisplayMedia', {
            configurable: true,
            value: async () => canvas.captureStream(30),
          });
          if (!navigator.mediaDevices) {
            Object.defineProperty(navigator, 'mediaDevices', {configurable: true, value: mediaDevices});
          }
        }""",
        encoded,
    )


def capture_static_observation(page: Any, *, base_url: str, mode: str, output: Path) -> dict[str, Any]:
    from playwright.sync_api import expect

    page.goto(
        f"{base_url}/play/?environment={ENVIRONMENT}&attempt=0&difficulty=3&interaction=full&time_mode={mode}",
        wait_until="networkidle",
    )
    expect(page.locator(".time-wheel-captcha")).to_be_visible()
    expect(page.locator(".time-wheel-captcha")).to_have_attribute("data-interaction", "full")
    page.get_by_role("button", name="Expand observation controls").click()
    expect(page.get_by_role("button", name="Capture model observation")).to_be_enabled()
    expected_state = "paused" if mode == "paused" else "running"
    page.wait_for_function(f"WeirdCaptchaTime.status().state === '{expected_state}'")
    before_delay = page.evaluate("WeirdCaptchaTime.status()")
    page.wait_for_timeout(750)
    after_delay = page.evaluate("WeirdCaptchaTime.status()")
    delay_delta = float(after_delay["task_time_ms"]) - float(before_delay["task_time_ms"])
    if mode == "live" and delay_delta < 550:
        raise AssertionError(f"live task clock did not advance through the observation delay: {delay_delta}")
    if mode == "paused" and abs(delay_delta) > 2:
        raise AssertionError(f"paused task clock advanced through the observation delay: {delay_delta}")
    install_page_snapshot_capture(page)
    page.get_by_role("button", name="Capture model observation").click()
    expect(page.locator(".weird-demo-observation")).to_have_attribute("data-open", "true", timeout=10_000)
    expect(page.locator(".weird-demo-frame")).to_have_count(5)
    expect(page.locator("[data-demo-screen-label]")).to_contain_text("obs.screen")
    if mode == "paused":
        page.wait_for_function("WeirdCaptchaTime.status().state === 'paused'")
    else:
        page.wait_for_function("WeirdCaptchaTime.status().state === 'running'")
    page.screenshot(path=str(output / f"{mode}-model-observation.png"), full_page=True)
    return {
        "mode": mode,
        "clock_before_750ms_delay": before_delay,
        "clock_after_750ms_delay": after_delay,
        "delay_task_time_delta_ms": delay_delta,
        "frames": page.locator(".weird-demo-frame").count(),
        "screen_label": page.locator("[data-demo-screen-label]").inner_text(),
        "clock_after_observation_capture": page.evaluate("WeirdCaptchaTime.status()"),
    }


def capture_static_observations(output: Path) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="time-wheel-static-evidence-") as temporary:
        site = Path(temporary) / "site"
        manifest = export_dashboard(site, copy_media=False)
        handler = partial(QuietHandler, directory=str(site))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(viewport=STATIC_VIEWPORT)
                page = context.new_page()
                base_url = f"http://127.0.0.1:{server.server_port}"
                observations = {
                    mode: capture_static_observation(page, base_url=base_url, mode=mode, output=output)
                    for mode in ("live", "paused")
                }
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
    result = {"environment": ENVIRONMENT, "difficulty": 3, "interaction": "full", "export": manifest["browser_play"], "observations": observations}
    write_json(output / "summary.json", result)
    return result


def main() -> None:
    from playwright.sync_api import sync_playwright

    args = parse_args()
    out_dir = args.out_dir.resolve()
    original_task = ENV_ROOT / "tasks" / f"{MECHANIC}_seed_0001" / "task.json"
    with tempfile.TemporaryDirectory(prefix="time-wheel-evidence-") as temporary:
        work_root = Path(temporary)
        materialized_root = work_root / "materialized"
        materializer.materialize_environment(ENV_ROOT, materialized_root)
        tasks_root = materialized_root / ENVIRONMENT / "tasks"
        original = load_task(original_task)
        l3_simplified = load_task(controlled_task(tasks_root, 3, "simplified"))
        l3_full = load_task(controlled_task(tasks_root, 3, "full"))
        original_public, original_truth = generate_task_state(original, EVIDENCE_SEED)
        simplified_public, simplified_truth = generate_task_state(l3_simplified, EVIDENCE_SEED)
        full_public, full_truth = generate_task_state(l3_full, EVIDENCE_SEED)
        if without_identity(original_public) != without_identity(simplified_public) or without_identity(original_truth) != without_identity(simplified_truth):
            raise AssertionError("fixed-seed L3 no longer preserves the original task")
        if without_identity(simplified_public) != without_identity(full_public) or without_identity(simplified_truth) != without_identity(full_truth):
            raise AssertionError("the L3 interaction pair no longer preserves one generated world")
        write_json(out_dir / "baseline-preservation.json", {
            "seed": EVIDENCE_SEED,
            "original_l3_world_fingerprint_without_identity": fingerprint(original_public),
            "controlled_l3_simplified_world_fingerprint_without_identity": fingerprint(simplified_public),
            "controlled_l3_full_world_fingerprint_without_identity": fingerprint(full_public),
            "public_state_preserved": True,
            "ground_truth_preserved": True,
            "identity_only_differences": ["task_id", "challenge_id", "control_condition"],
        })
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            visible = capture_local_screens(
                browser,
                original_task=original_task,
                tasks_root=tasks_root,
                work_root=work_root / "browser-state",
                output=out_dir / "visible_states",
            )
            browser.close()
    observations = capture_static_observations(out_dir / "model_observations")
    summary = {
        "environment": ENVIRONMENT,
        "baseline": {"difficulty": 3, "interaction": "full", "real_time": "live"},
        "visible_states": visible,
        "model_observations": observations["observations"],
    }
    write_json(out_dir / "capture-summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
