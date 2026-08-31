#!/usr/bin/env python3
"""Run an immutable Weird CUA task sample through one computer-use agent.

The manifest is the experiment contract. This runner validates its corpus
fingerprint before launching anything, streams a separate log for every task,
and records verifier failures separately from infrastructure failures.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_ROOT = REPO_ROOT / "weird_captcha_gym" / "environments"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def corpus_snapshot_for_tasks(tasks: list) -> tuple[list, str]:
    """The corpus snapshot in the same path convention as a manifest's tasks.

    Manifests drawn before the package left benchmarks/ are frozen
    provenance records carrying the historical path prefix. They are
    validated against that same convention instead of editing the records.
    """
    population, digest = corpus_snapshot()
    if any(str(t.get("environment_path", "")).startswith("benchmarks/") for t in tasks):
        # Pre-package-rename manifests are immutable 75-environment experiment
        # records. New tasks may explicitly exclude themselves from that
        # historical population without changing the current corpus snapshot.
        population = [
            entry
            for entry in population
            if json.loads((REPO_ROOT / entry["task_json"]).read_text(encoding="utf-8"))
            .get("metadata", {})
            .get("legacy_agent_sample_population", True)
            is not False
        ]
        population = [
            {
                **entry,
                "environment_path": "benchmarks/" + entry["environment_path"],
                "task_json": "benchmarks/" + entry["task_json"],
            }
            for entry in population
        ]
        canonical = json.dumps(
            population, sort_keys=True, separators=(",", ":")
        ).encode()
        digest = hashlib.sha256(canonical).hexdigest()
    return population, digest


def _current_repo_path(manifest_path: str) -> str:
    """Map a manifest path (possibly pre-rename) to the current layout."""
    prefix = "benchmarks/"
    if manifest_path.startswith(prefix):
        return manifest_path[len(prefix):]
    return manifest_path


def _population_entry(task_path: Path) -> dict[str, str]:
    spec = json.loads(task_path.read_text(encoding="utf-8"))
    relative_task = task_path.relative_to(REPO_ROOT)
    environment_path = task_path.parents[2].relative_to(REPO_ROOT)
    return {
        "environment_id": spec["env_id"],
        "environment_path": environment_path.as_posix(),
        "task_id": spec["id"].split("@", 1)[0],
        "task_spec_id": spec["id"],
        "title": spec["name"],
        "task_json": relative_task.as_posix(),
    }


def corpus_snapshot() -> tuple[list[dict[str, str]], str]:
    task_paths = sorted(CORPUS_ROOT.glob("*_env/tasks/*/task.json"))
    population = [_population_entry(path) for path in task_paths]
    canonical = json.dumps(population, sort_keys=True, separators=(",", ":")).encode()
    return population, hashlib.sha256(canonical).hexdigest()


def _read_manifest(path: Path, seen: set[Path] | None = None) -> dict[str, Any]:
    path = path.resolve()
    seen = set() if seen is None else seen
    if path in seen:
        raise ValueError(f"manifest inheritance cycle at {path}")
    seen.add(path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    base_ref = manifest.pop("base_manifest", None)
    if base_ref:
        base = _read_manifest((path.parent / str(base_ref)).resolve(), seen)
        manifest = {**base, **manifest}
    return manifest


def load_manifest(path: Path) -> dict[str, Any]:
    manifest = _read_manifest(path)
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported manifest schema")

    selection = manifest.get("selection") or {}
    protocol = manifest.get("protocol") or {}
    tasks = manifest.get("tasks") or []
    population, digest = corpus_snapshot_for_tasks(tasks)
    population_by_spec = {entry["task_spec_id"]: entry for entry in population}

    if len(population) != selection.get("population_size"):
        raise ValueError("task population size changed since the draw")
    if digest != selection.get("population_sha256"):
        raise ValueError("task population fingerprint changed since the draw")
    if len(tasks) != selection.get("sample_size"):
        raise ValueError("sample size does not match the frozen selection")
    if len({task.get("task_spec_id") for task in tasks}) != len(tasks):
        raise ValueError("sample contains duplicate task IDs")
    for task in tasks:
        if population_by_spec.get(task.get("task_spec_id")) != task:
            raise ValueError(f"sample task no longer matches corpus: {task.get('task_spec_id')}")

    display_resolution = protocol.get("display_resolution")
    if display_resolution is not None:
        if display_resolution != [1920, 1080]:
            raise ValueError("protocol display_resolution must be [1920, 1080]")
        for task in tasks:
            env_spec = json.loads(
                (REPO_ROOT / _current_repo_path(task["environment_path"]) / "env.json").read_text(
                    encoding="utf-8"
                )
            )
            screens = [
                item
                for item in env_spec.get("observation", [])
                if item.get("type") in {"rgb_screen", "frame_window"}
            ]
            # The frozen agent desktop contract is 1920 × 1080, while a task
            # may intentionally preserve a smaller historical screenshot
            # surface.  Validate the task's declared surface rather than
            # silently coercing it to the agent desktop size.
            resolution = screens[0].get("resolution") if len(screens) == 1 else None
            if (
                not isinstance(resolution, list)
                or len(resolution) != 2
                or not all(isinstance(value, int) and value > 0 for value in resolution)
            ):
                raise ValueError(
                    f"sample environment has no valid rgb_screen resolution: {task['environment_id']}"
                )

    required_protocol = {
        "agent": "GeminiComputerUseAgent",
        "model": "gemini-3.5-flash",
        "computer_use_environment": "desktop",
        "runner": "avf",
        "runs_per_task": 1,
        "parallelism": 1,
        "fast_io": False,
        "task_mutations_allowed": False,
    }
    for key, expected in required_protocol.items():
        if protocol.get(key) != expected:
            raise ValueError(f"protocol {key!r} must be {expected!r}")
    if not isinstance(protocol.get("seed"), int):
        raise ValueError("protocol seed must be an integer")
    if not isinstance(protocol.get("max_steps"), int) or protocol["max_steps"] < 1:
        raise ValueError("protocol max_steps must be a positive integer")
    if not str(protocol.get("task_instruction") or "").strip():
        raise ValueError("protocol task_instruction must be non-empty")
    retry_delays = protocol.get("no_candidate_retry_delays_seconds")
    if not isinstance(retry_delays, list) or not all(
        isinstance(delay, (int, float)) and delay >= 0 for delay in retry_delays
    ):
        raise ValueError("protocol no_candidate_retry_delays_seconds must be nonnegative numbers")
    if protocol.get("max_no_candidate_retries_per_turn") != len(retry_delays):
        raise ValueError("retry count must equal the number of retry delays")
    if not isinstance(protocol.get("post_reset_observation_delay_seconds"), (int, float)):
        raise ValueError("protocol post_reset_observation_delay_seconds must be numeric")
    http_retry_options = protocol.get("http_retry_options")
    if http_retry_options is not None:
        if not isinstance(http_retry_options, dict):
            raise ValueError("protocol http_retry_options must be an object")
        if not isinstance(http_retry_options.get("attempts"), int) or http_retry_options["attempts"] < 2:
            raise ValueError("protocol HTTP retry attempts must be at least 2")
        timeout_ms = http_retry_options.get("timeout_ms")
        if not isinstance(timeout_ms, int) or timeout_ms < 1:
            raise ValueError("protocol HTTP request timeout_ms must be a positive integer")
        for key in ("initial_delay", "max_delay", "jitter"):
            value = http_retry_options.get(key)
            if not isinstance(value, (int, float)) or value < 0:
                raise ValueError(f"protocol HTTP retry {key} must be nonnegative")
        exp_base = http_retry_options.get("exp_base")
        if not isinstance(exp_base, (int, float)) or exp_base < 1:
            raise ValueError("protocol HTTP retry exp_base must be at least 1")
        status_codes = http_retry_options.get("http_status_codes")
        if not isinstance(status_codes, list) or not all(
            isinstance(code, int) for code in status_codes
        ):
            raise ValueError("protocol HTTP retry status codes must be integers")


def build_command(manifest: dict[str, Any], task: dict[str, str]) -> list[str]:
    protocol = manifest["protocol"]
    decoding = json.dumps(
        {
            "temperature": protocol["temperature"],
            "thinking_level": protocol["thinking_level"],
        },
        separators=(",", ":"),
    )
    task_instruction = json.dumps(protocol["task_instruction"], separators=(",", ":"))
    retry_delays = json.dumps(protocol["no_candidate_retry_delays_seconds"], separators=(",", ":"))
    command = [
        sys.executable,
        "-m",
        "gym_anything.cli",
        "benchmark",
        str(REPO_ROOT / _current_repo_path(task["environment_path"])),
        "--task",
        task["task_id"],
        "--agent",
        protocol["agent"],
        "--model",
        protocol["model"],
        "--steps",
        str(protocol["max_steps"]),
        "--seed",
        str(protocol["seed"]),
        "--exp-name",
        manifest["experiment_id"],
        "--post-reset-observation-delay",
        str(protocol["post_reset_observation_delay_seconds"]),
        "--agent-arg",
        f"environment={protocol['computer_use_environment']}",
        "--agent-arg",
        f"decoding_params={decoding}",
        "--agent-arg",
        f"task_instruction={task_instruction}",
        "--agent-arg",
        f"no_candidate_retry_delays={retry_delays}",
    ]
    http_retry_options = protocol.get("http_retry_options")
    if http_retry_options is not None:
        command.extend([
            "--agent-arg",
            f"http_retry_options={json.dumps(http_retry_options, separators=(',', ':'))}",
        ])
    command.append("--verbose")
    return command


def _run_number(path: Path) -> int:
    try:
        return int(path.name.removeprefix("run_"))
    except ValueError:
        return -1


def _new_run_dir(manifest: dict[str, Any], task_id: str, before: set[Path]) -> Path | None:
    protocol = manifest["protocol"]
    root = REPO_ROOT / "all_runs" / manifest["experiment_id"] / protocol["model"] / task_id
    after = {path for path in root.glob("run_*") if path.is_dir()}
    created = sorted(after - before, key=_run_number)
    return created[-1] if created else None


def summarize_run(run_dir: Path | None, returncode: int, model_error: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "returncode": returncode,
        "run_dir": str(run_dir.relative_to(REPO_ROOT)) if run_dir else None,
        "model_api_error_observed": model_error,
        "outcome": "infrastructure_error" if returncode else "unknown",
        "verifier_passed": None,
        "verifier_score": None,
        "reason": None,
    }
    if run_dir is None:
        if returncode == 0:
            result["outcome"] = "incomplete_artifacts"
        return result

    info_path = run_dir / "info.pkl"
    if not info_path.exists():
        if returncode == 0:
            result["outcome"] = "incomplete_artifacts"
        return result

    try:
        with info_path.open("rb") as handle:
            info = pickle.load(handle)
    except Exception as exc:  # the artifact is evidence; report corruption without hiding it
        result["outcome"] = "infrastructure_error"
        result["artifact_error"] = f"{type(exc).__name__}: {exc}"
        return result

    result["reason"] = info.get("reason") if isinstance(info, dict) else None
    verifier = info.get("verifier") if isinstance(info, dict) else None
    if isinstance(verifier, dict):
        passed = verifier.get("passed")
        result["verifier_passed"] = passed
        result["verifier_score"] = verifier.get("score")
        if passed is True:
            result["outcome"] = "passed"
        elif model_error:
            result["outcome"] = "model_api_error"
        elif passed is False:
            result["outcome"] = "failed"
    elif model_error:
        result["outcome"] = "model_api_error"
    elif returncode == 0:
        result["outcome"] = "missing_verdict"
    return result


def _write_summary(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    temporary.replace(path)


def is_terminal_model_error_log(line: str) -> bool:
    return (
        "[gemini-cu] generate_content error:" in line
        or "[gemini-cu] no candidate retries exhausted" in line
    )


def run_sample(manifest_path: Path, results_dir: Path, dry_run: bool) -> int:
    manifest = load_manifest(manifest_path)
    commands = [build_command(manifest, task) for task in manifest["tasks"]]
    if dry_run:
        print(json.dumps({"experiment_id": manifest["experiment_id"], "commands": commands}, indent=2))
        return 0

    if (results_dir / "summary.json").exists():
        raise FileExistsError(f"refusing to overwrite existing experiment: {results_dir / 'summary.json'}")
    load_dotenv(REPO_ROOT / ".env")
    load_dotenv(REPO_ROOT.parent / ".env")
    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY is not loaded")

    summary: dict[str, Any] = {
        "schema_version": 1,
        "experiment_id": manifest["experiment_id"],
        "manifest": str(manifest_path.relative_to(REPO_ROOT)),
        "started_at_utc": utc_now(),
        "finished_at_utc": None,
        "tasks_total": len(manifest["tasks"]),
        "results": [],
    }
    summary_path = results_dir / "summary.json"
    child_env = os.environ.copy()
    child_env["GYM_ANYTHING_RUNNER"] = manifest["protocol"]["runner"]
    child_env["PYTHONUNBUFFERED"] = "1"

    infrastructure_failures = 0
    for index, (task, command) in enumerate(zip(manifest["tasks"], commands, strict=True), start=1):
        protocol = manifest["protocol"]
        run_root = (
            REPO_ROOT
            / "all_runs"
            / manifest["experiment_id"]
            / protocol["model"]
            / task["task_id"]
        )
        before = {path for path in run_root.glob("run_*") if path.is_dir()}
        log_path = results_dir / f"{index:02d}-{task['task_id']}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"\n[{index}/{len(commands)}] START {task['title']} ({task['task_id']})", flush=True)
        print("command:", " ".join(command), flush=True)
        model_error = False
        started_at = utc_now()
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                command,
                cwd=REPO_ROOT,
                env=child_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            assert process.stdout is not None
            for line in process.stdout:
                print(line, end="", flush=True)
                log.write(line)
                log.flush()
                if is_terminal_model_error_log(line):
                    model_error = True
            returncode = process.wait()

        run_dir = _new_run_dir(manifest, task["task_id"], before)
        result = {
            "index": index,
            "task_id": task["task_id"],
            "task_spec_id": task["task_spec_id"],
            "title": task["title"],
            "started_at_utc": started_at,
            "finished_at_utc": utc_now(),
            "log": str(log_path.relative_to(REPO_ROOT)),
            **summarize_run(run_dir, returncode, model_error),
        }
        summary["results"].append(result)
        if result["outcome"] in {
            "infrastructure_error",
            "incomplete_artifacts",
            "missing_verdict",
            "model_api_error",
        }:
            infrastructure_failures += 1
        _write_summary(summary_path, summary)
        print(f"[{index}/{len(commands)}] RESULT {result['outcome']}", flush=True)

    summary["finished_at_utc"] = utc_now()
    summary["counts"] = {
        outcome: sum(result["outcome"] == outcome for result in summary["results"])
        for outcome in sorted({result["outcome"] for result in summary["results"]})
    }
    _write_summary(summary_path, summary)
    print("\nFinal counts:", json.dumps(summary["counts"], sort_keys=True), flush=True)
    return 1 if infrastructure_failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--results-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Validate and print commands without launching VMs or models")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest_path = args.manifest.resolve()
    results_dir = (args.results_dir or manifest_path.parent / "runtime").resolve()
    return run_sample(manifest_path, results_dir, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
