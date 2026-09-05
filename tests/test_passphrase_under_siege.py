from __future__ import annotations

import copy
import importlib.util
import inspect
import json
import math
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "weird_captcha_gym"
ENV = BENCH / "environments/passphrase_under_siege_env"
GENERATOR_PATH = BENCH / "shared_scripts/incubator_generators/passphrase_under_siege.py"
GRADER_PATH = BENCH / "shared_runtime/server/incubator_graders/passphrase_under_siege.py"
SOLVER_PATH = BENCH / "tools/incubator_solvers/passphrase_under_siege.py"
VOWELS = frozenset("AEIOUaeiou")


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generator = _module("passphrase_under_siege_generator_test", GENERATOR_PATH)
grader = _module("passphrase_under_siege_grader_test", GRADER_PATH)
solver = _module("passphrase_under_siege_solver_test", SOLVER_PATH)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _task(level: int, interaction: str, real_time: str = "live") -> dict:
    controls = _read(ENV / "controls.json")
    task = _read(ENV / "tasks/passphrase_under_siege_seed_0001/task.json")
    task["_control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": copy.deepcopy(
            controls["difficulty"][str(level)]["parameters"]
        ),
    }
    return task


def _digit_sum(text: str) -> int:
    return sum(int(char) for char in text if char.isdigit())


def _password(public: dict) -> str:
    contract = public["contract"]
    clues = public["clues"]
    text = f"{clues['stamp']}!{clues.get('color') or ''}{clues.get('gauge_token') or ''}"
    remainder = int(contract["digit_sum_target"]) - _digit_sum(text)
    assert remainder >= 0
    while remainder >= 9:
        text += "9"
        remainder -= 9
    if remainder:
        text += str(remainder)
    exact = int(contract.get("exact_length") or 0)
    target = exact or max(int(contract["minimum_length"]), len(text))
    assert len(text) <= target
    return text + "z" * (target - len(text))


def _solution(public: dict, truth: dict, interaction: str) -> dict:
    password = _password(public)
    contract = truth["contract"]
    events: list[dict] = []
    now = 0

    def add(kind: str, **values) -> dict:
        nonlocal now
        now += 10
        event = {"sequence": len(events) + 1, "kind": kind, "t_ms": now, **values}
        events.append(event)
        return event

    for index, char in enumerate(password):
        add("type", index=index, text=char, input_source="physical_keyboard")

    select_source = "range_drag" if interaction == "full" else "endpoint_clicks"

    def formatting(start: int, end: int, style: str, value) -> None:
        add("select", start=start, end=end, input_source=select_source)
        add(
            "format",
            start=start,
            end=end,
            style=style,
            value=value,
            input_source="toolbar_button",
            selection_source=select_source,
        )

    stamp = truth["clues"]["stamp"]
    stamp_start = password.index(stamp)
    stamp_range = (stamp_start, stamp_start + len(stamp))
    if contract["bold_vowels"]:
        for index, char in enumerate(password):
            if char in VOWELS:
                formatting(index, index + 1, "bold", True)
    if contract["stamp_bold"]:
        formatting(*stamp_range, "bold", True)
    if contract["stamp_italic"]:
        formatting(*stamp_range, "italic", True)
    if contract["stamp_font"]:
        formatting(*stamp_range, "font", "serif")
    gauge = truth["clues"].get("gauge_token") or ""
    if int(contract["gauge_size_px"]):
        start = password.index(gauge) + 1
        formatting(start, start + len(gauge) - 1, "size", int(contract["gauge_size_px"]))
    color = truth["clues"].get("color") or ""
    if contract["color_font"]:
        start = password.index(color)
        formatting(start, start + len(color), "font", "serif")

    hazard_started = now
    feed_source = "token_drag" if interaction == "full" else "token_click_hatchling"
    hatchling = truth["hatchling"]
    quench_source = "ember_click" if interaction == "full" else "quench_button"
    scheduled: list[tuple[int, str, dict]] = []
    for index, token_id in enumerate(
        hatchling["grain_tokens"][: int(contract["feed_required"])]
    ):
        scheduled.append(
            (
                hazard_started + 10 + index * int(contract["feed_interval_ms"]),
                "feed",
                {
                    "token_id": token_id,
                    "x_norm": float(hatchling["x_norm"]),
                    "y_norm": float(hatchling["y_norm"]),
                    "input_source": feed_source,
                },
            )
        )
    for ember in truth["embers"]:
        wanted = hazard_started + int(ember["spawn_offset_ms"]) + 100
        details = {
            "ember_id": ember["id"],
            "input_source": quench_source,
        }
        if interaction == "full":
            local = wanted - hazard_started - int(ember["spawn_offset_ms"])
            phase = local / int(ember["ttl_ms"])
            details.update(
                x_norm=float(ember["start"][0])
                + (float(ember["end"][0]) - float(ember["start"][0])) * phase,
                y_norm=float(ember["start"][1])
                + (float(ember["end"][1]) - float(ember["start"][1])) * phase,
            )
        scheduled.append((wanted, "quench", details))

    for wanted, kind, details in sorted(scheduled, key=lambda item: item[0]):
        now = max(now, wanted - 10)
        add(kind, **details)

    add("begin_confirmation", input_source="seal_button")
    for char in password:
        add("confirm_type", text=char, input_source="physical_keyboard")
    add("submit", input_source="certify_button")
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction_mode": interaction,
        "events": events,
    }


