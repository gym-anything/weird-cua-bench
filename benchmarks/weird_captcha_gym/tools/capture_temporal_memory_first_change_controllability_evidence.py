#!/usr/bin/env python3
"""Capture inspectable First Change Memory controllability evidence.

The generic interaction smoke proves every difficulty/interaction transcript.
This companion capture makes the original uncontrolled L4 state, adjacent
levels, and the target environment's public live/paused observation frames
directly inspectable.  It uses only a local loopback server and isolated
headless Playwright contexts with a temporary profile.
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

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from benchmarks.weird_captcha_gym.dashboard.export_static import export_dashboard
from benchmarks.weird_captcha_gym.shared_scripts.setup_task import generate_task_state, load_task
from benchmarks.weird_captcha_gym.tools import materialize_controlled_tasks as materializer
from benchmarks.weird_captcha_gym.tools import smoke_controlled_interaction_ui as browser_smoke


ENVIRONMENT = "temporal_memory_first_change_env"
MECHANIC = "temporal_memory_first_change"
BENCHMARK = ROOT / "benchmarks" / "weird_captcha_gym"
ENV_ROOT = BENCHMARK / "environments" / ENVIRONMENT
ORIGINAL_TASK = ENV_ROOT / "tasks" / f"{MECHANIC}_seed_0001" / "task.json"
VIEWPORT = browser_smoke.observation_viewport(ENV_ROOT)
STATIC_VIEWPORT = {"width": 1280, "height": 720}
EVIDENCE_SEED = "first-change-original-l4-visible-evidence"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ENV_ROOT / "evidence_docs" / "completion_capture",
        help="Directory for inspectable screenshots and JSON result artifacts.",
    )
    return parser.parse_args()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def without_identity(value: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(value)
    for key in ("task_id", "challenge_id", "control_condition"):
        normalized.pop(key, None)
    return normalized


def fingerprint(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(without_identity(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def controlled_task(tasks_root: Path, difficulty: int, interaction: str) -> Path:
    return browser_smoke.controlled_task(tasks_root, difficulty, interaction)


def open_initial_page(page: Any, port: int, state_dir: Path) -> None:
    """Use the setup seed for the visible first browser state, not a fresh one."""
    current_task = state_dir / "current_task.json"
    task_text = current_task.read_text(encoding="utf-8")
    current_task.unlink()
    try:
        page.goto(
            f"http://127.0.0.1:{port}/?time_mode=paused&start_paused=1",
            wait_until="networkidle",
        )
    finally:
        current_task.write_text(task_text, encoding="utf-8")


def capture_visible_states(browser: Any, tasks_root: Path, work_root: Path, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    selected = [
        ("original-uncontrolled-l4-full", ORIGINAL_TASK, "full"),
        ("l3-full", controlled_task(tasks_root, 3, "full"), "full"),
        ("l4-full", controlled_task(tasks_root, 4, "full"), "full"),
        ("l5-full", controlled_task(tasks_root, 5, "full"), "full"),
        ("l4-simplified", controlled_task(tasks_root, 4, "simplified"), "simplified"),
    ]
    result: dict[str, Any] = {}
    for label, task_path, interaction in selected:
        state_dir = work_root / label
        state_dir.mkdir(parents=True, exist_ok=True)
        process, port = browser_smoke.start_server(task_path, MECHANIC, interaction, state_dir)
        context = browser.new_context(viewport=VIEWPORT, device_scale_factor=1)
        page = context.new_page()
        page_errors: list[str] = []
        console_errors: list[str] = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.on(
            "console",
            lambda message: console_errors.append(message.text) if message.type == "error" else None,
        )
        try:
            open_initial_page(page, port, state_dir)
            root = page.locator(".tracking-captcha")
            expect(root).to_have_attribute("data-interaction", interaction)
            canvas = page.locator(".tracking-canvas")
            expect(canvas).to_be_visible()
            screenshot = output / f"{label}-initial.png"
            canvas_screenshot = output / f"{label}-initial-canvas.png"
            image = page.screenshot(path=str(screenshot), full_page=True)
            canvas_image = canvas.screenshot(path=str(canvas_screenshot))
            if page_errors or console_errors:
                raise AssertionError(f"{label}: page={page_errors}; console={console_errors}")
            public = browser_smoke.read_json(state_dir / "public_state.json")
            truth = browser_smoke.read_json(state_dir / "ground_truth.json")
            canvas_box = canvas.bounding_box()
            if canvas_box is None:
                raise AssertionError(f"{label}: canvas has no visible geometry")
            result[label] = {
                "task_id": public["task_id"],
                "challenge_id": public["challenge_id"],
                "interaction": interaction,
                "difficulty": (public.get("control_condition") or {}).get("difficulty", 4),
                "world_fingerprint_without_identity": fingerprint(public),
                "truth_fingerprint_without_identity": fingerprint(truth),
                "object_count": len(public["timeline"]["objects"]),
                "event_count": len(public["timeline"]["events"]),
                "first_change_duration_ms": public["timeline"]["events"][0]["duration_ms"],
                "lens_radius": public["timeline"]["lens_radius"],
                "occluders": public["timeline"]["occluders"],
                "proof": public["timeline"]["proof"],
                "coordinate_controls_visible": page.locator(".tracking-coordinate-controls").count() == 1,
                "settled_slot_buttons": page.locator(".tracking-slot-controls button").count(),
                "canvas_css_pixels": {"width": canvas_box["width"], "height": canvas_box["height"]},
                "screenshot": screenshot.name,
                "canvas_screenshot": canvas_screenshot.name,
                "screenshot_sha256": hashlib.sha256(image).hexdigest(),
                "canvas_screenshot_sha256": hashlib.sha256(canvas_image).hexdigest(),
            }
        finally:
            page.close()
            context.close()
            process.terminate()
            try:
                process.wait(timeout=3)
            except Exception:
                process.kill()

    original = result["original-uncontrolled-l4-full"]
    l4_full = result["l4-full"]
    l4_simplified = result["l4-simplified"]
    if original["world_fingerprint_without_identity"] != l4_full["world_fingerprint_without_identity"]:
        raise AssertionError("controlled L4/full changed the uncontrolled original world")
    if original["truth_fingerprint_without_identity"] != l4_full["truth_fingerprint_without_identity"]:
        raise AssertionError("controlled L4/full changed the uncontrolled original goal")
    if original["canvas_screenshot_sha256"] != l4_full["canvas_screenshot_sha256"]:
        raise AssertionError("controlled L4/full changed the visible initial canvas")
    if l4_full["world_fingerprint_without_identity"] != l4_simplified["world_fingerprint_without_identity"]:
        raise AssertionError("L4 full and simplified did not share one visible world")
    if l4_full["truth_fingerprint_without_identity"] != l4_simplified["truth_fingerprint_without_identity"]:
        raise AssertionError("L4 full and simplified did not share one goal")
    write_json(output / "visible-states.json", result)
    return result


def install_snapshot_capture(page: Any) -> None:
    """Exercise the public inspector when native headless tab capture is unavailable.

    This is deliberately retained as separately labelled UI evidence. It does
    not stand in for native tab-capture evidence or an evaluation observation.
    """
    page.evaluate("document.documentElement.dataset.agentCapture = 'true'")
    image = page.screenshot()
    page.evaluate("delete document.documentElement.dataset.agentCapture")
    encoded = base64.b64encode(image).decode("ascii")
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


def inspect_static_mode(page: Any, mode: str, output: Path, *, synthetic_stream: bool) -> dict[str, Any]:
    page.get_by_role("button", name="Live" if mode == "live" else "Paused").click()
    expected_state = "running" if mode == "live" else "paused"
    page.wait_for_function(f"WeirdCaptchaTime.status().state === '{expected_state}'")
    before = page.evaluate("WeirdCaptchaTime.status()")
    if synthetic_stream:
        install_snapshot_capture(page)
    page.get_by_role("button", name="Capture model observation").click()
    page.wait_for_timeout(2_000)
    viewer = page.locator(".weird-demo-observation")
    if viewer.get_attribute("data-open") != "true":
        unavailable = output / f"{mode}-native-capture-unavailable.png"
        page.screenshot(path=str(unavailable), full_page=True)
        return {
            "available": False,
            "reason": page.locator("[data-demo-note]").inner_text(),
            "before": before,
            "screenshot": unavailable.name,
        }
    frames = page.locator(".weird-demo-frame")
    expect(frames).to_have_count(6)
    viewer_screenshot = output / f"{mode}-observation-viewer.png"
    first_screenshot = output / f"{mode}-frame-1.png"
    final_screenshot = output / f"{mode}-obs-screen-final-frame.png"
    page.screenshot(path=str(viewer_screenshot), full_page=True)
    frames.first.click()
    page.wait_for_timeout(100)
    first_label = page.locator("[data-demo-screen-label]").inner_text()
    first_image = page.locator("[data-demo-screen]").screenshot(path=str(first_screenshot))
    frames.last.click()
    page.wait_for_timeout(100)
    final_label = page.locator("[data-demo-screen-label]").inner_text()
    final_image = page.locator("[data-demo-screen]").screenshot(path=str(final_screenshot))
    if "obs.screen" in first_label.lower() or "obs.screen" not in final_label.lower():
        raise AssertionError(f"{mode}: selected screen is not the final chronological frame")
    if hashlib.sha256(first_image).digest() == hashlib.sha256(final_image).digest():
        raise AssertionError(f"{mode}: first and final observation frames are identical")
    page.get_by_role("button", name="Close").click()
    before_delay = page.evaluate("WeirdCaptchaTime.status()")
    before_delay_screenshot = output / f"{mode}-before-model-delay.png"
    after_delay_screenshot = output / f"{mode}-after-model-delay.png"
    page.screenshot(path=str(before_delay_screenshot), full_page=True)
    page.wait_for_timeout(700)
    after_delay = page.evaluate("WeirdCaptchaTime.status()")
    page.screenshot(path=str(after_delay_screenshot), full_page=True)
    delta = float(after_delay["task_time_ms"]) - float(before_delay["task_time_ms"])
    if mode == "live" and delta < 450:
        raise AssertionError(f"live task time did not advance through the model delay: {delta}")
    if mode == "paused" and abs(delta) > 2:
        raise AssertionError(f"paused task time advanced through the model delay: {delta}")
    return {
        "available": True,
        "before_capture": before,
        "after_capture": page.evaluate("WeirdCaptchaTime.status()"),
        "frame_count": 6,
        "first_frame_label": first_label,
        "final_frame_label": final_label,
        "viewer_screenshot": viewer_screenshot.name,
        "first_frame_screenshot": first_screenshot.name,
        "obs_screen_final_frame_screenshot": final_screenshot.name,
        "before_model_delay_screenshot": before_delay_screenshot.name,
        "after_model_delay_screenshot": after_delay_screenshot.name,
        "model_delay_task_time_delta_ms": delta,
        "synthetic_stream": synthetic_stream,
    }


def capture_static_observations(output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="first-change-static-evidence-") as temporary_name:
        temporary = Path(temporary_name)
        site = temporary / "site"
        profile = temporary / "fresh-playwright-profile"
        manifest = export_dashboard(site, copy_media=False)
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(site)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                context = playwright.chromium.launch_persistent_context(
                    str(profile),
                    headless=True,
                    viewport=STATIC_VIEWPORT,
                    device_scale_factor=1,
                    args=["--auto-accept-this-tab-capture"],
                )
                native_records: dict[str, Any] = {}
                for mode in ("live", "paused"):
                    page = context.new_page()
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.on(
                        "console",
                        lambda message: errors.append(message.text) if message.type == "error" else None,
                    )
                    page.goto(
                        f"http://127.0.0.1:{server.server_port}/play/"
                        f"?environment={ENVIRONMENT}&attempt=0&difficulty=4&interaction=full",
                        wait_until="networkidle",
                    )
                    expect(page.locator('.tracking-captcha[data-interaction="full"]')).to_be_visible()
                    page.locator(".tracking-arm").click()
                    page.wait_for_timeout(300)
                    page.get_by_role("button", name="Expand observation controls").click()
                    expect(page.get_by_role("button", name="Capture model observation")).to_be_enabled()
                    native_records[mode] = inspect_static_mode(page, mode, output, synthetic_stream=False)
                    page.close()
                context.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
    if errors:
        raise AssertionError(f"static observation browser errors: {errors}")
    synthetic_records: dict[str, Any] = {}
    if not all(record.get("available") for record in native_records.values()):
        synthetic_output = output / "synthetic_inspector_ui"
        synthetic_output.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="first-change-static-synthetic-evidence-") as temporary_name:
            temporary = Path(temporary_name)
            site = temporary / "site"
            manifest = export_dashboard(site, copy_media=False)
            server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(site)))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    for mode in ("live", "paused"):
                        context = browser.new_context(viewport=STATIC_VIEWPORT, device_scale_factor=1)
                        page = context.new_page()
                        page.goto(
                            f"http://127.0.0.1:{server.server_port}/play/"
                            f"?environment={ENVIRONMENT}&attempt=0&difficulty=4&interaction=full",
                            wait_until="networkidle",
                        )
                        expect(page.locator('.tracking-captcha[data-interaction="full"]')).to_be_visible()
                        page.locator(".tracking-arm").click()
                        page.wait_for_timeout(300)
                        page.get_by_role("button", name="Expand observation controls").click()
                        expect(page.get_by_role("button", name="Capture model observation")).to_be_enabled()
                        synthetic_records[mode] = inspect_static_mode(
                            page, mode, synthetic_output, synthetic_stream=True
                        )
                        page.close()
                        context.close()
                    browser.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)
    result = {
        "environment": ENVIRONMENT,
        "difficulty": 4,
        "interaction": "full",
        "export": manifest["browser_play"],
        "public_static_observations": native_records,
        "synthetic_inspector_ui": synthetic_records,
        "capture_method": {
            "browser": "isolated headless Playwright Chromium",
            "fresh_temporary_profile": True,
            "server": "local loopback static export",
            "stream": "browser-native navigator.mediaDevices.getDisplayMedia selected isolated tab",
            "picker_automation": "Chromium auto-accept-this-tab-capture",
            "synthetic_stream_override": False,
        },
    }
    write_json(output / "summary.json", result)
    return result


def main() -> None:
    args = parse_args()
    output = args.out_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="first-change-visible-evidence-") as temporary_name:
        temporary = Path(temporary_name)
        materialized_root = temporary / "materialized"
        materializer.materialize_environment(ENV_ROOT, materialized_root)
        tasks_root = materialized_root / ENVIRONMENT / "tasks"
        original = load_task(ORIGINAL_TASK)
        original_public, original_truth = generate_task_state(original, EVIDENCE_SEED)
        l4_full = load_task(controlled_task(tasks_root, 4, "full"))
        l4_full_public, l4_full_truth = generate_task_state(l4_full, EVIDENCE_SEED)
        if without_identity(original_public) != without_identity(l4_full_public):
            raise AssertionError("fixed-seed L4/full public world changed the uncontrolled original")
        if without_identity(original_truth) != without_identity(l4_full_truth):
            raise AssertionError("fixed-seed L4/full goal changed the uncontrolled original")
        baseline = {
            "seed": EVIDENCE_SEED,
            "uncontrolled_l4_world_fingerprint_without_identity": fingerprint(original_public),
            "controlled_l4_full_world_fingerprint_without_identity": fingerprint(l4_full_public),
            "uncontrolled_l4_truth_fingerprint_without_identity": fingerprint(original_truth),
            "controlled_l4_full_truth_fingerprint_without_identity": fingerprint(l4_full_truth),
            "public_state_preserved": True,
            "ground_truth_preserved": True,
            "identity_only_differences": ["task_id", "challenge_id", "control_condition"],
        }
        write_json(output / "baseline-preservation.json", baseline)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                visible = capture_visible_states(browser, tasks_root, temporary / "visible-browser-state", output / "visible_states")
            finally:
                browser.close()
    static_observations = capture_static_observations(output / "static_observations")
    summary = {
        "environment": ENVIRONMENT,
        "baseline": {"difficulty": 4, "interaction": "full", "real_time": "live"},
        "baseline_preservation": baseline,
        "visible_states": visible,
        "static_observations": static_observations,
    }
    write_json(output / "capture-summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
