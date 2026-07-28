#!/usr/bin/env python3
"""Record reproducible generation and transcript-binding evidence for Fake Desktop."""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
BENCHMARK = ROOT / "benchmarks" / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "fake_desktop_automation_inversion_env"
MECHANIC = "fake_desktop_automation_inversion"


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


SETUP = _module("fake_desktop_contract_setup", BENCHMARK / "shared_scripts" / "setup_task.py")
MATERIALIZER = _module("fake_desktop_contract_materializer", BENCHMARK / "tools" / "materialize_controlled_tasks.py")
GRADER = _module(
    "fake_desktop_contract_grader",
    BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{MECHANIC}.py",
)
VERIFIER = _module(
    "fake_desktop_contract_verifier",
    ENVIRONMENT / "tasks" / f"{MECHANIC}_seed_0001" / "verifier.py",
)


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _task(level: int, interaction: str) -> dict[str, Any]:
    controls = _json(ENVIRONMENT / "controls.json")
    base = _json(ENVIRONMENT / "tasks" / f"{MECHANIC}_seed_0001" / "task.json")
    return MATERIALIZER.controlled_task(
        base,
        mechanic_id=MECHANIC,
        level=level,
        interaction=interaction,
        profile=controls["difficulty"][str(level)],
        task_dir_name=f"{MECHANIC}_d{level}_{interaction}_seed_0001",
    )


def _without_identity(value: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(value)
    for key in ("task_id", "challenge_id", "control_condition"):
        normalized.pop(key, None)
    return normalized


def _l3_simplified_payload(public: dict[str, Any], truth: dict[str, Any]) -> dict[str, Any]:
    mappings = truth["mapping_sequence"]
    events: list[dict[str, Any]] = []

    def push(kind: str, **fields: Any) -> None:
        events.append({"sequence": len(events) + 1, "kind": kind, **fields})

    push("proxy", action="close_interceptor", input_source="automation_panel")
    push("proxy", action="move_vault", input_source="automation_panel")
    push("proxy", action="select_file", file_id=truth["target_file_ids"][0], input_source="automation_panel")
    push("proxy", action="transfer_selected", input_source="automation_panel")
    push("boundary", **{"from": 0, "to": 1, "reason": "keyfile_1_loaded", "mapping": mappings[1], "input_source": "automation_panel"})
    push("proxy", action="move_verifier", input_source="automation_panel")
    push("proxy", action="select_file", file_id=truth["target_file_ids"][1], input_source="automation_panel")
    push("proxy", action="transfer_selected", input_source="automation_panel")
    push("boundary", **{"from": 1, "to": 2, "reason": "keyfile_2_loaded", "mapping": mappings[2], "input_source": "automation_panel"})
    push("proxy", action="arm_manual_control", input_source="automation_panel")

    windows = {item["id"]: dict(item) for item in truth["initial_windows"]}
    windows["interceptor"]["closed"] = True
    width, height = truth["desktop"]["width"], truth["desktop"]["height"]
    for window_id, delta_x, delta_y, z in (("vault", 70, -20, 5), ("verifier", -55, 28, 6)):
        window = windows[window_id]
        window["x"] = max(0, min(width - window["width"], window["x"] + delta_x))
        window["y"] = max(0, min(height - window["height"], window["y"] + delta_y))
        window["z"] = z
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction": "simplified",
        "events": events,
        "window_state": [
            {key: window[key] for key in ("id", "x", "y", "z", "closed")}
            for window in sorted(windows.values(), key=lambda item: item["id"])
        ],
        "boundary_index": 2,
        "active_mapping": mappings[2],
        "loaded_file_ids": truth["target_file_ids"],
        "armed": True,
        "move_count": 2,
        "closed_count": 1,
        "z_order_changes": 2,
        "file_drag_moves": 2,
        "moved_window_ids": ["vault", "verifier"],
        "reset_count": 0,
    }


