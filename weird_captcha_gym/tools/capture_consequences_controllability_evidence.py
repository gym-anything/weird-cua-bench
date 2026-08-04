#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageChops, ImageDraw, ImageStat
from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "consequences_boss_env"
MECHANIC = "consequences_boss"

from weird_captcha_gym.tools import smoke_controlled_interaction_ui as smoke
from weird_captcha_gym.tools.incubator_solvers.reviewed_overhaul_common import drag
from weird_captcha_gym.shared_runtime.server.weird_captcha_server import PuzzleServer


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def normalized_world(value: dict) -> dict:
    result = copy.deepcopy(value)
    for key in ("task_id", "control_condition"):
        result.pop(key, None)
    return result


def json_digest(value: dict) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def image_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pixel_difference(left_path: Path, right_path: Path) -> float:
    left = Image.open(left_path).convert("RGB")
    right = Image.open(right_path).convert("RGB")
    return sum(
        ImageStat.Stat(ImageChops.difference(left, right)).mean
    ) / 3


class FixedStateServer(PuzzleServer):
    def do_GET(self) -> None:
        if urlparse(self.path).path == "/state":
            self._send_json_file(self.state_dir / "public_state.json")
            return
        super().do_GET()

    def log_message(self, _format: str, *_args: object) -> None:
        return


def start_fixed_server(
    state_dir: Path,
    public_state: dict,
    ground_truth: dict,
    *,
    name: str,
    app_dir: Path | None = None,
) -> tuple[ThreadingHTTPServer, threading.Thread]:
    write_json(state_dir / "public_state.json", public_state)
    write_json(state_dir / "ground_truth.json", ground_truth)
    handler = type(
        name,
        (FixedStateServer,),
        {
            "app_dir": app_dir or BENCHMARK / "shared_runtime" / "app",
            "state_dir": state_dir,
        },
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def baseline_rendering_evidence(
    setup,
    tasks_root: Path,
    out_dir: Path,
) -> None:
    baseline_dir = out_dir / "baseline_rendering"
    if baseline_dir.exists():
        shutil.rmtree(baseline_dir)
    baseline_dir.mkdir(parents=True)
    original_task = read_json(
        ENVIRONMENT
        / "tasks"
        / "consequences_boss_seed_0001"
        / "task.json"
    )
    controlled_task = read_json(
        smoke.controlled_task(tasks_root, 1, "full")
    )
    states = {
        "raw_current": setup.generate_task_state(
            original_task,
            "consequences-baseline-rendering",
        ),
        "controlled_l1_full": setup.generate_task_state(
            controlled_task,
            "consequences-baseline-rendering",
        ),
    }
    normalized_states_equal = all(
        normalized_world(states["raw_current"][index])
        == normalized_world(states["controlled_l1_full"][index])
        for index in (0, 1)
    )
    env_relative = (
        "weird_captcha_gym/environments/"
        "consequences_boss_env/env.json"
    )
    prior_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
    ).strip()
    prior_env = json.loads(
        subprocess.check_output(
            ["git", "show", f"HEAD:{env_relative}"],
            cwd=ROOT,
            text=True,
        )
    )
    current_env = read_json(ENVIRONMENT / "env.json")

    captures = {}
    errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for label in ("raw_current", "controlled_l1_full"):
            public, truth = states[label]
            with tempfile.TemporaryDirectory(
                prefix=f"consequences-baseline-{label}-"
            ) as state_name:
                state_dir = Path(state_name)
                server, thread = start_fixed_server(
                    state_dir,
                    public,
                    truth,
                    name=f"ConsequencesBaseline{label.title()}",
                )
                page = browser.new_page(
                    viewport={"width": 1280, "height": 720},
                    device_scale_factor=1,
                )
                page.on(
                    "pageerror",
                    lambda error: errors.append(str(error)),
                )
                try:
                    page.goto(
                        f"http://127.0.0.1:{server.server_port}/",
                        wait_until="networkidle",
                    )
                    expect(page.locator(".covenant-captcha")).to_be_visible()
                    screenshot = baseline_dir / f"{label}-initial.png"
                    page.screenshot(path=str(screenshot))
                    geometry = page.evaluate(
                        """() => {
                          const rect = selector => {
                            const box = document.querySelector(selector)
                              .getBoundingClientRect();
                            return [box.x, box.y, box.width, box.height];
                          };
                          return {
                            viewport: [innerWidth, innerHeight],
                            document: [
                              document.documentElement.scrollWidth,
                              document.documentElement.scrollHeight,
                            ],
                            captcha: rect(".covenant-captcha"),
                            world: rect(".covenant-world"),
                            control: rect(".covenant-control"),
                            relic: rect(".covenant-relic"),
                            seal: rect(".covenant-seal"),
                          };
                        }"""
                    )
                    captures[label] = {
                        "screenshot": screenshot.name,
                        "sha256": image_digest(screenshot),
                        "geometry": geometry,
                    }
                finally:
                    page.close()
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=3)
        browser.close()

    raw_frame = baseline_dir / captures["raw_current"]["screenshot"]
    controlled_frame = (
        baseline_dir / captures["controlled_l1_full"]["screenshot"]
    )
    difference = pixel_difference(raw_frame, controlled_frame)
    env_equal = current_env == prior_env
    geometry_equal = (
        captures["raw_current"]["geometry"]
        == captures["controlled_l1_full"]["geometry"]
    )
    frame_equal = raw_frame.read_bytes() == controlled_frame.read_bytes()
    if not env_equal:
        raise AssertionError("L1 environment configuration differs from HEAD")
    if (
        not normalized_states_equal
        or not geometry_equal
        or not frame_equal
        or difference != 0
    ):
        raise AssertionError(
            "raw task and controlled L1/full rendering differ: "
            f"state={normalized_states_equal}, geometry={geometry_equal}, "
            f"bytes={frame_equal}, diff={difference}"
        )
    if errors:
        raise AssertionError(f"baseline rendering browser errors: {errors}")
    write_json(
        baseline_dir / "manifest.json",
        {
            "seed": "consequences-baseline-rendering",
            "difficulty": 1,
            "interaction": "full",
            "environment_spec_equal_to_head": env_equal,
            "raw_and_controlled_world_and_truth_equal_after_identity_removal": (
                normalized_states_equal
            ),
            "observation_resolution": current_env["observation"][0][
                "resolution"
            ],
            "prior_commit": prior_commit,
            "environment_comparator": (
                f"git commit {prior_commit} environment specification"
            ),
            "rendering_comparator": (
                "current raw task versus current controlled L1/full task, "
                "both through the current shared runtime"
            ),
            "captures": captures,
            "geometry_equal": geometry_equal,
            "png_bytes_equal": frame_equal,
            "mean_pixel_difference": difference,
            "page_errors": [],
        },
    )


