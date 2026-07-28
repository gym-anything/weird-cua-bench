from __future__ import annotations

import importlib.util
import json
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright


ROOT = Path(__file__).resolve().parents[1]
AUDIT = (
    ROOT
    / "benchmarks/weird_captcha_gym/environments/marionette_checkpoint_env/evidence_docs/audit_passive_clearance.py"
)
STATIC_SMOKE = (
    ROOT
    / "benchmarks/weird_captcha_gym/environments/marionette_checkpoint_env/evidence_docs/smoke_target_static_browser_play.py"
)
sys.path.insert(0, str(ROOT))
from benchmarks.weird_captcha_gym.dashboard.catalog import build_catalog
from benchmarks.weird_captcha_gym.dashboard.export_static import _export_browser_play


def _audit_module():
    spec = importlib.util.spec_from_file_location("marionette_passive_clearance_test", AUDIT)
    if spec is None or spec.loader is None:
        raise ImportError(AUDIT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _static_smoke_module():
    spec = importlib.util.spec_from_file_location("marionette_static_contract_test", STATIC_SMOKE)
    if spec is None or spec.loader is None:
        raise ImportError(STATIC_SMOKE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_l1_and_l2_centered_rack_never_passes_and_their_geometry_is_solvable() -> None:
    result = _audit_module().audit(sample_count=200)
    assert set(result["records"]) == {"d1_simplified", "d1_full", "d2_simplified", "d2_full"}
    for record in result["records"].values():
        assert record["passive_completions"] == 0
        assert record["passive_accepted_samples"] == 0
        assert record["geometry_requires_string_adjustment"] is True
        assert record["solved"] == 200
        assert record["geometry_solvable"] is True


def test_visible_instruction_matches_the_active_strings_rings_and_acts(tmp_path: Path) -> None:
    static = _static_smoke_module()
    environment = next(item for item in build_catalog()["environments"] if item["id"] == "marionette_checkpoint_env")
    site = tmp_path / "site"
    _export_browser_play(site, {"environments": [environment]})
    bundle = json.loads((site / "play/challenges/marionette_checkpoint_env.json").read_text(encoding="utf-8"))

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, _format, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(site)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            for difficulty in range(1, 6):
                profiles = bundle["difficulty_profiles"][str(difficulty)]["interaction_profiles"]
                for interaction in ("simplified", "full"):
                    state = profiles[interaction]["challenges"][0]["public_state"]
                    page.goto(
                        f"http://127.0.0.1:{server.server_port}/play/?environment=marionette_checkpoint_env"
                        f"&attempt=0&difficulty={difficulty}&interaction={interaction}",
                        wait_until="domcontentloaded",
                    )
                    page.wait_for_function("document.body.dataset.mechanic === 'marionette-checkpoint'")
                    assert page.locator(".ivv-head p").inner_text() == static.instruction_for(state)
                    if interaction == "simplified":
                        assert page.locator("[data-string]").count() == len(state.get("active_string_indices") or [0, 1, 2, 3])
            l4 = bundle["difficulty_profiles"]["4"]["interaction_profiles"]["full"]["challenges"][0]["public_state"]
            assert static.instruction_for(l4) == (
                "Continuously track four moving inspection rings with coupled strings. "
                "Progress grows only while every limb is inside and leaks on misses."
            )
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
