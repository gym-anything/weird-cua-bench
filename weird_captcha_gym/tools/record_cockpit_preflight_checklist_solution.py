#!/usr/bin/env python3
"""Record the baseline solution in an isolated headless Chromium profile."""
from __future__ import annotations

import copy
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
ENV = BENCHMARK / "environments/cockpit_preflight_checklist_env"
MECHANIC = "cockpit_preflight_checklist"
TASK = ENV / "tasks/cockpit_preflight_checklist_seed_0001/task.json"
CONTROLS = ENV / "controls.json"
SETUP = BENCHMARK / "shared_scripts/setup_task.py"
SERVER = BENCHMARK / "shared_runtime/server/weird_captcha_server.py"
APP = BENCHMARK / "shared_runtime/app"
SOLVER = BENCHMARK / f"tools/incubator_solvers/{MECHANIC}.py"
GRADER = BENCHMARK / f"shared_runtime/server/incubator_graders/{MECHANIC}.py"
VERIFIER = TASK.parent / "verifier.py"
OUT = ENV / "evidence_docs/solution_videos"


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


def port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cockpit-solution-isolated-") as name:
        temp = Path(name)
        task = read(TASK)
        controls = read(CONTROLS)
        task["metadata"]["control_condition"] = {
            "difficulty": 2, "interaction": "full", "real_time": "live",
            "difficulty_parameters": copy.deepcopy(controls["difficulty"]["2"]["parameters"]),
        }
        task_path = temp / "task.json"
        write(task_path, task)
        state = temp / "state"
        subprocess.run(["python", "-B", str(SETUP), "--task-json", str(task_path), "--state-dir", str(state), "--seed", "cockpit-solution-film"], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
        server_port = port()
        process = subprocess.Popen(
            ["python", "-B", str(SERVER), "--host", "127.0.0.1", "--port", str(server_port), "--app-dir", str(APP), "--state-dir", str(state)],
            cwd=ROOT, env={**os.environ, "WEIRD_CAPTCHA_CHALLENGE_SEED": "cockpit-solution-film"}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
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
            raise TimeoutError("solution-film server did not start")
        video_path = None
        try:
            with sync_playwright() as playwright:
                context = playwright.chromium.launch_persistent_context(
                    str(temp / "fresh-profile"), headless=True, viewport={"width": 1280, "height": 720},
                    record_video_dir=str(temp / "recording"), record_video_size={"width": 1280, "height": 720}, slow_mo=150,
                )
                page = context.pages[0]
                errors: list[str] = []
                page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server_port}/", wait_until="networkidle")
                expect(page.locator(".cockpit-preflight.mode-full")).to_be_visible()
                page.wait_for_timeout(2500)
                load(SOLVER, "cockpit_solution_solver").solve(page, state, OUT, MECHANIC)
                expect(page.locator(".cpf-verdict.is-pass")).to_be_visible()
                page.wait_for_timeout(3000)
                video = page.video
                context.close()
                video_path = Path(video.path()) if video is not None else None
                if errors:
                    raise AssertionError(errors)
            if video_path is None:
                raise AssertionError("Playwright did not create a video")
            webm_source = video_path
            webm = OUT / f"{MECHANIC}-solution.webm"
            mp4 = OUT / f"{MECHANIC}-solution.mp4"
            shutil.copyfile(webm_source, webm)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(webm), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4)], check=True)
            export = {"public_state": read(state / "public_state.json"), "ground_truth": read(state / "ground_truth.json"), "result": read(state / "result.json")}
            direct = load(GRADER, "cockpit_solution_grader").grade(export["result"], export["ground_truth"], export["public_state"])
            export_path = temp / "export.json"
            write(export_path, export)
            verifier_module = load(VERIFIER, "cockpit_solution_verifier")
            verifier = verifier_module.verify_task(env_info={"copy_from_env": lambda source, destination: shutil.copyfile(export_path, destination)})
            probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,codec_name:format=duration", "-of", "json", str(mp4)], text=True))
            stream = probe["streams"][0]
            record = {
                "title": "Cockpit Preflight Checklist",
                "approach": "Follow the released calibration targets in order, use real thumb drags and rotary gestures while accounting for linked state changes, disclose every bay, set each circuit state, and certify.",
                "webm": webm.name,
                "mp4": mp4.name,
                "server_grade": export["result"]["server_grade"],
                "direct_grade": direct,
                "verifier": verifier,
                "media": {"duration_seconds": round(float(probe["format"]["duration"]), 3), "width": stream["width"], "height": stream["height"], "codec": stream["codec_name"]},
                "isolation": {"headless": True, "fresh_persistent_profile": True, "loopback_only": True},
            }
            manifest = {"schema_version": 1, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "ok": all(item.get("passed") is True for item in (record["server_grade"], direct, verifier)), "frozen_contract_verified": True, "videos": {MECHANIC: record}}
            write(OUT / "manifest.json", manifest)
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