def generation_evidence(
    setup,
    tasks_root: Path,
    out_dir: Path,
    *,
    deterministic_materialization: bool,
) -> None:
    original_task = read_json(
        ENVIRONMENT
        / "tasks"
        / "consequences_boss_seed_0001"
        / "task.json"
    )
    baseline_task = read_json(smoke.controlled_task(tasks_root, 1, "full"))
    baseline_rows = []
    for seed in (
        "consequences-baseline-evidence-a",
        "consequences-baseline-evidence-b",
        "consequences-baseline-evidence-c",
    ):
        original = setup.generate_task_state(original_task, seed)
        baseline = setup.generate_task_state(baseline_task, seed)
        normalized_original_public = normalized_world(original[0])
        normalized_baseline_public = normalized_world(baseline[0])
        normalized_original_truth = normalized_world(original[1])
        normalized_baseline_truth = normalized_world(baseline[1])
        baseline_rows.append(
            {
                "seed": seed,
                "challenge_id_equal": (
                    original[0]["challenge_id"] == baseline[0]["challenge_id"]
                ),
                "generator_name_equal": (
                    original[0]["generator"]["name"]
                    == baseline[0]["generator"]["name"]
                ),
                "public_world_equal": (
                    normalized_original_public == normalized_baseline_public
                ),
                "hidden_contract_equal": (
                    normalized_original_truth == normalized_baseline_truth
                ),
                "original_effective_minimum_distinct_states": 1,
                "controlled_minimum_distinct_states": baseline[1][
                    "control_condition"
                ]["difficulty_parameters"]["minimum_distinct_states"],
                "success_contract_equal": (
                    baseline[1]["control_condition"][
                        "difficulty_parameters"
                    ]["minimum_distinct_states"]
                    == 1
                ),
                "public_sha256": json_digest(normalized_baseline_public),
                "truth_sha256": json_digest(normalized_baseline_truth),
            }
        )
    write_json(
        out_dir / "baseline_preservation.json",
        {
            "baseline_difficulty": 1,
            "baseline_interaction": "full",
            "identity_fields_removed": ["task_id", "control_condition"],
            "rows": baseline_rows,
        },
    )

    records = []
    for level in range(1, 6):
        seed_checks = []
        representative_pair = None
        for seed in (
            "consequences-profile-evidence-a",
            "consequences-profile-evidence-b",
            "consequences-profile-evidence-c",
        ):
            pair = {}
            for interaction in ("simplified", "full"):
                task_path = smoke.controlled_task(tasks_root, level, interaction)
                task = read_json(task_path)
                first = setup.generate_task_state(task, seed)
                second = setup.generate_task_state(task, seed)
                if first != second:
                    raise AssertionError(
                        f"d{level} {interaction} generation is not deterministic"
                    )
                pair[interaction] = first
            same_public = (
                normalized_world(pair["simplified"][0])
                == normalized_world(pair["full"][0])
            )
            same_truth = (
                normalized_world(pair["simplified"][1])
                == normalized_world(pair["full"][1])
            )
            seed_checks.append(
                {
                    "seed": seed,
                    "deterministic": True,
                    "same_public_world_across_interaction": same_public,
                    "same_hidden_contract_across_interaction": same_truth,
                    "challenge_id_equal_across_interaction": (
                        pair["simplified"][0]["challenge_id"]
                        == pair["full"][0]["challenge_id"]
                    ),
                    "world_sha256": json_digest(
                        normalized_world(pair["full"][0])
                    ),
                    "truth_sha256": json_digest(
                        normalized_world(pair["full"][1])
                    ),
                }
            )
            representative_pair = pair
        assert representative_pair is not None
        parameters = representative_pair["full"][1]["control_condition"][
            "difficulty_parameters"
        ]
        records.append(
            {
                "difficulty": level,
                "scene_count": len(representative_pair["full"][0]["scenes"]),
                "scene_ids": representative_pair["full"][1]["scene_ids"],
                "boss_order": representative_pair["full"][1]["boss_order"],
                "minimum_distinct_states": parameters["minimum_distinct_states"],
                "seal_positions": parameters["seal_positions"],
                "socket_options": parameters["socket_options"],
                "same_world_across_interaction": all(
                    row["same_public_world_across_interaction"]
                    and row["same_hidden_contract_across_interaction"]
                    and row["challenge_id_equal_across_interaction"]
                    for row in seed_checks
                ),
                "seed_checks": seed_checks,
            }
        )
    write_json(
        out_dir / "generation_matrix.json",
        {
            "materialized_task_count": len(list(tasks_root.glob("*/task.json"))),
            "deterministic_materialization": deterministic_materialization,
            "baseline_level": 2,
            "baseline_seed_count": len(baseline_rows),
            "baseline_preserves_original_challenge_identity": all(
                row["challenge_id_equal"] for row in baseline_rows
            ),
            "baseline_preserves_original_generator_identity": all(
                row["generator_name_equal"] for row in baseline_rows
            ),
            "baseline_preserves_original_public_world": all(
                row["public_world_equal"] for row in baseline_rows
            ),
            "baseline_preserves_original_hidden_contract": all(
                row["hidden_contract_equal"] for row in baseline_rows
            ),
            "baseline_raw_and_controlled_success_contract_equal": all(
                row["success_contract_equal"] for row in baseline_rows
            ),
            "profiles": records,
        },
    )


