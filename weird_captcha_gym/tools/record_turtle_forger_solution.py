#!/usr/bin/env python3
"""Record the Turtle Forger baseline through isolated headless Chromium."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments/turtle_forger_env"
MECHANIC = "turtle_forger"
TASK = ENVIRONMENT / "tasks/turtle_forger_seed_0001/task.json"
CONTROLS = ENVIRONMENT / "controls.json"
SETUP = BENCHMARK / "shared_scripts/setup_task.py"
SERVER = BENCHMARK / "shared_runtime/server/weird_captcha_server.py"
APP = BENCHMARK / "shared_runtime/app"
SOLVER = BENCHMARK / f"tools/incubator_solvers/{MECHANIC}.py"
GENERATOR = BENCHMARK / f"shared_scripts/incubator_generators/{MECHANIC}.py"
GRADER = BENCHMARK / f"shared_runtime/server/incubator_graders/{MECHANIC}.py"
JAVASCRIPT = BENCHMARK / f"shared_runtime/app/mechanics/{MECHANIC}.js"
CSS = BENCHMARK / f"shared_runtime/app/mechanics/{MECHANIC}.css"
VERIFIER = TASK.parent / "verifier.py"
OUTPUT = ENVIRONMENT / "evidence_docs/solution_videos"
CONTRACT_FILES = (TASK, CONTROLS, GENERATOR, JAVASCRIPT, CSS, GRADER, SOLVER, VERIFIER)


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def contract_hashes() -> dict[str, str]:
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in CONTRACT_FILES
    }


def reserve_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    hashes_before = contract_hashes()
    with tempfile.TemporaryDirectory(prefix="turtle-solution-isolated-") as raw:
        temporary = Path(raw)
        task = read(TASK)
        controls = read(CONTROLS)
        task["metadata"]["control_condition"] = {
            "difficulty": 3,
            "interaction": "full",
            "real_time": "live",
            "difficulty_parameters": copy.deepcopy(controls["difficulty"]["3"]["parameters"]),
        }
        task_path = temporary / "task.json"
        write(task_path, task)
        state_dir = temporary / "state"
        subprocess.run(
            ["python", "-B", str(SETUP), "--task-json", str(task_path), "--state-dir", str(state_dir), "--seed", "turtle-solution-film"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        server_port = reserve_port()
        process = subprocess.Popen(
            ["python", "-B", str(SERVER), "--host", "127.0.0.1", "--port", str(server_port), "--app-dir", str(APP), "--state-dir", str(state_dir)],
            cwd=ROOT,
            env={**os.environ, "WEIRD_CAPTCHA_CHALLENGE_SEED": "turtle-solution-film"},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            try:
                urlopen(f"http://127.0.0.1:{server_port}/health", timeout=.5).read()
                break
            except Exception:  # noqa: BLE001
                time.sleep(.1)
        else:
            process.kill()
            raise TimeoutError("solution-film loopback server did not start")

        video_path = None
        try:
            with sync_playwright() as playwright:
                context = playwright.chromium.launch_persistent_context(
                    str(temporary / "fresh-profile"),
                    headless=True,
                    viewport={"width": 1280, "height": 720},
                    device_scale_factor=1,
                    record_video_dir=str(temporary / "recording"),
                    record_video_size={"width": 1280, "height": 720},
                    slow_mo=120,
                )
                page = context.pages[0]
                errors: list[str] = []
                page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server_port}/?time_mode=live&start_paused=0", wait_until="networkidle")
                expect(page.locator(".turtle-forger.mode-full")).to_be_visible(timeout=8_000)
                page.wait_for_timeout(900)
                state = read(state_dir / "public_state.json")
                page.locator("#tfg-scan").click()
                scan_ms = len(state["runtime_target_segments"]) * (
                    int(state["parameters"]["stroke_ms"]) + int(state["parameters"]["gap_ms"])
                )
                page.wait_for_timeout(scan_ms + 350)
                load(SOLVER, "turtle_solution_solver").solve(page, state_dir, temporary / "solver-frames", MECHANIC)
                expect(page.locator(".tfg-verdict.is-pass")).to_be_visible(timeout=8_000)
                page.wait_for_timeout(1800)
                video = page.video
                context.close()
                video_path = Path(video.path()) if video is not None else None
                if errors:
                    raise AssertionError(f"browser console errors: {errors}")

            if video_path is None:
                raise AssertionError("Playwright did not create a solution video")
            webm = OUTPUT / f"{MECHANIC}-solution.webm"
            mp4 = OUTPUT / f"{MECHANIC}-solution.mp4"
            shutil.copyfile(video_path, webm)
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", str(webm), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4)],
                check=True,
            )

            exported = {
                "public_state": read(state_dir / "public_state.json"),
                "ground_truth": read(state_dir / "ground_truth.json"),
                "result": read(state_dir / "result.json"),
            }
            direct = load(GRADER, "turtle_solution_grader").grade(
                exported["result"], exported["ground_truth"], exported["public_state"],
            )
            export_path = temporary / "export.json"
            write(export_path, exported)
            verifier = load(VERIFIER, "turtle_solution_verifier").verify_task(
                env_info={"copy_from_env": lambda source, destination: shutil.copyfile(export_path, destination)}
            )
            probe = json.loads(subprocess.check_output(
                ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,codec_name:format=duration", "-of", "json", str(mp4)],
                text=True,
            ))
            stream = probe["streams"][0]
            hashes_after = contract_hashes()
            frozen = hashes_before == hashes_after
            record = {
                "title": "Turtle Forger",
                "approach": "Replay the transient one-stroke master, drag the inferred loop, pen, ink, turn, and movement cards into the tape, proof the reconstructed seal, and certify the raster match.",
                "condition": {"difficulty": 3, "interaction": "full", "real_time": "live"},
                "webm": webm.name,
                "mp4": mp4.name,
                "server_grade": exported["result"]["server_grade"],
                "direct_grade": direct,
                "verifier": verifier,
                "media": {
                    "duration_seconds": round(float(probe["format"]["duration"]), 3),
                    "width": stream["width"],
                    "height": stream["height"],
                    "codec": stream["codec_name"],
                },
                "isolation": {
                    "headless": True,
                    "fresh_persistent_profile": True,
                    "loopback_only": True,
                    "existing_profile_reused": False,
                },
            }
            manifest = {
                "schema_version": 1,
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "ok": frozen and all(item.get("passed") is True for item in (record["server_grade"], direct, verifier)),
                "frozen_contract_verified": frozen,
                "contract_sha256_before": hashes_before,
                "contract_sha256_after": hashes_after,
                "videos": {MECHANIC: record},
            }
            write(OUTPUT / "manifest.json", manifest)
            print(json.dumps(manifest, indent=2, sort_keys=True))
            if not manifest["ok"]:
                raise SystemExit(1)
        finally:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()
