#!/usr/bin/env python3
"""Exercise Cockpit Preflight Checklist through exported static browser play.

The check exports a fresh site, serves it on loopback, and launches one new
headless persistent Chromium profile per interaction mode. Grading therefore
runs through the shipped Pyodide worker rather than the local Python server.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import tempfile
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from weird_captcha_gym.dashboard.export_static import export_dashboard  # noqa: E402


BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments/cockpit_preflight_checklist_env"
SOLVER = BENCHMARK / "tools/incubator_solvers/cockpit_preflight_checklist.py"
DEFAULT_OUTPUT = ENVIRONMENT / "evidence_docs/static_target_browser"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def fingerprint(state: dict) -> str:
    contract = {"panel": state["panel"], "parameters": state["parameters"]}
    return hashlib.sha256(json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.out_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    started = time.time()

    with tempfile.TemporaryDirectory(prefix="cockpit-static-browser-isolated-") as temp_name:
        temporary = Path(temp_name)
        site = temporary / "site"
        export_manifest = export_dashboard(site, copy_media=False)
        bundle_path = site / "play/challenges/cockpit_preflight_checklist_env.json"
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        handler = partial(QuietHandler, directory=str(site))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        records = []
        try:
            with sync_playwright() as playwright:
                solver = load_module(SOLVER, "cockpit_static_browser_solver")
                profiles = bundle["difficulty_profiles"]["2"]["interaction_profiles"]
                for interaction in ("simplified", "full"):
                    challenges = profiles[interaction]["challenges"]
                    initial_state = challenges[0]["public_state"]
                    retry_state = challenges[1]["public_state"]
                    profile = temporary / "fresh-profiles" / interaction
                    context = playwright.chromium.launch_persistent_context(
                        str(profile),
                        headless=True,
                        viewport={"width": 1440, "height": 900},
                        device_scale_factor=1,
                    )
                    page = context.pages[0]
                    errors: list[str] = []
                    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    try:
                        page.goto(
                            f"{base_url}/play/?environment=cockpit_preflight_checklist_env"
                            f"&attempt=0&difficulty=2&interaction={interaction}",
                            wait_until="networkidle",
                        )
                        expect(page.locator(f".cockpit-preflight.mode-{interaction}")).to_be_visible(timeout=10_000)
                        initial_card = page.locator(".cpf-checklist header p").inner_text()
                        page.screenshot(path=str(output / f"static-baseline-d2-{interaction}-initial.png"), full_page=True)

                        page.locator("#cpf-certify").click()
                        expect(page.locator(".cpf-verdict.is-fail")).to_be_visible(timeout=90_000)
                        failure = page.evaluate("async () => (await (await fetch('/result')).json())")
                        retry_card = page.locator(".cpf-checklist header p").inner_text()
                        if initial_card == retry_card:
                            raise AssertionError("static browser failure did not render a fresh card")
                        if failure.get("browser_grade", {}).get("passed") is not False:
                            raise AssertionError(f"static failure was not graded by Pyodide: {failure}")
                        if interaction == "full":
                            page.screenshot(path=str(output / "static-baseline-d2-full-failure-fresh.png"), full_page=True)

                        state_dir = temporary / "solver-state" / interaction
                        write_json(state_dir / "public_state.json", retry_state)
                        solver.solve(page, state_dir, output, "cockpit_preflight_checklist")
                        expect(page.locator(".cpf-verdict.is-pass")).to_be_visible(timeout=90_000)
                        passed = page.evaluate("async () => (await (await fetch('/result')).json())")
                        if passed.get("browser_grade", {}).get("passed") is not True:
                            raise AssertionError(f"static recovery was not graded by Pyodide: {passed}")
                        page.screenshot(path=str(output / f"static-baseline-d2-{interaction}-pass.png"), full_page=True)
                        if errors:
                            raise AssertionError(f"browser console errors: {errors}")
                        records.append({
                            "interaction": interaction,
                            "difficulty": 2,
                            "initial_challenge_id": initial_state["challenge_id"],
                            "retry_challenge_id": retry_state["challenge_id"],
                            "initial_world_fingerprint": fingerprint(initial_state),
                            "retry_world_fingerprint": fingerprint(retry_state),
                            "failure_browser_grade": failure["browser_grade"],
                            "recovery_browser_grade": passed["browser_grade"],
                            "ordinary_visible_inputs": True,
                            "headless": True,
                            "fresh_persistent_profile": True,
                            "loopback_only": True,
                            "console_errors": errors,
                        })
                    finally:
                        context.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    same_initial_world = records[0]["initial_world_fingerprint"] == records[1]["initial_world_fingerprint"]
    same_retry_world = records[0]["retry_world_fingerprint"] == records[1]["retry_world_fingerprint"]
    summary = {
        "ok": (
            len(records) == 2
            and same_initial_world
            and same_retry_world
            and all(item["failure_browser_grade"]["passed"] is False for item in records)
            and all(item["recovery_browser_grade"]["passed"] is True for item in records)
        ),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": round(time.time() - started, 3),
        "site_export": {
            "environment_count": export_manifest["browser_play"]["environments"],
            "python_runtime": export_manifest["browser_play"]["python_runtime"],
            "target_bundle": "play/challenges/cockpit_preflight_checklist_env.json",
        },
        "isolation": {
            "headless": True,
            "fresh_persistent_profile_per_interaction": True,
            "loopback_only": True,
            "existing_profile_reused": False,
        },
        "same_world_across_interactions": {
            "initial": same_initial_world,
            "retry": same_retry_world,
        },
        "records": records,
    }
    write_json(output / "summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not summary["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
