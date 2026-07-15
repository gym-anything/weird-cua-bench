#!/usr/bin/env python3
"""Exercise the published-dashboard -> localhost-companion -> browser-puzzle path."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright


BENCHMARK_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BENCHMARK_ROOT.parents[1]
sys.path.insert(0, str(REPO_ROOT))

from benchmarks.weird_captcha_gym.dashboard.export_static import export_dashboard  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test a static CAPTCHA Bench dashboard with its local companion.")
    parser.add_argument("--out-dir", default=str(BENCHMARK_ROOT / "dashboard" / "evidence"))
    return parser.parse_args()


def reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def wait_for_http(url: str, *, timeout: float = 15) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=0.4) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.08)
    raise RuntimeError(f"server did not become ready: {url}")


def stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def main() -> None:
    args = parse_args()
    output = Path(args.out_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    summary: dict[str, object] = {}

    with tempfile.TemporaryDirectory(prefix="captcha-dashboard-shared-") as temporary:
        temp_root = Path(temporary)
        static_port = reserve_port()
        companion_port = reserve_port()
        static_origin = f"http://127.0.0.1:{static_port}"
        static_url = f"{static_origin}/captcha-bench"
        companion_url = f"http://127.0.0.1:{companion_port}"
        token = "smoke-" + secrets.token_urlsafe(28)
        token_path = temp_root / "companion-token"
        token_path.write_text(token + "\n", encoding="utf-8")
        review_path = temp_root / "reviews.json"
        site_root = temp_root / "site"
        export_root = site_root / "captcha-bench"
        manifest = export_dashboard(export_root, companion_url=companion_url)

        environment = os.environ.copy()
        python_paths = [str(REPO_ROOT / "src"), str(REPO_ROOT)]
        if environment.get("PYTHONPATH"):
            python_paths.append(environment["PYTHONPATH"])
        environment["PYTHONPATH"] = os.pathsep.join(python_paths)
        environment["PYTHONUNBUFFERED"] = "1"

        static_process = subprocess.Popen(
            [sys.executable, "-m", "http.server", str(static_port), "--bind", "127.0.0.1", "--directory", str(site_root)],
            cwd=REPO_ROOT,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        companion_process = subprocess.Popen(
            [
                sys.executable,
                str(BENCHMARK_ROOT / "dashboard" / "server.py"),
                "--companion",
                "--host",
                "127.0.0.1",
                "--port",
                str(companion_port),
                "--runner",
                "local",
                "--allow-origin",
                static_origin,
                "--token-path",
                str(token_path),
                "--review-path",
                str(review_path),
            ],
            cwd=REPO_ROOT,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        try:
            wait_for_http(f"{static_url}/")
            wait_for_http(f"{companion_url}/api/health")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
                page.on("pageerror", lambda exc: errors.append(str(exc)))
                page.goto(static_url, wait_until="networkidle")
                expect(page.locator("#nav-environment-count")).to_have_text("75")
                expect(page.locator('[data-nav="atlas"]')).to_have_count(0)
                expect(page.locator(".companion-status")).to_have_attribute("data-connection", "optional")

                page.locator('[data-action="open-companion"]').click()
                expect(page.locator(".companion-modal h2")).to_have_text("Browser play needs no setup")
                expect(page.locator(".companion-ready")).to_contain_text("You do not need to connect anything")
                expect(page.locator(".companion-advanced")).to_contain_text("Enable optional VNC, reviews, and evaluations")
                expect(page.locator("#companion-form")).not_to_be_visible()
                page.screenshot(path=str(output / "shared-dashboard-local-setup.png"), full_page=True)
                page.locator(".modal-close").click()

                shortlist_context = browser.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
                shortlist = shortlist_context.new_page()
                shortlist.on("pageerror", lambda exc: errors.append(f"shared shortlist: {exc}"))
                shortlist.goto(
                    f"{static_url}/?stars=domino_autopsy_env,funeral_ritual_env#/environments",
                    wait_until="networkidle",
                )
                expect(shortlist.locator(".star-share-banner")).to_contain_text("Someone starred these for you")
                expect(shortlist.locator(".environment-card")).to_have_count(2)
                expect(shortlist.locator('[data-open-env="domino_autopsy_env"]')).to_have_count(1)
                expect(shortlist.locator('[data-open-env="funeral_ritual_env"]')).to_have_count(1)
                expect(shortlist.locator(".star-toggle-card")).to_have_count(2)
                expect(shortlist.locator(".star-toggle-card").first).to_be_disabled()
                if shortlist.evaluate("localStorage.getItem('captcha-bench-starred-environments:v1')") is not None:
                    raise AssertionError("static shortlist mutated personal browser stars on open")
                shortlist.screenshot(path=str(output / "shared-dashboard-starred-shortlist.png"), full_page=True)
                shortlist_context.close()

                page.goto(
                    f"{static_url}/#/environment/bureaucratic_signature_trap_env",
                    wait_until="networkidle",
                )
                expect(page.locator(".detail-title")).to_have_text("Bureaucratic Signature Trap")
                page.locator(".solution-reel > summary").click()
                page.wait_for_function(
                    "document.querySelector('.solution-reel video').readyState >= 1"
                )
                solution_video = page.locator(".solution-reel video")
                expect(solution_video).to_have_js_property("videoWidth", 1280)
                expect(solution_video).to_have_js_property("videoHeight", 720)
                if float(solution_video.evaluate("video => video.duration")) <= 7:
                    raise AssertionError("exported pending-cohort solution film is unexpectedly short")

                page.goto(f"{static_url}/#pair={token}", wait_until="networkidle")
                page.reload(wait_until="networkidle")  # Model the fresh tab opened by the launcher.
                expect(page.locator(".companion-status")).to_have_attribute("data-connection", "connected")
                expect(page).to_have_url(f"{static_url}/#/observatory")
                page.screenshot(path=str(output / "shared-dashboard-paired.png"), full_page=True)

                page.goto(f"{static_url}/#/environment/domino_autopsy_env", wait_until="networkidle")
                expect(page.locator(".detail-title")).to_have_text("Domino Autopsy")
                page.locator(".solution-reel > summary").click()
                domino_solution = page.locator(".solution-reel video")
                page.wait_for_function(
                    "document.querySelector('.solution-reel video').readyState >= 1"
                )
                expect(domino_solution).to_have_js_property("videoWidth", 1280)
                expect(domino_solution).to_have_js_property("videoHeight", 720)
                domino_mp4 = domino_solution.locator('source[type="video/mp4"]')
                if "foundational_seven_v1" not in str(domino_mp4.get_attribute("src")):
                    raise AssertionError("Domino dossier did not load the new foundational solution film")
                page.locator('[data-config-launch="domino_autopsy_env"]').first.click()
                expect(page.locator("#launch-mode")).to_have_value("browser")
                page.locator('#launch-form input[name="auto_open"]').evaluate("node => { node.checked = false; }")
                page.locator("#launch-seed").fill("1783650327")
                page.locator("#launch-form").evaluate("form => form.requestSubmit()")
                session_card = page.locator(".session-card").first
                expect(session_card).to_have_attribute("data-status", "running", timeout=20_000)
                browser_url = session_card.locator(".session-connection code").inner_text()
                if not browser_url.startswith("http://127.0.0.1:"):
                    raise AssertionError(f"unexpected local browser URL: {browser_url}")
                page.screenshot(path=str(output / "local-browser-session.png"), full_page=True)

                puzzle = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
                puzzle.on("pageerror", lambda exc: errors.append(f"puzzle: {exc}"))
                puzzle.goto(browser_url, wait_until="networkidle")
                expect(puzzle.locator("body")).to_contain_text("BUILD THE BRIDGE")
                puzzle.screenshot(path=str(output / "local-browser-puzzle.png"), full_page=True)
                puzzle.close()

                session_card.locator("[data-stop-session]").click()
                expect(session_card).to_have_attribute("data-status", "stopped", timeout=12_000)
                if errors:
                    raise AssertionError("browser errors: " + " | ".join(errors))
                summary = {
                    "ok": True,
                    "catalog_records": manifest["catalog"]["total"],
                    "built_environments": manifest["catalog"]["built"],
                    "survey_included": manifest["survey_included"],
                    "deployment_path": "/weird-cua-bench/",
                    "paired": True,
                    "starred_shortlist_loaded": True,
                    "pending_solution_video_loaded": True,
                    "foundational_solution_video_loaded": True,
                    "local_browser_url": browser_url,
                    "session_stopped": True,
                    "page_errors": errors,
                }
                browser.close()
        finally:
            stop_process(companion_process)
            stop_process(static_process)

    (output / "shared-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