def same_world_interaction_evidence(setup, tasks_root: Path, out_dir: Path) -> None:
    pair_dir = out_dir / "same_world_interaction_pair"
    pair_dir.mkdir(parents=True, exist_ok=True)
    states = {}
    for interaction in ("simplified", "full"):
        task = read_json(smoke.controlled_task(tasks_root, 1, interaction))
        states[interaction] = setup.generate_task_state(
            task,
            "consequences-visible-interaction-pair",
        )

    screenshots = {}
    interaction_geometry = {}
    page_errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for interaction in ("simplified", "full"):
            with tempfile.TemporaryDirectory(
                prefix=f"consequences-same-world-{interaction}-"
            ) as state_name:
                state_dir = Path(state_name)
                server, thread = start_fixed_server(
                    state_dir,
                    states[interaction][0],
                    states[interaction][1],
                    name=f"ConsequencesFixedState{interaction.title()}",
                )
                page = browser.new_page(
                    viewport={"width": 1280, "height": 720},
                    device_scale_factor=1,
                )
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                try:
                    page.goto(
                        f"http://127.0.0.1:{server.server_port}/",
                        wait_until="networkidle",
                    )
                    expect(page.locator(".covenant-captcha")).to_have_attribute(
                        "data-interaction",
                        interaction,
                    )
                    initial = pair_dir / f"{interaction}-initial.png"
                    page.screenshot(path=str(initial))
                    geometry = page.evaluate(
                        """() => {
                          const rect = selector => {
                            const node = document.querySelector(selector);
                            if (!node) return null;
                            const box = node.getBoundingClientRect();
                            return {
                              x: box.x,
                              y: box.y,
                              width: box.width,
                              height: box.height,
                            };
                          };
                          return {
                            viewport: [innerWidth, innerHeight],
                            document: [
                              document.documentElement.scrollWidth,
                              document.documentElement.scrollHeight,
                            ],
                            relic: rect(".covenant-relic"),
                            left_socket: rect('.covenant-socket[data-socket="left"]'),
                            right_socket: rect('.covenant-socket[data-socket="right"]'),
                            seal: rect(".covenant-seal"),
                            left_proxy: rect('.covenant-place-button[data-socket="left"]'),
                            zero_proxy: rect('.covenant-seal-button[data-seal-value="0"]'),
                          };
                        }"""
                    )
                    if geometry["document"] != [1290, 740]:
                        raise AssertionError(
                            f"{interaction} layout differs from legacy geometry: "
                            f"{geometry}"
                        )
                    if interaction == "simplified":
                        page.locator(
                            '.covenant-place-button[data-socket="left"]'
                        ).click()
                    else:
                        drag(
                            page,
                            page.locator(".covenant-relic"),
                            page.locator(
                                '.covenant-socket[data-socket="left"]'
                            ),
                            steps=1,
                        )
                    after = pair_dir / f"{interaction}-same-placement.png"
                    page.screenshot(path=str(after))
                    selected_socket = page.locator(
                        '.covenant-socket[data-selected="true"]'
                    ).get_attribute("data-socket")
                    bind_enabled = page.locator(
                        ".covenant-bind"
                    ).is_enabled()
                    screenshots[interaction] = {
                        "initial": initial.name,
                        "same_placement": after.name,
                    }
                    interaction_geometry[interaction] = {
                        **geometry,
                        "selected_socket_after_action": selected_socket,
                        "bind_enabled_after_action": bind_enabled,
                        "pointer_move_steps": (
                            1 if interaction == "full" else None
                        ),
                    }
                finally:
                    page.close()
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=3)
        browser.close()

    if page_errors:
        raise AssertionError(f"same-world interaction browser errors: {page_errors}")
    write_json(
        pair_dir / "manifest.json",
        {
            "seed": "consequences-visible-interaction-pair",
            "difficulty": 1,
            "normalized_public_worlds_equal": (
                normalized_world(states["simplified"][0])
                == normalized_world(states["full"][0])
            ),
            "normalized_hidden_contracts_equal": (
                normalized_world(states["simplified"][1])
                == normalized_world(states["full"][1])
            ),
            "scene_ids": states["full"][1]["scene_ids"],
            "boss_order": states["full"][1]["boss_order"],
            "challenge_id": {
                interaction: states[interaction][0]["challenge_id"]
                for interaction in ("simplified", "full")
            },
            "screenshots": screenshots,
            "interaction_geometry": interaction_geometry,
            "page_errors": [],
        },
    )


