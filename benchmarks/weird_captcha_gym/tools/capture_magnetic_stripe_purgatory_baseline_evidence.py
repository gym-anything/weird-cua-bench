#!/usr/bin/env python3
"""Capture fixed-seed baseline and interaction-pair browser evidence."""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from benchmarks.weird_captcha_gym.shared_scripts.setup_task import generate_task_state

from smoke_controlled_interaction_ui import (
    BENCH_ROOT,
    controlled_task,
    observation_viewport,
    read_json,
    start_server,
)


ENVIRONMENT = BENCH_ROOT / "environments" / "magnetic_stripe_purgatory_env"
BASE_TASK = ENVIRONMENT / "tasks" / "magnetic_stripe_purgatory_seed_0001" / "task.json"
MATERIALIZER_PATH = BENCH_ROOT / "tools" / "materialize_controlled_tasks.py"
MECHANIC = "magnetic_stripe_purgatory"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def without_control_identity(value: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(value)
    for key in ("task_id", "challenge_id", "control_condition"):
        normalized.pop(key, None)
    return normalized


def capture_initial(
    browser: Any,
    *,
    task_json: Path,
    interaction: str,
    state_dir: Path,
    screenshot: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    process, port = start_server(task_json, MECHANIC, interaction, state_dir)
    page = browser.new_page(viewport=observation_viewport(ENVIRONMENT), device_scale_factor=1)
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    # The companion's /state endpoint intentionally generates a fresh task when
    # current_task.json is present.  The interaction smoke keeps that file out of
    # the endpoint's reach while a fixed task is being observed; use the same
    # protocol here so all three captures retain the materialized fixed seed.
    current_task_path = state_dir / "current_task.json"
    current_task_text = current_task_path.read_text(encoding="utf-8")
    current_task_path.unlink()
    try:
        page.goto(f"http://127.0.0.1:{port}/?time_mode=live&start_paused=0", wait_until="networkidle")
        page.wait_for_selector(".stripe-purgatory")
        displayed_interaction = str(page.locator(".stripe-purgatory").get_attribute("data-interaction") or "full")
        if displayed_interaction != interaction:
            raise AssertionError(f"expected {interaction} surface, got {displayed_interaction}")
        page.screenshot(path=str(screenshot), full_page=True)
        if errors:
            raise AssertionError(f"browser errors: {errors}")
        return read_json(state_dir / "public_state.json"), read_json(state_dir / "ground_truth.json")
    finally:
        current_task_path.write_text(current_task_text, encoding="utf-8")
        page.close()
        process.terminate()
        try:
            process.wait(timeout=3)
        except Exception:
            process.kill()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ENVIRONMENT / "evidence_docs" / "baseline_verified_v5",
    )
    parser.add_argument(
        "--seed-sweep",
        type=int,
        default=1000,
        help="Number of generated original/L4 comparisons to record in addition to the fixed visual capture.",
    )
    args = parser.parse_args()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.seed_sweep < 1:
        raise SystemExit("--seed-sweep must be positive")
    materializer = load_module("magnetic_stripe_baseline_materializer", MATERIALIZER_PATH)
    viewport = observation_viewport(ENVIRONMENT)
    if viewport != {"width": 1280, "height": 720}:
        raise AssertionError(f"the preserved baseline requires the historical 1280×720 observation surface, got {viewport}")

    with tempfile.TemporaryDirectory(prefix="magnetic-stripe-baseline-") as temporary:
        temporary_root = Path(temporary)
        materializer.materialize_environment(ENVIRONMENT, temporary_root / "materialized")
        tasks_root = temporary_root / "materialized" / ENVIRONMENT.name / "tasks"
        l4_full = controlled_task(tasks_root, 4, "full")
        l4_simplified = controlled_task(tasks_root, 4, "simplified")
        evidence: dict[str, Any] = {
            "environment": ENVIRONMENT.name,
            "fixed_seed": "interaction-pair-magnetic_stripe_purgatory",
            "original_task": str(BASE_TASK.relative_to(ROOT)),
            "controlled_task": str(l4_full.relative_to(temporary_root)),
            "observation_surface": {
                "declared_rgb_screen": [viewport["width"], viewport["height"]],
                "capture_viewport": [viewport["width"], viewport["height"]],
            },
            "captures": {},
        }
        for seed_index in range(args.seed_sweep):
            seed = f"magnetic-stripe-baseline-sweep-{seed_index}"
            original_sweep_public, original_sweep_truth = generate_task_state(read_json(BASE_TASK), seed)
            full_sweep_public, full_sweep_truth = generate_task_state(read_json(l4_full), seed)
            if without_control_identity(original_sweep_public) != without_control_identity(full_sweep_public):
                raise AssertionError(f"controlled L4 changed uncontrolled public world for sweep seed {seed_index}")
            if without_control_identity(original_sweep_truth) != without_control_identity(full_sweep_truth):
                raise AssertionError(f"controlled L4 changed uncontrolled hidden world for sweep seed {seed_index}")
        evidence["seed_sweep"] = {
            "seed_count": args.seed_sweep,
            "uncontrolled_equals_l4_full_public": True,
            "uncontrolled_equals_l4_full_ground_truth": True,
        }
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            original_public, original_truth = capture_initial(
                browser,
                task_json=BASE_TASK,
                interaction="full",
                state_dir=temporary_root / "original",
                screenshot=out_dir / "original-uncontrolled-full.png",
            )
            full_public, full_truth = capture_initial(
                browser,
                task_json=l4_full,
                interaction="full",
                state_dir=temporary_root / "l4-full",
                screenshot=out_dir / "l4-full-controlled.png",
            )
            simplified_public, simplified_truth = capture_initial(
                browser,
                task_json=l4_simplified,
                interaction="simplified",
                state_dir=temporary_root / "l4-simplified",
                screenshot=out_dir / "l4-simplified-controlled.png",
            )
            browser.close()

    if without_control_identity(original_public) != without_control_identity(full_public):
        raise AssertionError("controlled L4 does not reproduce the uncontrolled public world")
    if without_control_identity(original_truth) != without_control_identity(full_truth):
        raise AssertionError("controlled L4 does not reproduce the uncontrolled hidden world")
    if without_control_identity(full_public) != without_control_identity(simplified_public):
        raise AssertionError("interaction pair changes the L4 public world")
    if without_control_identity(full_truth) != without_control_identity(simplified_truth):
        raise AssertionError("interaction pair changes the L4 hidden world")

    evidence["captures"] = {
        "uncontrolled_full": {
            "screenshot": "original-uncontrolled-full.png",
            "challenge_id": original_public["challenge_id"],
        },
        "controlled_l4_full": {
            "screenshot": "l4-full-controlled.png",
            "challenge_id": full_public["challenge_id"],
        },
        "controlled_l4_simplified": {
            "screenshot": "l4-simplified-controlled.png",
            "challenge_id": simplified_public["challenge_id"],
        },
    }
    evidence["checks"] = {
        "uncontrolled_equals_l4_full_public": True,
        "uncontrolled_equals_l4_full_ground_truth": True,
        "l4_full_equals_l4_simplified_public": True,
        "l4_full_equals_l4_simplified_ground_truth": True,
    }
    (out_dir / "baseline-comparison.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
