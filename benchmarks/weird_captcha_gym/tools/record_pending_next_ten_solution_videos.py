#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
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
    _PacedPage,
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


MECHANICS = (
    "bureaucratic_signature_trap",
    "temporal_memory_first_change",
    "polyrhythm_customs",
    "exact_change_candy_cascade",
    "tiny_fps_customs",
    "thirty_year_time_wheel",
    "photograph_eats_the_room",
    "clockwork_doppelganger_customs",
    "recursive_dollhouse_smuggling",
    "flat_prisoner",
)

WALKTHROUGHS = {
    "bureaucratic_signature_trap": (
        "Bureaucratic Signature Trap",
        "Register all four displaced carbon sheets, expose the seeded original, then trace its exact multi-loop path in one continuous stroke.",
    ),
    "temporal_memory_first_change": (
        "First Change Memory",
        "Watch the one-shot moving field, scrub the review spool, inspect the earliest reversible event through the identity lens, then recover that carrier after settlement.",
    ),
    "polyrhythm_customs": (
        "Polyrhythm Customs",
        "Inspect four lanes separately, remember their taps, holds, and chords, then reproduce the complete interleaved score on A, S, D, and F.",
    ),
    "exact_change_candy_cascade": (
        "Exact-Change Candy Cascade",
        "Plan four legal adjacent swaps over the changing board, use deterministic cascades to reach the exact receipt, and never touch black licorice.",
    ),
    "tiny_fps_customs": (
        "Tiny FPS Customs",
        "Navigate the generated maze, compare full warrant traits against close protected look-alikes, and clear all four warranted travellers without a protected hit.",
    ),
    "thirty_year_time_wheel": (
        "Thirty-Year Time Wheel",
        "Physically wind month, year, and day to the target date, catch any release momentum, then lock only when all three rings are settled.",
    ),
    "photograph_eats_the_room": (
        "The Photograph Eats the Room",
        "Frame two real source geometries, carry and align their photograph planes, develop both changes into collision reality, then traverse to the terminal.",
    ),
    "clockwork_doppelganger_customs": (
        "Clockwork Doppelgänger Customs",
        "Record three complete action loops, derive their phases from the handoffs, then run one synchronized master cycle from pickup through stamping and delivery.",
    ),
    "recursive_dollhouse_smuggling": (
        "Recursive Dollhouse Smuggling",
        "Move one canonical gate through the giant projection, then transfer the parcel through miniature, human, and giant frames without collision or reset.",
    ),
    "flat_prisoner": (
        "The Flat Prisoner",
        "Orbit, pan, and dolly the 3D prison until distant ledges join in projection, freeze that topology once, then physically jump to the exit.",
    ),
}

# These pauses exist only in this capture wrapper. They make otherwise
# near-instant scripted motor actions legible in the film and never change a
# task, generator, frontend, grader, verifier, or solver file.
PACE = {
    "bureaucratic_signature_trap": {"key_press_ms": 0, "mouse_move_ms": 10},
    "temporal_memory_first_change": {"key_press_ms": 10, "mouse_move_ms": 0},
    "tiny_fps_customs": {"key_press_ms": 7, "mouse_move_ms": 0},
    "thirty_year_time_wheel": {"key_press_ms": 0, "mouse_move_ms": 16},
    "photograph_eats_the_room": {"key_press_ms": 8, "mouse_move_ms": 10},
    "clockwork_doppelganger_customs": {"key_press_ms": 6, "mouse_move_ms": 0},
    "recursive_dollhouse_smuggling": {"key_press_ms": 0, "mouse_move_ms": 13},
}


class _PacedMouse:
    def __init__(self, page: Any, pause_ms: int) -> None:
        self._page = page
        self._mouse = page.mouse
        self._pause_ms = pause_ms
        self._position: tuple[float, float] | None = None

    def move(self, x: float, y: float, *, steps: int = 1) -> None:
        target = (float(x), float(y))
        count = max(1, int(steps))
        if self._pause_ms and self._position is not None and count > 1:
            start = self._position
            for index in range(1, count + 1):
                amount = index / count
                self._mouse.move(
                    start[0] + (target[0] - start[0]) * amount,
                    start[1] + (target[1] - start[1]) * amount,
                )
                self._page.wait_for_timeout(self._pause_ms)
        else:
            self._mouse.move(*target, steps=count)
            if self._pause_ms:
                self._page.wait_for_timeout(self._pause_ms)
        self._position = target

    def click(self, x: float, y: float, **kwargs: Any) -> None:
        self._mouse.click(x, y, **kwargs)
        self._position = (float(x), float(y))
        if self._pause_ms:
            self._page.wait_for_timeout(max(35, self._pause_ms))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._mouse, name)