def difficulty_progression_evidence(
    setup,
    tasks_root: Path,
    out_dir: Path,
) -> None:
    progression_dir = out_dir / "difficulty_progression"
    progression_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for level in range(1, 6):
            task = read_json(smoke.controlled_task(tasks_root, level, "full"))
            public, truth = setup.generate_task_state(
                task,
                "consequences-visible-difficulty-progression",
            )
            with tempfile.TemporaryDirectory(
                prefix=f"consequences-difficulty-d{level}-"
            ) as state_name:
                state_dir = Path(state_name)
                server, thread = start_fixed_server(
                    state_dir,
                    public,
                    truth,
                    name=f"ConsequencesDifficultyD{level}",
                )
                page = browser.new_page(
                    viewport={"width": 1280, "height": 720},
                    device_scale_factor=1,
                )
                page.on("pageerror", lambda error: errors.append(str(error)))
                try:
                    page.goto(
                        f"http://127.0.0.1:{server.server_port}/",
                        wait_until="networkidle",
                    )
                    expect(
                        page.locator('.covenant-captcha[data-interaction="full"]')
                    ).to_be_visible()
                    expect(page.locator(".covenant-phase")).to_contain_text(
                        f"/ {len(public['scenes']):02d}"
                    )
                    layout = page.evaluate(
                        """() => ({
                          viewport: [innerWidth, innerHeight],
                          document: [
                            document.documentElement.scrollWidth,
                            document.documentElement.scrollHeight,
                          ],
                        })"""
                    )
                    if layout["document"] != [1290, 740]:
                        raise AssertionError(
                            f"d{level} layout differs from legacy geometry: "
                            f"{layout}"
                        )
                    screenshot = progression_dir / f"d{level}-full-initial.png"
                    page.screenshot(path=str(screenshot))
                    parameters = truth["control_condition"][
                        "difficulty_parameters"
                    ]
                    rows.append(
                        {
                            "difficulty": level,
                            "screenshot": screenshot.name,
                            "sha256": image_digest(screenshot),
                            "challenge_id": public["challenge_id"],
                            "scene_count": parameters["scene_count"],
                            "seal_positions": parameters["seal_positions"],
                            "minimum_distinct_states": parameters[
                                "minimum_distinct_states"
                            ],
                            "shuffle_judgment": parameters[
                                "shuffle_judgment"
                            ],
                            "layout": layout,
                        }
                    )
                finally:
                    page.close()
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=3)
        browser.close()

    if errors:
        raise AssertionError(f"difficulty progression browser errors: {errors}")
    thumbs = []
    for row in rows:
        frame = Image.open(progression_dir / row["screenshot"]).convert("RGB")
        frame.thumbnail((600, 338))
        thumbs.append((row["difficulty"], frame.copy()))
    contact = Image.new("RGB", (1280, 1160), "#090910")
    draw = ImageDraw.Draw(contact)
    for index, (level, frame) in enumerate(thumbs):
        column = index % 2
        line = index // 2
        x = 20 + column * 630
        y = 42 + line * 372
        draw.text((x, y - 24), f"L{level} · full · fixed seed", fill="#d9ff58")
        contact.paste(frame, (x, y))
    contact_path = progression_dir / "difficulty-progression-contact-sheet.png"
    contact.save(contact_path)
    write_json(
        progression_dir / "manifest.json",
        {
            "seed": "consequences-visible-difficulty-progression",
            "interaction": "full",
            "viewport": [1280, 720],
            "contact_sheet": contact_path.name,
            "rows": rows,
            "page_errors": [],
        },
    )


def set_full_seal(page, value: int, positions: int) -> None:
    if positions == 1:
        return
    seal = page.locator(".covenant-seal")
    box = seal.bounding_box()
    if box is None:
        raise AssertionError("seal has no visible bounding box")
    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2
    angle = -0.5 * math.pi + value * (2 * math.pi / positions)
    point = (cx + 32 * math.cos(angle), cy + 32 * math.sin(angle))
    page.mouse.move(*point)
    page.mouse.down()
    page.mouse.move(*point, steps=2)
    page.mouse.up()


def full_answer(page, socket: str, seal: int, positions: int) -> None:
    drag(
        page,
        page.locator(".covenant-relic"),
        page.locator(f'.covenant-socket[data-socket="{socket}"]'),
        steps=12,
        hold_ms=90,
    )
    set_full_seal(page, seal, positions)
    page.locator(".covenant-bind").click()


