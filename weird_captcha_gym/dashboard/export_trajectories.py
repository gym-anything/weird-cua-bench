#!/usr/bin/env python3
"""Export a static, lazy-loading viewer for a Weird CUA evaluation corpus."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from collections import Counter
from pathlib import Path
from typing import Any


DASHBOARD_ROOT = Path(__file__).resolve().parent
STATIC_ROOT = DASHBOARD_ROOT / "trajectory_static"
STEP_RE = re.compile(r"weird_input_(\d+)\.png$")
FRAME_RE = re.compile(r"observation_(\d+)_frame_(\d+)\.png$")
RUN_RE = re.compile(r"run_(\d+)$")


def _load_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [
        value
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and isinstance((value := json.loads(line)), dict)
    ]


def _relative_url(path: Path, output: Path) -> str:
    return Path(os.path.relpath(path.resolve(), output.resolve())).as_posix()


def _agent_run_dir(run_dir: Path) -> Path | None:
    candidates = [
        path
        for path in (run_dir / "all_runs").rglob("run_*")
        if path.is_dir()
        and RUN_RE.fullmatch(path.name)
        and (path / "responses.json").is_file()
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: int(RUN_RE.fullmatch(path.name).group(1)))


def _environment_title(record: dict[str, Any]) -> str:
    task_path = (
        Path(str(record.get("env_dir", "")))
        / "tasks"
        / str(record.get("task_id", ""))
        / "task.json"
    )
    task = _load_json(task_path, {})
    name = task.get("name") if isinstance(task, dict) else None
    if isinstance(name, str) and name.strip():
        return name.split(" · Difficulty", 1)[0].strip()
    mechanic = str(record.get("mechanic_id") or record.get("environment") or "Unknown")
    return mechanic.removesuffix("_env").replace("_", " ").title()


def _task_instruction(record: dict[str, Any], episode_dir: Path | None) -> str:
    candidates = [
        Path(str(record.get("env_dir", "")))
        / "tasks"
        / str(record.get("task_id", ""))
        / "task.json"
    ]
    if episode_dir is not None:
        candidates.append(episode_dir / "current_task.json")
    for path in candidates:
        task = _load_json(path, {})
        if not isinstance(task, dict):
            continue
        for key in ("natural_language", "description"):
            value = task.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _response_payload(agent_dir: Path | None) -> tuple[list[Any], list[Any]]:
    if agent_dir is None:
        return [], []
    response_document = _load_json(agent_dir / "responses.json", {})
    if isinstance(response_document, dict):
        responses = response_document.get("model_responses") or []
        parsed = response_document.get("parsed_responses") or []
    else:
        responses = response_document if isinstance(response_document, list) else []
        parsed = []
    parsed_document = _load_json(agent_dir / "parsed_responses.json", None)
    if isinstance(parsed_document, list):
        parsed = parsed_document
    return list(responses), list(parsed)


def _screenshots(agent_dir: Path | None, output: Path) -> dict[int, dict[str, Any]]:
    if agent_dir is None:
        return {}
    turns: dict[int, dict[str, Any]] = {}
    for path in agent_dir.iterdir():
        step_match = STEP_RE.fullmatch(path.name)
        if step_match:
            step = int(step_match.group(1))
            turns.setdefault(step, {"frames": []})["frames"].append(
                {"url": _relative_url(path, output), "kind": "current"}
            )
            continue
        frame_match = FRAME_RE.fullmatch(path.name)
        if frame_match:
            step = int(frame_match.group(1))
            frame = int(frame_match.group(2))
            turns.setdefault(step, {"frames": []})["frames"].append(
                {
                    "url": _relative_url(path, output),
                    "kind": "window",
                    "sequence": frame,
                }
            )
    for value in turns.values():
        value["frames"].sort(
            key=lambda item: (
                1 if item["kind"] == "current" else 0,
                int(item.get("sequence", 0)),
            )
        )
    return turns


def _timing_events(done: dict[str, Any], run_dir: Path) -> list[dict[str, Any]]:
    local = run_dir / "realtime_timing.jsonl"
    if local.is_file():
        return _load_jsonl(local)
    episode_dir = done.get("episode_dir")
    if isinstance(episode_dir, str):
        return _load_jsonl(Path(episode_dir) / "realtime_timing.jsonl")
    return []


def _click_point(parsed: Any) -> dict[str, float] | None:
    if not isinstance(parsed, dict):
        return None
    for action in parsed.get("actions") or []:
        if not isinstance(action, dict):
            continue
        mouse = action.get("mouse")
        if not isinstance(mouse, dict):
            continue
        for name in ("left_click", "right_click", "double_click", "middle_click"):
            coordinate = mouse.get(name)
            if (
                isinstance(coordinate, list)
                and len(coordinate) >= 2
                and all(isinstance(value, (int, float)) for value in coordinate[:2])
            ):
                return {"x": float(coordinate[0]), "y": float(coordinate[1])}
        coordinate = mouse.get("left_click_drag")
        if isinstance(coordinate, list) and len(coordinate) >= 2:
            start = coordinate[0]
            if isinstance(start, list) and len(start) >= 2:
                return {"x": float(start[0]), "y": float(start[1])}
    return None


def _run_payload(
    record: dict[str, Any],
    run_dir: Path,
    output: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    done = _load_json(run_dir / "done.json", {})
    if not isinstance(done, dict):
        done = {}
    agent_dir = _agent_run_dir(run_dir)
    responses, parsed_responses = _response_payload(agent_dir)
    screenshot_turns = _screenshots(agent_dir, output)
    timing = _timing_events(done, run_dir)
    setup = next((event for event in timing if event.get("event") == "setup"), {})
    turn_timing = [event for event in timing if event.get("event") == "turn"]
    episode_dir_value = done.get("episode_dir")
    episode_dir = Path(episode_dir_value) if isinstance(episode_dir_value, str) else None
    agent_info = _load_json(agent_dir / "info.json", {}) if agent_dir else {}
    verifier = done.get("verifier") or agent_info.get("verifier") or {}
    turn_count = max(
        len(responses),
        len(parsed_responses),
        len(turn_timing),
        max(screenshot_turns, default=-1) + 1,
    )
    turns: list[dict[str, Any]] = []
    for index in range(turn_count):
        parsed = parsed_responses[index] if index < len(parsed_responses) else None
        event = turn_timing[index] if index < len(turn_timing) else {}
        screenshot = screenshot_turns.get(index, {"frames": []})
        turns.append(
            {
                "index": index,
                "frames": screenshot["frames"],
                "response": responses[index] if index < len(responses) else "",
                "parsed": parsed,
                "click": _click_point(parsed),
                "timing": event,
            }
        )

    title = _environment_title(record)
    run_id = str(record.get("run_id") or run_dir.name)
    poster = next(
        (
            frame["url"]
            for turn in turns
            for frame in turn["frames"]
            if frame.get("kind") == "current"
        ),
        None,
    )
    summary = {
        "id": run_id,
        "index": int(record.get("index", 0)),
        "title": title,
        "environment": record.get("environment"),
        "mechanic_id": record.get("mechanic_id"),
        "difficulty": record.get("difficulty"),
        "interaction": record.get("interaction"),
        "time_mode": record.get("time_mode"),
        "seed": record.get("seed"),
        "model": record.get("model"),
        "outcome": done.get("outcome") or done.get("state") or "unknown",
        "reason": done.get("benchmark_reason") or agent_info.get("benchmark_reason") or "unknown",
        "passed": verifier.get("passed") is True,
        "score": verifier.get("score"),
        "feedback": verifier.get("feedback") or "",
        "duration_seconds": done.get("duration_seconds"),
        "turn_count": turn_count,
        "frame_count": sum(len(turn["frames"]) for turn in turns),
        "poster": poster,
        "detail_url": f"data/runs/{int(record.get('index', 0)):03d}.json",
    }
    detail = {
        **summary,
        "task_id": record.get("task_id"),
        "instruction": _task_instruction(record, episode_dir),
        "verifier": verifier,
        "setup": setup,
        "turns": turns,
    }
    return summary, detail


def export_trajectory_dashboard(evaluation_root: Path, output: Path | None = None) -> dict[str, Any]:
    evaluation_root = evaluation_root.expanduser().resolve()
    output = (output or (evaluation_root / "trajectory_dashboard")).expanduser().resolve()
    manifest_path = evaluation_root / "manifest.jsonl"
    records = _load_jsonl(manifest_path)
    if not records:
        raise ValueError(f"evaluation manifest is empty or missing: {manifest_path}")
    if output == evaluation_root or evaluation_root not in output.parents:
        raise ValueError("trajectory output must be a child of the evaluation root")

    shutil.rmtree(output, ignore_errors=True)
    (output / "static").mkdir(parents=True)
    (output / "data" / "runs").mkdir(parents=True)
    for name in ("index.html", "styles.css", "app.js"):
        destination = output / (name if name == "index.html" else f"static/{name}")
        shutil.copy2(STATIC_ROOT / name, destination)

    summaries: list[dict[str, Any]] = []
    for record in records:
        index = int(record["index"])
        run_dir = evaluation_root / "runs" / f"{index:03d}_{record['run_id']}"
        summary, detail = _run_payload(record, run_dir, output)
        summaries.append(summary)
        (output / "data" / "runs" / f"{index:03d}.json").write_text(
            json.dumps(detail, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )

    protocol = _load_json(evaluation_root / "protocol.json", {})
    reasons = Counter(str(run["reason"]) for run in summaries)
    outcomes = Counter(str(run["outcome"]) for run in summaries)
    document = {
        "version": 1,
        "evaluation": evaluation_root.name,
        "protocol": protocol,
        "stats": {
            "runs": len(summaries),
            "passes": sum(run["passed"] for run in summaries),
            "failures": sum(not run["passed"] for run in summaries),
            "model_turns": sum(int(run["turn_count"]) for run in summaries),
            "screenshots": sum(int(run["frame_count"]) for run in summaries),
            "reasons": reasons,
            "outcomes": outcomes,
        },
        "runs": summaries,
    }
    (output / "data" / "index.json").write_text(
        json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "evaluation_root": str(evaluation_root),
                "run_count": len(summaries),
                "serve_from": str(evaluation_root),
                "entrypoint": f"{output.name}/index.html",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return document


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    document = export_trajectory_dashboard(args.evaluation_root, args.output)
    print(
        f"trajectory dashboard: {document['stats']['runs']} runs · "
        f"{document['stats']['model_turns']} model turns · "
        f"{document['stats']['screenshots']} screenshots"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
