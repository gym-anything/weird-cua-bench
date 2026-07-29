#!/usr/bin/env python3
"""Capture the visible evidence required for Orbital Docking Customs controls.

This supplements the full browser solve matrices with three deliberately
inspectable items: the uncontrolled L4 browser state beside the controlled
L4 state, every simplified difficulty at its initial visible state, and the
actual screen captured by the static browser's live and paused observation
viewer.  The matrix smoke remains the authoritative browser solve/grading
check; this tool records the missing visual comparison evidence.
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


ENVIRONMENT = "orbital_docking_customs_env"
MECHANIC = "orbital_docking_customs"
ENV_ROOT = ROOT / "benchmarks" / "weird_captcha_gym" / "environments" / ENVIRONMENT
LOCAL_VIEWPORT = browser_smoke.observation_viewport(ENV_ROOT)
STATIC_VIEWPORT = {"width": 1280, "height": 720}
EVIDENCE_SEED = "orbital-docking-controllability-evidence-v1"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture inspectable baseline, level, interaction, and observation evidence for Orbital Docking Customs."
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "benchmarks" / "weird_captcha_gym" / "environments" / ENVIRONMENT / "evidence_docs",
        help="Evidence directory (defaults to the environment's evidence_docs directory).",
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
    payload = json.dumps(without_identity(value), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def controlled_task(tasks_root: Path, difficulty: int, interaction: str) -> Path:
    return browser_smoke.controlled_task(tasks_root, difficulty, interaction)


def capture_local_screens(
    browser: Any,
    *,
    original_task: Path,
    tasks_root: Path,
    work_root: Path,
    output: Path,
) -> dict[str, dict[str, Any]]:
    output.mkdir(parents=True, exist_ok=True)
    selected: list[tuple[str, Path, str]] = [("original-l4-uncontrolled", original_task, "simplified")]
    selected.extend((f"d{level}-simplified", controlled_task(tasks_root, level, "simplified"), "simplified") for level in range(1, 6))
    selected.append(("d4-full", controlled_task(tasks_root, 4, "full"), "full"))
    result: dict[str, dict[str, Any]] = {}
    for label, task_path, interaction in selected:
        state_dir = work_root / label
        state_dir.mkdir(parents=True, exist_ok=True)
        process, port = browser_smoke.start_server(task_path, MECHANIC, interaction, state_dir)
        page = browser.new_page(viewport=LOCAL_VIEWPORT, device_scale_factor=1)
        try:
            # The local server uses a missing current-task descriptor as the
            # explicit instruction to serve the setup seed rather than issue a
            # fresh challenge for the first /state request. This is the same
            # browser-start contract exercised by the full matrix smoke.
            current_task_path = state_dir / "current_task.json"
            current_task_text = current_task_path.read_text(encoding="utf-8")
            current_task_path.unlink()
            try:
                page.goto(f"http://127.0.0.1:{port}/?time_mode=live", wait_until="networkidle")
            finally:
                current_task_path.write_text(current_task_text, encoding="utf-8")
            expect(page.locator(".ivv-orbital-docking-customs")).to_be_visible()
            if label == "d4-full":
                expect(page.locator(".orbital-keyboard-note")).to_be_visible()
            else:
                expect(page.locator("[data-orbit=\"thrust\"]")).to_be_visible()
            # Each evidence image is the first 1280×720 task observation.
            # Reset any automatic focus scroll from control assertions before
            # the capture so every adjacent-level image has one comparable
            # browser viewport.
            page.evaluate("window.scrollTo(0, 0)")
            # Canvas rasterization is asynchronous in headless Chromium.
            # Asking the browser for its PNG first flushes the entire scene,
            # avoiding partial debris/scan captures in a screenshot taken on
            # the initial render frame.
            canvas_data_url = page.evaluate("document.getElementById('orbital-canvas').toDataURL('image/png')")
            if not isinstance(canvas_data_url, str) or len(canvas_data_url) < 1_000:
                raise AssertionError("orbital canvas did not rasterize before evidence capture")
            encoded_canvas = canvas_data_url.partition(",")[2]
            (output / f"{label}-canvas.png").write_bytes(base64.b64decode(encoded_canvas))
            page.wait_for_timeout(250)
            page.screenshot(path=str(output / f"{label}.png"), full_page=False)
            public = browser_smoke.read_json(state_dir / "public_state.json")
            condition = public.get("control_condition") or {}
            result[label] = {
                "task_id": public["task_id"],
                "challenge_id": public["challenge_id"],
                "difficulty": condition.get("difficulty"),
                "interaction": condition.get("interaction", "simplified"),
                "world_fingerprint_without_identity": fingerprint(public),
                "debris": len(public["debris"]),
                "beacons": len(public["beacons"]),
                "station_motion": {
                    "y_amplitude": public["station"]["y_amplitude"],
                    "rotation_deg_per_tick": public["station"]["rotation_deg_per_tick"],
                },
                "physics": {
                    key: public["physics"][key]
                    for key in ("fuel", "dock_distance", "dock_speed", "angle_tolerance_deg", "max_ticks")
                },
            }
        finally:
            page.close()
            process.terminate()
            try:
                process.wait(timeout=3)
            except Exception:  # pragma: no cover - cleanup fallback.
                process.kill()
    if result["original-l4-uncontrolled"]["world_fingerprint_without_identity"] != result["d4-simplified"]["world_fingerprint_without_identity"]:
        raise AssertionError("the visible uncontrolled and controlled L4 runs did not preserve one generated world")
    if result["d4-simplified"]["world_fingerprint_without_identity"] != result["d4-full"]["world_fingerprint_without_identity"]:
        raise AssertionError("the visible simplified/full L4 pair did not preserve one generated world")
    write_json(output / "visible-worlds.json", result)
    return result


def install_page_snapshot_capture(page: Any) -> None:
    """Feed the browser inspector a 1280×720 image of the task it just rendered.

    The browser demo normally asks the operator to select the current tab. In
    a headless evidence run there is no picker, so the equivalent visible page
    image is supplied to the test media stream. The inspector still performs
    its own timed capture, frame accounting, and paused-clock behavior.
    """
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
          // canvas.captureStream only emits frames when its bitmap changes.
          // Toggle one unobtrusive corner pixel so the browser's real capture
          // pipeline receives the one-frame observation requested here.
          let capturePulse = false;
          const native = window.WeirdCaptchaTime?.native || window;
          native.setInterval(() => {
            capturePulse = !capturePulse;
            context.fillStyle = capturePulse ? '#000001' : '#000000';
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
    page.goto(
        f"{base_url}/play/?environment={ENVIRONMENT}&attempt=0&difficulty=4&interaction=full&time_mode={mode}",
        wait_until="networkidle",
    )
    expect(page.locator(".ivv-orbital-docking-customs")).to_be_visible()
    expect(page.locator(".orbital-keyboard-note")).to_be_visible()
    expect(page.get_by_role("button", name="Expand observation controls")).to_be_visible()
    page.get_by_role("button", name="Expand observation controls").click()
    expect(page.get_by_role("button", name="Capture model observation")).to_be_enabled()
    expected_state = "paused" if mode == "paused" else "running"
    page.wait_for_function(f"WeirdCaptchaTime.status().state === '{expected_state}'")
    initial = page.evaluate("WeirdCaptchaTime.status()")
    page.wait_for_timeout(350)
    after_wait = page.evaluate("WeirdCaptchaTime.status()")
    delta = float(after_wait["task_time_ms"]) - float(initial["task_time_ms"])
    if mode == "live" and delta < 250:
        raise AssertionError(f"live observation clock did not advance through waiting: {delta}")
    if mode == "paused" and abs(delta) > 2:
        raise AssertionError(f"paused observation clock advanced through waiting: {delta}")
    install_page_snapshot_capture(page)
    page.get_by_role("button", name="Capture model observation").click()
    # A static one-frame observation still traverses the browser's video-frame
    # callback before the viewer is made visible. Give that callback one
    # rendering turn before asserting the public viewer state.
    page.wait_for_timeout(1_000)
    expect(page.locator(".weird-demo-observation")).to_have_attribute("data-open", "true", timeout=10_000)
    expect(page.locator(".weird-demo-frame")).to_have_count(1)
    expect(page.locator("[data-demo-screen-label]")).to_contain_text("obs.screen")
    if mode == "paused":
        page.wait_for_function("WeirdCaptchaTime.status().state === 'paused'")
    else:
        page.wait_for_function("WeirdCaptchaTime.status().state === 'running'")
    page.screenshot(path=str(output / f"{mode}-model-observation.png"), full_page=True)
    return {
        "mode": mode,
        "clock_initial": initial,
        "clock_after_350ms_wait": after_wait,
        "task_time_delta_ms": delta,
        "viewer_meta": page.locator("[data-demo-observation-meta]").inner_text(),
        "viewer_label": page.locator("[data-demo-screen-label]").inner_text(),
        "frames": page.locator(".weird-demo-frame").count(),
        "clock_after_capture": page.evaluate("WeirdCaptchaTime.status()"),
    }


def capture_static_observations(output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="orbital-docking-static-evidence-") as temporary:
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
    result = {"environment": ENVIRONMENT, "difficulty": 4, "interaction": "full", "export": manifest["browser_play"], "observations": observations}
    write_json(output / "summary.json", result)
    return result


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir.resolve()
    env_root = ENV_ROOT
    original_task = env_root / "tasks" / f"{MECHANIC}_seed_0001" / "task.json"
    if not original_task.is_file():
        raise FileNotFoundError(original_task)

    with tempfile.TemporaryDirectory(prefix="orbital-docking-evidence-") as temporary:
        work_root = Path(temporary)
        materialized_root = work_root / "materialized"
        materializer.materialize_environment(env_root, materialized_root)
        tasks_root = materialized_root / ENVIRONMENT / "tasks"

        original = load_task(original_task)
        l4_simplified = load_task(controlled_task(tasks_root, 4, "simplified"))
        l4_full = load_task(controlled_task(tasks_root, 4, "full"))
        original_public, original_truth = generate_task_state(original, EVIDENCE_SEED)
        simplified_public, simplified_truth = generate_task_state(l4_simplified, EVIDENCE_SEED)
        full_public, full_truth = generate_task_state(l4_full, EVIDENCE_SEED)
        if without_identity(original_public) != without_identity(simplified_public) or without_identity(original_truth) != without_identity(simplified_truth):
            raise AssertionError("fixed-seed controlled L4 no longer preserves the original task")
        if without_identity(simplified_public) != without_identity(full_public) or without_identity(simplified_truth) != without_identity(full_truth):
            raise AssertionError("the L4 interaction pair no longer preserves the generated world")
        write_json(out_dir / "baseline-preservation.json", {
            "seed": EVIDENCE_SEED,
            "original_l4_world_fingerprint_without_identity": fingerprint(original_public),
            "controlled_l4_simplified_world_fingerprint_without_identity": fingerprint(simplified_public),
            "controlled_l4_full_world_fingerprint_without_identity": fingerprint(full_public),
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
        "baseline": {"difficulty": 4, "interaction": "simplified", "real_time": "live"},
        "visible_states": visible,
        "model_observations": observations["observations"],
    }
    write_json(out_dir / "capture-summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