class _CapturePage(_PacedPage):
    def __init__(self, page: Any, *, key_press_ms: int, mouse_move_ms: int) -> None:
        super().__init__(page, key_press_ms=key_press_ms, minimum_short_wait_ms=0)
        self.mouse = _PacedMouse(page, mouse_move_ms)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record verified clean solution videos for the audited pending next-ten cohort."
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=BENCH_ROOT / "evidence" / "pending_next_ten_v2" / "solution_videos",
    )
    parser.add_argument("--port", type=int, default=9210)
    parser.add_argument("--seed-prefix", default="pending-next-ten-v2-solution-video")
    parser.add_argument("--mechanic", action="append", choices=MECHANICS)
    return parser.parse_args()


def _contract_files(mechanic: str) -> dict[str, Path]:
    task_dir = BENCH_ROOT / "environments" / f"{mechanic}_env" / "tasks" / f"{mechanic}_seed_0001"
    return {
        "task": task_dir / "task.json",
        "verifier": task_dir / "verifier.py",
        "generator": BENCH_ROOT / "shared_scripts" / "incubator_generators" / f"{mechanic}.py",
        "setup": BENCH_ROOT / "shared_scripts" / "setup_task.py",
        "frontend": BENCH_ROOT / "shared_runtime" / "app" / "mechanics" / f"{mechanic}.js",
        "styles": BENCH_ROOT / "shared_runtime" / "app" / "mechanics" / f"{mechanic}.css",
        "shared_frontend": BENCH_ROOT / "shared_runtime" / "app" / "app.js",
        "shared_styles": BENCH_ROOT / "shared_runtime" / "app" / "styles.css",
        "server": BENCH_ROOT / "shared_runtime" / "server" / "weird_captcha_server.py",
        "grader": GRADER_ROOT / f"{mechanic}.py",
        "solver": SOLVER_ROOT / f"{mechanic}.py",
        "solver_common": SOLVER_ROOT / "reviewed_overhaul_common.py",
    }


def _contract_snapshot(mechanics: tuple[str, ...]) -> dict[str, dict[str, str]]:
    return {
        mechanic: {label: _sha256(path) for label, path in _contract_files(mechanic).items()}
        for mechanic in mechanics
    }