def _verify(payload: dict[str, Any], public: dict[str, Any], truth: dict[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="fake-desktop-contract-export-") as temporary_name:
        exported = Path(temporary_name) / "result.json"
        exported.write_text(
            json.dumps({"result": payload, "public_state": public, "ground_truth": truth}),
            encoding="utf-8",
        )

        def copy_from_env(_source: str, destination: str) -> None:
            shutil.copy2(exported, destination)

        return VERIFIER.verify_task(env_info={"copy_from_env": copy_from_env})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=ENVIRONMENT / "evidence_docs")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    base = _json(ENVIRONMENT / "tasks" / f"{MECHANIC}_seed_0001" / "task.json")
    seeds = ("fake-desktop-contract-a", "fake-desktop-contract-b", "fake-desktop-contract-c")
    baseline: dict[str, Any] = {}
    profiles: dict[str, Any] = {}
    for seed in seeds:
        original_public, original_truth = SETUP.generate_task_state(base, seed)
        l3_public, l3_truth = SETUP.generate_task_state(_task(3, "full"), seed)
        baseline[seed] = {
            "same_challenge_id": original_public["challenge_id"] == l3_public["challenge_id"],
            "same_public_world": _without_identity(original_public) == _without_identity(l3_public),
            "same_private_world": _without_identity(original_truth) == _without_identity(l3_truth),
        }
        if not all(baseline[seed].values()):
            raise AssertionError(f"L3 baseline changed the original challenge for {seed}")

    for level in range(1, 6):
        per_seed: dict[str, Any] = {}
        for seed in seeds:
            full_task = _task(level, "full")
            simplified_task = _task(level, "simplified")
            full = SETUP.generate_task_state(full_task, seed)
            repeated = SETUP.generate_task_state(full_task, seed)
            simplified = SETUP.generate_task_state(simplified_task, seed)
            full_public, full_truth = full
            simplified_public, simplified_truth = simplified
            per_seed[seed] = {
                "deterministic": full == repeated,
                "same_challenge_id": full_public["challenge_id"] == simplified_public["challenge_id"],
                "same_public_world": _without_identity(full_public) == _without_identity(simplified_public),
                "same_private_world": _without_identity(full_truth) == _without_identity(simplified_truth),
                "targets": len(full_truth["target_file_ids"]),
                "files": len(full_public["files"]),
                "mapping_phases": len(full_public["mapping_sequence"]),
                "mapping_sequence": full_public["mapping_sequence"],
                "final_mapping_changes": len(full_public["mapping_sequence"]) < 2 or full_public["mapping_sequence"][-1] != full_public["mapping_sequence"][-2],
                "required_moved_window_ids": full_public["required_moved_window_ids"],
            }
            if not all(per_seed[seed][key] for key in ("deterministic", "same_challenge_id", "same_public_world", "same_private_world")):
                raise AssertionError(f"controlled pair contract failed at L{level} {seed}")
        profiles[str(level)] = per_seed

    l5_remap_sweep: list[dict[str, Any]] = []
    for index in range(100):
        seed = f"fake-desktop-l5-final-remap-{index}"
        public, _truth = SETUP.generate_task_state(_task(5, "full"), seed)
        mappings = list(public["mapping_sequence"])
        if len(set(mappings[:4])) != 4 or mappings[-1] == mappings[-2]:
            l5_remap_sweep.append({"seed": seed, "mapping_sequence": mappings})
    if l5_remap_sweep:
        raise AssertionError(f"L5 emitted a non-changing final remap: {l5_remap_sweep}")

    simplified_public, simplified_truth = SETUP.generate_task_state(_task(3, "simplified"), "fake-desktop-contract-binding")
    full_public, full_truth = SETUP.generate_task_state(_task(3, "full"), "fake-desktop-contract-binding")
    payload = _l3_simplified_payload(simplified_public, simplified_truth)
    accepted = GRADER.grade(payload, simplified_truth, simplified_public)
    verifier = _verify(payload, simplified_public, simplified_truth)
    wrong_interaction = copy.deepcopy(payload)
    wrong_interaction["interaction"] = "full"
    wrong_source = copy.deepcopy(payload)
    wrong_source["events"][0]["input_source"] = "remote_pointer"
    wrong_selection = copy.deepcopy(payload)
    decoy = next(file_item["id"] for file_item in simplified_truth["files"] if file_item["id"] not in simplified_truth["target_file_ids"])
    first_selection = next(event for event in wrong_selection["events"] if event.get("action") == "select_file")
    first_selection["file_id"] = decoy
    stale = copy.deepcopy(payload)
    stale["challenge_id"] = "stale-challenge"
    adapted_cross_mode = copy.deepcopy(payload)
    adapted_cross_mode["task_id"] = full_public["task_id"]
    transcript_binding = {
        "accepted_simplified": accepted,
        "independent_export_verifier": verifier,
        "wrong_interaction": GRADER.grade(wrong_interaction, simplified_truth, simplified_public),
        "wrong_input_source": GRADER.grade(wrong_source, simplified_truth, simplified_public),
        "wrong_selected_keyfile": GRADER.grade(wrong_selection, simplified_truth, simplified_public),
        "stale_challenge": GRADER.grade(stale, simplified_truth, simplified_public),
        "unmodified_simplified_transcript_against_full": GRADER.grade(payload, full_truth, full_public),
        "adapted_simplified_transcript_against_full": GRADER.grade(adapted_cross_mode, full_truth, full_public),
    }
    expected_failures = (
        "wrong_interaction", "wrong_input_source", "wrong_selected_keyfile", "stale_challenge",
        "unmodified_simplified_transcript_against_full", "adapted_simplified_transcript_against_full",
    )
    if accepted.get("passed") is not True or verifier.get("passed") is not True:
        raise AssertionError(f"valid L3 transcript was rejected: {accepted}; verifier={verifier}")
    if any(transcript_binding[name].get("passed") is True for name in expected_failures):
        raise AssertionError(f"an invalid transcript passed: {transcript_binding}")

    report = {
        "environment": ENVIRONMENT.name,
        "seeds": list(seeds),
        "baseline_l3_preservation": baseline,
        "difficulty_and_interaction_profiles": profiles,
        "l5_final_remap_sweep": {
            "seeds_checked": 100,
            "violations": l5_remap_sweep,
        },
        "transcript_binding": transcript_binding,
    }
    path = args.out_dir / "contract-validation.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
