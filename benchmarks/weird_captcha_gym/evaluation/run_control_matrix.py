#!/usr/bin/env python3
"""Create and execute a resumable Weird CUA controllability matrix."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


INTERACTIONS = ("simplified", "full")
TIME_MODES = ("live", "paused")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _load_record(manifest: Path, index: int) -> dict[str, Any]:
    with manifest.open(encoding="utf-8") as handle:
        for current, line in enumerate(handle):
            if current == index:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"manifest item {index} is not an object")
                return value
    raise IndexError(f"manifest has no item {index}")


def create_manifest(args: argparse.Namespace) -> int:
    repo_root = args.repo_root.resolve()
    environments_root = repo_root / "benchmarks" / "weird_captcha_gym" / "environments"
    controls_paths = sorted(environments_root.glob("*_env/controls.json"))
    if len(controls_paths) != args.expected_environments:
        raise ValueError(
            f"expected {args.expected_environments} environments but found {len(controls_paths)}"
        )

    records: list[dict[str, Any]] = []
    for controls_path in controls_paths:
        controls = json.loads(controls_path.read_text(encoding="utf-8"))
        mechanic_id = str(controls["mechanic_id"])
        env_dir = controls_path.parent.resolve()
        for interaction in INTERACTIONS:
            if controls["interaction"][interaction]["implemented"] is not True:
                raise ValueError(f"{env_dir.name}: {interaction} interaction is not implemented")
            task_id = f"{mechanic_id}_d{args.difficulty}_{interaction}_seed_0001"
            task_path = env_dir / "tasks" / task_id / "task.json"
            if not task_path.is_file():
                raise FileNotFoundError(task_path)
            task = json.loads(task_path.read_text(encoding="utf-8"))
            condition = task.get("metadata", {}).get("control_condition", {})
            expected = {"difficulty": args.difficulty, "interaction": interaction}
            if any(condition.get(key) != value for key, value in expected.items()):
                raise ValueError(f"{task_path}: wrong control condition {condition}")
            for time_mode in TIME_MODES:
                run_id = (
                    f"{mechanic_id}_l{args.difficulty}_{interaction}_{time_mode}_seed{args.seed}"
                )
                records.append(
                    {
                        "index": len(records),
                        "run_id": run_id,
                        "environment": env_dir.name,
                        "env_dir": str(env_dir),
                        "mechanic_id": mechanic_id,
                        "task_id": task_id,
                        "difficulty": args.difficulty,
                        "interaction": interaction,
                        "time_mode": time_mode,
                        "seed": args.seed,
                        "model": args.model,
                    }
                )

    expected_runs = args.expected_environments * len(INTERACTIONS) * len(TIME_MODES)
    if len(records) != expected_runs:
        raise ValueError(f"expected {expected_runs} runs but built {len(records)}")

    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    manifest = output_root / "manifest.jsonl"
    temporary = manifest.with_suffix(".jsonl.tmp")
    temporary.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    temporary.replace(manifest)
    _write_json(
        output_root / "protocol.json",
        {
            "created_at": _utc_now(),
            "repo_root": str(repo_root),
            "git_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True
            ).strip(),
            "difficulty": args.difficulty,
            "interactions": list(INTERACTIONS),
            "time_modes": list(TIME_MODES),
            "seed": args.seed,
            "model": args.model,
            "run_count": len(records),
            "request_timeout_seconds": args.request_timeout_seconds,
            "request_attempts": args.request_attempts,
            "task_play_time_limit_seconds": None,
            "remote_url": args.remote_url,
            "vlm_base_url": args.vlm_base_url,
        },
    )
    print(f"wrote {len(records)} runs to {manifest}")
    return 0


def _result_from_summary(summary_path: Path) -> dict[str, Any]:
    if not summary_path.is_file():
        return {"outcome": "missing_summary"}
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    info = summary.get("info") or {}
    verifier = info.get("verifier") or {}
    if verifier.get("passed") is True:
        outcome = "passed"
    elif verifier.get("decided") is True:
        outcome = "benchmark_failure"
    else:
        outcome = "undecided"
    return {
        "outcome": outcome,
        "episode_dir": summary.get("episode_dir"),
        "benchmark_reason": info.get("benchmark_reason"),
        "verifier": verifier,
    }


def run_item(args: argparse.Namespace) -> int:
    manifest = args.manifest.resolve()
    record = _load_record(manifest, args.index)
    output_root = manifest.parent
    run_dir = output_root / "runs" / f"{args.index:03d}_{record['run_id']}"
    run_dir.mkdir(parents=True, exist_ok=True)
    done_path = run_dir / "done.json"
    if done_path.is_file() and not args.rerun:
        print(f"already completed: {record['run_id']}")
        return 0

    protocol = json.loads((output_root / "protocol.json").read_text(encoding="utf-8"))
    summary_path = run_dir / "episode-summary.json"
    command = [
        args.evaluator,
        "--env-dir",
        record["env_dir"],
        "--task",
        record["task_id"],
        "--agent",
        "WeirdQwen35VLAgent",
        "--agent-args",
        json.dumps(
            {
                "model": record["model"],
                "temperature": 0.0,
                "history_n": 100,
                "image_max": 20,
                "fold_size": 10,
                "max_tokens": 2048,
                "exp_name": output_root.name,
                "task_name": record["run_id"],
            },
            separators=(",", ":"),
        ),
        "--time-mode",
        record["time_mode"],
        "--seed",
        str(record["seed"]),
        "--use-cache",
        "--cache-level",
        "pre_start",
        "--fast-io",
        "--no-play-time-limit",
        "--remote-url",
        protocol["remote_url"],
        "--remote-timeout",
        "7200",
        "--request-timeout-seconds",
        str(protocol["request_timeout_seconds"]),
        "--request-attempts",
        str(protocol["request_attempts"]),
        "--episode-summary-path",
        str(summary_path),
    ]
    env = os.environ.copy()
    env["VLM_BASE_URL"] = protocol["vlm_base_url"]
    env["PYTHONUNBUFFERED"] = "1"
    started_at = _utc_now()
    started = time.monotonic()
    _write_json(
        run_dir / "status.json",
        {
            "state": "running",
            "started_at": started_at,
            "record": record,
            "command": command,
        },
    )
    print(f"starting {record['run_id']}", flush=True)
    completed = subprocess.run(command, cwd=run_dir, env=env, check=False)
    status = {
        "state": "completed" if completed.returncode == 0 else "infrastructure_failure",
        "started_at": started_at,
        "finished_at": _utc_now(),
        "duration_seconds": time.monotonic() - started,
        "exit_code": completed.returncode,
        "record": record,
        "command": command,
    }
    if completed.returncode == 0:
        status.update(_result_from_summary(summary_path))
        _write_json(done_path, status)
    _write_json(run_dir / "status.json", status)
    print(json.dumps(status, sort_keys=True), flush=True)
    return completed.returncode


def run_range(args: argparse.Namespace) -> int:
    indices = list(range(args.start, args.end + 1))
    failures: list[int] = []

    def execute(index: int) -> tuple[int, int]:
        item_args = argparse.Namespace(
            manifest=args.manifest,
            index=index,
            evaluator=args.evaluator,
            rerun=args.rerun,
        )
        try:
            return index, run_item(item_args)
        except Exception as error:
            print(f"index {index} failed before evaluator completion: {error!r}", flush=True)
            return index, 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as executor:
        futures = [executor.submit(execute, index) for index in indices]
        for future in concurrent.futures.as_completed(futures):
            index, returncode = future.result()
            if returncode:
                failures.append(index)
            print(
                f"matrix progress: finished={len(indices) - sum(not item.done() for item in futures)}"
                f"/{len(indices)} failures={len(failures)} last_index={index}",
                flush=True,
            )
    if failures:
        print(f"failed indices: {','.join(map(str, sorted(failures)))}", flush=True)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create")
    create.add_argument("--repo-root", type=Path, required=True)
    create.add_argument("--output-root", type=Path, required=True)
    create.add_argument("--difficulty", type=int, choices=range(1, 6), required=True)
    create.add_argument("--seed", type=int, default=42)
    create.add_argument("--model", default="Qwen/Qwen3.5-9B")
    create.add_argument("--expected-environments", type=int, default=75)
    create.add_argument("--remote-url", default="http://babel-p9-16:5800")
    create.add_argument("--vlm-base-url", default="http://babel-p9-16:8600/v1")
    create.add_argument("--request-timeout-seconds", type=float, default=300.0)
    create.add_argument("--request-attempts", type=int, default=1)
    create.set_defaults(func=create_manifest)

    run = subparsers.add_parser("run")
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--index", type=int, required=True)
    run.add_argument("--evaluator", required=True)
    run.add_argument("--rerun", action="store_true")
    run.set_defaults(func=run_item)

    run_many = subparsers.add_parser("run-range")
    run_many.add_argument("--manifest", type=Path, required=True)
    run_many.add_argument("--start", type=int, required=True)
    run_many.add_argument("--end", type=int, required=True)
    run_many.add_argument("--jobs", type=int, default=20)
    run_many.add_argument("--evaluator", required=True)
    run_many.add_argument("--rerun", action="store_true")
    run_many.set_defaults(func=run_range)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
