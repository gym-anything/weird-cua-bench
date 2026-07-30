#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from types import ModuleType
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[3]
BENCHMARK = ROOT / "benchmarks" / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "portal_freight_oversized_parcel_env"
MECHANIC = "portal_freight_oversized_parcel"
SETUP = BENCHMARK / "shared_scripts" / "setup_task.py"
SERVER = BENCHMARK / "shared_runtime" / "server" / "weird_captcha_server.py"
APP = BENCHMARK / "shared_runtime" / "app"
GRADER = BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{MECHANIC}.py"
SOLVER = BENCHMARK / "tools" / "incubator_solvers" / f"{MECHANIC}.py"
MATERIALIZER = BENCHMARK / "tools" / "materialize_controlled_tasks.py"


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalise(state: dict) -> dict:
    result = copy.deepcopy(state)
    for key in ("task_id", "challenge_id", "control_condition"):
        result.pop(key, None)
    return result


def _world_fingerprint(state: dict) -> str:
    """Fingerprint the rendered physical world, excluding control/UI descriptors."""
    world = {
        key: state.get(key)
        for key in ("canvas", "room", "walls", "tools", "controls", "parcel", "delivery", "qualification")
    }
    payload = json.dumps(world, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _start_server(task_json: Path, state_dir: Path, port: int, seed: str) -> subprocess.Popen:
    subprocess.run(
        ["python", "-B", str(SETUP), "--task-json", str(task_json), "--state-dir", str(state_dir), "--seed", seed],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    process = subprocess.Popen(
        [
            "python", "-B", str(SERVER), "--host", "127.0.0.1", "--port", str(port),
            "--app-dir", str(APP), "--state-dir", str(state_dir),
        ],
        cwd=ROOT,
        env={
            **os.environ,
            "WEIRD_CAPTCHA_CHEAT_PASSWORD": "portal-freight-control-smoke",
            # /state issues a fresh browser challenge.  Pin its evaluator
            # seed so the two UI surfaces visibly start from one sampled
            # world, while the failure path still receives its next index.
            "WEIRD_CAPTCHA_CHALLENGE_SEED": seed,
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 8
    while time.time() < deadline:
        try:
            urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5).read()
            return process
        except Exception:
            time.sleep(0.1)
    process.kill()
    raise RuntimeError(f"portal freight server did not start on {port}")


def _verify(task_json: Path, exported: dict, temporary: Path, name: str) -> dict:
    verifier = _load(task_json.parent / "verifier.py", f"portal_freight_verifier_{name}")
    export_path = temporary / f"{name}-export.json"
    export_path.write_text(json.dumps(exported), encoding="utf-8")

    def copy_from_env(source: str, destination: str) -> None:
        if source != "/tmp/task_result.json":
            raise ValueError(f"unexpected verifier source {source}")
        shutil.copyfile(export_path, destination)

    result = verifier.verify_task(env_info={"copy_from_env": copy_from_env})
    if not isinstance(result, dict):
        raise AssertionError(f"verifier returned {result!r}")
    return result


def _terminate(process: subprocess.Popen) -> None:
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()


def run(out_dir: Path, port: int, only_level: int | None = None, only_interaction: str | None = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    visual_dir = out_dir / "visual"
    result_dir = out_dir / "results"
    result_dir.mkdir(exist_ok=True)
    materializer = _load(MATERIALIZER, "portal_freight_materializer")
    setup = _load(SETUP, "portal_freight_setup")
    grader = _load(GRADER, "portal_freight_grader")
    solver = _load(SOLVER, "portal_freight_solver")
    controls = _read(ENVIRONMENT / "controls.json")
    materializer.validate_controls(controls, ENVIRONMENT)
    summary: dict[str, object] = {
        "headless_isolated": True,
        "browser_launch": "Playwright Chromium headless=True with one fresh context per condition",
        "loopback_only": True,
        "conditions": {},
    }

    with tempfile.TemporaryDirectory(prefix="portal-freight-controls-") as temporary_name:
        temporary = Path(temporary_name)
        generated_root = temporary / "generated"
        written = materializer.materialize_environment(ENVIRONMENT, generated_root)
        if len(written) != 10:
            raise AssertionError(f"expected 10 controlled tasks, found {len(written)}")

        base_task = _read(ENVIRONMENT / "tasks" / f"{MECHANIC}_seed_0001" / "task.json")
        baseline_task = _read(generated_root / ENVIRONMENT.name / "tasks" / f"{MECHANIC}_d4_simplified_seed_0001" / "task.json")
        original_public, original_truth = setup.generate_task_state(base_task, "portal-freight-baseline-evidence")
        baseline_public, baseline_truth = setup.generate_task_state(baseline_task, "portal-freight-baseline-evidence")
        summary["baseline_preservation"] = {
            "difficulty": 4,
            "interaction": "simplified",
            "same_challenge_id": original_public["challenge_id"] == baseline_public["challenge_id"],
            "public_state_equal_without_control_identity": _normalise(original_public) == _normalise(baseline_public),
            "ground_truth_equal_without_control_identity": _normalise(original_truth) == _normalise(baseline_truth),
        }
        if not all(summary["baseline_preservation"].values()):
            raise AssertionError("L4 simplified did not preserve the original portal freight task")

        for level in range(1, 6):
            simplified = _read(generated_root / ENVIRONMENT.name / "tasks" / f"{MECHANIC}_d{level}_simplified_seed_0001" / "task.json")
            full = _read(generated_root / ENVIRONMENT.name / "tasks" / f"{MECHANIC}_d{level}_full_seed_0001" / "task.json")
            simplified_public, simplified_truth = setup.generate_task_state(simplified, f"portal-freight-pair-{level}")
            full_public, full_truth = setup.generate_task_state(full, f"portal-freight-pair-{level}")
            same_world = (
                simplified_public["challenge_id"] == full_public["challenge_id"]
                and _normalise(simplified_public) == _normalise(full_public)
                and _normalise(simplified_truth) == _normalise(full_truth)
            )
            summary[f"paired_world_l{level}"] = {"same_generated_world": same_world}
            if not same_world:
                raise AssertionError(f"difficulty {level} changed the portal freight world across interaction modes")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                original_state_dir = temporary / "original-l4-uncontrolled"
                original_state_dir.mkdir()
                original_process = _start_server(
                    ENVIRONMENT / "tasks" / f"{MECHANIC}_seed_0001" / "task.json",
                    original_state_dir,
                    port + 20,
                    "portal-freight-baseline-evidence",
                )
                original_context = browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
                original_page = original_context.new_page()
                try:
                    page_errors: list[str] = []
                    original_page.on("console", lambda message: page_errors.append(message.text) if message.type == "error" else None)
                    original_page.on("pageerror", lambda error: page_errors.append(str(error)))
                    original_page.goto(f"http://127.0.0.1:{port + 20}/", wait_until="networkidle")
                    expect(original_page.locator('.portal-freight[data-active="true"]')).to_be_visible(timeout=8_000)
                    if original_page.locator('[data-fire="blue"]').is_disabled():
                        raise AssertionError("uncontrolled Portal Freight did not retain its simplified proxy controls")
                    original_visual = visual_dir / "original-l4-uncontrolled"
                    original_visual.mkdir(parents=True, exist_ok=True)
                    original_page.screenshot(path=str(original_visual / "initial.png"), full_page=True)
                    if page_errors:
                        raise AssertionError(f"uncontrolled L4 browser errors: {page_errors}")
                    summary["original_browser_reference"] = {
                        "difficulty": 4,
                        "interaction": "simplified",
                        "browser_seed": "portal-freight-baseline-evidence",
                        "world_fingerprint": _world_fingerprint(_read(original_state_dir / "public_state.json")),
                        "screenshot": "visual/original-l4-uncontrolled/initial.png",
                    }
                finally:
                    original_context.close()
                    _terminate(original_process)

                browser_fingerprints: dict[str, str] = {}
                for index, task_dir in enumerate(sorted(written)):
                    task_json = task_dir / "task.json"
                    condition = _read(task_json)["metadata"]["control_condition"]
                    level = int(condition["difficulty"])
                    interaction = str(condition["interaction"])
                    if only_level is not None and level != only_level:
                        continue
                    if only_interaction is not None and interaction != only_interaction:
                        continue
                    label = f"l{level}-{interaction}"
                    state_dir = temporary / label
                    state_dir.mkdir()
                    browser_seed = f"portal-freight-browser-l{level}"
                    process = _start_server(task_json, state_dir, port + index, browser_seed)
                    context = browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
                    page = context.new_page()
                    errors: list[str] = []
                    page.on("console", lambda message, sink=errors: sink.append(message.text) if message.type == "error" else None)
                    page.on("pageerror", lambda error, sink=errors: sink.append(str(error)))
                    variant_dir = visual_dir / label
                    variant_dir.mkdir(parents=True, exist_ok=True)
                    try:
                        page.goto(f"http://127.0.0.1:{port + index}/", wait_until="networkidle")
                        expect(page.locator('.portal-freight[data-active="true"]')).to_be_visible(timeout=8_000)
                        expect(page.locator("#freight-canvas")).to_be_visible()
                        page.screenshot(path=str(variant_dir / "initial.png"), full_page=True)
                        browser_fingerprints[label] = _world_fingerprint(_read(state_dir / "public_state.json"))
                        if interaction == "full":
                            expect(page.locator(".direct-surface")).to_be_visible()
                            if not page.locator('[data-fire="blue"]').is_disabled():
                                raise AssertionError("full interaction left the proxy portal control enabled")
                        else:
                            if page.locator('[data-fire="blue"]').is_disabled():
                                raise AssertionError("simplified interaction disabled the proxy portal control")

                        solver.fail_once(page, state_dir, variant_dir, MECHANIC)
                        solver.solve(page, state_dir, variant_dir, MECHANIC)
                        expect(page.locator(".readout")).to_have_text("PASS", timeout=8_000)
                        page.screenshot(path=str(variant_dir / "pass.png"), full_page=True)
                        exported = {
                            "public_state": _read(state_dir / "public_state.json"),
                            "ground_truth": _read(state_dir / "ground_truth.json"),
                            "result": _read(state_dir / "result.json"),
                        }
                        server_grade = exported["result"].get("server_grade") or {}
                        direct_grade = grader.grade(exported["result"], exported["ground_truth"], exported["public_state"])
                        verifier_grade = _verify(
                            ENVIRONMENT / "tasks" / f"{MECHANIC}_seed_0001" / "task.json",
                            exported,
                            temporary,
                            label,
                        )
                        if not (server_grade.get("passed") is True and direct_grade.get("passed") is True and verifier_grade.get("passed") is True):
                            raise AssertionError(f"{label} grade disagreement: {server_grade}, {direct_grade}, {verifier_grade}")
                        wrong_surface = copy.deepcopy(exported["result"])
                        wrong_surface["interaction_mode"] = "full" if interaction == "simplified" else "simplified"
                        rejected = grader.grade(wrong_surface, exported["ground_truth"], exported["public_state"])
                        if rejected.get("passed") is not False:
                            raise AssertionError(f"{label} accepted a transcript marked as the other interaction mode")
                        stale = copy.deepcopy(exported["result"])
                        stale["challenge_id"] = f"stale-{exported['result']['challenge_id']}"
                        stale_rejected = grader.grade(stale, exported["ground_truth"], exported["public_state"])
                        if stale_rejected.get("passed") is not False or stale_rejected.get("feedback") != "stale challenge":
                            raise AssertionError(f"{label} did not reject a stale challenge: {stale_rejected}")
                        malformed = copy.deepcopy(exported["result"])
                        malformed["events"] = []
                        malformed_rejected = grader.grade(malformed, exported["ground_truth"], exported["public_state"])
                        if malformed_rejected.get("passed") is not False or malformed_rejected.get("feedback") != "freight transcript is missing or too long":
                            raise AssertionError(f"{label} did not reject an invalid transcript: {malformed_rejected}")
                        failure_attempts_path = state_dir / "attempts.jsonl"
                        failure_attempts = [
                            json.loads(line)
                            for line in failure_attempts_path.read_text(encoding="utf-8").splitlines()
                            if line.strip()
                        ] if failure_attempts_path.is_file() else []
                        if len(failure_attempts) != 1:
                            raise AssertionError(f"{label} expected one archived failure before recovery, found {len(failure_attempts)}")
                        archived_failure = failure_attempts[0].get("server_grade") or {}
                        if archived_failure.get("passed") is not False:
                            raise AssertionError(f"{label} archived failure was not graded as a failure: {archived_failure}")
                        if errors:
                            raise AssertionError(f"{label} browser errors: {errors}")
                        artifact = {
                            "condition": condition,
                            "browser_seed": browser_seed,
                            "initial_world_fingerprint": browser_fingerprints[label],
                            "server_grade": server_grade,
                            "direct_grade": direct_grade,
                            "verifier": verifier_grade,
                            "opposite_interaction_rejected": rejected,
                            "stale_challenge_rejected": stale_rejected,
                            "malformed_transcript_rejected": malformed_rejected,
                            "failure_retry": {
                                "archived_failure_count": len(failure_attempts),
                                "archived_failure_grade": archived_failure,
                                "recovered_challenge_id": exported["public_state"]["challenge_id"],
                            },
                            "console_errors": errors,
                            "screenshots": sorted(str(path.relative_to(out_dir)) for path in variant_dir.glob("*.png")),
                        }
                        (result_dir / f"{label}.json").write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                        summary["conditions"][label] = artifact
                    finally:
                        context.close()
                        _terminate(process)
                for level in range(1, 6):
                    simplified_label = f"l{level}-simplified"
                    full_label = f"l{level}-full"
                    if simplified_label not in browser_fingerprints or full_label not in browser_fingerprints:
                        continue
                    same_initial_world = browser_fingerprints[simplified_label] == browser_fingerprints[full_label]
                    summary[f"browser_visual_pair_l{level}"] = {
                        "same_initial_world": same_initial_world,
                        "simplified_screenshot": f"visual/{simplified_label}/initial.png",
                        "full_screenshot": f"visual/{full_label}/initial.png",
                    }
                    if not same_initial_world:
                        raise AssertionError(
                            f"browser screenshots for L{level} used different generated worlds: "
                            f"{browser_fingerprints[simplified_label]} != {browser_fingerprints[full_label]}"
                        )
            finally:
                browser.close()

    summary["real_time"] = {
        "shared_framework_configuration": controls["real_time"],
        "live_observation": {"observation_window_ms": 0, "frames_per_observation": 1},
        "paused_observation": {"observation_window_ms": 0, "frames_per_observation": 1},
        "note": "Portal Freight has no autonomous task clock; one static frame is the complete observation in both modes. Pausing is supplied by the shared runtime rather than a task-specific branch.",
    }
    summary_path = out_dir / "summary.json"
    if (only_level is not None or only_interaction is not None) and summary_path.is_file():
        previous = _read(summary_path)
        previous.setdefault("conditions", {}).update(summary["conditions"])
        for key, value in summary.items():
            if key != "conditions":
                previous[key] = value
        summary = previous
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run all isolated headless Portal Freight controllability checks.")
    parser.add_argument("--out-dir", type=Path, default=ENVIRONMENT / "evidence_docs" / "browser_controls")
    parser.add_argument("--port", type=int, default=9050)
    parser.add_argument("--only-level", type=int, choices=range(1, 6))
    parser.add_argument("--only-interaction", choices=("simplified", "full"))
    args = parser.parse_args()
    run(args.out_dir, args.port, args.only_level, args.only_interaction)


if __name__ == "__main__":
    main()