def _world(public: dict) -> dict:
    world = copy.deepcopy(public)
    world.pop("control_condition", None)
    return world


def test_all_ten_control_conditions_share_world_and_grade() -> None:
    for level in range(1, 6):
        worlds = []
        for interaction in ("simplified", "full"):
            public, truth = generator.generate(
                _task(level, interaction), f"ten-controls-{level}"
            )
            decision = grader.grade(_solution(public, truth, interaction), truth, public)
            assert decision["passed"] is True, (level, interaction, decision)
            worlds.append(_world(public))
        assert worlds[0] == worlds[1]


def test_fifty_seeded_instances_are_deterministic_and_reachable() -> None:
    for level in range(1, 6):
        for seed_index in range(10):
            seed = f"reach-{level}-{seed_index}"
            full_public, full_truth = generator.generate(_task(level, "full"), seed)
            again_public, again_truth = generator.generate(_task(level, "full"), seed)
            assert (full_public, full_truth) == (again_public, again_truth)
            assert grader.grade(
                _solution(full_public, full_truth, "full"), full_truth, full_public
            )["passed"]
            simple_public, simple_truth = generator.generate(
                _task(level, "simplified"), seed
            )
            assert _world(simple_public) == _world(full_public)
            assert grader.grade(
                _solution(simple_public, simple_truth, "simplified"),
                simple_truth,
                simple_public,
            )["passed"]


def test_live_and_paused_generation_preserve_the_world() -> None:
    live, _ = generator.generate(_task(4, "full", "live"), "clock-pair")
    paused, _ = generator.generate(_task(4, "full", "paused"), "clock-pair")
    assert _world(live) == _world(paused)
    assert live["control_condition"]["real_time"] == "live"
    assert paused["control_condition"]["real_time"] == "paused"


def test_grader_rejects_stale_cross_mode_and_forged_geometry() -> None:
    public, truth = generator.generate(_task(4, "full"), "negative-contract")
    payload = _solution(public, truth, "full")
    payload["challenge_id"] = "stale"
    assert "stale" in grader.grade(payload, truth, public)["feedback"]

    payload = _solution(public, truth, "full")
    payload["interaction_mode"] = "simplified"
    assert "wrong interaction mode" in grader.grade(payload, truth, public)["feedback"]

    payload = _solution(public, truth, "full")
    ember = next(event for event in payload["events"] if event["kind"] == "quench")
    ember["x_norm"], ember["y_norm"] = 0.0, 0.0
    assert "missed" in grader.grade(payload, truth, public)["feedback"]

    payload = _solution(public, truth, "full")
    feed = next(event for event in payload["events"] if event["kind"] == "feed")
    hatchling = truth["hatchling"]
    feed["x_norm"] = float(hatchling["x_norm"]) + float(hatchling["radius_x_norm"]) * 1.01
    feed["y_norm"] = float(hatchling["y_norm"])
    assert "did not land" in grader.grade(payload, truth, public)["feedback"]

    payload = _solution(public, truth, "full")
    feed = next(event for event in payload["events"] if event["kind"] == "feed")
    feed["x_norm"] = float(hatchling["x_norm"]) + float(hatchling["radius_x_norm"]) * 0.99
    feed["y_norm"] = float(hatchling["y_norm"])
    assert grader.grade(payload, truth, public)["passed"] is True