def realtime_evidence(setup, task_json: Path, out_dir: Path) -> None:
    realtime_dir = out_dir / "realtime"
    realtime_dir.mkdir(parents=True, exist_ok=True)
    task = read_json(task_json)
    fixed_states = {
        mode: setup.generate_task_state(
            task,
            "consequences-realtime-shared-world",
        )
        for mode in ("paused", "live")
    }
    mode_results = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for mode in ("paused", "live"):
            public, truth = fixed_states[mode]
            with tempfile.TemporaryDirectory(
                prefix=f"consequences-realtime-{mode}-"
            ) as state_name:
                state_dir = Path(state_name)
                server, thread = start_fixed_server(
                    state_dir,
                    public,
                    truth,
                    name=f"ConsequencesRealtime{mode.title()}",
                )
                page = browser.new_page(
                    viewport={"width": 1280, "height": 720},
                    device_scale_factor=1,
                )
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                try:
                    page.goto(
                        f"http://127.0.0.1:{server.server_port}/"
                        f"?time_mode={mode}&start_paused="
                        f"{'1' if mode == 'paused' else '0'}&time_control=1",
                        wait_until="domcontentloaded",
                    )
                    expect(
                        page.locator('.covenant-captcha[data-interaction="full"]')
                    ).to_be_visible()
                    expected_state = "paused" if mode == "paused" else "running"
                    page.wait_for_function(
                        "state => WeirdCaptchaTime.status().state === state",
                        arg=expected_state,
                    )

                    initial_frame = (
                        realtime_dir / f"{mode}-observation-frame-000.png"
                    )
                    page.screenshot(path=str(initial_frame))
                    initial_before = page.evaluate("WeirdCaptchaTime.status()")
                    page.wait_for_timeout(700)
                    initial_after_frame = (
                        realtime_dir / f"{mode}-initial-after-model-delay.png"
                    )
                    page.screenshot(path=str(initial_after_frame))
                    initial_after = page.evaluate("WeirdCaptchaTime.status()")

                    action_evidence = None
                    if mode == "paused":
                        action_before = page.evaluate(
                            "WeirdCaptchaTime.status()"
                        )
                        page.evaluate("WeirdCaptchaTime.resume()")
                        drag(
                            page,
                            page.locator(".covenant-relic"),
                            page.locator(
                                '.covenant-socket[data-socket="left"]'
                            ),
                            steps=12,
                            hold_ms=120,
                        )
                        page.evaluate("WeirdCaptchaTime.pause()")
                        action_after = page.evaluate(
                            "WeirdCaptchaTime.status()"
                        )
                        action_frame = (
                            realtime_dir / "paused-mode-action-ran.png"
                        )
                        page.screenshot(path=str(action_frame))
                        action_evidence = {
                            "before": action_before,
                            "after": action_after,
                            "task_time_delta_ms": (
                                float(action_after["task_time_ms"])
                                - float(action_before["task_time_ms"])
                            ),
                            "clock_state_after": action_after["state"],
                            "evidence_frame": str(
                                action_frame.relative_to(out_dir)
                            ),
                        }
                        page.evaluate("WeirdCaptchaTime.resume()")
                        set_full_seal(page, 0, 4)
                        page.locator(".covenant-bind").click()
                        page.evaluate("WeirdCaptchaTime.pause()")
                    else:
                        full_answer(page, "left", 0, 4)

                    parameters = truth["control_condition"][
                        "difficulty_parameters"
                    ]
                    if parameters["minimum_distinct_states"] != 1:
                        raise AssertionError(
                            "real-time L1 diagnostic expected one distinct state"
                        )
                    for index in range(1, len(public["scenes"])):
                        if mode == "paused":
                            page.evaluate("WeirdCaptchaTime.resume()")
                        full_answer(
                            page,
                            "right" if index == 1 else "left",
                            0,
                            4,
                        )
                        if mode == "paused":
                            page.evaluate("WeirdCaptchaTime.pause()")

                    expect(page.locator(".covenant-storm")).to_be_visible()
                    storm_frame = (
                        realtime_dir
                        / f"{mode}-storm-observation-frame-000.png"
                    )
                    page.screenshot(path=str(storm_frame))
                    storm_before = page.evaluate("WeirdCaptchaTime.status()")
                    page.wait_for_timeout(1_700)
                    storm_after_frame = (
                        realtime_dir / f"{mode}-storm-after-model-delay.png"
                    )
                    page.screenshot(path=str(storm_after_frame))
                    storm_after = page.evaluate("WeirdCaptchaTime.status()")
                    storm_still_visible = page.locator(
                        ".covenant-storm"
                    ).count() == 1

                    mode_results[mode] = {
                        "challenge_id": public["challenge_id"],
                        "world_sha256": json_digest(normalized_world(public)),
                        "initial_observation": {
                            "screen": str(initial_frame.relative_to(out_dir)),
                            "frames": [
                                {
                                    "path": str(
                                        initial_frame.relative_to(out_dir)
                                    ),
                                    "offset_ms": 0,
                                    "sha256": image_digest(initial_frame),
                                }
                            ],
                            "latest_frame_is_screen": True,
                            "before_model_delay": initial_before,
                            "after_700ms_model_delay": initial_after,
                            "task_time_delta_ms": (
                                float(initial_after["task_time_ms"])
                                - float(initial_before["task_time_ms"])
                            ),
                            "after_model_delay_frame": str(
                                initial_after_frame.relative_to(out_dir)
                            ),
                            "visual_difference": pixel_difference(
                                initial_frame,
                                initial_after_frame,
                            ),
                        },
                        "storm_observation": {
                            "screen": str(storm_frame.relative_to(out_dir)),
                            "frames": [
                                {
                                    "path": str(
                                        storm_frame.relative_to(out_dir)
                                    ),
                                    "offset_ms": 0,
                                    "sha256": image_digest(storm_frame),
                                }
                            ],
                            "latest_frame_is_screen": True,
                            "before_model_delay": storm_before,
                            "after_1700ms_model_delay": storm_after,
                            "task_time_delta_ms": (
                                float(storm_after["task_time_ms"])
                                - float(storm_before["task_time_ms"])
                            ),
                            "after_model_delay_frame": str(
                                storm_after_frame.relative_to(out_dir)
                            ),
                            "visual_difference": pixel_difference(
                                storm_frame,
                                storm_after_frame,
                            ),
                            "storm_still_visible_after_delay": (
                                storm_still_visible
                            ),
                        },
                        "paused_mode_action": action_evidence,
                        "page_errors": errors,
                    }
                finally:
                    page.close()
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=3)
        browser.close()

    paused = mode_results["paused"]
    live = mode_results["live"]
    paused_initial_delta = paused["initial_observation"][
        "task_time_delta_ms"
    ]
    live_initial_delta = live["initial_observation"]["task_time_delta_ms"]
    paused_storm_delta = paused["storm_observation"]["task_time_delta_ms"]
    live_storm_delta = live["storm_observation"]["task_time_delta_ms"]
    action_delta = paused["paused_mode_action"]["task_time_delta_ms"]
    checks = {
        "same_generated_world": (
            paused["challenge_id"] == live["challenge_id"]
            and paused["world_sha256"] == live["world_sha256"]
        ),
        "paused_initial_model_delay_froze_task_time": (
            abs(paused_initial_delta) <= 1
        ),
        "live_initial_model_delay_advanced_task_time": (
            live_initial_delta >= 500
        ),
        "paused_storm_model_delay_froze_task_time": (
            abs(paused_storm_delta) <= 1
        ),
        "paused_storm_remained_visibly_frozen": (
            paused["storm_observation"]["visual_difference"] == 0
            and paused["storm_observation"][
                "storm_still_visible_after_delay"
            ]
        ),
        "live_storm_advanced_during_model_delay": (
            live_storm_delta >= 1_400
            and live["storm_observation"]["visual_difference"] > 0
            and not live["storm_observation"][
                "storm_still_visible_after_delay"
            ]
        ),
        "action_advanced_task_time_while_paused_mode_was_resumed": (
            action_delta > 0
            and paused["paused_mode_action"]["clock_state_after"] == "paused"
        ),
        "screen_is_final_frame": all(
            result[observation]["latest_frame_is_screen"]
            and result[observation]["screen"]
            == result[observation]["frames"][-1]["path"]
            for result in (paused, live)
            for observation in (
                "initial_observation",
                "storm_observation",
            )
        ),
        "no_browser_errors": not (
            paused["page_errors"] or live["page_errors"]
        ),
    }
    if not all(checks.values()):
        raise AssertionError(f"real-time evidence checks failed: {checks}")
    contact = Image.new("RGB", (1280, 780), "#090910")
    draw = ImageDraw.Draw(contact)
    contact_rows = (
        (
            "PAUSED · browser-clock diagnostic checkpoint",
            realtime_dir / "paused-storm-observation-frame-000.png",
        ),
        (
            "PAUSED · after simulated inference delay · unchanged",
            realtime_dir / "paused-storm-after-model-delay.png",
        ),
        (
            "LIVE · browser-clock diagnostic checkpoint",
            realtime_dir / "live-storm-observation-frame-000.png",
        ),
        (
            "LIVE · after simulated inference delay · reckoning",
            realtime_dir / "live-storm-after-model-delay.png",
        ),
    )
    for index, (label, source) in enumerate(contact_rows):
        frame = Image.open(source).convert("RGB")
        frame.thumbnail((600, 338))
        column = index % 2
        line = index // 2
        x = 20 + column * 630
        y = 42 + line * 382
        draw.text((x, y - 24), label, fill="#d9ff58")
        contact.paste(frame, (x, y))
    realtime_contact = realtime_dir / "realtime-observation-contact-sheet.png"
    contact.save(realtime_contact)
    write_json(
        realtime_dir / "observation_manifest.json",
        {
            "evidence_class": (
                "Playwright browser-clock diagnostic; not an evaluator "
                "observation"
            ),
            "settings": {
                "play_time_seconds": 180,
                "observation_window_ms": 0,
                "frames_per_observation": 1,
            },
            "same_seed": "consequences-realtime-shared-world",
            "contact_sheet": str(realtime_contact.relative_to(out_dir)),
            "paused": paused,
            "live": live,
            "checks": checks,
        },
    )