def main() -> None:
    args = parse_args()
    mechanics = tuple(args.mechanic or MECHANICS)
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("solution video export requires ffmpeg and ffprobe")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    contract_before = _contract_snapshot(mechanics)
    manifest: dict[str, Any] = {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "task_implementations_modified": False,
        "capture_contract": (
            "Clean ordinary-input Playwright solve against the live frozen task server. "
            "Capture-only pauses affect presentation, never task code or acceptance."
        ),
        "frozen_contract_files": contract_before,
        "videos": {},
    }

    with tempfile.TemporaryDirectory(prefix="pending-next-ten-solution-video-") as temp_name, sync_playwright() as playwright:
        temporary = Path(temp_name)
        browser = playwright.chromium.launch(headless=True)
        for index, mechanic in enumerate(mechanics):
            print(f"[{index + 1}/{len(mechanics)}] recording {mechanic}", flush=True)
            task_dir = temporary / mechanic
            state_dir = task_dir / "state"
            capture_dir = task_dir / "captures"
            browser_video_dir = task_dir / "browser-video"
            state_dir.mkdir(parents=True)
            capture_dir.mkdir(parents=True)
            browser_video_dir.mkdir(parents=True)
            webm_path = args.out_dir / f"{mechanic}-solution.webm"
            mp4_path = args.out_dir / f"{mechanic}-solution.mp4"
            webm_path.unlink(missing_ok=True)
            mp4_path.unlink(missing_ok=True)

            server = start_server(mechanic, args.port + index, state_dir, args.seed_prefix)
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                device_scale_factor=1,
                record_video_dir=str(browser_video_dir),
                record_video_size={"width": 1280, "height": 720},
            )
            page = context.new_page()
            video = page.video
            console_errors: list[str] = []
            page.on(
                "console",
                lambda message, errors=console_errors: errors.append(message.text)
                if message.type == "error"
                else None,
            )
            page.on("pageerror", lambda error, errors=console_errors: errors.append(str(error)))
            try:
                title, description = WALKTHROUGHS[mechanic]
                page.set_content("<!doctype html><html><body></body></html>")
                _inject_walkthrough_chrome(page, title, description, show_intro=True)
                page.wait_for_timeout(1_900)

                page.goto(f"http://127.0.0.1:{args.port + index}/", wait_until="networkidle")
                page.wait_for_function(
                    "mechanic => Boolean(window.WeirdCaptchaMechanics?.[mechanic]?.rootSelector)",
                    arg=mechanic,
                )
                root_selector = page.evaluate(
                    "mechanic => window.WeirdCaptchaMechanics[mechanic].rootSelector",
                    mechanic,
                )
                expect(page.locator(root_selector)).to_be_visible()
                _inject_walkthrough_chrome(page, title, description, show_intro=False)
                page.wait_for_timeout(850)

                pace = PACE.get(mechanic, {"key_press_ms": 0, "mouse_move_ms": 0})
                capture_page = _CapturePage(page, **pace)
                solver = load_module(SOLVER_ROOT / f"{mechanic}.py", f"pending_solution_video_solver_{mechanic}")
                solver.solve(capture_page, state_dir, capture_dir, mechanic)
                expect(page.locator(".readout")).to_contain_text("PASS", timeout=12_000)
                expect(page.locator(".readout")).to_have_attribute("data-status", "passed")

                exported = exported_payload(state_dir)
                server_grade = exported["result"].get("server_grade") or {}
                grader = load_module(GRADER_ROOT / f"{mechanic}.py", f"pending_solution_video_grader_{mechanic}")
                direct_grade = grader.grade(
                    exported["result"], exported["ground_truth"], exported["public_state"]
                )
                verifier = run_task_verifier(mechanic, exported, temporary)
                for label, grade in (
                    ("server", server_grade),
                    ("direct", direct_grade),
                    ("verifier", verifier),
                ):
                    if grade.get("passed") is not True:
                        raise AssertionError(f"{mechanic} {label} rejected recorded solve: {grade}")
                if console_errors:
                    raise AssertionError(f"{mechanic} browser errors: {console_errors}")

                page.evaluate(
                    "message => window.__solutionVideoOverlay.showOutro(message)",
                    f"PASS · LIVE SERVER ACCEPTED · {server_grade.get('feedback') or 'accepted'}",
                )
                page.wait_for_timeout(2_100)
            finally:
                page.close()
                if video is not None:
                    video.save_as(str(webm_path))
                context.close()
                server.terminate()
                try:
                    server.wait(timeout=3)
                except Exception:
                    server.kill()

            _transcode(webm_path, mp4_path)
            media = _probe(mp4_path)
            manifest["videos"][mechanic] = {
                "title": WALKTHROUGHS[mechanic][0],
                "approach": WALKTHROUGHS[mechanic][1],
                "webm": webm_path.name,
                "mp4": mp4_path.name,
                "webm_sha256": _sha256(webm_path),
                "mp4_sha256": _sha256(mp4_path),
                "media": media,
                "server_grade": server_grade,
                "direct_grade": direct_grade,
                "verifier": verifier,
                "console_errors": console_errors,
            }
            print(f"[{index + 1}/{len(mechanics)}] PASS {mechanic} ({media['duration_seconds']:.1f}s)", flush=True)
        browser.close()

    contract_after = _contract_snapshot(mechanics)
    if contract_after != contract_before:
        raise AssertionError("a frozen task implementation changed during solution-video capture")
    manifest["frozen_contract_verified"] = True
    manifest_path = args.out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(manifest_path, flush=True)


if __name__ == "__main__":
    main()