def test_grader_replays_formatting_damage_and_memory() -> None:
    public, truth = generator.generate(_task(5, "full"), "replay-contract")

    payload = _solution(public, truth, "full")
    formatting = next(event for event in payload["events"] if event["kind"] == "format")
    formatting["value"] = False
    assert grader.grade(payload, truth, public)["passed"] is False

    payload = _solution(public, truth, "full")
    first_quench = next(index for index, event in enumerate(payload["events"]) if event["kind"] == "quench")
    payload["events"][first_quench]["t_ms"] = 999_999
    assert "task time is invalid" in grader.grade(payload, truth, public)["feedback"]

    payload = _solution(public, truth, "full")
    confirm = next(event for event in payload["events"] if event["kind"] == "confirm_type")
    confirm["text"] = "X" if confirm["text"] != "X" else "Y"
    assert "does not match" in grader.grade(payload, truth, public)["feedback"]


def test_public_contract_mutation_and_event_order_are_rejected() -> None:
    public, truth = generator.generate(_task(3, "simplified"), "binding-contract")
    payload = _solution(public, truth, "simplified")
    changed_public = copy.deepcopy(public)
    changed_public["contract"]["digit_sum_target"] += 1
    assert "difficulty contract" in grader.grade(payload, truth, changed_public)["feedback"]

    payload = _solution(public, truth, "simplified")
    payload["events"][1]["sequence"] = 900
    assert "sequence mismatch" in grader.grade(payload, truth, public)["feedback"]

    full_public, full_truth = generator.generate(_task(1, "full"), "keyboard-selection-source")
    payload = _solution(full_public, full_truth, "full")
    selection = next(event for event in payload["events"] if event["kind"] == "select")
    selection["input_source"] = "keyboard_select_all"
    assert "select-all" in grader.grade(payload, full_truth, full_public)["feedback"]


def test_difficulty_profiles_change_the_same_decision_problem() -> None:
    controls = _read(ENV / "controls.json")
    assert controls["baseline"] == {
        "difficulty": 4,
        "interaction": "full",
        "real_time": "live",
    }
    levels = controls["difficulty"]
    assert [levels[str(level)]["parameters"]["exact_length"] for level in range(1, 6)] == [0, 0, 28, 34, 42]
    assert [levels[str(level)]["parameters"]["ember_count"] for level in range(1, 6)] == [0, 0, 1, 2, 3]
    assert [levels[str(level)]["parameters"]["feed_required"] for level in range(1, 6)] == [0, 0, 0, 1, 2]
    assert [levels[str(level)]["parameters"]["feed_interval_ms"] for level in range(1, 6)] == [0, 0, 0, 0, 5000]
    assert [levels[str(level)]["parameters"]["color_font"] for level in range(1, 6)] == [False, False, False, False, True]


