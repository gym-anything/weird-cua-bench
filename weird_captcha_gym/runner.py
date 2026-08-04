"""WeirdCaptchaRunner: the Weird CUA world party for Gym-Anything.

This runner composes an inner VM runner (avf, qemu, docker, ...) resolved
through the Gym-Anything runner registry and owns every benchmark-specific
behavior that previously lived in the evaluation control layer:

- the puzzle clock (live/paused), driven through the in-guest time
  controller, exposed to core via ``supports_time_control`` and forwarded
  ``{"action": "time", "command": ...}`` action payloads;
- frame-window observations (the ``frame_window`` modality), captured by
  the in-guest observation script and returned through the standard
  ``capture_observation`` door;
- guest configuration (``WEIRD_CAPTCHA_*`` variables) derived from
  ``EnvSpec.runner_options`` and the episode seed;
- benchmark artifact collection into the episode directory.

Core never learns any of this: it forwards the modality, the actions, and
the options untouched. The inner runner never learns it either: it sees a
spec whose ``frame_window`` entry is rewritten to ``rgb_screen`` so display
geometry is configured exactly as before.
"""

from __future__ import annotations

import copy
import json
import logging
import shlex
import time
from pathlib import Path
from typing import Any, Dict, Optional

from gym_anything.runtime.runners import registry as runner_registry
from gym_anything.runtime.runners.base import BaseRunner
from gym_anything.specs import EnvSpec

logger = logging.getLogger(__name__)

FRAME_WINDOW_TYPE = "frame_window"

TIME_CONTROL_SCRIPT = "/workspace/shared_scripts/time_control.py"
CAPTURE_SCRIPT = "/workspace/shared_scripts/capture_observation_window.py"
GUEST_OBSERVATION_ROOT = "/tmp/weird_cua_observations"

TIME_COMMANDS = {"status", "wait-ready", "pause", "settle-pause", "resume"}
TIME_MODES = {"live", "paused"}

COLLECTABLE_ARTIFACTS = {
    "current_task.json": "/tmp/weird_captcha_gym/current_task.json",
    "public_state.json": "/tmp/weird_captcha_gym/public_state.json",
    "parallel_grillmaster_witness_ledger.json": (
        "/tmp/weird_captcha_gym/parallel_grillmaster_witness_ledger.json"
    ),
    "parallel_grillmaster_witness_clock.json": (
        "/tmp/weird_captcha_gym/parallel_grillmaster_witness_clock.json"
    ),
    "slot_reel_witness_ledger.json": (
        "/tmp/weird_captcha_gym/slot_reel_witness_ledger.json"
    ),
    "slot_reel_witness_clock.json": (
        "/tmp/weird_captcha_gym/slot_reel_witness_clock.json"
    ),
}

_ALLOWED_OPTIONS = {
    "inner",
    "time_mode",
    "start_paused",
    "challenge_seed",
    "observation_window_ms",
    "frames_per_observation",
    "play_time_seconds",
}


