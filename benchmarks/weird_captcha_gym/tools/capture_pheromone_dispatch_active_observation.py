#!/usr/bin/env python3
"""Capture isolated, active-state browser evidence for Pheromone Dispatch."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from smoke_controlled_interaction_ui import (
    BENCH_ROOT,
    HELPERS,
    MATERIALIZER,
    controlled_task,
    load_module,
    observation_viewport,
    read_json,
    start_server,
)


ENVIRONMENT = "pheromone_dispatch_env"
MECHANIC = "pheromone_dispatch"
BASE_TASK = BENCH_ROOT / "environments" / ENVIRONMENT / "tasks" / "pheromone_dispatch_seed_0001" / "task.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def screen_point(canvas_box: dict[str, float], point: list[float] | tuple[float, float]) -> tuple[float, float]:
    return (
        canvas_box["x"] + float(point[0]) / 900 * canvas_box["width"],
        canvas_box["y"] + float(point[1]) / 480 * canvas_box["height"],
    )


def paint_route(
    page,
    canvas_box: dict[str, float],
    field_id: str,
    path: list[list[float]],
    interaction: str,
    *,
    sparse: bool = False,
) -> None:
    page.locator(f'[data-field="{field_id}"]').click()
    if interaction == "simplified":
        points = [path[0]]
        for first, second in zip(path, path[1:]):
            steps = 1 if sparse else max(1, int((math.dist(first, second) + 119) // 120))
            points.extend([
                [
                    float(first[0]) + (float(second[0]) - float(first[0])) * step / steps,
                    float(first[1]) + (float(second[1]) - float(first[1])) * step / steps,
                ]
                for step in range(1, steps + 1)
            ])
        for point in points:
            page.mouse.click(*screen_point(canvas_box, point))
        page.locator("#pheromone-commit").click()
        return
    page.mouse.move(*screen_point(canvas_box, path[0]))
    page.mouse.down()
    try:
        for first, second in zip(path, path[1:]):
            steps = 1 if sparse else max(1, int((math.dist(first, second) + 119) // 120))
            for step in range(1, steps + 1):
                amount = step / steps
                page.mouse.move(*screen_point(canvas_box, [
                    float(first[0]) + (float(second[0]) - float(first[0])) * amount,
                    float(first[1]) + (float(second[1]) - float(first[1])) * amount,
                ]))
    finally:
        page.mouse.up()


def model_snapshot(page) -> dict:
    return page.evaluate(
        """() => {
            const model = window.pheromoneDispatchModel;
            const ants = Object.fromEntries(Object.entries(model.ants).map(([field, items]) => [field, items.slice(0, 2).map((ant) => ({x: ant.x, y: ant.y, carrying: ant.carrying, done: ant.done}))]));
            return {tick: model.tick, running: model.running, delivered: {...model.delivered}, last_refresh: {...model.lastRefresh}, ants, clock: WeirdCaptchaTime.status()};
        }"""
    )


def refresh_until_pass(page, canvas_box: dict[str, float], public: dict, truth: dict, interaction: str) -> None:
    deadline = time.time() + 38
    while time.time() < deadline:
        if page.locator(".ivv-verdict.is-pass").count() and page.locator(".ivv-verdict.is-pass").is_visible():
            return
        snapshot = model_snapshot(page)
        for field in public["fields"]:
            if page.locator(".ivv-verdict.is-pass").count() and page.locator(".ivv-verdict.is-pass").is_visible():
                return
            field_id = field["id"]
            if int(snapshot["tick"]) - int(snapshot["last_refresh"][field_id]) >= int(field["trail_ttl_ticks"]) - 28:
                paint_route(page, canvas_box, field_id, truth["reference_paths"][field_id], interaction)
        page.wait_for_timeout(100)
    raise AssertionError("active observation run did not complete")


def capture_active_mode(*, browser, task_json: Path, mode: str, root: Path, helpers) -> dict:
    evidence_dir = root / mode
    evidence_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"pheromone-active-{mode}-") as temp_name:
        state_dir = Path(temp_name) / "state"
        state_dir.mkdir()
        server, port = start_server(task_json, MECHANIC, "full", state_dir)
        page = browser.new_page(viewport=observation_viewport(BENCH_ROOT / "environments" / ENVIRONMENT), device_scale_factor=1)
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            current_task = state_dir / "current_task.json"
            original_task_text = current_task.read_text(encoding="utf-8")
            current_task.unlink()
            try:
                page.goto(
                    f"http://127.0.0.1:{port}/?time_mode={mode}&start_paused={'1' if mode == 'paused' else '0'}",
                    wait_until="networkidle",
                )
            finally:
                current_task.write_text(original_task_text, encoding="utf-8")
            expect(page.locator("[data-interaction]")).to_have_attribute("data-interaction", "full")
            public = read_json(state_dir / "public_state.json")
            truth = read_json(state_dir / "ground_truth.json")
            canvas = page.locator("#pheromone-canvas")
            canvas_box = canvas.bounding_box()
            if not canvas_box:
                raise AssertionError("Pheromone Dispatch canvas has no geometry")
            if mode == "paused":
                page.evaluate("() => WeirdCaptchaTime.resume()")
            for field in public["fields"]:
                paint_route(page, canvas_box, field["id"], truth["reference_paths"][field["id"]], "full")
            page.locator("#pheromone-dispatch").click()
            page.wait_for_function("() => window.pheromoneDispatchModel.running && window.pheromoneDispatchModel.tick >= 8")
            if mode == "paused":
                page.evaluate("() => WeirdCaptchaTime.pause()")
            before_delay = model_snapshot(page)
            write_json(evidence_dir / "before-model-delay.json", before_delay)
            frames: list[dict] = []
            for index in range(6):
                frame_name = f"obs-screen-{index + 1:02d}.png"
                frame_path = evidence_dir / frame_name
                page.screenshot(path=str(frame_path))
                frames.append({
                    "frame": frame_name,
                    "sha256": hashlib.sha256(frame_path.read_bytes()).hexdigest(),
                    "snapshot": model_snapshot(page),
                })
                if index < 5:
                    page.wait_for_timeout(90)
            unique_frames = len({frame["sha256"] for frame in frames})
            if mode == "live" and unique_frames < 2:
                raise AssertionError("live active observation did not produce changing frames")
            if mode == "paused" and unique_frames != 1:
                raise AssertionError("paused active observation did not freeze the rendered swarm")
            write_json(evidence_dir / "observation-frames.json", {
                "mode": mode,
                "frame_count": 6,
                "final_obs_screen": "obs-screen-06.png",
                "unique_frame_hashes": unique_frames,
                "frames": frames,
            })
            page.wait_for_timeout(350)
            after_delay = model_snapshot(page)
            write_json(evidence_dir / "after-model-delay.json", after_delay)
            page.screenshot(path=str(evidence_dir / "after-model-delay.png"))
            if mode == "live":
                if int(after_delay["tick"]) <= int(before_delay["tick"]):
                    raise AssertionError("live active swarm did not advance during model delay")
            elif int(after_delay["tick"]) != int(before_delay["tick"]) or abs(float(after_delay["clock"]["task_time_ms"]) - float(before_delay["clock"]["task_time_ms"])) > 2:
                raise AssertionError("paused active swarm advanced during model delay")
            if mode == "paused":
                page.evaluate("() => WeirdCaptchaTime.resume()")
            refresh_until_pass(page, canvas_box, public, truth, "full")
            if mode == "paused":
                page.evaluate("() => WeirdCaptchaTime.pause()")
            expect(page.locator(".readout")).to_have_attribute("data-status", "passed", timeout=8_000)
            page.screenshot(path=str(evidence_dir / "pass.png"))
            exported = {
                "public_state": read_json(state_dir / "public_state.json"),
                "ground_truth": read_json(state_dir / "ground_truth.json"),
                "result": read_json(state_dir / "result.json"),
            }
            server_grade = exported["result"].get("server_grade") or {}
            verifier = helpers.verify_external_mechanic(exported, MECHANIC)
            if server_grade.get("passed") is not True or verifier.get("passed") is not True:
                raise AssertionError(f"active observation result rejected: {server_grade}, {verifier}")
            write_json(evidence_dir / "server-grade.json", server_grade)
            write_json(evidence_dir / "verifier.json", verifier)
            write_json(evidence_dir / "exported-result.json", exported)
            if errors:
                raise AssertionError(f"browser errors: {errors}")
            return {
                "mode": mode,
                "passed": True,
                "before_delay": before_delay,
                "after_delay": after_delay,
                "server_grade": server_grade,
                "verifier": verifier,
            }
        finally:
            page.close()
            server.terminate()
            try:
                server.wait(timeout=3)
            except Exception:
                server.kill()


def sampling_snapshot(page) -> dict:
    return page.evaluate(
        """() => {
            const model = window.pheromoneDispatchModel;
            const readout = document.querySelector(".readout");
            return {
                active_stroke_rejected: model.activeStrokeRejected,
                event_types: model.events.map((event) => event.type),
                paths: Object.fromEntries(Object.entries(model.paths).map(([field, path]) => [field, path.length])),
                running: model.running,
                status: readout?.dataset.status || null,
                tick: model.tick,
                verdict: readout?.textContent || "",
            };
        }"""
    )


def capture_sampled_route_pass(*, browser, task_json: Path, interaction: str, root: Path, helpers) -> dict:
    evidence_dir = root / interaction
    evidence_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"pheromone-sampled-{interaction}-") as temp_name:
        state_dir = Path(temp_name) / "state"
        state_dir.mkdir()
        server, port = start_server(task_json, MECHANIC, interaction, state_dir)
        page = browser.new_page(viewport=observation_viewport(BENCH_ROOT / "environments" / ENVIRONMENT), device_scale_factor=1)
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            current_task = state_dir / "current_task.json"
            current_task_text = current_task.read_text(encoding="utf-8")
            current_task.unlink()
            try:
                page.goto(f"http://127.0.0.1:{port}/?time_mode=live", wait_until="networkidle")
            finally:
                current_task.write_text(current_task_text, encoding="utf-8")
            expect(page.locator("[data-interaction]")).to_have_attribute("data-interaction", interaction)
            public = read_json(state_dir / "public_state.json")
            truth = read_json(state_dir / "ground_truth.json")
            canvas_box = page.locator("#pheromone-canvas").bounding_box()
            if not canvas_box:
                raise AssertionError("sampled-route canvas has no geometry")
            for field in public["fields"]:
                paint_route(page, canvas_box, field["id"], truth["reference_paths"][field["id"]], interaction)
            before_dispatch = sampling_snapshot(page)
            if any(length <= 5 for length in before_dispatch["paths"].values()) or before_dispatch["status"] != "passed":
                raise AssertionError(f"browser did not accept sampled {interaction} routes: {before_dispatch}")
            page.locator("#pheromone-dispatch").click()
            page.wait_for_function("() => window.pheromoneDispatchModel.running && window.pheromoneDispatchModel.tick >= 3")
            accepted = sampling_snapshot(page)
            if not accepted["running"] or "dispatch" not in accepted["event_types"]:
                raise AssertionError(f"browser did not dispatch accepted {interaction} routes: {accepted}")
            page.screenshot(path=str(evidence_dir / "accepted-route-running.png"))
            write_json(evidence_dir / "accepted-browser-snapshot.json", accepted)
            refresh_until_pass(page, canvas_box, public, truth, interaction)
            expect(page.locator(".readout")).to_have_attribute("data-status", "passed", timeout=8_000)
            page.screenshot(path=str(evidence_dir / "pass.png"))
            exported = {
                "public_state": read_json(state_dir / "public_state.json"),
                "ground_truth": read_json(state_dir / "ground_truth.json"),
                "result": read_json(state_dir / "result.json"),
            }
            server_grade = exported["result"].get("server_grade") or {}
            verifier = helpers.verify_external_mechanic(exported, MECHANIC)
            if server_grade.get("passed") is not True or verifier.get("passed") is not True:
                raise AssertionError(f"sampled {interaction} route failed replay: {server_grade}, {verifier}")
            write_json(evidence_dir / "server-grade.json", server_grade)
            write_json(evidence_dir / "verifier.json", verifier)
            write_json(evidence_dir / "exported-result.json", exported)
            if errors:
                raise AssertionError(f"browser errors: {errors}")
            return {
                "interaction": interaction,
                "accepted_browser_snapshot": accepted,
                "passed": True,
                "server_grade": server_grade,
                "verifier": verifier,
            }
        finally:
            page.close()
            server.terminate()
            try:
                server.wait(timeout=3)
            except Exception:
                server.kill()


def capture_sparse_rejection(*, browser, task_json: Path, interaction: str, label: str, root: Path) -> dict:
    evidence_dir = root / label
    evidence_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"pheromone-sparse-{label}-") as temp_name:
        state_dir = Path(temp_name) / "state"
        state_dir.mkdir()
        server, port = start_server(task_json, MECHANIC, interaction, state_dir)
        page = browser.new_page(viewport=observation_viewport(BENCH_ROOT / "environments" / ENVIRONMENT), device_scale_factor=1)
        try:
            page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
            page.wait_for_function(f"() => window.pheromoneDispatchModel?.interaction === '{interaction}'")
            public = read_json(state_dir / "public_state.json")
            truth = read_json(state_dir / "ground_truth.json")
            canvas_box = page.locator("#pheromone-canvas").bounding_box()
            if not canvas_box:
                raise AssertionError("sparse-rejection canvas has no geometry")
            for field in public["fields"]:
                paint_route(page, canvas_box, field["id"], truth["reference_paths"][field["id"]], interaction, sparse=True)
            snapshot = sampling_snapshot(page)
            if snapshot["running"] or snapshot["status"] != "error" or "dispatch" in snapshot["event_types"]:
                raise AssertionError(f"browser accepted sparse {interaction} route before dispatch: {snapshot}")
            if "GAP TOO LARGE" not in snapshot["verdict"]:
                raise AssertionError(f"browser did not visibly explain sparse {interaction} rejection: {snapshot}")
            if (state_dir / "result.json").exists():
                raise AssertionError("sparse route unexpectedly produced an authoritative submission")
            page.screenshot(path=str(evidence_dir / "sparse-route-rejected.png"))
            write_json(evidence_dir / "browser-snapshot.json", snapshot)
            write_json(evidence_dir / "public_state.json", public)
            write_json(evidence_dir / "ground_truth.json", truth)
            return {
                "interaction": interaction,
                "label": label,
                "rejected_before_dispatch": True,
                "status": snapshot["status"],
                "verdict": snapshot["verdict"],
            }
        finally:
            page.close()
            server.terminate()
            try:
                server.wait(timeout=3)
            except Exception:
                server.kill()


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    environment = BENCH_ROOT / "environments" / ENVIRONMENT
    controls = read_json(environment / "controls.json")
    materializer = load_module("pheromone_active_materializer", MATERIALIZER)
    helpers = load_module("pheromone_active_helpers", HELPERS)
    with tempfile.TemporaryDirectory(prefix="pheromone-active-materialized-") as temp_name, sync_playwright() as playwright:
        tasks_root = Path(temp_name) / "materialized"
        materializer.materialize_environment(environment, tasks_root)
        tasks = tasks_root / ENVIRONMENT / "tasks"
        l4_full = controlled_task(tasks, int(controls["baseline"]["difficulty"]), "full")
        l4_simplified = controlled_task(tasks, int(controls["baseline"]["difficulty"]), "simplified")
        browser = playwright.chromium.launch(headless=True)
        try:
            result = {
                "isolation": {
                    "browser": "chromium.launch(headless=True)",
                    "profile": "fresh Playwright browser and page",
                    "server": "per-run loopback server",
                    "state": "fresh TemporaryDirectory per run",
                },
                "route_sampling": {
                    "accepted_full": capture_sampled_route_pass(browser=browser, task_json=l4_full, interaction="full", root=args.out_dir / "route-sampling", helpers=helpers),
                    "accepted_simplified": capture_sampled_route_pass(browser=browser, task_json=l4_simplified, interaction="simplified", root=args.out_dir / "route-sampling", helpers=helpers),
                    "original_full_sparse": capture_sparse_rejection(browser=browser, task_json=BASE_TASK, interaction="full", label="original-full-sparse", root=args.out_dir / "route-sampling"),
                    "l4_full_sparse": capture_sparse_rejection(browser=browser, task_json=l4_full, interaction="full", label="l4-full-sparse", root=args.out_dir / "route-sampling"),
                    "l4_simplified_sparse": capture_sparse_rejection(browser=browser, task_json=l4_simplified, interaction="simplified", label="l4-simplified-sparse", root=args.out_dir / "route-sampling"),
                },
                "active_observation": {
                    mode: capture_active_mode(browser=browser, task_json=l4_full, mode=mode, root=args.out_dir / "active-observation", helpers=helpers)
                    for mode in ("live", "paused")
                },
            }
        finally:
            browser.close()
    write_json(args.out_dir / "summary.json", result)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
