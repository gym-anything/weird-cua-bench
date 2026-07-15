#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.weird_captcha_gym.shared_runtime.server.legacy_browser_grader import (  # noqa: E402
    grade as legacy_grade,
)
from benchmarks.weird_captcha_gym.tools import (  # noqa: E402
    smoke_interaction_first_five_ui as first_five,
)
from benchmarks.weird_captcha_gym.tools import (  # noqa: E402
    smoke_interaction_second_five_ui as second_five,
)
from benchmarks.weird_captcha_gym.tools import (  # noqa: E402
    record_pending_next_ten_solution_videos as recorder,
)
from benchmarks.weird_captcha_gym.tools.record_next_ten_solution_videos import (  # noqa: E402
    _inject_walkthrough_chrome,
    _probe,
    _sha256,
    _transcode,
)
from benchmarks.weird_captcha_gym.tools.smoke_incubator_batch_one_ui import (  # noqa: E402
    BENCH_ROOT,
    exported_payload,
    run_task_verifier,
    start_server,
)


MECHANICS = (
    "motion_only_ghost_jigsaw",
    "cursor_constellation_hunt",
    "parallel_grillmaster",
    "rotating_keyboard",
    "slot_reel_capture",
    "domino_autopsy",
    "funeral_ritual",
)

WALKTHROUGHS = {
    "motion_only_ghost_jigsaw": (
        "Motion-Only Ghost Jigsaw",
        "Recover nine tiles whose pictures exist only as opposing motion in noise, remember their identities across frames, and drag every live tile into its matching slot.",
    ),
    "cursor_constellation_hunt": (
        "Cursor Constellation Hunt",
        "Search the dark field with the cursor as an active lens, reject drifting decoy alignments, and click the one coordinate where the constellation resolves coherently.",
    ),
    "parallel_grillmaster": (
        "Parallel Grillmaster",
        "Start six foods together, monitor their different visual timing windows in parallel, and move each to the tray at its own peak doneness.",
    ),
    "rotating_keyboard": (
        "Rotating On-Screen Keyboard",
        "Enter the target code entirely by clicking a keyboard whose coordinate frame begins continuously tumbling after the first character.",
    ),
    "slot_reel_capture": (
        "Slot-Reel Character Capture",
        "Freeze five independently moving reels by typing each symbol only while it crosses the center line, recovering within the visible three-strike budget.",
    ),
    "domino_autopsy": (
        "Domino Autopsy",
        "Place and orient the loose rigid bodies, run the real Matter.js chain in either-facing configurations, and transfer continuous collision impulse into the suspended bell.",
    ),
    "funeral_ritual": (
        "Funeral With No Instructions",
        "Infer the memorial ritual from affordances alone: uncover the epitaph, clear the moss, light the candle, gather every flower, and lay down the bouquet.",
    ),
}

ROOT_SELECTORS = {
    "motion_only_ghost_jigsaw": ".interaction-captcha",
    "cursor_constellation_hunt": ".interaction-captcha",
    "parallel_grillmaster": ".interaction-captcha",
    "rotating_keyboard": ".interaction-captcha",
    "slot_reel_capture": ".interaction-captcha",
    "domino_autopsy": ".domino-captcha",
    "funeral_ritual": ".funeral-captcha",
}

SOLVERS: dict[str, Callable[..., None]] = {
    **first_five.SOLVERS,
    "domino_autopsy": second_five.solve_domino,
    "funeral_ritual": second_five.solve_funeral,
}

# These pauses are presentation-only. The two multi-deadline mechanics retain
# their exact original timing behavior.
PACE = {
    "motion_only_ghost_jigsaw": {"key_press_ms": 0, "mouse_move_ms": 12},
    "cursor_constellation_hunt": {"key_press_ms": 0, "mouse_move_ms": 12},
    "parallel_grillmaster": {"key_press_ms": 0, "mouse_move_ms": 0},
    "rotating_keyboard": {"key_press_ms": 0, "mouse_move_ms": 0},
    "slot_reel_capture": {"key_press_ms": 0, "mouse_move_ms": 0},
    "domino_autopsy": {"key_press_ms": 0, "mouse_move_ms": 10},
    "funeral_ritual": {"key_press_ms": 0, "mouse_move_ms": 10},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record frozen-contract solution films for the seven foundational legacy-runtime puzzles."
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=BENCH_ROOT / "evidence" / "foundational_seven_v1" / "solution_videos",
    )
    parser.add_argument("--port", type=int, default=9600)
    parser.add_argument("--seed-prefix", default="foundational-seven-solution-video")
    parser.add_argument("--mechanic", action="append", choices=MECHANICS)
    return parser.parse_args()


