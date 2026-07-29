#!/usr/bin/env python3
"""Capture inspectable controllability evidence for Photograph Eats the Room.

The browser solve matrix checks every controlled condition.  This companion
capture records the evidence that is otherwise hard to inspect from a matrix:
the uncontrolled L4 task beside controlled L4, visible L1–L5 changes, the
two L4 input surfaces on the same world, and the target task's actual static
browser observation viewer in live and paused modes.
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


ENVIRONMENT = "photograph_eats_the_room_env"
MECHANIC = "photograph_eats_the_room"
ENV_ROOT = ROOT / "benchmarks" / "weird_captcha_gym" / "environments" / ENVIRONMENT
LOCAL_VIEWPORT = browser_smoke.observation_viewport(ENV_ROOT)
STATIC_VIEWPORT = {"width": 1440, "height": 1000}
EVIDENCE_SEED = "photograph-room-controllability-evidence-v1"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture baseline, level, interaction, and model-observation evidence for Photograph Eats the Room."
    )
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
    payload = json.dumps(without_identity(value), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def controlled_task(tasks_root: Path, difficulty: int, interaction: str) -> Path:
    return browser_smoke.controlled_task(tasks_root, difficulty, interaction)


def visible_profile(public: dict[str, Any]) -> dict[str, Any]:
    condition = public.get("control_condition") or {}
    parameters = dict(condition.get("difficulty_parameters") or {})
    return {
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "difficulty": condition.get("difficulty"),
        "interaction": condition.get("interaction", "simplified"),
        "world_fingerprint_without_identity": fingerprint(public),
        "sources": len(public["sources"]),
        "source_offset": parameters.get("source_offset", 2.25),
        "void_width": round(float(public["room"]["void"]["x2"]) - float(public["room"]["void"]["x1"]), 2),
        "capture_range": public["qualification"]["capture_range"],
        "socket_tolerance": public["sockets"][0]["tolerance"],
        "angle_tolerance_deg": parameters.get("angle_tolerance_deg", 10),
        "bridge_half_width": public["qualification"]["bridge_half_width"],
        "door_half_width": parameters.get("door_half_width", 0.45),
        "plane_rotation_step_deg": public["controls"]["plane_rotation_step_deg"],
        "plane_scale_step": public["controls"]["plane_scale_step"],
    }


def exercise_historical_hybrid_inputs(page: Any, *, output: Path, label: str) -> dict[str, Any]:
    """Prove the historically advertised keyboard routes remain usable.

    This uses only the rendered task, its visible readout, and ordinary
    keyboard input.  The capture key may legitimately either load a negative
    or report that no geometry is framed at the current camera position.
    """
    root = page.locator(".photo-room")
    rail = page.locator(".photo-stage-rail span")
    expect(rail).to_have_text("WASD MOVE · ← → TURN · C CAPTURE")
    root.focus()
    before_x = float(root.get_attribute("data-camera-x") or 0)
    before_yaw = float(root.get_attribute("data-yaw") or 0)
    page.keyboard.down("w")
    page.wait_for_timeout(220)
    page.keyboard.up("w")
    after_x = float(root.get_attribute("data-camera-x") or 0)
    if after_x <= before_x + 0.1:
        raise AssertionError(f"held W did not move the historical hybrid surface: {before_x} -> {after_x}")
    page.keyboard.press("ArrowRight")
    after_yaw = float(root.get_attribute("data-yaw") or 0)
    if after_yaw == before_yaw:
        raise AssertionError(f"ArrowRight did not turn the historical hybrid surface: {before_yaw} -> {after_yaw}")
    page.keyboard.press("c")
    page.wait_for_timeout(50)
    readout = page.locator(".photo-foot .readout").inner_text()
    carrying = root.get_attribute("data-carrying") or ""
    if not carrying and "CAPTURE FAILED" not in readout:
        raise AssertionError(f"C did not invoke the historical capture route: {readout!r}")
    screenshot = output / f"{label}-hybrid-inputs.png"
    page.screenshot(path=str(screenshot), full_page=False)
    return {
        "rail": rail.inner_text(),
        "held_w_camera_x": {"before": before_x, "after": after_x},
        "arrow_right_yaw": {"before": before_yaw, "after": after_yaw},
        "c_capture": {"carrying": carrying, "readout": readout},
        "screenshot": screenshot.name,
    }


def capture_local_screens(
    browser: Any,
    *,
    original_task: Path,
    tasks_root: Path,
    work_root: Path,
    output: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    output.mkdir(parents=True, exist_ok=True)
    selected: list[tuple[str, Path, str]] = [("original-l4-uncontrolled", original_task, "simplified")]
    selected.extend((f"d{level}-simplified", controlled_task(tasks_root, level, "simplified"), "simplified") for level in range(1, 6))
    selected.append(("d4-full", controlled_task(tasks_root, 4, "full"), "full"))
    result: dict[str, dict[str, Any]] = {}
    historical_hybrid_inputs: dict[str, dict[str, Any]] = {}
    for label, task_path, interaction in selected:
        state_dir = work_root / label
        state_dir.mkdir(parents=True, exist_ok=True)
        process, port = browser_smoke.start_server(task_path, MECHANIC, interaction, state_dir)
        page = browser.new_page(viewport=LOCAL_VIEWPORT, device_scale_factor=1)
        try:
            # The missing descriptor is the local browser contract for serving
            # the setup seed on the first state request rather than replacing
            # it with a fresh challenge.
            current_task_path = state_dir / "current_task.json"
            current_task_text = current_task_path.read_text(encoding="utf-8")
            current_task_path.unlink()
            try:
                page.goto(f"http://127.0.0.1:{port}/?time_mode=live", wait_until="networkidle")
            finally:
                current_task_path.write_text(current_task_text, encoding="utf-8")
            root = page.locator(".photo-room")
            expect(root).to_be_visible()
            expect(root).to_have_attribute("data-interaction", interaction)
            if interaction == "full":
                expect(page.locator("#photo-room-canvas")).to_be_visible()
                expect(page.locator("#photo-capture")).to_be_hidden()
            else:
                expect(page.locator("#photo-capture")).to_be_visible()
                expect(page.locator("#photo-plane-pad")).to_be_visible()
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(200)
            page.screenshot(path=str(output / f"{label}.png"), full_page=False)
            result[label] = visible_profile(browser_smoke.read_json(state_dir / "public_state.json"))
            if label in {"original-l4-uncontrolled", "d4-simplified"}:
                historical_hybrid_inputs[label] = exercise_historical_hybrid_inputs(page, output=output, label=label)
        finally:
            page.close()
            process.terminate()
            try:
                process.wait(timeout=3)
            except Exception:  # pragma: no cover - cleanup fallback.
                process.kill()
    if result["original-l4-uncontrolled"]["world_fingerprint_without_identity"] != result["d4-simplified"]["world_fingerprint_without_identity"]:
        raise AssertionError("the visible uncontrolled and controlled L4 rooms did not preserve one generated world")
    if result["d4-simplified"]["world_fingerprint_without_identity"] != result["d4-full"]["world_fingerprint_without_identity"]:
        raise AssertionError("the visible simplified/full L4 pair did not preserve one generated world")
    write_json(output / "visible-worlds.json", result)
    write_json(output / "historical-hybrid-inputs.json", historical_hybrid_inputs)
    return result, historical_hybrid_inputs


def install_page_snapshot_capture(page: Any) -> None:
    """Provide the observation viewer with the rendered task screen in headless mode."""
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
          // captureStream emits frames only when the bitmap changes.  Pulse a
          // single corner pixel so this uses the real video-frame pipeline.
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
    page.goto(
        f"{base_url}/play/?environment={ENVIRONMENT}&attempt=0&difficulty=4&interaction=full&time_mode={mode}",
        wait_until="networkidle",
    )
    expect(page.locator(".photo-room[data-interaction='full']")).to_be_visible()
    expect(page.locator("#photo-room-canvas")).to_be_visible()
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
    page.wait_for_timeout(1_000)
    expect(page.locator(".weird-demo-observation")).to_have_attribute("data-open", "true", timeout=10_000)
    frames = page.locator(".weird-demo-frame").count()
    if frames < 1:
        raise AssertionError("model observation viewer contains no captured frame")
    expect(page.locator("[data-demo-screen-label]")).to_contain_text("obs.screen")
    page.wait_for_function(f"WeirdCaptchaTime.status().state === '{expected_state}'")
    page.screenshot(path=str(output / f"{mode}-model-observation.png"), full_page=True)
    return {
        "mode": mode,
        "clock_initial": initial,
        "clock_after_350ms_wait": after_wait,
        "task_time_delta_ms": delta,
        "viewer_meta": page.locator("[data-demo-observation-meta]").inner_text(),
        "viewer_label": page.locator("[data-demo-screen-label]").inner_text(),
        "frames": frames,
        "clock_after_capture": page.evaluate("WeirdCaptchaTime.status()"),
    }


def capture_static_observations(output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="photograph-room-static-evidence-") as temporary:
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
    result = {
        "environment": ENVIRONMENT,
        "difficulty": 4,
        "interaction": "full",
        "export": manifest["browser_play"],
        "observations": observations,
    }
    write_json(output / "summary.json", result)
    return result


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir.resolve()
    original_task = ENV_ROOT / "tasks" / f"{MECHANIC}_seed_0001" / "task.json"
    if not original_task.is_file():
        raise FileNotFoundError(original_task)

    with tempfile.TemporaryDirectory(prefix="photograph-room-evidence-") as temporary:
        work_root = Path(temporary)
        materialized_root = work_root / "materialized"
        materializer.materialize_environment(ENV_ROOT, materialized_root)
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
            visible, historical_hybrid_inputs = capture_local_screens(
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
        "historical_hybrid_inputs": historical_hybrid_inputs,
        "model_observations": observations["observations"],
    }
    write_json(out_dir / "capture-summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
