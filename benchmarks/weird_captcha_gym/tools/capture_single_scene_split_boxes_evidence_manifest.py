#!/usr/bin/env python3
"""Validate and inventory the canonical Split Boxes controllability evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[3]
BENCHMARK = ROOT / "benchmarks" / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "single_scene_split_boxes_env"
EVIDENCE = ENVIRONMENT / "evidence_docs"
MECHANIC = "single_scene_split_boxes"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def validate_generation() -> dict[str, Any]:
    path = EVIDENCE / "generation_contract.json"
    evidence = read_json(path)
    rows = evidence.get("baseline", {}).get("rows", [])
    historical_fixture = evidence.get("historical_fixture", {})
    require(len(rows) == 5, "baseline preservation requires the five locked historical seeds")
    require(historical_fixture.get("historical_revision"), "generation evidence has no explicit pre-control revision")
    require(
        historical_fixture.get("identity_fields_removed_for_comparison") == ["task_id", "challenge_id", "control_condition"],
        "historical comparison removes substantive state fields",
    )
    for row in rows:
        require(
            all(
                row.get(field) is True
                for field in (
                    "challenge_id_equal",
                    "uncontrolled_full_public_contract_equal",
                    "uncontrolled_full_truth_contract_equal",
                    "uncontrolled_public_matches_historical",
                    "uncontrolled_truth_matches_historical",
                    "controlled_public_matches_historical",
                    "controlled_truth_matches_historical",
                    "public_world_equal",
                    "truth_contract_equal",
                    "historical_dimensions_present",
                    "uncontrolled_dimensions_present",
                    "controlled_dimensions_present",
                    "natural_language_equal",
                )
            ),
            f"baseline changed at {row.get('seed')}",
        )
    require(evidence.get("materialized_task_count") == 10, "not all controlled tasks were materialized")
    profiles = evidence.get("profiles", [])
    require([item.get("difficulty") for item in profiles] == [1, 2, 3, 4, 5], "difficulty profiles are incomplete")
    for profile in profiles:
        require(profile.get("interaction_world_equal") is True, f"interaction pair changed world at L{profile.get('difficulty')}")
        require(all(profile.get("parameters_match", {}).values()), f"inactive profile parameter at L{profile.get('difficulty')}")
        require(profile.get("speed_scale_probe_changes_motion") is True, f"inactive speed scale at L{profile.get('difficulty')}")
    return {
        "path": relative(path),
        "baseline_seeds": [row["seed"] for row in rows],
        "historical_revision": historical_fixture["historical_revision"],
        "profile_count": len(profiles),
    }


def validate_matrix(directory: str, expected_mode: str) -> dict[str, Any]:
    path = EVIDENCE / directory / "summary.json"
    summary = read_json(path)
    require(summary.get("time_mode") == expected_mode, f"{directory} has the wrong time mode")
    require(summary.get("model_delay_ms") == 500, f"{directory} does not retain the artificial model delay")
    conditions: list[dict[str, Any]] = []
    for level in range(1, 6):
        row = summary.get("difficulties", {}).get(str(level), {})
        pair_fingerprints: set[str] = set()
        for interaction, expected_source in (("simplified", "slot_button"), ("full", "tile_drag")):
            record = row.get(interaction, {})
            require(record.get("passed") is True, f"{directory} L{level} {interaction} failed")
            require(record.get("server_grade", {}).get("passed") is True, f"{directory} L{level} {interaction} server grade failed")
            require(record.get("verifier", {}).get("passed") is True, f"{directory} L{level} {interaction} verifier failed")
            sources = set(record.get("input_sources") or [])
            require(expected_source in sources, f"{directory} L{level} {interaction} did not use {expected_source}")
            require({"rotation_button", "phase_track"}.issubset(sources), f"{directory} L{level} {interaction} omitted shared transform input sources")
            pair_fingerprints.add(str(record.get("initial_browser_run_world_fingerprint") or ""))
            evidence_dir = EVIDENCE / directory / f"d{level}-{interaction}"
            required = (
                "initial.png",
                "after-model-delay.png",
                "single_scene_split_boxes-active-temporal.png",
                "single_scene_split_boxes-coherent.png",
                "single_scene_split_boxes-phase-geometry.png",
                "single_scene_split_boxes-fail-refresh.png",
                "pass.png",
                "failed-attempts.jsonl",
                "failure-server-grade.json",
                "retry_public_state.json",
                "exported-result.json",
                "server-grade.json",
                "verifier.json",
            )
            require(all((evidence_dir / name).is_file() for name in required), f"{directory} L{level} {interaction} is missing a visible or result artifact")
            if level >= 2:
                require((evidence_dir / "single_scene_split_boxes-active-spatial.png").is_file(), f"{directory} L{level} {interaction} is missing an active spatial state")
            phase_geometry = record.get("phase_geometry", {})
            require(
                phase_geometry.get("expected_tick_count") == phase_geometry.get("rendered_tick_count"),
                f"{directory} L{level} {interaction} rendered the wrong phase tick count",
            )
            require(
                phase_geometry.get("expected_master_index") == phase_geometry.get("rendered_master_index"),
                f"{directory} L{level} {interaction} rendered the master at the wrong phase index",
            )
            require(
                all(
                    phase_geometry.get(field) is True
                    for field in ("no_wrap", "master_matches_zero_input", "zero_handle_matches_master")
                ),
                f"{directory} L{level} {interaction} phase scale diverges from its input geometry",
            )
            failure = read_json(evidence_dir / "failure-server-grade.json")
            require(failure.get("passed") is False, f"{directory} L{level} {interaction} did not reject its deliberate failure")
            initial_clock = record.get("clock", {}).get("initial", {})
            delayed_clock = record.get("clock", {}).get("after_model_delay", {})
            delta = float(delayed_clock.get("task_time_ms", 0)) - float(initial_clock.get("task_time_ms", 0))
            if expected_mode == "live":
                require(delta >= 350, f"{directory} L{level} {interaction} did not run through model delay")
            else:
                require(abs(delta) <= 2, f"{directory} L{level} {interaction} advanced while paused")
            conditions.append({"difficulty": level, "interaction": interaction, "model_delay_task_delta_ms": delta})
        require(len(pair_fingerprints) == 1 and next(iter(pair_fingerprints)), f"{directory} L{level} paired modes did not share a world")
    return {"path": relative(path), "time_mode": expected_mode, "conditions": conditions}


def validate_realtime() -> dict[str, Any]:
    path = EVIDENCE / "realtime_observations" / "summary.json"
    evidence = read_json(path)
    modes = evidence.get("modes", {})
    for mode in ("live", "paused"):
        record = modes.get(mode, {})
        frames = record.get("frames", [])
        require(len(frames) == 6, f"{mode} does not retain six observation frames")
        require([frame.get("target_elapsed_ms") for frame in frames] == [0.0, 128.0, 256.0, 384.0, 512.0, 640.0], f"{mode} frame targets are not chronological")
        require(all((path.parent / str(frame.get("image"))).is_file() for frame in frames), f"{mode} frame screenshots are missing")
        require(float(record.get("action_task_time_delta_ms", 0)) > 0, f"{mode} action did not run while task time advanced")
    live = modes["live"]
    paused = modes["paused"]
    require(float(live.get("model_delay_task_time_delta_ms", 0)) >= 620, "live observation did not advance during model delay")
    require(live.get("model_delay_images_equal") is False, "live model delay did not change the image")
    require(abs(float(paused.get("model_delay_task_time_delta_ms", 1))) <= 2, "paused observation advanced during model delay")
    require(paused.get("model_delay_images_equal") is True, "paused model delay changed the image")
    return {"path": relative(path), "frame_count": 6, "window_ms": 640}


def validate_rejections() -> dict[str, Any]:
    path = EVIDENCE / "adversarial_transcript_rejection.json"
    evidence = read_json(path)
    accepted = evidence.get("accepted_browser_exports", {})
    require(set(accepted) == {"simplified", "full"}, "accepted replay evidence must include both input surfaces")
    for values in accepted.values():
        require(all(value.get("passed") is True for value in values.values()), "accepted browser export did not replay")
    wrong = evidence.get("wrong_interaction_sources", {})
    require(set(wrong) == {"simplified_swap_as_full_drag", "full_drag_as_simplified_slot_button"}, "bidirectional wrong-surface evidence is incomplete")
    for values in wrong.values():
        require(all(value.get("passed") is False for value in values.values()), "wrong surface was accepted")
    for name in ("stale_challenge", "public_control_condition_mismatch"):
        values = evidence.get(name, {})
        require(all(value.get("passed") is False for value in values.values()), f"{name} was accepted")
    return {"path": relative(path), "wrong_surface_cases": sorted(wrong)}


def validate_static_target() -> dict[str, Any]:
    path = EVIDENCE / "static_target" / "target-static-summary.json"
    evidence = read_json(path)
    require(evidence.get("all_ten_pyodide_replays") == "PASS", "target static Pyodide replay did not pass")
    require(evidence.get("visible_failure_and_recovery") == "d4-full", "target static failure/recovery is missing")
    conditions = evidence.get("conditions", {})
    require(len(conditions) == 10, "target static export did not exercise ten variants")
    for level in range(1, 6):
        full = conditions.get(f"d{level}-full", {})
        simplified = conditions.get(f"d{level}-simplified", {})
        require(full.get("initial_world_fingerprint") == simplified.get("initial_world_fingerprint"), f"static L{level} interaction worlds differ")
        for record in (full, simplified):
            require(record.get("pyodide_grade", {}).get("passed") is True, "static Pyodide grade failed")
            require(record.get("independent_exported_verifier", {}).get("passed") is True, "static exported verifier failed")
    failure_dir = EVIDENCE / "static_target" / "d4-full"
    require(all((failure_dir / name).is_file() for name in ("failure.png", "fresh-retry.png", "pyodide-pass.png", "browser-result.json")), "static visible failure/recovery artifacts are incomplete")
    return {"path": relative(path), "condition_count": len(conditions)}


def validate_native_static_observer() -> tuple[dict[str, Any], list[str]]:
    path = EVIDENCE / "static_observations_headless" / "summary.json"
    evidence = read_json(path)
    capture = evidence.get("capture_method", {})
    require(capture.get("browser") == "isolated headless Playwright Chromium", "static observer browser is not isolated headless Playwright")
    require(capture.get("fresh_temporary_profile") is True, "static observer profile is not fresh and temporary")
    require(capture.get("synthetic_stream_override") is False, "static observer used a synthetic media stream")
    records = evidence.get("public_static_observations", {})
    require(set(records) == {"live", "paused"}, "static observer modes are incomplete")
    status = evidence.get("status")
    require(status in {"available", "not_available"}, "static observer status is invalid")
    if status == "not_available":
        for mode, record in records.items():
            require(record.get("available") is False and str(record.get("reason") or ""), f"static {mode} missing unavailability reason")
            require((path.parent / str(record.get("screenshot"))).is_file(), f"static {mode} missing unavailability screenshot")
        return ({"path": relative(path), "status": status, "reason": {mode: record["reason"] for mode, record in records.items()}}, ["Native target-tab getDisplayMedia observation is unavailable in isolated headless Chromium; see static_observations_headless/summary.json and its live/paused screenshots."])
    for mode, record in records.items():
        require(record.get("available") is True and record.get("frame_count") == 6, f"static {mode} did not produce six observations")
        require((path.parent / str(record.get("viewer_screenshot"))).is_file(), f"static {mode} viewer screenshot is missing")
    return ({"path": relative(path), "status": status, "frame_count": 6}, [])


def validate_pytest() -> dict[str, Any]:
    path = EVIDENCE / "pytest-results.xml"
    root = ElementTree.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    require(suites, "pytest JUnit artifact has no suite")
    failures = sum(int(suite.attrib.get("failures", "0")) for suite in suites)
    errors = sum(int(suite.attrib.get("errors", "0")) for suite in suites)
    tests = sum(int(suite.attrib.get("tests", "0")) for suite in suites)
    skipped = sum(int(suite.attrib.get("skipped", "0")) for suite in suites)
    require(failures == 0 and errors == 0 and tests > 0, "pytest JUnit artifact is not clean")
    return {"path": relative(path), "tests": tests, "skipped": skipped}


def source_hashes() -> dict[str, str]:
    paths = (
        ENVIRONMENT / "controls.json",
        ENVIRONMENT / "tasks" / "single_scene_split_boxes_seed_0001" / "task.json",
        ENVIRONMENT / "historical_l4_baseline_fixture.json",
        BENCHMARK / "shared_scripts" / "incubator_generators" / f"{MECHANIC}.py",
        BENCHMARK / "shared_runtime" / "app" / "mechanics" / f"{MECHANIC}.js",
        BENCHMARK / "shared_runtime" / "app" / "mechanics" / f"{MECHANIC}.css",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{MECHANIC}.py",
        BENCHMARK / "tools" / "incubator_solvers" / f"{MECHANIC}.py",
        BENCHMARK / "tools" / "smoke_controlled_interaction_ui.py",
    )
    return {relative(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=EVIDENCE / "evidence_manifest.json")
    args = parser.parse_args()
    static_observer, unmet = validate_native_static_observer()
    checks = {
        "generation": validate_generation(),
        "live_matrix": validate_matrix("browser_pairs_live_delay_final", "live"),
        "paused_matrix": validate_matrix("browser_pairs_paused_final", "paused"),
        "real_time": validate_realtime(),
        "interaction_rejection": validate_rejections(),
        "static_target": validate_static_target(),
        "native_static_observer": static_observer,
        "pytest": validate_pytest(),
    }
    static_smoke = read_json(EVIDENCE / "static_browser_play_final" / "summary.json")
    require(static_smoke.get("ok") is True and not static_smoke.get("failures"), "shared static-browser smoke did not pass")
    command_outputs = EVIDENCE / "command_outputs"
    required_outputs = ("targeted-pytest.txt", "full-pytest.txt", "strict-audit.txt")
    require(all((command_outputs / name).is_file() for name in required_outputs), "exact command output artifacts are incomplete")
    output = {
        "environment": ENVIRONMENT.name,
        "public_environment_name": "Live Shattered-Scene Synchronizer",
        "automated_evidence_validated": True,
        "native_static_observation_status": static_observer["status"],
        "unmet_evidence": unmet,
        "checks": checks,
        "static_browser_smoke": relative(EVIDENCE / "static_browser_play_final" / "summary.json"),
        "command_outputs": [relative(command_outputs / name) for name in required_outputs],
        "source_hashes": source_hashes(),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
