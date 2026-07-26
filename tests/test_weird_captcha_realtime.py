from __future__ import annotations

import json
import os
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from benchmarks.weird_captcha_gym.realtime import (
    RealTimeSettings,
    load_real_time_settings,
    mechanic_id_from_env_dir,
)
from benchmarks.weird_captcha_gym.shared_scripts import capture_observation_window as CAPTURE
from benchmarks.weird_captcha_gym.shared_runtime.server.weird_captcha_server import PuzzleServer


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "weird_captcha_gym"


def request_json(url: str, payload: dict | None = None) -> tuple[int, dict]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"content-type": "application/json"} if body else {},
        method="POST" if body else "GET",
    )
    with urllib.request.urlopen(request) as response:
        return response.status, json.load(response)


def test_every_environment_has_valid_real_time_settings() -> None:
    environment_ids = {
        path.name.removesuffix("_env")
        for path in (BENCHMARK / "environments").glob("*_env")
    }
    configured = json.loads((BENCHMARK / "real_time.json").read_text(encoding="utf-8"))["environments"]
    assert set(configured) == environment_ids
    for mechanic_id in environment_ids:
        assert isinstance(load_real_time_settings(mechanic_id), RealTimeSettings)


def test_existing_control_files_match_canonical_real_time_settings() -> None:
    for path in (BENCHMARK / "environments").glob("*_env/controls.json"):
        mechanic_id = path.parent.name.removesuffix("_env")
        controls = json.loads(path.read_text(encoding="utf-8"))
        assert controls["real_time"] == load_real_time_settings(mechanic_id).__dict__


def test_mechanic_id_comes_from_environment_directory() -> None:
    assert mechanic_id_from_env_dir("/tmp/rotating_keyboard_env") == "rotating_keyboard"


def test_frame_targets_include_both_ends_of_a_window() -> None:
    assert CAPTURE.frame_targets(1000, 600, 4) == [1000, 1200, 1400, 1600]
    assert CAPTURE.frame_targets(1000, 0, 1) == [1000]


def test_frame_selection_uses_nearest_capture_time(tmp_path: Path) -> None:
    paths = []
    for index, timestamp_ms in enumerate((1000, 1100, 1200)):
        path = tmp_path / f"{index}.png"
        path.write_bytes(b"png")
        timestamp_ns = timestamp_ms * 1_000_000
        path.touch()
        os.utime(path, ns=(timestamp_ns, timestamp_ns))
        paths.append(path)
    assert CAPTURE.select_frames(paths, [1010, 1190]) == [paths[0], paths[2]]


def test_time_control_server_sequences_commands_and_records_status(tmp_path: Path) -> None:
    app_dir = tmp_path / "app"
    state_dir = tmp_path / "state"
    app_dir.mkdir()
    state_dir.mkdir()
    (app_dir / "index.html").write_text("ok", encoding="utf-8")
    PuzzleServer.app_dir = app_dir
    PuzzleServer.state_dir = state_dir
    server = ThreadingHTTPServer(("127.0.0.1", 0), PuzzleServer)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        _, initial = request_json(f"{base}/time-control")
        assert initial == {"command": "status", "sequence": 0}

        _, pause = request_json(f"{base}/time-control", {"command": "pause"})
        _, window = request_json(
            f"{base}/time-control",
            {"command": "run_for", "milliseconds": 500, "start_delay_ms": 50},
        )
        assert pause["sequence"] == 1
        assert window["sequence"] == 2

        request_json(f"{base}/time-control/status", {
            "sequence": 2,
            "state": "paused",
            "phase": "completed",
            "task_time_ms": 500,
        })
        _, current = request_json(f"{base}/time-control")
        _, status = request_json(f"{base}/time-control/status")
        assert current["sequence"] == 2
        assert current["command"] == "pause"
        assert status["phase"] == "completed"
        assert status["task_time_ms"] == 500
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
