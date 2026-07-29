#!/usr/bin/env python3
"""Validate and inventory the canonical Occlusion Shell Swindle evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[3]
BENCHMARK = ROOT / "benchmarks" / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "occlusion_shell_swindle_env"
EVIDENCE = ENVIRONMENT / "evidence_docs"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate_matrix(name: str, expected_mode: str) -> dict[str, Any]:
    summary_path = EVIDENCE / name / "summary.json"
    summary = read_json(summary_path)
    require(summary.get("time_mode") == expected_mode, f"{name} has the wrong time mode")
    conditions: list[dict[str, Any]] = []
    for level in range(1, 6):
        row = summary.get("difficulties", {}).get(str(level), {})
        for interaction in ("simplified", "full"):
            record = row.get(interaction, {})
            require(record.get("passed") is True, f"{name} d{level} {interaction} did not pass")
            require(record.get("server_grade", {}).get("passed") is True, f"{name} d{level} {interaction} server grade failed")
            require(record.get("verifier", {}).get("passed") is True, f"{name} d{level} {interaction} verifier failed")
            directory = EVIDENCE / name / f"d{level}-{interaction}"
            for filename in ("initial.png", "pass.png", "exported-result.json", "server-grade.json", "verifier.json"):
                require((directory / filename).is_file(), f"{name} d{level} {interaction} is missing {filename}")
            conditions.append({
                "difficulty": level,
                "interaction": interaction,
                "server_score": record["server_grade"].get("score"),
                "verifier_score": record["verifier"].get("score"),
                "input_sources": record.get("input_sources"),
            })
    return {"summary": str(summary_path.relative_to(ROOT)), "conditions": conditions}


def validate_generation() -> dict[str, Any]:
    path = EVIDENCE / "generation_contract.json"
    evidence = read_json(path)
    rows = evidence.get("baseline", {}).get("rows", [])
    require(len(rows) >= 3, "baseline preservation needs at least three seeds")
    for row in rows:
        require(
            all(row.get(field) is True for field in ("challenge_id_equal", "public_world_equal", "truth_contract_equal")),
            f"baseline preservation failed for {row.get('seed')}",
        )
    require(evidence.get("materialized_task_count") == 10, "not all controlled tasks were materialized")
    profiles = evidence.get("profiles", [])
    require([item.get("difficulty") for item in profiles] == [1, 2, 3, 4, 5], "difficulty profiles are incomplete")
    require(all(item.get("interaction_world_equal") is True and item.get("parameters_match") is True for item in profiles), "paired interaction worlds differ")
    return {"path": str(path.relative_to(ROOT)), "baseline_seeds": [row.get("seed") for row in rows]}


def validate_realtime() -> dict[str, Any]:
    path = EVIDENCE / "realtime_observations" / "summary.json"
    evidence = read_json(path)
    settings = evidence.get("settings", {})
    require(settings == {"play_time_seconds": 120, "observation_window_ms": 800, "frames_per_observation": 6}, "real-time settings differ from controls")
    modes = evidence.get("modes", {})
    for mode in ("live", "paused"):
        record = modes.get(mode, {})
        frames = record.get("frames", [])
        require(len(frames) == 6, f"{mode} observation does not have six frames")
        require([frame.get("offset_ms") for frame in frames] == [0, 160, 320, 480, 640, 800], f"{mode} frame offsets are not chronological")
        require(all((path.parent / str(frame.get("path"))).is_file() for frame in frames), f"{mode} observation screenshots are missing")
        require(float(record.get("action_after", {}).get("task_time_ms", 0)) > float(record.get("action_before", {}).get("task_time_ms", 0)), f"{mode} action did not run while task time advanced")
    require(float(modes["live"].get("delay_task_delta_ms", 0)) >= 700, "live model delay did not advance task time")
    require(abs(float(modes["paused"].get("delay_task_delta_ms", 1))) <= 2, "paused model delay advanced task time")
    require(float(modes["live"].get("delay_image_difference", 0)) > 0.02, "live model delay did not change the visible world")
    require(float(modes["paused"].get("delay_image_difference", 1)) <= 0.02, "paused model delay changed the visible world")
    return {"path": str(path.relative_to(ROOT)), "settings": settings}


def validate_rejections() -> dict[str, Any]:
    path = EVIDENCE / "adversarial_transcript_rejection.json"
    evidence = read_json(path)
    accepted = evidence.get("accepted_browser_exports", {})
    require(set(accepted) == {"simplified", "full"}, "both accepted interaction exports are required")
    for mode, verdicts in accepted.items():
        require(all(verdict.get("passed") is True for verdict in verdicts.values()), f"accepted {mode} transcript did not replay")
    wrong = evidence.get("wrong_interaction_sources", {})
    expected = {
        "simplified_sample_as_full",
        "simplified_selection_as_full",
        "full_sample_as_simplified",
        "full_selection_as_simplified",
    }
    require(set(wrong) == expected, "bidirectional wrong-surface evidence is incomplete")
    for label, verdicts in wrong.items():
        require(all(verdict.get("passed") is False for verdict in verdicts.values()), f"{label} was accepted")
    wrong_relay = evidence.get("wrong_visible_relay_choice", {})
    require(set(wrong_relay) == {"server_grader", "exported_verifier"}, "decoy relay-choice evidence is incomplete")
    require(all(verdict.get("passed") is False for verdict in wrong_relay.values()), "a decoy relay choice was accepted")
    stale = evidence.get("stale_challenge", {})
    require(all(verdict.get("passed") is False for verdict in stale.values()), "stale challenge was accepted")
    return {"path": str(path.relative_to(ROOT)), "wrong_surface_cases": sorted(wrong)}


def validate_static_observer() -> dict[str, Any]:
    path = EVIDENCE / "static_observations_headless" / "summary.json"
    evidence = read_json(path)
    capture = evidence.get("capture_method", {})
    require(capture.get("browser") == "isolated headless Playwright Chromium", "static capture did not use isolated headless Playwright")
    require(capture.get("fresh_temporary_profile") is True, "static capture did not use a fresh temporary profile")
    require(capture.get("synthetic_stream_override") is False, "static capture used a synthetic stream override")
    records = evidence.get("public_static_observations", {})
    require(set(records) == {"live", "paused"}, "static observation modes are incomplete")
    status = evidence.get("status")
    require(status in {"available", "not_available"}, "static observation status is malformed")
    if status == "not_available":
        for mode, record in records.items():
            require(record.get("available") is False, f"static {mode} was not recorded as unavailable")
            require(str(record.get("reason") or ""), f"static {mode} unavailability has no reason")
            require((path.parent / str(record.get("screenshot"))).is_file(), f"static {mode} unavailability screenshot is missing")
        return {"path": str(path.relative_to(ROOT)), "status": status, "reason": {mode: record.get("reason") for mode, record in records.items()}}
    for mode, record in records.items():
        require(record.get("available") is True, f"static {mode} observer was not available")
        require(record.get("frame_count") == 6, f"static {mode} observer did not return six frames")
        require((path.parent / str(record.get("viewer_screenshot"))).is_file(), f"static {mode} observer screenshot is missing")
    require(records["live"].get("after", {}).get("state") == "running", "static live observer did not remain live")
    require(records["paused"].get("after", {}).get("state") == "paused", "static paused observer did not remain paused")
    return {"path": str(path.relative_to(ROOT)), "status": status, "frame_count": 6}


def validate_pytest() -> dict[str, Any]:
    path = EVIDENCE / "pytest-results.xml"
    root = ElementTree.parse(path).getroot()
    suite = root.find("testsuite")
    require(suite is not None, "pytest JUnit artifact has no testsuite")
    require(int(suite.attrib.get("errors", "-1")) == 0, "pytest JUnit artifact reports errors")
    require(int(suite.attrib.get("failures", "-1")) == 0, "pytest JUnit artifact reports failures")
    require(int(suite.attrib.get("tests", "0")) > 0, "pytest JUnit artifact reports no tests")
    return {
        "path": str(path.relative_to(ROOT)),
        "tests": int(suite.attrib["tests"]),
        "skipped": int(suite.attrib.get("skipped", "0")),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=EVIDENCE / "evidence_manifest.json")
    args = parser.parse_args()
    checks = {
        "generation": validate_generation(),
        "live_matrix": validate_matrix("live_matrix_final_fixed", "live"),
        "paused_matrix": validate_matrix("paused_matrix_final", "paused"),
        "real_time": validate_realtime(),
        "public_static_observer": validate_static_observer(),
        "interaction_rejection": validate_rejections(),
        "pytest": validate_pytest(),
    }
    static = EVIDENCE / "static_browser_smoke"
    required_static = ["dashboard-browser-play.png", "browser-observation-viewer.png", "browser-play-pyodide-pass.png"]
    require(all((static / filename).is_file() for filename in required_static), "static-browser smoke screenshots are incomplete")
    sources = (
        ENVIRONMENT / "controls.json",
        ENVIRONMENT / "tasks" / "occlusion_shell_swindle_seed_0001" / "task.json",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "occlusion_shell_swindle.py",
        BENCHMARK / "shared_runtime" / "app" / "mechanics" / "occlusion_shell_swindle.js",
        BENCHMARK / "shared_runtime" / "app" / "mechanics" / "occlusion_shell_swindle.css",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "occlusion_shell_swindle.py",
        BENCHMARK / "tools" / "incubator_solvers" / "occlusion_shell_swindle.py",
    )
    result = {
        "environment": ENVIRONMENT.name,
        "passed": checks["public_static_observer"].get("status") == "available",
        "unmet_evidence": [] if checks["public_static_observer"].get("status") == "available" else ["native public-static target-tab observation is unavailable under isolated headless Playwright"],
        "checks": checks,
        "static_browser_smoke": [str((static / filename).relative_to(ROOT)) for filename in required_static],
        "source_hashes": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
