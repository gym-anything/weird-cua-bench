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
    "specular_lighthouse_relay",
    "wind_tunnel_seed_courier",
    "hologram_silhouette_foundry",
    "orbital_docking_customs",
    "gravity_room_freight",
    "floodgate_archive_rescue",
    "elastic_membrane_sorter",
    "pheromone_dispatch",
    "clockwork_clutch_safe",
    "marionette_checkpoint",
)

WALKTHROUGHS = {
    "specular_lighthouse_relay": (
        "Specular Lighthouse Relay",
        "Align a three-mirror optical path, then continuously track four vertically moving receivers while charge leaks whenever the live reflected beam drifts off target.",
    ),
    "wind_tunnel_seed_courier": (
        "Wind-Tunnel Seed Courier",
        "Fly two differently weighted seed pods through eight moving apertures using one shared four-fan plant whose spool and heat persist between deliveries.",
    ),
    "hologram_silhouette_foundry": (
        "Hologram Silhouette Foundry",
        "Place six color-coded rods in a 7³ volume so the frontmost visible colors—not just occupancy—match three occluding orthographic dies at once.",
    ),
    "orbital_docking_customs": (
        "Orbital Docking Customs",
        "Navigate an S-shaped inertial corridor, clear two scan beacons in order, avoid both debris fields, and match a moving, rotating customs port with low closing speed.",
    ),
    "gravity_room_freight": (
        "Gravity-Room Freight",
        "Rotate one shared gravity field to move an archive crate and an isolated under-deck counterweight through four ordered seals into separate docks.",
    ),
    "floodgate_archive_rescue": (
        "Floodgate Archive Rescue",
        "Conserve water across five chambers while two archive capsules travel in opposite directions through four locks that must be equalized in sequence.",
    ),
    "elastic_membrane_sorter": (
        "Elastic Membrane Sorter",
        "Steer the membrane while each marble is already moving, threading two ordered checkpoint rings before entering its assigned well slowly enough to capture.",
    ),
    "pheromone_dispatch": (
        "Pheromone Dispatch",
        "Maintain two independently evaporating pheromone fields while amber and violet carrier swarms alternate between caches and the shared nest around obstacles.",
    ),
    "clockwork_clutch_safe": (
        "Clockwork Clutch Safe",
        "Release and re-engage four shafts at target phases while every clutch action redistributes drive load and changes all remaining angular velocities.",
    ),
    "marionette_checkpoint": (
        "Marionette Checkpoint",
        "Continuously coordinate four coupled string lengths so the puppet follows moving limb targets across three acts while off-target frames visibly erase progress.",
    ),
}

# Recording-only pacing. It changes neither task state nor accepted actions.
PACE = {
    "hologram_silhouette_foundry": {"key_press_ms": 12, "minimum_short_wait_ms": 0},
    # These two mechanics advance continuously while range controls are focused.
    # Added keyboard delay changes the physical trajectory, so capture their
    # ordinary Playwright keypresses without an extra recording-only pause.
    "elastic_membrane_sorter": {"key_press_ms": 0, "minimum_short_wait_ms": 0},
    "marionette_checkpoint": {"key_press_ms": 0, "minimum_short_wait_ms": 0},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record verified ordinary-input solutions for Interaction VII–VIII."
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=BENCH_ROOT / "evidence" / "interaction_vii_viii_difficulty_v2" / "solution_videos",
    )
    parser.add_argument("--port", type=int, default=9280)
    parser.add_argument("--seed-prefix", default="interaction-vii-viii-difficulty-v2-solution-video")
    parser.add_argument("--mechanic", action="append", choices=MECHANICS)
    return parser.parse_args()


def _contract_files(mechanic: str) -> dict[str, Path]:
    mechanics = BENCH_ROOT / "shared_runtime" / "app" / "mechanics"
    generators = BENCH_ROOT / "shared_scripts" / "incubator_generators"
    solvers = BENCH_ROOT / "tools" / "incubator_solvers"
    return {
        "task": BENCH_ROOT / "environments" / f"{mechanic}_env" / "tasks" / f"{mechanic}_seed_0001" / "task.json",
        "generator_wrapper": generators / f"{mechanic}.py",
        "generator_common": generators / "_interaction_vii_viii_common.py",
        "frontend_wrapper": mechanics / f"{mechanic}.js",
        "frontend_common": mechanics / "_interaction_vii_viii.js",
        "style_wrapper": mechanics / f"{mechanic}.css",
        "style_common": mechanics / "_interaction_vii_viii.css",
        "grader": GRADER_ROOT / f"{mechanic}.py",
        "solver_wrapper": solvers / f"{mechanic}.py",
        "solver_common": solvers / "_interaction_vii_viii_common.py",
    }


def _contract_snapshot(mechanics: tuple[str, ...]) -> dict[str, dict[str, str]]:
    return {
        mechanic: {label: _sha256(path) for label, path in _contract_files(mechanic).items()}
        for mechanic in mechanics
    }


