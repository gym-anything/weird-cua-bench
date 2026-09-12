"""Run two real puzzles through an isolated Gym master/worker on a CPU job."""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path

import requests

from gym_anything.remote import RemoteGymEnv
from weird_captcha_gym.evaluation.codex_cli import WeirdCodexActionGateway


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def wait_for(check, processes):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        assert all(process.poll() is None for process in processes), "master/worker exited"
        try:
            if check():
                return
        except requests.RequestException:
            pass
        time.sleep(0.2)
    raise TimeoutError("master/worker did not become ready; inspect the saved logs")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        staging = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="wcb-remote-inputs-")))
        env_dir = Path("weird_captcha_gym/environments/rotating_keyboard_env")
        mounts = json.loads((env_dir / "env.json").read_text())["mounts"]
        for index, mount in enumerate(mounts):
            destination = staging / str(index)
            shutil.copytree(mount["source"], destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
            mount["source"] = str(destination)
        master_port, worker_port = free_port(), free_port()
        master_url = f"http://127.0.0.1:{master_port}"
        commands = [
            [sys.executable, "-u", "-m", "gym_anything.remote.master", "--host", "127.0.0.1", "--port", str(master_port), "--dev"],
            [sys.executable, "-u", "-c",
             "from gym_anything.runtime.runners.registry import register_runner; "
             "from weird_captcha_gym.runner import WeirdCaptchaRunner; "
             "register_runner('weird_captcha', WeirdCaptchaRunner, replace=True); "
             "from gym_anything.remote.worker import main; main()",
             "--host", "127.0.0.1", "--port", str(worker_port), "--master-url", master_url,
             "--max-envs", "2", "--heartbeat-interval", "1", "--advertise-host", "127.0.0.1",
             "--must-support-runner", "weird_captcha,sandweave"],
        ]
        processes = []
        for name, command in zip(("master", "worker"), commands):
            log = stack.enter_context((output / f"{name}.log").open("wb"))
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=os.environ.copy())
            stack.callback(stop, process)
            processes.append(process)
            if name == "master":
                wait_for(lambda: requests.get(master_url + "/health", timeout=2).ok, processes)
        wait_for(lambda: bool(requests.get(master_url + "/workers/list", timeout=2).json().get("workers")), processes)
        workers = requests.get(master_url + "/workers/list", timeout=2).json()
        (output / "workers.json").write_text(json.dumps(workers, indent=2))
        print("Master and Sandweave worker ready", flush=True)

        def episode(mode, seed):
            live = mode != "paused"
            folder = output / mode
            folder.mkdir()
            env = RemoteGymEnv.from_benchmark(
                master_url, "weird_captcha_gym", "rotating_keyboard_env",
                "rotating_keyboard_d3_full_seed_0001", timeout=600, fast_io=True,
                overrides={
                    "mounts": mounts,
                    "runner_options": {"inner": "sandweave", "time_mode": "live" if live else "paused",
                                       "start_paused": True, "frames_per_observation": 1 if live else 6,
                                       "observation_window_ms": 0 if live else 800},
                    "recording": {"enable": True, "output_dir": str(folder)},
                },
            )
            try:
                obs = env.reset(seed=seed)
                assert len(obs["frames"]) == (1 if live else 6)
                session = env.get_session_info()
                assert Path(env.fetch_path(obs["frames"][-1]["path"])).is_file()
                gateway = WeirdCodexActionGateway(env, (1920, 1080), 20, "smoke-only", temporal_mode=mode, timing_path=folder / "timing.jsonl")
                first = gateway.step_from_command('{"action":"screenshot"}')
                assert len(first["screenshots_b64"]) == (1 if live else 6)
                point = [round(1270 / gateway.ratio_x), round(305 / gateway.ratio_y)]
                command = {"actions": [{"mouse": {"left_click": point}}]}
                if live:
                    command["execute_at_s"] = first["timing"]["current_time_s"] + 1.0
                response = gateway.step_from_command(json.dumps(command))
                assert not response.get("error"), response
                if live:
                    assert response["timing"]["action_executed_at_s"] >= command["execute_at_s"] - 0.01
                (folder / "after-click.png").write_bytes(base64.b64decode(response["screenshot_b64"]))
                report = {"mode": mode, "env_id": env.env_id, "sandbox_id": session.instance_name,
                          "episode_dir": session.artifacts_dir, "timing": response.get("timing")}
            finally:
                env.close()
            assert (Path(report["episode_dir"]) / "recording.mp4").stat().st_size > 0
            print(f"PASS remote {mode}", flush=True)
            return report

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda pair: episode(*pair), [("paused", 43), ("live_timestamped_execution", 42)]))
        assert len({result["sandbox_id"] for result in results}) == 2
        (output / "results.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