def test_metadata_security_boundary_and_registration() -> None:
    task = _read(ENV / "tasks/passphrase_under_siege_seed_0001/task.json")
    controls = _read(ENV / "controls.json")
    split = _read(BENCH / "splits/passphrase_under_siege_split.json")
    env = _read(ENV / "env.json")
    assert task["name"] == "Passphrase Under Siege"
    assert task["metadata"]["source_anchors"] == ["WEB-001", "SOC-246", "SOC-220"]
    assert task["metadata"]["legacy_agent_sample_population"] is False
    assert "visible controls" in task["natural_language"]
    assert "Developer Tools" in task["natural_language"]
    assert "DOM or page-state inspection" in task["natural_language"]
    assert len(split["variations_tasks"]) == 20
    assert env["runner"] == "weird_captcha"
    assert env["runner_options"] == controls["real_time"]
    manifest = _read(BENCH / "benchmark_manifest.json")
    assert "passphrase_under_siege_env" in manifest["environments"]
    assert manifest["environment_count"] == len(manifest["environments"])
    assert _read(BENCH / "real_time.json")["environments"]["passphrase_under_siege"] == controls["real_time"]

    public, truth = generator.generate(_task(4, "full"), "public-boundary")
    assert "seed" not in public
    assert truth["seed"] == "public-boundary"
    assert public["asset_manifest"].endswith("passphrase_under_siege_v0.json")

    for hook in (
        ENV / "scripts/install_puzzle_runtime.sh",
        ENV / "scripts/setup_puzzle_runtime.sh",
        ENV / "tasks/passphrase_under_siege_seed_0001/setup_task.sh",
        ENV / "tasks/passphrase_under_siege_seed_0001/export_result.sh",
    ):
        assert os.access(hook, os.X_OK), hook


def test_generated_geometry_is_finite_bounded_and_human_clickable() -> None:
    for seed_index in range(100):
        public, _ = generator.generate(_task(5, "full"), f"geometry-{seed_index}")
        for ember in public["embers"]:
            assert int(ember["ttl_ms"]) >= 3_800
            for point in (ember["start"], ember["end"]):
                assert len(point) == 2
                assert all(math.isfinite(value) and 0.05 <= value <= 0.95 for value in point)
        hatchling = public["hatchling"]
        assert 0.1 <= hatchling["x_norm"] <= 0.9
        assert 0.1 <= hatchling["y_norm"] <= 0.9
        assert hatchling["radius_x_norm"] == 0.0375
        assert hatchling["radius_y_norm"] == 0.065
        assert hatchling["x_norm"] + hatchling["radius_x_norm"] < 1
        assert hatchling["y_norm"] + hatchling["radius_y_norm"] < 1


def test_gauge_has_geometry_only_answer_and_viewport_repairs_are_present() -> None:
    frontend = (BENCH / "shared_runtime/app/mechanics/passphrase_under_siege.js").read_text(encoding="utf-8")
    styles = (BENCH / "shared_runtime/app/mechanics/passphrase_under_siege.css").read_text(encoding="utf-8")
    assert "-180 + (value / 12) * 180" in frontend
    assert "Array.from({length: 13}" in frontend
    assert "siege-gauge-readout" not in frontend
    assert 'class="siege-chip-code"' in frontend
    assert "radius_x_norm" in frontend and "radius_y_norm" in frontend
    assert 'body[data-mechanic="passphrase-under-siege-v1"] #app.app-shell' in styles
    assert "height: 100%;" in styles
    assert "overflow: hidden;" in styles
    solve_source = inspect.getsource(solver.solve)
    visible_source = inspect.getsource(solver._read_visible_clues)
    assert '["clues"]' not in solve_source
    assert ".siege-chip-code" in visible_source
    assert "_read_gauge_geometry" in visible_source


def test_l5_second_grain_is_temporally_separated_and_replay_enforced() -> None:
    public, truth = generator.generate(_task(5, "full"), "separated-feed-window")
    payload = _solution(public, truth, "full")
    feeds = [event for event in payload["events"] if event["kind"] == "feed"]
    assert len(feeds) == 2
    assert feeds[1]["t_ms"] - feeds[0]["t_ms"] >= 5000
    assert grader.grade(payload, truth, public)["passed"] is True

    forged = copy.deepcopy(payload)
    feed_indices = [
        index for index, event in enumerate(forged["events"])
        if event["kind"] == "feed"
    ]
    second = forged["events"].pop(feed_indices[1])
    first_index = feed_indices[0]
    second["t_ms"] = forged["events"][first_index]["t_ms"] + 10
    forged["events"].insert(first_index + 1, second)
    for sequence, event in enumerate(forged["events"], start=1):
        event["sequence"] = sequence
    decision = grader.grade(forged, truth, public)
    assert decision["passed"] is False
    assert "next grain is not ready" in decision["feedback"]
