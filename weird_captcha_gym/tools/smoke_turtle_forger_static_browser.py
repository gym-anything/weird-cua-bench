#!/usr/bin/env python3
"""Exercise Turtle Forger through its exported static Pyodide runtime."""
from __future__ import annotations

import copy
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

from weird_captcha_gym.dashboard.catalog import build_catalog  # noqa: E402
from weird_captcha_gym.dashboard.export_static import _export_browser_play  # noqa: E402


BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT_ID = "turtle_forger_env"
SOLVER = BENCHMARK / "tools/incubator_solvers/turtle_forger.py"
DEFAULT_OUTPUT = BENCHMARK / "environments/turtle_forger_env/evidence_docs/static_target_browser"


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


def target_catalog() -> dict:
    catalog = copy.deepcopy(build_catalog())
    selected = [item for item in catalog["environments"] if item["id"] == ENVIRONMENT_ID]
    if len(selected) != 1:
        raise AssertionError(f"could not select Turtle Forger from catalog: {selected}")
    catalog["environments"] = selected
    return catalog


def fingerprint(public: dict) -> str:
    value = copy.deepcopy(public)
    for key in ("task_id", "challenge_id", "control_condition"):
        value.pop(key, None)
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main() -> None:
    output = DEFAULT_OUTPUT.resolve()
    output.mkdir(parents=True, exist_ok=True)
    started = time.time()
    records = []
    with tempfile.TemporaryDirectory(prefix="turtle-static-browser-isolated-") as raw:
        temporary = Path(raw)
        site = temporary / "site"
        export_manifest = _export_browser_play(site, target_catalog())
        bundle = json.loads((site / f"play/challenges/{ENVIRONMENT_ID}.json").read_text(encoding="utf-8"))
        profile = bundle["difficulty_profiles"]["3"]
        handler = partial(QuietHandler, directory=str(site))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            with sync_playwright() as playwright:
                solver = load_module(SOLVER, "turtle_static_solver")
                for interaction in ("simplified", "full"):
                    challenges = profile["interaction_profiles"][interaction]["challenges"]
                    challenge_by_id = {
                        item["public_state"]["challenge_id"]: item
                        for item in challenges
                    }
                    challenge_by_seal = {
                        item["public_state"]["seal_id"]: item
                        for item in challenges
                    }
                    context = playwright.chromium.launch_persistent_context(
                        str(temporary / "fresh-profiles" / interaction),
                        headless=True,
                        viewport={"width": 1280, "height": 720},
                        device_scale_factor=1,
                    )
                    page = context.pages[0]
                    errors: list[str] = []
                    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    try:
                        page.goto(
                            f"{base_url}/play/?environment={ENVIRONMENT_ID}&attempt=0"
                            f"&difficulty=3&interaction={interaction}&time_mode=live",
                            wait_until="networkidle",
                        )
                        expect(page.locator(f".turtle-forger.mode-{interaction}")).to_be_visible(timeout=10_000)
                        visible_seal = page.locator(".tfg-header aside span").inner_text().removeprefix("MASTER ").strip()
                        if visible_seal not in challenge_by_seal:
                            raise AssertionError(f"unknown visible static master {visible_seal}")
                        initial_challenge = challenge_by_seal[visible_seal]
                        initial = initial_challenge["public_state"]
                        initial_id = str(initial["challenge_id"])
                        page.screenshot(path=str(output / f"baseline-d3-{interaction}-initial.png"))

                        first_key = str(initial["command_palette"][0]["key"])
                        solver._append_visible_card(page, first_key, interaction)
                        page.locator("#tfg-proof").click()
                        page.locator("#tfg-certify").click()
                        expect(page.locator(".tfg-verdict.is-fail")).to_be_visible(timeout=90_000)
                        failed = page.evaluate("async () => await (await fetch('/result')).json()")
                        retry_seal = page.locator(".tfg-header aside span").inner_text().removeprefix("MASTER ").strip()
                        if retry_seal not in challenge_by_seal:
                            raise AssertionError(f"unknown fresh static master {retry_seal}")
                        retry = challenge_by_seal[retry_seal]["public_state"]
                        retry_id = str(retry["challenge_id"])
                        if retry_id == initial_id or retry_id not in challenge_by_id:
                            raise AssertionError(f"static failure did not select a fresh exported challenge: {retry_id}")
                        if (failed.get("browser_grade") or {}).get("passed") is not False:
                            raise AssertionError(f"static invalid proof was not rejected by Pyodide: {failed}")
                        page.screenshot(path=str(output / f"baseline-d3-{interaction}-failure-fresh.png"))

                        retry_challenge = challenge_by_id[retry_id]
                        page.locator("#tfg-scan").click()
                        scan_ms = len(retry["runtime_target_segments"]) * (
                            int(retry["parameters"]["stroke_ms"])
                            + int(retry["parameters"]["gap_ms"])
                        )
                        expect(page.locator("#tfg-scan-counter")).to_have_text(
                            "SCAN COMPLETE · REPLAY AVAILABLE",
                            timeout=scan_ms + 5_000,
                        )
                        state_dir = temporary / "solver-state" / interaction
                        write_json(state_dir / "public_state.json", retry_challenge["public_state"])
                        write_json(state_dir / "ground_truth.json", retry_challenge["ground_truth"])
                        solver.solve(page, state_dir, output, "turtle_forger")
                        expect(page.locator(".tfg-verdict.is-pass")).to_be_visible(timeout=90_000)
                        passed = page.evaluate("async () => await (await fetch('/result')).json()")
                        browser_grade = passed.get("browser_grade") or {}
                        if browser_grade.get("passed") is not True:
                            raise AssertionError(f"static canonical proof was rejected by Pyodide: {passed}")
                        if int(passed.get("scan_count") or 0) < 1:
                            raise AssertionError("static successful challenge bypassed SCAN MASTER")
                        page.screenshot(path=str(output / f"baseline-d3-{interaction}-pyodide-pass.png"))
                        if errors:
                            raise AssertionError(f"browser errors in {interaction}: {errors}")
                        records.append({
                            "interaction": interaction,
                            "difficulty": 3,
                            "initial_challenge_id": initial_id,
                            "retry_challenge_id": retry_id,
                            "initial_world_fingerprint": fingerprint(challenge_by_id[initial_id]["public_state"]),
                            "retry_world_fingerprint": fingerprint(retry_challenge["public_state"]),
                            "failure_browser_grade": failed["browser_grade"],
                            "recovery_browser_grade": browser_grade,
                            "successful_scan_count": int(passed["scan_count"]),
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

    same_initial = records[0]["initial_world_fingerprint"] == records[1]["initial_world_fingerprint"]
    same_retry = records[0]["retry_world_fingerprint"] == records[1]["retry_world_fingerprint"]
    summary = {
        "ok": (
            len(records) == 2
            and same_initial
            and same_retry
            and all(item["failure_browser_grade"]["passed"] is False for item in records)
            and all(item["recovery_browser_grade"]["passed"] is True for item in records)
        ),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": round(time.time() - started, 3),
        "site_export": {
            "environment_count": export_manifest["environments"],
            "target_bundle": f"play/challenges/{ENVIRONMENT_ID}.json",
        },
        "isolation": {
            "headless": True,
            "fresh_persistent_profile_per_interaction": True,
            "loopback_only": True,
            "existing_profile_reused": False,
        },
        "same_world_across_interactions": {"initial": same_initial, "retry": same_retry},
        "records": records,
    }
    write_json(output / "summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not summary["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