def export_and_verify_evidence(task_json: Path, out_dir: Path) -> None:
    artifacts = out_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    solver = load_module(
        "consequences_evidence_solver",
        BENCHMARK / "tools" / "incubator_solvers" / "consequences_boss.py",
    )
    grader = load_module(
        "consequences_evidence_grader",
        BENCHMARK
        / "shared_runtime"
        / "server"
        / "incubator_graders"
        / "consequences_boss.py",
    )
    verifier = load_module(
        "consequences_evidence_verifier",
        ENVIRONMENT
        / "tasks"
        / "consequences_boss_seed_0001"
        / "verifier.py",
    )
    with tempfile.TemporaryDirectory(prefix="consequences-export-evidence-") as state_name:
        state_dir = Path(state_name)
        process, port = smoke.start_server(
            task_json,
            MECHANIC,
            "full",
            state_dir,
        )
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1280, "height": 720})
                page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
                solver.solve(page, state_dir, artifacts, MECHANIC)
                expect(page.locator(".readout")).to_have_attribute(
                    "data-status",
                    "passed",
                    timeout=8_000,
                )
                page.screenshot(path=str(artifacts / "baseline-full-pass.png"))
                browser.close()

            export = subprocess.run(
                ["bash", str(BENCHMARK / "shared_scripts" / "export_result.sh")],
                cwd=ROOT,
                env={**os.environ, "WEIRD_CAPTCHA_STATE_DIR": str(state_dir)},
                check=True,
                capture_output=True,
                text=True,
            )
            exported_path = artifacts / "baseline-full-export.json"
            shutil.copyfile("/tmp/task_result.json", exported_path)
            exported = read_json(exported_path)
            direct_grade = grader.grade(
                exported["result"],
                exported["ground_truth"],
                exported["public_state"],
            )

            def copy_from_env(source: str, destination: str) -> None:
                if source != "/tmp/task_result.json":
                    raise ValueError(f"unexpected verifier source {source}")
                shutil.copyfile(exported_path, destination)

            verifier_result = verifier.verify_task(
                env_info={"copy_from_env": copy_from_env}
            )
            stale = copy.deepcopy(exported["result"])
            stale["challenge_id"] = "stale-evidence"
            stale_result = grader.grade(
                stale,
                exported["ground_truth"],
                exported["public_state"],
            )
            wrong_mode = copy.deepcopy(exported["result"])
            first_place = next(
                event
                for event in wrong_mode["events"]
                if event.get("kind") == "place"
            )
            first_place["input_source"] = "socket_button"
            wrong_mode_result = grader.grade(
                wrong_mode,
                exported["ground_truth"],
                exported["public_state"],
            )
            early_judgment = copy.deepcopy(exported["result"])
            storm_event = next(
                event
                for event in early_judgment["events"]
                if event.get("kind") == "storm"
            )
            judgment_event = next(
                event
                for event in early_judgment["events"]
                if event.get("kind") == "judgment"
            )
            required_storm_ms = int(
                exported["ground_truth"]["storm_ms"]
            )
            observed_storm_ms = (
                int(judgment_event["elapsed_ms"])
                - int(storm_event["elapsed_ms"])
            )
            shift = observed_storm_ms - required_storm_ms + 1
            judgment_index = early_judgment["events"].index(judgment_event)
            for event in early_judgment["events"][judgment_index:]:
                event["elapsed_ms"] = int(event["elapsed_ms"]) - shift
            storm_event["duration_ms"] = required_storm_ms * 100
            early_judgment_result = grader.grade(
                early_judgment,
                exported["ground_truth"],
                exported["public_state"],
            )
            if early_judgment_result.get("passed") is not False:
                raise AssertionError(
                    "grader accepted an early judgment with forged duration"
                )
            write_json(
                artifacts / "storm-timing-replay.json",
                {
                    "required_storm_ms": required_storm_ms,
                    "accepted_transcript": {
                        "storm_elapsed_ms": storm_event["elapsed_ms"],
                        "judgment_elapsed_ms": (
                            int(storm_event["elapsed_ms"])
                            + observed_storm_ms
                        ),
                        "elapsed_delta_ms": observed_storm_ms,
                        "direct_grade": direct_grade,
                    },
                    "forged_early_transcript": {
                        "declared_duration_ms": storm_event["duration_ms"],
                        "storm_elapsed_ms": storm_event["elapsed_ms"],
                        "judgment_elapsed_ms": early_judgment["events"][
                            judgment_index
                        ]["elapsed_ms"],
                        "elapsed_delta_ms": required_storm_ms - 1,
                        "grade": early_judgment_result,
                    },
                },
            )
            write_json(
                artifacts / "grading_export_summary.json",
                {
                    "export_command": (
                        "WEIRD_CAPTCHA_STATE_DIR=<state-dir> "
                        "bash weird_captcha_gym/shared_scripts/export_result.sh"
                    ),
                    "export_stdout": export.stdout.strip(),
                    "server_grade": exported["result"].get("server_grade"),
                    "direct_grade": direct_grade,
                    "task_verifier": verifier_result,
                    "stale_challenge_rejection": stale_result,
                    "wrong_interaction_rejection": wrong_mode_result,
                    "early_judgment_with_forged_duration_rejection": (
                        early_judgment_result
                    ),
                    "storm_timing_replay": "storm-timing-replay.json",
                },
            )
        finally:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()


