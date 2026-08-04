#!/usr/bin/env python3
"""Exercise Fake Desktop's target-only static browser export with Pyodide."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import sys
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = "fake_desktop_automation_inversion_env"
MECHANIC = "fake_desktop_automation_inversion"
sys.path.insert(0, str(ROOT))

from weird_captcha_gym.dashboard.catalog import build_catalog
from weird_captcha_gym.dashboard.export_static import _export_browser_play


def _load_solver():
    path = BENCHMARK / "tools" / "incubator_solvers" / f"{MECHANIC}.py"
    spec = importlib.util.spec_from_file_location("fake_desktop_static_solver", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load visible solver from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SOLVER = _load_solver()


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args()


def _target_catalog() -> dict[str, Any]:
    catalog = copy.deepcopy(build_catalog())
    catalog["environments"] = [
        environment for environment in catalog["environments"]
        if str(environment.get("id")) == ENVIRONMENT
    ]
    if len(catalog["environments"]) != 1:
        raise AssertionError("target was not present exactly once in the static catalog")
    return catalog


def _world_fingerprint(public: dict[str, Any]) -> str:
    visible = copy.deepcopy(public)
    for key in ("task_id", "challenge_id", "control_condition"):
        visible.pop(key, None)
    return hashlib.sha256(
        json.dumps(visible, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _challenge_id(page) -> str:
    return str(page.locator(".fake-desktop-captcha").get_attribute("data-challenge-id") or "")


def _write_truth(root: Path, label: str, challenge: dict[str, Any]) -> Path:
    state_dir = root / label
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "ground_truth.json").write_text(
        json.dumps(challenge["ground_truth"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return state_dir


def _expand_observation_panel(page) -> None:
    panel = page.locator(".weird-demo-clock")
    expect(panel).to_be_visible()
    if panel.get_attribute("data-collapsed") == "true":
        panel.locator("[data-demo-action='collapse']").click()


def main() -> None:
    args = _arguments()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    conditions: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    with tempfile.TemporaryDirectory(prefix="fake-desktop-static-") as temporary_name:
        temporary = Path(temporary_name)
        site = temporary / "site"
        export_manifest = _export_browser_play(site, _target_catalog())
        bundle = json.loads(
            (site / "play" / "challenges" / f"{ENVIRONMENT}.json").read_text(encoding="utf-8")
        )
        (out_dir / "target-static-export-summary.json").write_text(
            json.dumps(
                {
                    "environment_id": bundle["environment_id"],
                    "mechanic_id": bundle["mechanic_id"],
                    "default_difficulty": bundle["default_difficulty"],
                    "default_interaction": bundle["default_interaction"],
                    "difficulty_profiles": sorted(int(level) for level in bundle["difficulty_profiles"]),
                    "real_time": bundle["real_time"],
                    "target_export_manifest": export_manifest,
                },
                indent=2,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )

        handler = partial(_QuietHandler, directory=str(site))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 1280, "height": 720})
                for difficulty in range(1, 6):
                    profile = bundle["difficulty_profiles"][str(difficulty)]
                    for interaction in ("simplified", "full"):
                        label = f"d{difficulty}-{interaction}"
                        evidence_dir = out_dir / label
                        evidence_dir.mkdir(parents=True, exist_ok=True)
                        pool = profile["interaction_profiles"][interaction]["challenges"]
                        challenge_by_id = {
                            str(item["public_state"]["challenge_id"]): item for item in pool
                        }
                        page = context.new_page()
                        page.on("pageerror", lambda error, label=label: errors.append(f"{label}: {error}"))
                        try:
                            page.goto(
                                f"{base_url}/play/?environment={ENVIRONMENT}&attempt=0"
                                f"&difficulty={difficulty}&interaction={interaction}&time_mode=live",
                                wait_until="networkidle",
                            )
                            root = page.locator(f'.fake-desktop-captcha[data-interaction="{interaction}"]')
                            expect(root).to_be_visible(timeout=30_000)
                            initial_id = _challenge_id(page)
                            if initial_id not in challenge_by_id:
                                raise AssertionError(f"{label} rendered an unknown static challenge {initial_id!r}")
                            page.screenshot(path=str(evidence_dir / "initial.png"), full_page=True)

                            if difficulty == 3 and interaction == "full":
                                _expand_observation_panel(page)
                                page.screenshot(path=str(out_dir / "live-model-observation.png"), full_page=True)

                            solved_id = initial_id
                            fresh_failure = False
                            if difficulty == 3 and interaction == "full":
                                page.locator(".fd-submit").click()
                                expect(page.locator(".fd-failure-stamp")).to_be_visible(timeout=90_000)
                                page.wait_for_function(
                                    "old => document.querySelector('.fake-desktop-captcha')?.dataset.challengeId !== old",
                                    arg=initial_id,
                                )
                                solved_id = _challenge_id(page)
                                if solved_id not in challenge_by_id:
                                    raise AssertionError("static failure did not issue a pool challenge")
                                page.screenshot(path=str(evidence_dir / "fail-refresh.png"), full_page=True)
                                fresh_failure = True

                            state_dir = _write_truth(temporary / "solver-state", label, challenge_by_id[solved_id])
                            SOLVER.solve(page, state_dir, evidence_dir, MECHANIC)
                            page.screenshot(path=str(evidence_dir / "pyodide-pass.png"), full_page=True)
                            storage_key = f"weird-cua-browser-results:{ENVIRONMENT}:d{difficulty}:i{interaction}"
                            result = page.evaluate(
                                "key => JSON.parse(localStorage.getItem(key) || 'null')", storage_key
                            )
                            if not isinstance(result, dict):
                                raise AssertionError(f"{label} did not retain a static browser result")
                            grade = result.get("browser_grade") or {}
                            if grade.get("passed") is not True:
                                raise AssertionError(f"{label} Pyodide grade failed: {grade}")
                            (evidence_dir / "browser-result.json").write_text(
                                json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                            )
                            conditions[label] = {
                                "difficulty": difficulty,
                                "interaction": interaction,
                                "initial_challenge_id": initial_id,
                                "solved_challenge_id": solved_id,
                                "initial_world_fingerprint": _world_fingerprint(challenge_by_id[initial_id]["public_state"]),
                                "fresh_failure_and_recovery": fresh_failure,
                                "pyodide_grade": grade,
                            }
                        finally:
                            page.close()

                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(f"paused-observation: {error}"))
                try:
                    page.goto(
                        f"{base_url}/play/?environment={ENVIRONMENT}&attempt=0"
                        "&difficulty=3&interaction=full&time_mode=paused",
                        wait_until="networkidle",
                    )
                    expect(page.locator('.fake-desktop-captcha[data-interaction="full"]')).to_be_visible(timeout=30_000)
                    _expand_observation_panel(page)
                    expect(page.locator("[data-demo-mode='paused']")).to_have_attribute("aria-pressed", "true")
                    page.screenshot(path=str(out_dir / "paused-model-observation.png"), full_page=True)
                finally:
                    page.close()
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    if errors:
        raise AssertionError(f"static browser page errors: {errors}")
    same_world_pairs: dict[str, dict[str, Any]] = {}
    for difficulty in range(1, 6):
        simplified = conditions[f"d{difficulty}-simplified"]
        full = conditions[f"d{difficulty}-full"]
        same_challenge = simplified["initial_challenge_id"] == full["initial_challenge_id"]
        same_world = simplified["initial_world_fingerprint"] == full["initial_world_fingerprint"]
        if not (same_challenge and same_world):
            raise AssertionError(f"static interaction pair diverged at difficulty {difficulty}")
        same_world_pairs[str(difficulty)] = {
            "challenge_id": simplified["initial_challenge_id"],
            "world_fingerprint": simplified["initial_world_fingerprint"],
        }
    summary = {
        "environment": ENVIRONMENT,
        "static_export": "target-only browser-play export",
        "conditions": conditions,
        "all_ten_pyodide_replays": "PASS",
        "same_world_pairs": same_world_pairs,
        "visible_failure_and_recovery": "d3-full",
        "model_observations": {"live": "live-model-observation.png", "paused": "paused-model-observation.png"},
        "page_errors": [],
    }
    (out_dir / "target-static-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