def main() -> None:
    args = parse_args()
    mechanics = tuple(args.mechanic or MECHANICS)
    before = _contract_snapshot(mechanics)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("solution-video export requires ffmpeg and ffprobe")

    manifest: dict[str, Any] = {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "task_implementations_modified": False,
        "capture_contract": (
            "Paced Playwright capture using only ordinary visible mouse/keyboard controls "
            "against live task servers; every replay is checked by server, direct grader, and task verifier."
        ),
        "frozen_contract_files": before,
        "videos": {},
    }

    with tempfile.TemporaryDirectory(prefix="interaction-vii-viii-video-") as temp_name, sync_playwright() as playwright:
        temporary = Path(temp_name)
        browser = playwright.chromium.launch(headless=True)
        for index, mechanic in enumerate(mechanics):
            print(f"[{index + 1}/{len(mechanics)}] recording {mechanic}", flush=True)
            state_dir = temporary / mechanic / "state"
            captures = temporary / mechanic / "captures"
            browser_video = temporary / mechanic / "browser-video"
            state_dir.mkdir(parents=True)
            captures.mkdir(parents=True)
            browser_video.mkdir(parents=True)
            webm_path = args.out_dir / f"{mechanic}-solution.webm"
            mp4_path = args.out_dir / f"{mechanic}-solution.mp4"
            webm_path.unlink(missing_ok=True)
            mp4_path.unlink(missing_ok=True)

            server = start_server(mechanic, args.port + index, state_dir, args.seed_prefix)
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                device_scale_factor=1,
                record_video_dir=str(browser_video),
                record_video_size={"width": 1280, "height": 720},
            )
            page = context.new_page()
            errors: list[str] = []
            page.on("console", lambda message, output=errors: output.append(message.text) if message.type == "error" else None)
            page.on("pageerror", lambda error, output=errors: output.append(str(error)))
            video = page.video
            server_grade: dict[str, Any] = {}
            direct_grade: dict[str, Any] = {}
            verifier: dict[str, Any] = {}
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
                    "mechanic => window.WeirdCaptchaMechanics[mechanic].rootSelector", mechanic
                )
                expect(page.locator(root_selector)).to_be_visible()
                _inject_walkthrough_chrome(page, title, description, show_intro=False)
                page.wait_for_timeout(450)

                pace = PACE.get(mechanic, {"key_press_ms": 0, "minimum_short_wait_ms": 0})
                solver = load_module(SOLVER_ROOT / f"{mechanic}.py", f"video_solver_{mechanic}")
                solver.solve(_PacedPage(page, **pace), state_dir, captures, mechanic)
                expect(page.locator(".readout")).to_have_attribute("data-status", "passed", timeout=20_000)

                exported = exported_payload(state_dir)
                server_grade = exported["result"].get("server_grade") or {}
                grader = load_module(GRADER_ROOT / f"{mechanic}.py", f"video_grader_{mechanic}")
                direct_grade = grader.grade(
                    exported["result"], exported["ground_truth"], exported["public_state"]
                )
                verifier = run_task_verifier(mechanic, exported, temporary)
                for label, grade in (("server", server_grade), ("direct", direct_grade), ("verifier", verifier)):
                    if grade.get("passed") is not True:
                        raise AssertionError(f"{mechanic} {label} rejected recorded solution: {grade}")
                if errors:
                    raise AssertionError(f"{mechanic} browser errors: {errors}")

                feedback = str(server_grade.get("feedback") or "accepted")
                page.evaluate(
                    "message => window.__solutionVideoOverlay.showOutro(message)",
                    f"PASS · LIVE SERVER ACCEPTED · {feedback}",
                )
                page.wait_for_timeout(2_000)
            finally:
                page.close()
                if video is not None:
                    video.save_as(str(webm_path))
                context.close()
                server.terminate()
                try:
                    server.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    server.kill()

            _transcode(webm_path, mp4_path)
            manifest["videos"][mechanic] = {
                "title": WALKTHROUGHS[mechanic][0],
                "approach": WALKTHROUGHS[mechanic][1],
                "webm": webm_path.name,
                "mp4": mp4_path.name,
                "webm_sha256": _sha256(webm_path),
                "mp4_sha256": _sha256(mp4_path),
                "media": _probe(mp4_path),
                "server_grade": server_grade,
                "direct_grade": direct_grade,
                "verifier": verifier,
                "console_errors": errors,
            }
            print(f"[{index + 1}/{len(mechanics)}] PASS {mechanic} ({_probe(mp4_path)['duration_seconds']:.1f}s)", flush=True)
        browser.close()

    after = _contract_snapshot(mechanics)
    if after != before:
        raise AssertionError("a frozen task implementation changed during solution-video capture")
    manifest["frozen_contract_verified"] = True
    manifest_path = args.out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(manifest_path, flush=True)


if __name__ == "__main__":
    main()
