#!/usr/bin/env python3
"""Exercise Fence the Fox through its exported static Pyodide runtime."""
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
ENVIRONMENT_ID = "fence_the_fox_env"
SOLVER = BENCHMARK / "tools/incubator_solvers/fence_the_fox.py"
DEFAULT_OUTPUT = BENCHMARK / "environments/fence_the_fox_env/evidence_docs/static_target_browser"


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
        raise AssertionError(f"could not select Fence the Fox from catalog: {selected}")
    catalog["environments"] = selected
    return catalog


def fingerprint(public: dict) -> str:
    # The interaction-specific prompt must differ (click versus drag), while
    # the generated decision world must not. Fingerprint only world state.
    value = {
        key: copy.deepcopy(public[key])
        for key in (
            "radius",
            "cells",
            "fox_start",
            "initial_fences",
            "stake_budget",
            "wind_start",
            "runtime_wind_sequence",
            "runtime_driver_patterns",
            "parameters",
            "palette",
        )
    }
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main() -> int:
    output = DEFAULT_OUTPUT.resolve()
    output.mkdir(parents=True, exist_ok=True)
    started = time.time()
    records = []
    with tempfile.TemporaryDirectory(prefix="fence-fox-static-browser-isolated-") as raw:
        temporary = Path(raw)
        site = temporary / "site"
        export_manifest = _export_browser_play(site, target_catalog())
        bundle_path = site / f"play/challenges/{ENVIRONMENT_ID}.json"
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        profile = bundle["difficulty_profiles"]["3"]
        handler = partial(QuietHandler, directory=str(site))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            with sync_playwright() as playwright:
                solver = load_module(SOLVER, "fence_fox_static_solver")
                for interaction in ("simplified", "full"):
                    challenges = profile["interaction_profiles"][interaction]["challenges"]
                    challenge_by_id = {
                        item["public_state"]["challenge_id"]: item
                        for item in challenges
                    }
                    context = playwright.chromium.launch_persistent_context(
                        str(temporary / "fresh-profiles" / interaction),
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
                            f"{base_url}/play/?environment={ENVIRONMENT_ID}&attempt=0"
                            f"&difficulty=3&interaction={interaction}&time_mode=live",
                            wait_until="networkidle",
                        )
                        expect(page.locator(f".fence-fox-captcha.mode-{interaction}")).to_be_visible(timeout=10_000)
                        initial_id = str(page.locator(".fence-fox-captcha").get_attribute("data-challenge-id"))
                        initial = challenge_by_id[initial_id]
                        page.screenshot(path=str(output / f"baseline-d3-{interaction}-initial.png"))

                        page.locator("#fox-certify").click()
                        expect(page.locator(".fox-verdict.is-fail")).to_be_visible(timeout=90_000)
                        failed = page.evaluate("async () => await (await fetch('/result')).json()")
                        retry_id = str(page.locator(".fence-fox-captcha").get_attribute("data-challenge-id"))
                        if retry_id == initial_id or retry_id not in challenge_by_id:
                            raise AssertionError(f"static failure did not select a fresh exported challenge: {retry_id}")
                        if (failed.get("browser_grade") or {}).get("passed") is not False:
                            raise AssertionError(f"static incomplete enclosure was not rejected by Pyodide: {failed}")
                        page.screenshot(path=str(output / f"baseline-d3-{interaction}-failure-fresh.png"))

                        retry = challenge_by_id[retry_id]
                        state_dir = temporary / "solver-state" / interaction
                        write_json(state_dir / "public_state.json", retry["public_state"])
                        write_json(state_dir / "ground_truth.json", retry["ground_truth"])
                        solver.solve(page, state_dir, output, "fence_the_fox")
                        expect(page.locator(".fox-verdict.is-pass")).to_be_visible(timeout=90_000)
                        passed = page.evaluate("async () => await (await fetch('/result')).json()")
                        browser_grade = passed.get("browser_grade") or {}
                        if browser_grade.get("passed") is not True:
                            raise AssertionError(f"static enclosure was rejected by Pyodide: {passed}")
                        page.screenshot(path=str(output / f"baseline-d3-{interaction}-pyodide-pass.png"))
                        if errors:
                            raise AssertionError(f"browser errors in {interaction}: {errors}")
                        records.append({
                            "interaction": interaction,
                            "difficulty": 3,
                            "initial_challenge_id": initial_id,
                            "retry_challenge_id": retry_id,
                            "initial_world_fingerprint": fingerprint(initial["public_state"]),
                            "retry_world_fingerprint": fingerprint(retry["public_state"]),
                            "failure_browser_grade": failed["browser_grade"],
                            "recovery_browser_grade": browser_grade,
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