def _contract_files(mechanic: str) -> dict[str, Path]:
    task_dir = (
        BENCH_ROOT
        / "environments"
        / f"{mechanic}_env"
        / "tasks"
        / f"{mechanic}_seed_0001"
    )
    solver_path = (
        Path(first_five.__file__)
        if mechanic in first_five.MECHANICS
        else Path(second_five.__file__)
    )
    return {
        "task": task_dir / "task.json",
        "verifier": task_dir / "verifier.py",
        "generator_and_dispatch": BENCH_ROOT / "shared_scripts" / "setup_task.py",
        "frontend_and_styles": BENCH_ROOT / "shared_runtime" / "app" / "app.js",
        "shared_styles": BENCH_ROOT / "shared_runtime" / "app" / "styles.css",
        "server": BENCH_ROOT / "shared_runtime" / "server" / "weird_captcha_server.py",
        "direct_grader": BENCH_ROOT / "shared_runtime" / "server" / "legacy_browser_grader.py",
        "verifier_helpers": BENCH_ROOT / "shared_runtime" / "verifier_helpers.py",
        "browser_solver": solver_path,
    }


def _snapshot(mechanics: tuple[str, ...]) -> dict[str, dict[str, str]]:
    return {
        mechanic: {
            label: _sha256(path) for label, path in _contract_files(mechanic).items()
        }
        for mechanic in mechanics
    }


def _validate(
    mechanic: str, state_dir: Path, temporary: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    exported = exported_payload(state_dir)
    server_grade = exported["result"].get("server_grade") or {}
    direct_grade = legacy_grade(
        exported["result"], exported["ground_truth"], exported["public_state"]
    )
    verifier = run_task_verifier(mechanic, exported, temporary)
    for label, decision in (
        ("server", server_grade),
        ("direct", direct_grade),
        ("verifier", verifier),
    ):
        if decision.get("passed") is not True:
            raise AssertionError(
                f"{mechanic} {label} rejected recorded solution: {decision}"
            )
    return server_grade, direct_grade, verifier


def main() -> None:
    args = parse_args()
    mechanics = tuple(args.mechanic or MECHANICS)
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("solution video export requires ffmpeg and ffprobe")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    frozen_before = _snapshot(mechanics)
    manifest: dict[str, Any] = {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "task_implementations_modified": False,
        "capture_contract": (
            "Clean ordinary-input Playwright solve against each live frozen legacy task. "
            "Capture-only pauses affect presentation, never task code or acceptance."
        ),
        "frozen_contract_files": frozen_before,
        "videos": {},
    }

    with tempfile.TemporaryDirectory(
        prefix="foundational-seven-solution-video-"
    ) as temp_name, sync_playwright() as playwright:
        temporary = Path(temp_name)
        browser = playwright.chromium.launch(headless=True)
        for index, mechanic in enumerate(mechanics):
            print(f"[{index + 1}/{len(mechanics)}] recording {mechanic}", flush=True)
            mechanic_root = temporary / mechanic
            state_dir = mechanic_root / "state"
            capture_dir = mechanic_root / "captures"
            raw_dir = mechanic_root / "raw"
            state_dir.mkdir(parents=True)
            capture_dir.mkdir(parents=True)
            raw_dir.mkdir(parents=True)
            webm_path = args.out_dir / f"{mechanic}-solution.webm"
            mp4_path = args.out_dir / f"{mechanic}-solution.mp4"
            webm_path.unlink(missing_ok=True)
            mp4_path.unlink(missing_ok=True)

            port = args.port + index
            server = start_server(mechanic, port, state_dir, args.seed_prefix)
            context = browser.new_context(
                # These foundational layouts were authored and browser-smoked at
                # 1280x820. Playwright still encodes the public film at 1280x720.
                viewport={"width": 1280, "height": 820},
                device_scale_factor=1,
                record_video_dir=str(raw_dir),
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
            page.on(
                "pageerror",
                lambda error, errors=console_errors: errors.append(str(error)),
            )
            try:
                title, description = WALKTHROUGHS[mechanic]
                page.set_content("<!doctype html><html><body></body></html>")
                _inject_walkthrough_chrome(
                    page, title, description, show_intro=True
                )
                page.wait_for_timeout(1_900)

                page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
                expect(page.locator(ROOT_SELECTORS[mechanic])).to_be_visible()
                _inject_walkthrough_chrome(
                    page, title, description, show_intro=False
                )
                page.wait_for_timeout(850)

                capture_page = recorder._CapturePage(page, **PACE[mechanic])
                SOLVERS[mechanic](capture_page, state_dir, capture_dir, mechanic)
                expect(page.locator(".readout")).to_contain_text(
                    "PASS", timeout=14_000
                )
                server_grade, direct_grade, verifier = _validate(
                    mechanic, state_dir, temporary
                )
                if console_errors:
                    raise AssertionError(
                        f"{mechanic} browser errors: {console_errors}"
                    )

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
            print(
                f"[{index + 1}/{len(mechanics)}] PASS {mechanic} "
                f"({media['duration_seconds']:.1f}s)",
                flush=True,
            )
        browser.close()

    frozen_after = _snapshot(mechanics)
    if frozen_after != frozen_before:
        raise AssertionError(
            "a frozen task implementation changed during solution-video capture"
        )
    manifest["frozen_contract_verified"] = True
    manifest_path = args.out_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(manifest_path, flush=True)


if __name__ == "__main__":
    main()
