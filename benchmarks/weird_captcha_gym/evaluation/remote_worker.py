from __future__ import annotations

import shlex
from pathlib import Path

from flask import jsonify, request
from gym_anything.remote import worker as gym_worker

from .control import (
    COLLECTABLE_ARTIFACTS,
    capture_observation_window,
    time_command,
)
from .remote import WEIRD_CUA_WORKER_CAPABILITY


ALLOWED_ENVIRONMENT_KEYS = {
    "WEIRD_CAPTCHA_TIME_MODE",
    "WEIRD_CAPTCHA_START_PAUSED",
    "WEIRD_CAPTCHA_CHALLENGE_SEED",
    "SEED",
}
ALLOWED_TIME_COMMANDS = {
    "status",
    "wait-ready",
    "pause",
    "settle-pause",
    "resume",
}


def _environment(env_id: str):
    return gym_worker.env_manager.get_environment(env_id)


@gym_worker.app.route("/envs/<env_id>/weird/configure", methods=["POST"])
def configure_environment(env_id: str):
    try:
        env = _environment(env_id)
        payload = request.get_json() or {}
        values = payload.get("environment") or {}
        if not isinstance(values, dict):
            return jsonify({"error": "environment must be an object"}), 400
        unknown = sorted(set(values) - ALLOWED_ENVIRONMENT_KEYS)
        if unknown:
            return jsonify({"error": f"unsupported environment keys: {unknown}"}), 400
        normalized = {str(key): str(value) for key, value in values.items()}
        mode = normalized.get("WEIRD_CAPTCHA_TIME_MODE")
        if mode is not None and mode not in {"live", "paused"}:
            return jsonify({"error": "WEIRD_CAPTCHA_TIME_MODE must be live or paused"}), 400
        start_paused = normalized.get("WEIRD_CAPTCHA_START_PAUSED")
        if start_paused is not None and start_paused not in {"0", "1"}:
            return jsonify({"error": "WEIRD_CAPTCHA_START_PAUSED must be 0 or 1"}), 400
        env.env_spec.security.resolved_env.update(normalized)
        return jsonify({"configured": sorted(normalized)})
    except ValueError as error:
        return jsonify({"error": str(error)}), 404
    except Exception as error:
        gym_worker.logger.error(
            "Error configuring Weird CUA environment %s: %s",
            env_id,
            error,
            exc_info=True,
        )
        return jsonify({"error": str(error)}), 500


@gym_worker.app.route("/envs/<env_id>/weird/time", methods=["POST"])
def control_time(env_id: str):
    try:
        command = str((request.get_json() or {}).get("command") or "")
        if command not in ALLOWED_TIME_COMMANDS:
            return jsonify({"error": f"unsupported time command: {command}"}), 400
        return jsonify({"status": time_command(_environment(env_id), command)})
    except ValueError as error:
        return jsonify({"error": str(error)}), 404
    except Exception as error:
        gym_worker.logger.error(
            "Error controlling Weird CUA clock for %s: %s",
            env_id,
            error,
            exc_info=True,
        )
        return jsonify({"error": str(error)}), 500


@gym_worker.app.route("/envs/<env_id>/weird/capture-window", methods=["POST"])
def capture_window(env_id: str):
    try:
        env = _environment(env_id)
        payload = request.get_json() or {}
        mode = str(payload.get("mode") or "")
        duration_ms = int(payload.get("duration_ms"))
        frames = int(payload.get("frames_per_observation"))
        turn = int(payload.get("turn"))
        hold_paused = bool(payload.get("hold_paused", False))
        if mode not in {"live", "paused"}:
            return jsonify({"error": f"unsupported time mode: {mode}"}), 400
        if duration_ms < 0 or duration_ms > 60_000:
            return jsonify({"error": "duration_ms must be between 0 and 60000"}), 400
        if frames < 1 or frames > 64:
            return jsonify({"error": "frames_per_observation must be between 1 and 64"}), 400
        if turn < 0 or turn > 100_000:
            return jsonify({"error": "turn must be between 0 and 100000"}), 400
        if env.episode_dir is None:
            return jsonify({"error": "environment has no active episode"}), 409
        observation = capture_observation_window(
            env,
            mode=mode,
            duration_ms=duration_ms,
            frames_per_observation=frames,
            turn=turn,
            host_dir=(
                Path(env.episode_dir).resolve()
                / "observations"
                / f"turn-{turn:04d}"
            ),
            hold_paused=hold_paused,
        )
        return jsonify({"observation": observation})
    except (TypeError, ValueError) as error:
        return jsonify({"error": str(error)}), 400
    except Exception as error:
        gym_worker.logger.error(
            "Error capturing Weird CUA frame window for %s: %s",
            env_id,
            error,
            exc_info=True,
        )
        return jsonify({"error": str(error)}), 500


@gym_worker.app.route("/envs/<env_id>/weird/collect-artifacts", methods=["POST"])
def collect_artifacts(env_id: str):
    try:
        env = _environment(env_id)
        if env.episode_dir is None:
            return jsonify({"error": "environment has no active episode"}), 409
        destination_dir = Path(env.episode_dir).resolve() / "weird-collected"
        destination_dir.mkdir(parents=True, exist_ok=True)
        artifacts = {}
        for name, guest_path in COLLECTABLE_ARTIFACTS.items():
            present = env.runner.exec_capture(
                f"test -s {shlex.quote(guest_path)} && echo present"
            )
            if "present" not in present.split():
                continue
            destination = destination_dir / name
            env.runner.copy_from(guest_path, str(destination))
            artifacts[name] = str(destination)
        return jsonify({"artifacts": artifacts})
    except ValueError as error:
        return jsonify({"error": str(error)}), 404
    except Exception as error:
        gym_worker.logger.error(
            "Error collecting Weird CUA artifacts for %s: %s",
            env_id,
            error,
            exc_info=True,
        )
        return jsonify({"error": str(error)}), 500


def main() -> None:
    gym_preflight = gym_worker.run_runner_preflight

    def weird_cua_preflight(*, must_support, skip):
        available = gym_preflight(must_support=must_support, skip=skip)
        return sorted(set(available) | {WEIRD_CUA_WORKER_CAPABILITY})

    gym_worker.run_runner_preflight = weird_cua_preflight
    gym_worker.main()


if __name__ == "__main__":
    main()
