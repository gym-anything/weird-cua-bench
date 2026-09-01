#!/usr/bin/env python3
"""Exercise Five-Second Rule through exported static Pyodide browser play."""
from __future__ import annotations

import argparse
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
ENVIRONMENT = BENCHMARK / "environments/five_second_rule_env"
SOLVER = BENCHMARK / "tools/incubator_solvers/five_second_rule.py"
CAPTURE_HELPERS = BENCHMARK / "tools/capture_five_second_rule_evidence.py"
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.out_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    started = time.time()

    with tempfile.TemporaryDirectory(prefix="five-second-static-isolated-") as temporary_text:
        temporary = Path(temporary_text)
        site = temporary / "site"
        export_manifest = export_dashboard(site, copy_media=False)
        bundle_path = site / "play/challenges/five_second_rule_env.json"
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        handler = partial(QuietHandler, directory=str(site))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        records = []
        try:
            with sync_playwright() as playwright:
                solver = load_module(SOLVER, "five_second_static_solver")
                helpers = load_module(CAPTURE_HELPERS, "five_second_static_helpers")
                profiles = bundle["difficulty_profiles"]["4"]["interaction_profiles"]
                for interaction in ("simplified", "full"):
                    challenges = profiles[interaction]["challenges"]
                    initial_state = challenges[0]["public_state"]
                    retry_state = challenges[1]["public_state"]
                    retry_truth = challenges[1]["ground_truth"]
                    profile = temporary / "fresh-profiles" / interaction
                    context = playwright.chromium.launch_persistent_context(
                        str(profile),
                        headless=True,
                        viewport={"width": 1290, "height": 740},
                        device_scale_factor=1,
                    )
                    page = context.pages[0]
                    errors: list[str] = []
                    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    try:
                        page.goto(
                            f"{base_url}/play/?environment=five_second_rule_env"
                            f"&attempt=0&difficulty=4&interaction={interaction}",
                            wait_until="networkidle",
                        )
                        expect(page.locator(f".five-second-rule.mode-{interaction}")).to_be_visible(timeout=10_000)
                        initial_instruction = page.locator(".fsr-order").inner_text()
                        page.screenshot(path=str(output / f"static-baseline-d4-{interaction}-initial.png"), full_page=True)

                        helpers.issue_failure(page, initial_state["rounds"][0], interaction)
                        expect(page.locator(".fsr-verdict.is-fail")).to_be_visible(timeout=90_000)
                        failed = page.evaluate("async () => (await (await fetch('/result')).json())")
                        retry_instruction = page.locator(".fsr-order").inner_text()
                        if failed.get("browser_grade", {}).get("passed") is not False:
                            raise AssertionError(f"static failure was not graded by Pyodide: {failed}")
                        if initial_instruction == retry_instruction or initial_state["challenge_id"] == retry_state["challenge_id"]:
                            raise AssertionError("static failure did not render the next bundled challenge")
                        page.screenshot(path=str(output / f"static-baseline-d4-{interaction}-failure-fresh.png"), full_page=True)

                        state_dir = temporary / "solver-state" / interaction
                        write_json(state_dir / "public_state.json", retry_state)
                        write_json(state_dir / "ground_truth.json", retry_truth)
                        solver.solve(page, state_dir, output, "five_second_rule")
                        expect(page.locator(".fsr-verdict.is-pass")).to_be_visible(timeout=90_000)
                        passed = page.evaluate("async () => (await (await fetch('/result')).json())")
                        if passed.get("browser_grade", {}).get("passed") is not True:
                            raise AssertionError(f"static recovery was not graded by Pyodide: {passed}")
                        page.screenshot(path=str(output / f"static-baseline-d4-{interaction}-pass.png"), full_page=True)
                        if errors:
                            raise AssertionError(f"browser console errors: {errors}")
                        records.append({
                            "interaction": interaction,
                            "difficulty": 4,
                            "initial_challenge_id": initial_state["challenge_id"],
                            "retry_challenge_id": retry_state["challenge_id"],
                            "initial_world_fingerprint": initial_state["world_fingerprint"],
                            "retry_world_fingerprint": retry_state["world_fingerprint"],
                            "failure_browser_grade": failed["browser_grade"],
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

    same_initial = len(records) == 2 and len({item["initial_world_fingerprint"] for item in records}) == 1
    same_retry = len(records) == 2 and len({item["retry_world_fingerprint"] for item in records}) == 1
    summary = {
        "ok": len(records) == 2 and same_initial and same_retry and all(not item["failure_browser_grade"]["passed"] and item["recovery_browser_grade"]["passed"] for item in records),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": round(time.time() - started, 3),
        "site_export": {
            "environment_count": export_manifest["browser_play"]["environments"],
            "python_runtime": export_manifest["browser_play"]["python_runtime"],
            "target_bundle": "play/challenges/five_second_rule_env.json",
        },
        "isolation": {
            "headless": True,
            "fresh_persistent_profile_per_interaction": True,
            "loopback_only": True,
            "existing_profile_reused": False,
            "foreground_browser_used": False,
        },
        "same_world_across_interactions": {"initial": same_initial, "retry": same_retry},
        "records": records,
    }
    write_json(output / "summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
