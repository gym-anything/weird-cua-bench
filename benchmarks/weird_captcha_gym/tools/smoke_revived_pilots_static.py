#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.weird_captcha_gym.dashboard.export_static import export_dashboard  # noqa: E402


BENCH_ROOT = ROOT / "benchmarks" / "weird_captcha_gym"
MECHANICS = ("moving_checkbox_evasive_button", "reverse_identity_gate")


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


def load_solver(mechanic: str):
    path = BENCH_ROOT / "tools" / "incubator_solvers" / f"{mechanic}.py"
    spec = importlib.util.spec_from_file_location(f"static_solver_{mechanic}", path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    output = BENCH_ROOT / "evidence" / "incubator_batch_revived_v1" / "static-summary.json"
    summary: dict[str, object] = {"ok": True, "mechanics": {}}
    with tempfile.TemporaryDirectory(prefix="revived-static-") as temporary:
        temporary_root = Path(temporary)
        site = temporary_root / "site"
        export_dashboard(site, copy_media=False)
        handler = partial(QuietHandler, directory=str(site))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 1280, "height": 720})
                for mechanic in MECHANICS:
                    state_dir = temporary_root / mechanic / "state"
                    capture_dir = temporary_root / mechanic / "captures"
                    state_dir.mkdir(parents=True)
                    bundle = json.loads((site / "play" / "challenges" / f"{mechanic}_env.json").read_text(encoding="utf-8"))
                    challenge = bundle["challenges"][0]
                    (state_dir / "ground_truth.json").write_text(json.dumps(challenge["ground_truth"]), encoding="utf-8")
                    page = context.new_page()
                    errors: list[str] = []
                    page.on("pageerror", lambda error, errors=errors: errors.append(str(error)))
                    try:
                        page.goto(
                            f"http://127.0.0.1:{server.server_port}/play/?environment={mechanic}_env&attempt=0",
                            wait_until="networkidle",
                        )
                        root_selector = page.evaluate("m => window.WeirdCaptchaMechanics[m].rootSelector", mechanic)
                        expect(page.locator(root_selector)).to_be_visible()
                        load_solver(mechanic).solve(page, state_dir, capture_dir, mechanic)
                        expect(page.locator(".readout")).to_have_text("PASS", timeout=60_000)
                        expect(page.locator(".readout")).to_have_attribute("data-status", "passed")
                        if errors:
                            raise AssertionError(errors)
                        summary["mechanics"][mechanic] = {
                            "ok": True,
                            "attempt": 0,
                            "challenge_id": challenge["ground_truth"]["challenge_id"],
                            "pyodide_grade": "PASS",
                            "real_tabs": 4 if mechanic == "reverse_identity_gate" else None,
                        }
                    finally:
                        for candidate in list(context.pages):
                            if candidate is not page:
                                try:
                                    candidate.close()
                                except Exception:
                                    pass
                        page.close()
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