def browser_time_matrix_evidence(out_dir: Path) -> str | None:
    paths = {
        "live": out_dir / "browser_matrix" / "summary.json",
        "paused": out_dir / "browser_matrix_paused" / "summary.json",
    }
    if not all(path.is_file() for path in paths.values()):
        return None
    summaries = {mode: read_json(path) for mode, path in paths.items()}
    rows = []
    for difficulty in range(1, 6):
        for interaction in ("simplified", "full"):
            records = {
                mode: summaries[mode]["difficulties"][str(difficulty)][
                    interaction
                ]
                for mode in ("live", "paused")
            }
            clock_states = {
                mode: {
                    checkpoint: {
                        "mode": status["mode"],
                        "state": status["state"],
                        "task_time_ms": status["task_time_ms"],
                    }
                    for checkpoint, status in records[mode]["clock"].items()
                }
                for mode in ("live", "paused")
            }
            clock_modes_valid = all(
                status["mode"] == mode
                and status["state"] == (
                    "running" if mode == "live" else "paused"
                )
                for mode, checkpoints in clock_states.items()
                for status in checkpoints.values()
            )
            row = {
                "difficulty": difficulty,
                "interaction": interaction,
                "live_passed": records["live"]["passed"],
                "paused_passed": records["paused"]["passed"],
                "live_server_passed": records["live"]["server_grade"][
                    "passed"
                ],
                "paused_server_passed": records["paused"]["server_grade"][
                    "passed"
                ],
                "live_verifier_passed": records["live"]["verifier"]["passed"],
                "paused_verifier_passed": records["paused"]["verifier"][
                    "passed"
                ],
                "verifier_scores": {
                    mode: records[mode]["verifier"]["score"]
                    for mode in ("live", "paused")
                },
                "initial_world_fingerprint": records["live"][
                    "initial_browser_run_world_fingerprint"
                ],
                "same_initial_world_across_time": (
                    records["live"][
                        "initial_browser_run_world_fingerprint"
                    ]
                    == records["paused"][
                        "initial_browser_run_world_fingerprint"
                    ]
                ),
                "clock_states": clock_states,
                "clock_modes_valid": clock_modes_valid,
                "paused_initial_task_time_is_zero": (
                    abs(
                        float(
                            clock_states["paused"]["initial"][
                                "task_time_ms"
                            ]
                        )
                    )
                    <= 1
                ),
            }
            rows.append(row)
    all_checks_pass = all(
        row["live_passed"]
        and row["paused_passed"]
        and row["live_server_passed"]
        and row["paused_server_passed"]
        and row["live_verifier_passed"]
        and row["paused_verifier_passed"]
        and row["verifier_scores"] == {"live": 100, "paused": 100}
        and row["same_initial_world_across_time"]
        and row["clock_modes_valid"]
        and row["paused_initial_task_time_is_zero"]
        for row in rows
    )
    if not all_checks_pass:
        raise AssertionError(f"twenty-condition browser matrix failed: {rows}")
    artifact = out_dir / "browser_time_matrix_summary.json"
    write_json(
        artifact,
        {
            "environment": "consequences_boss_env",
            "condition_count": len(rows) * 2,
            "difficulty_interaction_pairs": len(rows),
            "time_modes": ["live", "paused"],
            "all_checks_pass": True,
            "source_summaries": {
                mode: str(path.relative_to(out_dir))
                for mode, path in paths.items()
            },
            "rows": rows,
        },
    )
    return artifact.name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture Consequences Boss controllability evidence."
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ENVIRONMENT / "evidence_docs",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    materializer = load_module(
        "consequences_evidence_materializer",
        BENCHMARK / "tools" / "materialize_controlled_tasks.py",
    )
    setup = load_module(
        "consequences_evidence_setup",
        BENCHMARK / "shared_scripts" / "setup_task.py",
    )
    with tempfile.TemporaryDirectory(prefix="consequences-tasks-evidence-") as task_name:
        materializer.materialize_environment(ENVIRONMENT, Path(task_name))
        tasks_root = (
            Path(task_name)
            / "consequences_boss_env"
            / "tasks"
        )
        with tempfile.TemporaryDirectory(
            prefix="consequences-tasks-evidence-repeat-"
        ) as repeat_name:
            materializer.materialize_environment(
                ENVIRONMENT,
                Path(repeat_name),
            )
            repeat_root = (
                Path(repeat_name)
                / "consequences_boss_env"
                / "tasks"
            )
            first_files = {
                path.relative_to(tasks_root): path.read_bytes()
                for path in tasks_root.rglob("*")
                if path.is_file()
            }
            repeat_files = {
                path.relative_to(repeat_root): path.read_bytes()
                for path in repeat_root.rglob("*")
                if path.is_file()
            }
            deterministic_materialization = first_files == repeat_files
        if not deterministic_materialization:
            raise AssertionError(
                "two controlled materializations produced different files"
            )
        generation_evidence(
            setup,
            tasks_root,
            out_dir,
            deterministic_materialization=deterministic_materialization,
        )
        baseline_rendering_evidence(setup, tasks_root, out_dir)
        same_world_interaction_evidence(setup, tasks_root, out_dir)
        difficulty_progression_evidence(setup, tasks_root, out_dir)
        baseline_full = smoke.controlled_task(tasks_root, 1, "full")
        realtime_evidence(setup, baseline_full, out_dir)
        export_and_verify_evidence(baseline_full, out_dir)
    browser_time_matrix = browser_time_matrix_evidence(out_dir)
    summary = {
        "ok": True,
        "baseline_preservation": "baseline_preservation.json",
        "baseline_rendering": "baseline_rendering/manifest.json",
        "generation": "generation_matrix.json",
        "difficulty_progression": "difficulty_progression/manifest.json",
        "same_world_interaction": "same_world_interaction_pair/manifest.json",
        "browser_clock_diagnostic": "realtime/observation_manifest.json",
        "export_and_grading": "artifacts/grading_export_summary.json",
    }
    if browser_time_matrix:
        summary["browser_time_matrix"] = browser_time_matrix
    write_json(out_dir / "capture_summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
