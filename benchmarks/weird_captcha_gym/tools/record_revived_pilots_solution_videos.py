#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.weird_captcha_gym.tools.record_next_ten_solution_videos import (  # noqa: E402
    _inject_walkthrough_chrome,
    _probe,
    _sha256,
    _transcode,
)
from benchmarks.weird_captcha_gym.tools.smoke_incubator_batch_one_ui import (  # noqa: E402
    BENCH_ROOT,
    GRADER_ROOT,
    SOLVER_ROOT,
    exported_payload,
    load_module,
    run_task_verifier,
    start_server,
)


MECHANICS = ("moving_checkbox_evasive_button", "reverse_identity_gate")
WALKTHROUGHS = {
    "moving_checkbox_evasive_button": (
        "Scroll-Cage Checkbox",
        "Align three portal pairs carried by four independent scroll surfaces, then use only the visible cursor-repulsion field to herd the physical checkbox through every divider and into its final clamp.",
    ),
    "reverse_identity_gate": (
        "Four-Tab Robot Handshake",
        "Deploy four real browser tabs as robot limbs, switch to the pulsing glyph, directionally track each moving phase while holding contact, and seal eight relays into one distributed identity ledger.",
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record frozen-contract solution films for the two rebuilt pilots.")
    parser.add_argument("--out-dir", type=Path, default=BENCH_ROOT / "evidence" / "incubator_batch_revived_v1" / "solution_videos")
    parser.add_argument("--port", type=int, default=9460)
    parser.add_argument("--seed-prefix", default="revived-pilots-solution-video")
    return parser.parse_args()


def contract_files(mechanic: str) -> dict[str, Path]:
    task_dir = BENCH_ROOT / "environments" / f"{mechanic}_env" / "tasks" / f"{mechanic}_seed_0001"
    return {
        "task": task_dir / "task.json",
        "verifier": task_dir / "verifier.py",
        "generator": BENCH_ROOT / "shared_scripts" / "incubator_generators" / f"{mechanic}.py",
        "frontend": BENCH_ROOT / "shared_runtime" / "app" / "mechanics" / f"{mechanic}.js",
        "styles": BENCH_ROOT / "shared_runtime" / "app" / "mechanics" / f"{mechanic}.css",
        "grader": GRADER_ROOT / f"{mechanic}.py",
        "solver": SOLVER_ROOT / f"{mechanic}.py",
        "server": BENCH_ROOT / "shared_runtime" / "server" / "weird_captcha_server.py",
        "setup": BENCH_ROOT / "shared_scripts" / "setup_task.py",
    }


def snapshot() -> dict[str, dict[str, str]]:
    return {mechanic: {label: _sha256(path) for label, path in contract_files(mechanic).items()} for mechanic in MECHANICS}


def validate(mechanic: str, state_dir: Path, temporary: Path) -> tuple[dict, dict, dict]:
    exported = exported_payload(state_dir)
    server_grade = exported["result"].get("server_grade") or {}
    grader = load_module(GRADER_ROOT / f"{mechanic}.py", f"revived_video_grader_{mechanic}")
    direct_grade = grader.grade(exported["result"], exported["ground_truth"], exported["public_state"])
    verifier = run_task_verifier(mechanic, exported, temporary)
    for label, decision in (("server", server_grade), ("direct", direct_grade), ("verifier", verifier)):
        if decision.get("passed") is not True:
            raise AssertionError(f"{mechanic} {label} rejected recorded solution: {decision}")
    return server_grade, direct_grade, verifier


def record_scroll(playwright, browser, args, temporary: Path) -> dict[str, Any]:
    mechanic = "moving_checkbox_evasive_button"
    state_dir = temporary / mechanic / "state"
    capture_dir = temporary / mechanic / "captures"
    raw_dir = temporary / mechanic / "raw"
    state_dir.mkdir(parents=True)
    capture_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    webm = args.out_dir / f"{mechanic}-solution.webm"
    mp4 = args.out_dir / f"{mechanic}-solution.mp4"
    server = start_server(mechanic, args.port, state_dir, args.seed_prefix)
    context = browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1,
                                  record_video_dir=str(raw_dir), record_video_size={"width": 1280, "height": 720})
    page = context.new_page()
    video = page.video
    errors: list[str] = []
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        title, description = WALKTHROUGHS[mechanic]
        page.set_content("<!doctype html><html><body></body></html>")
        _inject_walkthrough_chrome(page, title, description, show_intro=True)
        page.wait_for_timeout(1900)
        page.goto(f"http://127.0.0.1:{args.port}/", wait_until="networkidle")
        expect(page.locator(".scroll-cage")).to_be_visible()
        _inject_walkthrough_chrome(page, title, description, show_intro=False)
        page.wait_for_timeout(700)
        solver = load_module(SOLVER_ROOT / f"{mechanic}.py", "revived_scroll_video_solver")
        solver.solve(page, state_dir, capture_dir, mechanic)
        expect(page.locator(".readout")).to_have_text("PASS", timeout=8_000)
        server_grade, direct_grade, verifier = validate(mechanic, state_dir, temporary)
        if errors:
            raise AssertionError(f"{mechanic} browser errors: {errors}")
        page.evaluate("message => window.__solutionVideoOverlay.showOutro(message)",
                      f"PASS · FIXED-STEP REPLAY ACCEPTED · {server_grade.get('feedback')}")
        page.wait_for_timeout(2100)
    finally:
        page.close()
        if video is not None:
            video.save_as(str(webm))
        context.close()
        server.terminate()
        try:
            server.wait(timeout=3)
        except Exception:
            server.kill()
    _transcode(webm, mp4)
    return {
        "title": WALKTHROUGHS[mechanic][0], "approach": WALKTHROUGHS[mechanic][1],
        "webm": webm.name, "mp4": mp4.name, "webm_sha256": _sha256(webm), "mp4_sha256": _sha256(mp4),
        "media": _probe(mp4), "server_grade": server_grade, "direct_grade": direct_grade,
        "verifier": verifier, "console_errors": errors,
    }


class FrameCapture:
    def __init__(self, folder: Path, fps: int = 8) -> None:
        self.folder = folder
        self.folder.mkdir(parents=True)
        self.index = 0
        self.fps = fps

    def take(self, page, repeats: int = 1, *, wait: bool = True) -> None:
        for _ in range(repeats):
            self.index += 1
            page.screenshot(path=str(self.folder / f"frame-{self.index:06d}.jpg"), type="jpeg", quality=82)
            if wait:
                page.wait_for_timeout(1000 / self.fps)


def encode_frames(frames: FrameCapture, webm: Path) -> None:
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-framerate", str(frames.fps),
        "-i", str(frames.folder / "frame-%06d.jpg"), "-an", "-c:v", "libvpx-vp9", "-crf", "30",
        "-b:v", "0", "-pix_fmt", "yuv420p", str(webm),
    ], check=True)