def guest_json(env: Any, arguments: list) -> Dict[str, Any]:
    """Run a guest command through the environment's runner, parse the last
    JSON object line. Kept for evidence and probe tools that drive captures
    explicitly; evaluation itself goes through the runner's own methods."""
    command = " ".join(shlex.quote(str(part)) for part in arguments)
    output = env.runner.exec_capture(command)
    for line in reversed(output.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise RuntimeError(f"guest command returned no JSON object: {output}")


def capture_observation_window(
    env: Any,
    *,
    mode: str,
    duration_ms: int,
    frames_per_observation: int,
    turn: int,
    host_dir: Path,
    hold_paused: bool = False,
) -> Dict[str, Any]:
    """Explicit window capture for evidence and probe tools.

    ``hold_paused`` records the scheduled frame sequence during a frozen
    paused-mode hold instead of advancing the task. Evaluation does not call
    this; ``WeirdCaptchaRunner.capture_observation`` owns the schedule.
    """
    if mode not in TIME_MODES:
        raise ValueError(f"unsupported time mode: {mode}")
    if hold_paused and mode != "paused":
        raise ValueError("hold_paused is valid only for paused observations")
    if duration_ms < 0:
        raise ValueError("duration_ms must be non-negative")
    if frames_per_observation < 1:
        raise ValueError("frames_per_observation must be positive")
    if turn < 0:
        raise ValueError("turn must be non-negative")

    host_dir = host_dir.resolve()
    guest_dir = f"{GUEST_OBSERVATION_ROOT}/turn-{turn:04d}"
    command = [
        "python3",
        CAPTURE_SCRIPT,
        "--mode",
        mode,
        "--duration-ms",
        str(duration_ms),
        "--frames",
        str(frames_per_observation),
        "--output-dir",
        guest_dir,
    ]
    if hold_paused:
        command.append("--hold-paused")
    manifest = guest_json(env, command)

    host_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for index, frame in enumerate(manifest["frames"]):
        host_path = host_dir / f"frame-{index:03d}.png"
        env.runner.copy_from(frame["path"], str(host_path))
        frames.append(
            {
                "path": str(host_path),
                "offset_ms": frame["offset_ms"],
                "target_offset_ms": frame["target_offset_ms"],
            }
        )

    manifest_path = host_dir / "guest-capture-manifest.json"
    env.runner.copy_from(f"{guest_dir}/manifest.json", str(manifest_path))
    time_status = manifest["time_status"]
    resolution = manifest.get("resolution")
    if (
        not isinstance(resolution, list)
        or len(resolution) != 2
        or not all(isinstance(value, int) and value > 0 for value in resolution)
    ):
        raise RuntimeError(f"capture returned an invalid resolution: {resolution!r}")
    configured_resolution = list(env.env_spec.observation[0].resolution)
    if resolution != configured_resolution:
        raise RuntimeError(
            "capture resolution does not match the environment: "
            f"captured {resolution}, configured {configured_resolution}"
        )
    return {
        "screen": {
            "path": frames[-1]["path"],
            "format": "png",
            "resolution": resolution,
        },
        "frames": frames,
        "capture_manifest": str(manifest_path),
        "time": {
            "mode": mode,
            "task_time_ms": time_status.get("task_time_ms"),
            "observation_window_ms": duration_ms,
            "frames_per_observation": frames_per_observation,
        },
    }


def _inner_spec_for(spec: EnvSpec) -> EnvSpec:
    """The spec view the inner VM runner receives.

    The outer spec declares ``frame_window`` so core delegates observation
    capture to this runner. The inner runner still needs ``rgb_screen`` to
    configure display geometry (resolution, fps), so the entry is rewritten
    in its copy.
    """
    inner = copy.deepcopy(spec)
    for entry in inner.observation:
        if entry.type == FRAME_WINDOW_TYPE:
            entry.type = "rgb_screen"
    return inner


class WeirdCaptchaRunner(BaseRunner):
    """Composing world runner for Weird CUA puzzle environments."""

    def __init__(self, spec: EnvSpec):
        super().__init__(spec)
        options = spec.runner_options or {}
        # The base preset injects an rgb_screen observation, and the preset
        # merge keeps it alongside frame_window. This world owns the screen
        # through its frame windows, so it declines core's per-step
        # screenshot convenience by removing the merged-in entry. Otherwise
        # core would deliver its own stale "screen" ahead of the window's
        # final frame.
        if any(entry.type == FRAME_WINDOW_TYPE for entry in spec.observation):
            spec.observation[:] = [
                entry for entry in spec.observation if entry.type != "rgb_screen"
            ]
        self._inner_spec = _inner_spec_for(spec)
        inner_ref = options.get("inner")
        if inner_ref:
            ref = inner_ref if runner_registry.is_locator(inner_ref) else inner_ref.lower()
            inner_cls = runner_registry.resolve_runner_class(ref, self._inner_spec)
            if inner_cls is None:
                raise runner_registry.RunnerRegistryError(
                    f"runner_options.inner {inner_ref!r} does not resolve to a runner"
                )
        else:
            inner_cls = runner_registry.autodetect_runner_class(self._inner_spec)
        if inner_cls is type(self):
            raise runner_registry.RunnerRegistryError(
                "runner_options.inner must name the VM runner, not weird_captcha itself"
            )
        self.inner: BaseRunner = inner_cls(self._inner_spec)
        logger.info("WeirdCaptchaRunner wraps %s", type(self.inner).__name__)

        self._context: Dict[str, Any] = {}
        self._turn = 0
        self._ready = False
        self._live_started = False
        self._clock_running = False
        self.last_time_status: Dict[str, Any] = {}
        self.last_action_result: Optional[Dict[str, Any]] = None
        # Ordered (command, result) clock transitions for this episode, so
        # callers can read e.g. the settle-pause result of the last turn
        # without an extra guest roundtrip.
        self.clock_log: list = []

    # --- class-level facts ------------------------------------------------

    @classmethod
    def validate_options(cls, spec: EnvSpec) -> list:
        options = spec.runner_options or {}
        errors = [
            f"unknown runner_options key: {key!r}"
            for key in options
            if key not in _ALLOWED_OPTIONS
        ]
        mode = options.get("time_mode")
        if mode is not None and mode not in TIME_MODES:
            errors.append(f"time_mode must be one of {sorted(TIME_MODES)}, got {mode!r}")
        inner = options.get("inner")
        if inner is not None and not runner_registry.is_known_reference(str(inner)):
            errors.append(f"runner_options.inner {inner!r} is not a known runner reference")
        for key in ("observation_window_ms", "frames_per_observation", "play_time_seconds"):
            value = options.get(key)
            if value is None:
                continue
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                errors.append(f"{key} must be a non-negative integer, got {value!r}")
        frames = options.get("frames_per_observation")
        if frames is not None and frames < 1:
            errors.append("frames_per_observation must be positive")
        seed = options.get("challenge_seed")
        if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool)):
            errors.append(f"challenge_seed must be an integer, got {seed!r}")
        start_paused = options.get("start_paused")
        if start_paused is not None and not isinstance(start_paused, bool):
            errors.append(f"start_paused must be a boolean, got {start_paused!r}")
        return errors

    @classmethod
    def doctor_status(cls) -> Dict[str, Any]:
        # This wrapper has no host dependencies of its own; the inner VM
        # runner's probe (avf, qemu, docker) covers the host. A non-empty
        # reason means unavailable by convention, so it stays None here.
        return {"available": True, "reason": None, "deps": {}}

    @classmethod
    def platform_priority(cls) -> int:
        return 0

    @classmethod
    def autodetect_eligible(cls, spec=None) -> bool:
        return False

    # --- option accessors -------------------------------------------------

    @property
    def time_mode(self) -> str:
        return (self.spec.runner_options or {}).get("time_mode", "paused")

    @property
    def observation_window_ms(self) -> int:
        value = (self.spec.runner_options or {}).get("observation_window_ms")
        if value is None:
            raise ValueError("runner_options.observation_window_ms is required to capture")
        return int(value)

    @property
    def frames_per_observation(self) -> int:
        value = (self.spec.runner_options or {}).get("frames_per_observation")
        if value is None:
            raise ValueError("runner_options.frames_per_observation is required to capture")
        return int(value)

    # --- episode participation -------------------------------------------

    def on_episode_start(self, context: Dict[str, Any]) -> None:
        self._context = dict(context)
        if self._context.get("episode_dir"):
            # Frame paths travel to remote clients that fetch them by this
            # string; a cwd-relative episode dir would not survive the trip.
            self._context["episode_dir"] = str(
                Path(self._context["episode_dir"]).resolve()
            )
        self._turn = 0
        self._ready = False
        self._live_started = False
        self._clock_running = False
        self.last_time_status = {}
        self.last_action_result = None
        self.clock_log = []

        options = self.spec.runner_options or {}
        guest_env: Dict[str, str] = {
            "WEIRD_CAPTCHA_TIME_MODE": self.time_mode,
            "WEIRD_CAPTCHA_START_PAUSED": (
                "1" if options.get("start_paused", True) else "0"
            ),
        }
        seed = options.get("challenge_seed", context.get("seed"))
        if seed is not None:
            guest_env["WEIRD_CAPTCHA_CHALLENGE_SEED"] = str(seed)
            guest_env["SEED"] = str(seed)
        for spec in (self.spec, self._inner_spec):
            spec.security.resolved_env.update(guest_env)
        self.inner.on_episode_start(context)

    def supports_time_control(self) -> bool:
        return True

    # --- the clock --------------------------------------------------------

    def _guest_json(self, arguments: list) -> Dict[str, Any]:
        command = " ".join(shlex.quote(str(part)) for part in arguments)
        output = self.inner.exec_capture(command)
        for line in reversed(output.splitlines()):
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
        raise RuntimeError(f"guest command returned no JSON object: {output}")

    def time_command(self, command: str) -> Dict[str, Any]:
        if command not in TIME_COMMANDS:
            raise ValueError(f"unsupported time command: {command}")
        result = self._guest_json(
            ["python3", TIME_CONTROL_SCRIPT, command, "--timeout", "30"]
        )
        if command == "resume":
            self._clock_running = True
        elif command in ("pause", "settle-pause"):
            self._clock_running = False
        self.last_time_status = result
        self.clock_log.append({"command": command, "result": result})
        return result

    def _ensure_ready(self) -> None:
        if not self._ready:
            self.time_command("wait-ready")
            self._ready = True

    def _ensure_live_started(self) -> None:
        if self.time_mode == "live" and not self._live_started:
            self.time_command("resume")
            self._live_started = True

    # --- actions ----------------------------------------------------------

    def inject_action(self, action: Dict[str, Any]):
        kind = action.get("action") if isinstance(action, dict) else None
        if kind == "time":
            self._ensure_ready()
            result = self.time_command(str(action.get("command")))
            self.last_action_result = result
            # Returned dicts surface in env.step info["world_action_results"],
            # locally and over the remote wire.
            return result
        if kind == "wait":
            seconds = float(action.get("time", 1.0))
            self._ensure_ready()
            if self.time_mode == "live":
                self._ensure_live_started()
            elif not self._clock_running:
                self.time_command("resume")
            time.sleep(seconds)
            return
        self._ensure_ready()
        if self.time_mode == "live":
            self._ensure_live_started()
        elif not self._clock_running:
            # First real input of this turn: run the clock so the world can
            # respond. The next observation settles it back to paused.
            self.time_command("resume")
        self.inner.inject_action(action)

    # --- observations -----------------------------------------------------

    def capture_observation(self) -> Dict[str, Any]:
        if not self._context.get("episode_dir"):
            raise RuntimeError("no episode context; capture requires on_episode_start")
        self._ensure_ready()
        settle_status = None
        if self.time_mode == "live":
            self._ensure_live_started()
        elif self._clock_running:
            # A task may have an accepted finite transition (for example, a
            # room rotation) still in flight. The shared controller pauses
            # only after such registered actions settle, so the next turn
            # cannot silently lose its input to a frozen action lock.
            settle_status = self.time_command("settle-pause")

        turn = self._turn
        guest_dir = f"{GUEST_OBSERVATION_ROOT}/turn-{turn:04d}"
        manifest = self._guest_json(
            [
                "python3",
                CAPTURE_SCRIPT,
                "--mode",
                self.time_mode,
                "--duration-ms",
                str(self.observation_window_ms),
                "--frames",
                str(self.frames_per_observation),
                "--output-dir",
                guest_dir,
            ]
        )

        host_dir = Path(self._context["episode_dir"]) / "observations" / f"turn-{turn:04d}"
        host_dir.mkdir(parents=True, exist_ok=True)
        frames = []
        for index, frame in enumerate(manifest["frames"]):
            host_path = host_dir / f"frame-{index:03d}.png"
            self.inner.copy_from(frame["path"], str(host_path))
            frames.append(
                {
                    "path": str(host_path),
                    "offset_ms": frame["offset_ms"],
                    "target_offset_ms": frame["target_offset_ms"],
                }
            )
        manifest_path = host_dir / "guest-capture-manifest.json"
        self.inner.copy_from(f"{guest_dir}/manifest.json", str(manifest_path))

        resolution = manifest.get("resolution")
        if (
            not isinstance(resolution, list)
            or len(resolution) != 2
            or not all(isinstance(value, int) and value > 0 for value in resolution)
        ):
            raise RuntimeError(f"capture returned an invalid resolution: {resolution!r}")
        configured = next(
            (
                list(entry.resolution)
                for entry in self.spec.observation
                if entry.type == FRAME_WINDOW_TYPE and entry.resolution
            ),
            None,
        )
        if configured is not None and resolution != configured:
            raise RuntimeError(
                "capture resolution does not match the environment: "
                f"captured {resolution}, configured {configured}"
            )

        time_status = manifest["time_status"]
        self.last_time_status = time_status
        self._turn += 1
        return {
            "screen": {
                "path": frames[-1]["path"],
                "format": "png",
                "resolution": resolution,
            },
            "frames": frames,
            "capture_manifest": str(manifest_path),
            "time": {
                "mode": self.time_mode,
                "task_time_ms": time_status.get("task_time_ms"),
                "observation_window_ms": self.observation_window_ms,
                "frames_per_observation": self.frames_per_observation,
            },
            # Raw clock reports for callers that need them without another
            # guest roundtrip (they also cross the remote wire this way):
            # the post-window status, and the settle-pause result when this
            # capture settled a running paused-mode clock.
            "time_status": time_status,
            "settle_status": settle_status,
        }

    # --- artifacts --------------------------------------------------------

    def collect_artifacts(self) -> None:
        episode_dir = self._context.get("episode_dir")
        if not episode_dir:
            return
        for name, guest_path in COLLECTABLE_ARTIFACTS.items():
            try:
                present = self.inner.exec_capture(
                    f"test -s {shlex.quote(guest_path)} && echo present"
                )
                if "present" not in present.split():
                    continue
                self.inner.copy_from(guest_path, str(Path(episode_dir) / name))
            except Exception:
                continue

    # --- lifecycle delegation ---------------------------------------------

    def start(self, seed: Optional[int] = None) -> None:
        self.inner.start(seed)

    def stop(self) -> None:
        try:
            self.collect_artifacts()
        except Exception:
            logger.warning("Could not collect Weird CUA artifacts", exc_info=True)
        finally:
            self.inner.stop()

    def run_reset(self, reset_script: str, seed: Optional[int] = None) -> None:
        self.inner.run_reset(reset_script, seed)

    def run_task_init(self, init_script: str) -> None:
        self.inner.run_task_init(init_script)

    def run_hook(self, command: str, *, stage: str,
                 timeout: Optional[int] = None, use_pty: bool = True) -> int:
        return self.inner.run_hook(command, stage=stage, timeout=timeout, use_pty=use_pty)

    def set_reporter(self, reporter) -> None:
        super().set_reporter(reporter)
        self.inner.set_reporter(reporter)

    def set_fast_io(self, enabled: bool) -> None:
        super().set_fast_io(enabled)
        self.inner.set_fast_io(enabled)

    # --- capability queries (owned by the inner world) ----------------------

    def supports_live_recording(self) -> bool:
        return self.inner.supports_live_recording()

    def supports_checkpoint_caching(self) -> bool:
        return self.inner.supports_checkpoint_caching()

    def supports_savevm(self) -> bool:
        return self.inner.supports_savevm()

    def supports_fast_io(self) -> bool:
        return self.inner.supports_fast_io()

    def acks_input_delivery(self) -> bool:
        return self.inner.acks_input_delivery()

    def get_platform_family(self):
        return self.inner.get_platform_family()

    def get_runtime_info(self):
        return self.inner.get_runtime_info()

    # --- guest access delegation -------------------------------------------

    def exec(self, cmd: str, env: Optional[Dict[str, str]] = None,
             user: Optional[str] = None, use_pty: bool = True, timeout: int = 600) -> int:
        return self.inner.exec(cmd, env=env, user=user, use_pty=use_pty, timeout=timeout)

    def exec_async(self, cmd: str, env: Optional[Dict[str, str]] = None, stdout=None, stderr=None):
        return self.inner.exec_async(cmd, env=env, stdout=stdout, stderr=stderr)

    def exec_capture(self, cmd: str) -> str:
        return self.inner.exec_capture(cmd)

    def exec_capture_bytes(self, cmd: str) -> bytes:
        return self.inner.exec_capture_bytes(cmd)

    def put_file(self, host_path) -> str:
        return self.inner.put_file(host_path)

    def to_container_path(self, host_path):
        return self.inner.to_container_path(host_path)

    def copy_to(self, host_src: str, container_dst: str) -> None:
        self.inner.copy_to(host_src, container_dst)

    def copy_from(self, container_src: str, host_dst: str) -> None:
        self.inner.copy_from(container_src, host_dst)

    def capture_screenshot(self, host_path) -> bool:
        return self.inner.capture_screenshot(host_path)

    def capture_screenshot_image(self):
        return self.inner.capture_screenshot_image()

    def capture_audio_raw(self, duration_sec: float, rate: int, channels: int) -> bytes:
        return self.inner.capture_audio_raw(duration_sec, rate, channels)

    def capture_ui_tree(self) -> str:
        return self.inner.capture_ui_tree()

    def save_state(self, save_paths) -> str:
        return self.inner.save_state(save_paths)

    def load_state(self, snapshot_container_path: str) -> None:
        self.inner.load_state(snapshot_container_path)

    def set_checkpoint_key(self, cache_level: str, task_id: Optional[str] = None,
                           use_savevm: bool = False) -> None:
        self.inner.set_checkpoint_key(cache_level, task_id=task_id, use_savevm=use_savevm)

    def checkpoint_exists(self) -> bool:
        return self.inner.checkpoint_exists()

    def create_checkpoint(self) -> bool:
        return self.inner.create_checkpoint()

    def start_from_checkpoint(self, seed: Optional[int] = None) -> bool:
        return self.inner.start_from_checkpoint(seed)
