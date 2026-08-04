#!/usr/bin/env python3
"""Lock the pre-control L4 state for Live Shattered-Scene Synchronizer.

The fixture is generated from an explicit git revision, not from the current
controlled generator.  Tests compare current uncontrolled and L4/full output
against this public-state and ground-truth record after removing only task,
challenge, and control-condition identity fields.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "single_scene_split_boxes_env"
GENERATOR_PATH = "weird_captcha_gym/shared_scripts/incubator_generators/single_scene_split_boxes.py"
TASK_PATH = "weird_captcha_gym/environments/single_scene_split_boxes_env/tasks/single_scene_split_boxes_seed_0001/task.json"
DEFAULT_OUT = ENVIRONMENT / "historical_l4_baseline_fixture.json"
SEEDS = (
    "1",
    "split-boxes-baseline-a",
    "split-boxes-baseline-b",
    "split-boxes-baseline-c",
    "interaction-pair-single_scene_split_boxes",
)


def git_show(revision: str, path: str) -> bytes:
    return subprocess.check_output(("git", "show", f"{revision}:{path}"), cwd=ROOT)


def resolve_revision(revision: str) -> str:
    return subprocess.check_output(("git", "rev-parse", f"{revision}^{{commit}}"), cwd=ROOT, text=True).strip()


def load_historical_generator(source: bytes):
    with tempfile.TemporaryDirectory(prefix="split-boxes-historical-generator-") as temporary_name:
        module_path = Path(temporary_name) / "single_scene_split_boxes.py"
        module_path.write_bytes(source)
        spec = importlib.util.spec_from_file_location("historical_split_boxes_generator", module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("could not load historical split-box generator")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", default="HEAD", help="pre-control revision to lock")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    revision = resolve_revision(args.revision)
    generator_source = git_show(revision, GENERATOR_PATH)
    task_source = git_show(revision, TASK_PATH)
    task = json.loads(task_source)
    generated: list[dict[str, Any]] = []
    # The temporary source is needed only while importlib executes it.
    generator = load_historical_generator(generator_source)
    for seed in SEEDS:
        public_state, ground_truth = generator.generate(task, seed)
        generated.append(
            {
                "seed": seed,
                "public_state": public_state,
                "ground_truth": ground_truth,
            }
        )

    fixture = {
        "fixture_format": 1,
        "environment": ENVIRONMENT.name,
        "public_environment_name": "Live Shattered-Scene Synchronizer",
        "historical_revision": revision,
        "historical_generator_path": GENERATOR_PATH,
        "historical_generator_sha256": hashlib.sha256(generator_source).hexdigest(),
        "historical_task_path": TASK_PATH,
        "historical_task_sha256": hashlib.sha256(task_source).hexdigest(),
        "identity_fields_removed_for_comparison": ["task_id", "challenge_id", "control_condition"],
        "seeds": generated,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(fixture, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: fixture[key] for key in fixture if key != "seeds"} | {"seed_count": len(generated)}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