def record_tabs(playwright, browser, args, temporary: Path) -> dict[str, Any]:
    mechanic = "reverse_identity_gate"
    state_dir = temporary / mechanic / "state"
    frames_dir = temporary / mechanic / "frames"
    state_dir.mkdir(parents=True)
    frames = FrameCapture(frames_dir)
    webm = args.out_dir / f"{mechanic}-solution.webm"
    mp4 = args.out_dir / f"{mechanic}-solution.mp4"
    server = start_server(mechanic, args.port + 1, state_dir, args.seed_prefix)
    context = browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
    page = context.new_page()
    errors: list[str] = []
    context.on("page", lambda child: child.on("pageerror", lambda error: errors.append(str(error))))
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: errors.append(str(error)))
    tabs: dict[int, Any] = {}
    try:
        page.goto(f"http://127.0.0.1:{args.port + 1}/", wait_until="networkidle")
        expect(page.locator(".robot-master")).to_be_visible()
        title, description = WALKTHROUGHS[mechanic]
        _inject_walkthrough_chrome(page, title, description, show_intro=True)
        frames.take(page, 16)
        page.evaluate("() => window.__solutionVideoOverlay.hideIntro()")
        frames.take(page, 6)
        for station in range(4):
            page.bring_to_front()
            with page.expect_popup() as popup:
                page.locator(f'[data-deploy="{station}"]').click()
            child = popup.value
            child.wait_for_load_state("domcontentloaded")
            expect(child.locator(f'[data-station-page="{station}"]')).to_be_visible()
            tabs[station] = child
            page.bring_to_front()
            frames.take(page, 4)
        frames.take(page, 8)
        truth = json.loads((state_dir / "ground_truth.json").read_text(encoding="utf-8"))
        for stage_data in truth["stages"]:
            station = int(stage_data["station"])
            child = tabs[station]
            child.bring_to_front()
            root = child.locator(f'[data-station-page="{station}"]')
            expect(root).to_have_attribute("data-active", "true", timeout=5_000)
            frames.take(child, 4)
            key = "d" if int(stage_data["pulse_speed_deg_per_tick"]) > 0 else "a"
            child.keyboard.down(key)
            contact = child.locator("#station-contact")
            bounds = contact.bounding_box()
            if not bounds:
                raise AssertionError("station contact missing")
            child.mouse.move(bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2)
            child.mouse.down()
            for _ in range(150):
                frames.take(child)
                if root.get_attribute("data-active") == "false":
                    break
            else:
                raise AssertionError(f"station {station} did not seal inside capture window")
            child.mouse.up()
            child.keyboard.up(key)
            frames.take(child, 3)
        page.bring_to_front()
        frames.take(page, 8)
        page.locator("#robot-verify").click()
        expect(page.locator(".readout")).to_have_text("PASS", timeout=8_000)
        server_grade, direct_grade, verifier = validate(mechanic, state_dir, temporary)
        if errors:
            raise AssertionError(f"{mechanic} browser errors: {errors}")
        page.evaluate("message => window.__solutionVideoOverlay.showOutro(message)",
                      f"PASS · FOUR REAL TABS ACCEPTED · {server_grade.get('feedback')}")
        frames.take(page, 18)
    finally:
        for child in tabs.values():
            try:
                if not child.is_closed():
                    child.close()
            except Exception:
                pass
        page.close()
        context.close()
        server.terminate()
        try:
            server.wait(timeout=3)
        except Exception:
            server.kill()
    encode_frames(frames, webm)
    _transcode(webm, mp4)
    return {
        "title": WALKTHROUGHS[mechanic][0], "approach": WALKTHROUGHS[mechanic][1],
        "webm": webm.name, "mp4": mp4.name, "webm_sha256": _sha256(webm), "mp4_sha256": _sha256(mp4),
        "media": _probe(mp4), "server_grade": server_grade, "direct_grade": direct_grade,
        "verifier": verifier, "console_errors": errors,
        "capture_note": "Frame-accurate browser-tab montage; each frame is captured from the real active Playwright Page while ordinary inputs execute against the frozen live server.",
    }


