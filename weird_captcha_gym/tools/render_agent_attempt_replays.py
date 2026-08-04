#!/usr/bin/env python3
"""Render honest videos from saved computer-use trajectory artifacts.

These are accelerated step replays, not continuous screen recordings. Every
task frame comes from Gym-Anything's saved observation PNGs, and every action
annotation comes from the corresponding trajectory step. The renderer never
runs a solver, calls a model, or mutates an environment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from weird_captcha_gym.tools.run_agent_sample import REPO_ROOT, load_manifest  # noqa: E402


OUTPUT_WIDTH = 1920
OUTPUT_HEIGHT = 1080
OBSERVATION_RE = re.compile(r"observation_(-?\d+)\.png$")
REPLAY_DISCLOSURE = (
    "Accelerated reconstruction from exact saved per-step screenshots and "
    "recorded Gemini actions; not a continuous real-time screen recording."
)


@dataclass(frozen=True)
class Segment:
    image: Path
    start: float
    end: float
    kind: str
    step: dict[str, Any] | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--task-id", action="append", help="Render only these task IDs")
    parser.add_argument("--seconds-per-step", type=float, default=0.75)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _recorded_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def _png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        header = stream.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"not a PNG: {path}")
    return struct.unpack(">II", header[16:24])


def observation_frames(run_dir: Path) -> dict[int, Path]:
    frames: dict[int, Path] = {}
    for path in run_dir.glob("observation_*.png"):
        match = OBSERVATION_RE.match(path.name)
        if match:
            frames[int(match.group(1))] = path
    return frames


def frame_for_step(frames: dict[int, Path], step_number: int) -> Path:
    """Return the observation immediately before ``step_number`` executes."""
    if not frames:
        raise ValueError("no observation frames")
    target = step_number - 1
    if target in frames:
        return frames[target]
    earlier = [index for index in frames if index <= target]
    if earlier:
        return frames[max(earlier)]
    return frames[min(frames)]


def _compact(value: Any, limit: int = 155) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _pointer_points(step: dict[str, Any]) -> list[tuple[int, int, str]]:
    points: list[tuple[int, int, str]] = []
    for env_action in step.get("env_actions") or []:
        mouse = env_action.get("mouse") if isinstance(env_action, dict) else None
        if not isinstance(mouse, dict):
            continue
        for key in ("left_click", "double_click", "right_click", "move"):
            point = mouse.get(key)
            if isinstance(point, list) and len(point) == 2:
                points.append((int(point[0]), int(point[1]), "pointer"))
                break
        drag = mouse.get("left_click_drag")
        if (
            isinstance(drag, list)
            and len(drag) >= 2
            and all(isinstance(point, list) and len(point) == 2 for point in drag[:2])
        ):
            points.append((int(drag[0][0]), int(drag[0][1]), "drag_start"))
            points.append((int(drag[-1][0]), int(drag[-1][1]), "drag_end"))
    deduplicated: list[tuple[int, int, str]] = []
    for point in points:
        if point not in deduplicated:
            deduplicated.append(point)
    return deduplicated


def describe_action(step: dict[str, Any]) -> str:
    action = str(step.get("action") or "unknown")
    args = step.get("args") if isinstance(step.get("args"), dict) else {}
    points = _pointer_points(step)
    label = action.replace("_", " ").upper()
    if action in {"click", "double_click", "right_click", "triple_click", "move", "mouse_down", "mouse_up"}:
        if points:
            x, y, _ = points[-1]
            return f"{label} @ ({x}, {y})"
    if action == "drag_and_drop" and len(points) >= 2:
        return f"DRAG ({points[0][0]}, {points[0][1]}) → ({points[-1][0]}, {points[-1][1]})"
    if action in {"press_key", "key_down", "key_up"}:
        return f"{label} · {args.get('key', '?')}"
    if action == "type":
        return f"TYPE · {_compact(args.get('text', ''), 70)!r}"
    if action == "wait":
        return f"WAIT · {args.get('seconds', '?')} s"
    if action == "scroll":
        return f"SCROLL · x={args.get('x', 0)} y={args.get('y', 0)}"
    if action == "take_screenshot":
        return "OBSERVE · TAKE SCREENSHOT"
    return label


def _segment_duration(step: dict[str, Any], default: float) -> float:
    action = str(step.get("action") or "")
    if action in {"DONE", "MODEL_API_RETRY", "MODEL_NO_CANDIDATE"}:
        return max(default, 1.15)
    return default


def build_segments(
    frames: dict[int, Path],
    steps: list[dict[str, Any]],
    blank_frame: Path,
    seconds_per_step: float,
) -> list[Segment]:
    source = frames.get(-1) or (frames[min(frames)] if frames else blank_frame)
    cursor = 0.0
    segments = [Segment(source, cursor, cursor + 1.8, "intro")]
    cursor = segments[-1].end
    for position, step in enumerate(steps):
        number = step.get("step")
        number = int(number) if isinstance(number, int) else position
        image = frame_for_step(frames, number) if frames else blank_frame
        duration = _segment_duration(step, seconds_per_step)
        segments.append(Segment(image, cursor, cursor + duration, "step", step))
        cursor = segments[-1].end
    final_image = segments[-1].image
    segments.append(Segment(final_image, cursor, cursor + 2.6, "outcome"))
    return segments


def _ass_time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    whole_seconds, fraction = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{whole_seconds:02d}.{fraction:02d}"


def _ass_escape(text: str) -> str:
    return (
        text.replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\n", r"\N")
    )


def _dialogue(
    layer: int,
    start: float,
    end: float,
    style: str,
    text: str,
    *,
    allow_override_tags: bool = False,
) -> str:
    rendered_text = text if allow_override_tags else _ass_escape(text)
    return (
        f"Dialogue: {layer},{_ass_time(start)},{_ass_time(end)},{style},"
        f",0,0,0,,{rendered_text}"
    )


def _outcome_text(result: dict[str, Any]) -> tuple[str, str]:
    outcome = str(result.get("outcome") or "unknown")
    provider_error_detail = result.get("provider_error_detail")
    labels = {
        "passed": ("OutcomePass", "PASS"),
        "failed": ("OutcomeFail", "FAIL"),
        "model_api_error": ("OutcomeError", "MODEL API ERROR · excluded from pass/fail"),
        "infrastructure_error": ("OutcomeError", "INFRASTRUCTURE ERROR · invalid benchmark outcome"),
        "incomplete_artifacts": ("OutcomeError", "INCOMPLETE ARTIFACTS · invalid benchmark outcome"),
        "missing_verdict": ("OutcomeError", "MISSING VERDICT · invalid benchmark outcome"),
    }
    style, label = labels.get(outcome, ("OutcomeError", outcome.replace("_", " ").upper()))
    if outcome == "model_api_error" and provider_error_detail == "safety_block":
        label = "PROVIDER SAFETY BLOCK · excluded from pass/fail"
    elif outcome == "model_api_error" and provider_error_detail == "candidate_exhausted":
        label = "MODEL RESPONSE EXHAUSTED · excluded from pass/fail"
    elif outcome == "model_api_error" and provider_error_detail == "request_error":
        label = "MODEL REQUEST ERROR · excluded from pass/fail"
    score = result.get("verifier_score")
    if score is not None and outcome in {"passed", "failed"}:
        label += f" · verifier score {score}"
    return style, f"RECORDED OUTCOME · {label}"


def _ass_document(
    *,
    title: str,
    task_id: str,
    model: str,
    result: dict[str, Any],
    segments: list[Segment],
    steps_total: int,
) -> str:
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {OUTPUT_WIDTH}",
        f"PlayResY: {OUTPUT_HEIGHT}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        "Style: Header,Arial,22,&H00EEEBDD,&H00FFFFFF,&HCC000000,&HAA050807,1,0,0,0,100,100,1,0,3,8,0,7,26,26,24,1",
        "Style: Intro,Arial,34,&H00F4F7E8,&H00FFFFFF,&H60050807,&H60050807,1,0,0,0,100,100,0,0,3,18,0,5,120,120,0,1",
        "Style: Action,Arial,25,&H00F4F7E8,&H00FFFFFF,&HFF050807,&HDD050807,1,0,0,0,100,100,0,0,3,14,0,2,75,75,36,1",
        "Style: Pointer,Arial,58,&H0054FFD7,&H00FFFFFF,&HFF000000,&H00000000,1,0,0,0,100,100,0,0,1,5,0,5,0,0,0,1",
        "Style: DragStart,Arial,52,&H005B9BFF,&H00FFFFFF,&HFF000000,&H00000000,1,0,0,0,100,100,0,0,1,5,0,5,0,0,0,1",
        "Style: DragEnd,Arial,52,&H0054FFD7,&H00FFFFFF,&HFF000000,&H00000000,1,0,0,0,100,100,0,0,1,5,0,5,0,0,0,1",
        "Style: OutcomePass,Arial,38,&H0054FFD7,&H00FFFFFF,&HFF050807,&HE6050807,1,0,0,0,100,100,0,0,3,20,0,5,100,100,0,1",
        "Style: OutcomeFail,Arial,38,&H006F6BFF,&H00FFFFFF,&HFF050807,&HE6050807,1,0,0,0,100,100,0,0,3,20,0,5,100,100,0,1",
        "Style: OutcomeError,Arial,35,&H0067A0FF,&H00FFFFFF,&HFF050807,&HE6050807,1,0,0,0,100,100,0,0,3,20,0,5,100,100,0,1",
        "",
        "[Events]",
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ]
    total_end = segments[-1].end
    lines.append(
        _dialogue(
            1,
            0,
            total_end,
            "Header",
            f"GEMINI ATTEMPT REPLAY  ·  {task_id}  ·  {model}",
        )
    )
    intro = segments[0]
    lines.append(
        _dialogue(
            1,
            intro.start,
            intro.end,
            "Intro",
            f"{title}\n\nEXACT SAVED TRAJECTORY · {steps_total} MODEL STEPS\n"
            "Accelerated per-step replay — not continuous screen recording",
        )
    )
    step_index = 0
    for segment in segments:
        if segment.kind != "step" or segment.step is None:
            continue
        step_index += 1
        action = describe_action(segment.step)
        intent = _compact(segment.step.get("intent"), 175)
        caption = f"STEP {step_index:03d}/{steps_total:03d}  ·  {action}"
        if intent:
            caption += f"\nIntent: {intent}"
        lines.append(_dialogue(1, segment.start, segment.end, "Action", caption))
        for x, y, marker_kind in _pointer_points(segment.step):
            x = min(max(x, 0), OUTPUT_WIDTH - 1)
            y = min(max(y, 0), OUTPUT_HEIGHT - 1)
            style = {
                "drag_start": "DragStart",
                "drag_end": "DragEnd",
            }.get(marker_kind, "Pointer")
            symbol = {"drag_start": "S", "drag_end": "E"}.get(marker_kind, "+")
            marker = rf"{{\pos({x},{y})}}{symbol}"
            lines.append(
                _dialogue(
                    2,
                    segment.start,
                    segment.end,
                    style,
                    marker,
                    allow_override_tags=True,
                )
            )
    outcome = segments[-1]
    style, text = _outcome_text(result)
    lines.append(_dialogue(3, outcome.start, outcome.end, style, text))
    return "\n".join(lines) + "\n"


def _ffconcat_path(path: Path) -> str:
    return path.resolve().as_posix().replace("'", r"'\''")


def _write_ffconcat(path: Path, segments: Iterable[Segment]) -> None:
    segments = list(segments)
    lines = ["ffconcat version 1.0"]
    for segment in segments:
        lines.append(f"file '{_ffconcat_path(segment.image)}'")
        lines.append(f"duration {segment.end - segment.start:.6f}")
    lines.append(f"file '{_ffconcat_path(segments[-1].image)}'")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _ass_filter_path(path: Path) -> str:
    value = path.resolve().as_posix()
    for source, replacement in (("\\", r"\\"), (":", r"\:"), ("'", r"\'"), (",", r"\,")):
        value = value.replace(source, replacement)
    return value


def _make_blank_frame(path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x090d0b:s={OUTPUT_WIDTH}x{OUTPUT_HEIGHT}",
            "-frames:v",
            "1",
            str(path),
        ],
        check=True,
    )


def _render_video(
    concat_path: Path,
    ass_path: Path,
    output_path: Path,
    *,
    duration: float,
    fps: int,
) -> None:
    filters = (
        f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=0x090d0b,"
        f"ass=filename='{_ass_filter_path(ass_path)}'"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-vf",
            filters,
            "-an",
            "-t",
            f"{duration:.6f}",
            "-r",
            str(fps),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output_path),
        ],
        check=True,
    )


def _probe(path: Path) -> dict[str, Any]:
    process = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "format=duration,size:stream=codec_name,width,height,avg_frame_rate,pix_fmt",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(process.stdout)
    stream = payload["streams"][0]
    return {
        "duration_seconds": round(float(payload["format"]["duration"]), 3),
        "bytes": int(payload["format"]["size"]),
        "codec": stream["codec_name"],
        "pixel_format": stream["pix_fmt"],
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "frame_rate": stream["avg_frame_rate"],
    }


def _load_trajectory(run_dir: Path | None) -> tuple[list[dict[str, Any]], dict[int, Path]]:
    if run_dir is None:
        return [], {}
    trajectory_path = run_dir / "trajectory.json"
    trajectory = json.loads(trajectory_path.read_text(encoding="utf-8")) if trajectory_path.exists() else {}
    steps = trajectory.get("steps") if isinstance(trajectory, dict) else []
    if not isinstance(steps, list):
        steps = []
    return [step for step in steps if isinstance(step, dict)], observation_frames(run_dir)


def _verifier_feedback(run_dir: Path | None) -> str | None:
    if run_dir is None or not (run_dir / "info.pkl").exists():
        return None
    try:
        with (run_dir / "info.pkl").open("rb") as stream:
            info = pickle.load(stream)
    except Exception:
        return None
    verifier = info.get("verifier") if isinstance(info, dict) else None
    feedback = verifier.get("feedback") if isinstance(verifier, dict) else None
    return str(feedback) if feedback is not None else None


def _provider_error_detail(log_path: Path | None) -> str | None:
    if log_path is None or not log_path.exists():
        return None
    text = log_path.read_text(encoding="utf-8", errors="replace")
    if "BlockedReason.SAFETY" in text:
        return "safety_block"
    if "[gemini-cu] generate_content error:" in text:
        return "request_error"
    if "[gemini-cu] no candidate retries exhausted" in text:
        return "candidate_exhausted"
    return None


def _write_markdown_index(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Gemini starred-task attempt replays",
        "",
        REPLAY_DISCLOSURE,
        "",
        "| # | Task | Outcome | Steps | Replay |",
        "|---:|---|---|---:|---|",
    ]
    for item in payload["videos"]:
        relative = Path(item["video"]).name
        lines.append(
            f"| {item['index']} | {item['title']} | {item['outcome']} | "
            f"{item['trajectory_steps']} | [{relative}]({relative}) |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    if args.seconds_per_step <= 0:
        raise ValueError("--seconds-per-step must be positive")
    if args.fps <= 0:
        raise ValueError("--fps must be positive")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("ffmpeg and ffprobe are required")

    manifest_path = args.manifest.resolve()
    summary_path = args.summary.resolve()
    manifest = load_manifest(manifest_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("experiment_id") != manifest.get("experiment_id"):
        raise ValueError("summary experiment does not match manifest")
    if summary.get("finished_at_utc") is None:
        raise ValueError("refusing to render an unfinished evaluation summary")

    wanted = set(args.task_id or [])
    results = [
        result
        for result in summary.get("results", [])
        if isinstance(result, dict) and (not wanted or result.get("task_id") in wanted)
    ]
    if wanted - {str(result.get("task_id")) for result in results}:
        raise ValueError(f"unknown requested task IDs: {sorted(wanted - {str(result.get('task_id')) for result in results})}")

    task_by_spec = {task["task_spec_id"]: task for task in manifest["tasks"]}
    args.out_dir.mkdir(parents=True, exist_ok=True)
    generated: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="gemini-attempt-replay-") as temporary_name:
        temporary = Path(temporary_name)
        blank_frame = temporary / "blank.png"
        _make_blank_frame(blank_frame)
        for result in results:
            index = int(result["index"])
            task_id = str(result["task_id"])
            task = task_by_spec.get(result.get("task_spec_id"), {})
            title = str(result.get("title") or task.get("title") or task_id)
            run_dir_value = result.get("run_dir")
            run_dir = (REPO_ROOT / run_dir_value).resolve() if run_dir_value else None
            log_value = result.get("log")
            log_path = (REPO_ROOT / log_value).resolve() if log_value else None
            provider_error_detail = _provider_error_detail(log_path)
            rendered_result = {**result, "provider_error_detail": provider_error_detail}
            steps, frames = _load_trajectory(run_dir)
            for frame in frames.values():
                if _png_dimensions(frame) != (OUTPUT_WIDTH, OUTPUT_HEIGHT):
                    raise ValueError(f"saved observation is not 1920x1080: {frame}")
            segments = build_segments(frames, steps, blank_frame, args.seconds_per_step)

            stem = f"{index:02d}-{task_id}-gemini-attempt-replay"
            output_path = args.out_dir / f"{stem}.mp4"
            if output_path.exists() and not args.overwrite:
                raise FileExistsError(f"refusing to overwrite {output_path}")
            task_temp = temporary / stem
            task_temp.mkdir()
            concat_path = task_temp / "frames.ffconcat"
            ass_path = task_temp / "annotations.ass"
            _write_ffconcat(concat_path, segments)
            ass_path.write_text(
                _ass_document(
                    title=title,
                    task_id=task_id,
                    model=str(manifest["protocol"]["model"]),
                    result=rendered_result,
                    segments=segments,
                    steps_total=len(steps),
                ),
                encoding="utf-8",
            )
            print(f"[{index}/{len(summary['results'])}] rendering {title}", flush=True)
            _render_video(
                concat_path,
                ass_path,
                output_path,
                duration=segments[-1].end,
                fps=args.fps,
            )
            probe = _probe(output_path)
            if (
                probe["codec"] != "h264"
                or probe["pixel_format"] != "yuv420p"
                or probe["width"] != OUTPUT_WIDTH
                or probe["height"] != OUTPUT_HEIGHT
            ):
                raise AssertionError(f"invalid replay encoding: {probe}")
            generated.append(
                {
                    "index": index,
                    "task_id": task_id,
                    "task_spec_id": result.get("task_spec_id"),
                    "title": title,
                    "outcome": result.get("outcome"),
                    "verifier_passed": result.get("verifier_passed"),
                    "verifier_score": result.get("verifier_score"),
                    "verifier_feedback": _verifier_feedback(run_dir),
                    "provider_error_detail": provider_error_detail,
                    "trajectory_steps": len(steps),
                    "saved_observation_frames": len(frames),
                    "source_run_dir": run_dir_value,
                    "source_log": result.get("log"),
                    "video": _recorded_path(output_path),
                    "sha256": _sha256(output_path),
                    "probe": probe,
                    "disclosure": REPLAY_DISCLOSURE,
                }
            )

    index_payload = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment_id": manifest["experiment_id"],
        "model": manifest["protocol"]["model"],
        "manifest": _recorded_path(manifest_path),
        "summary": _recorded_path(summary_path),
        "disclosure": REPLAY_DISCLOSURE,
        "videos": generated,
    }
    index_path = args.out_dir / "index.json"
    index_path.write_text(json.dumps(index_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_markdown_index(args.out_dir / "index.md", index_payload)
    print(f"Rendered {len(generated)} replays; index: {index_path}", flush=True)


if __name__ == "__main__":
    main()