def main() -> None:
    args = parse_args()
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("ffmpeg and ffprobe are required")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for mechanic in MECHANICS:
        (args.out_dir / f"{mechanic}-solution.webm").unlink(missing_ok=True)
        (args.out_dir / f"{mechanic}-solution.mp4").unlink(missing_ok=True)
    before = snapshot()
    manifest: dict[str, Any] = {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "task_implementations_modified": False,
        "capture_contract": "Ordinary browser input against frozen live tasks; server, direct grader, and exported verifier must all accept the exact recorded trajectory.",
        "frozen_contract_files": before,
        "videos": {},
    }
    with tempfile.TemporaryDirectory(prefix="revived-pilots-video-") as temp_name, sync_playwright() as playwright:
        temporary = Path(temp_name)
        browser = playwright.chromium.launch(headless=True)
        manifest["videos"]["moving_checkbox_evasive_button"] = record_scroll(playwright, browser, args, temporary)
        print("[1/2] PASS moving_checkbox_evasive_button", flush=True)
        manifest["videos"]["reverse_identity_gate"] = record_tabs(playwright, browser, args, temporary)
        print("[2/2] PASS reverse_identity_gate", flush=True)
        browser.close()
    after = snapshot()
    if before != after:
        raise AssertionError("a frozen task implementation changed during capture")
    manifest["frozen_contract_verified"] = True
    (args.out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({mechanic: manifest["videos"][mechanic]["media"] for mechanic in MECHANICS}, indent=2))


if __name__ == "__main__":
    main()
