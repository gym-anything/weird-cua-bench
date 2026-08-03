from __future__ import annotations

import json
import os
import subprocess
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
from benchmarks.weird_captcha_gym.shared_scripts.setup_task import generate_task_state
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


def test_lidar_real_time_settings_cover_motion_before_the_replay_ceiling() -> None:
    settings = load_real_time_settings("lidar_blacksite")
    assert settings == RealTimeSettings(
        play_time_seconds=90,
        observation_window_ms=500,
        frames_per_observation=5,
    )
    assert CAPTURE.frame_targets(0, settings.observation_window_ms, settings.frames_per_observation) == [
        0,
        125,
        250,
        375,
        500,
    ]

    task_path = (
        BENCHMARK
        / "environments"
        / "lidar_blacksite_env"
        / "tasks"
        / "lidar_blacksite_seed_0001"
        / "task.json"
    )
    public_state, _ = generate_task_state(
        json.loads(task_path.read_text(encoding="utf-8")),
        "lidar-real-time-contract",
    )
    tick_ms = int(public_state["controls"]["tick_ms"])
    maximum_replay_ms = int(public_state["requirements"]["maximum_session_ticks"]) * tick_ms
    assert settings.observation_window_ms == 25 * tick_ms
    assert settings.play_time_seconds * 1000 < maximum_replay_ms

    mechanic_source = (
        BENCHMARK / "shared_runtime" / "app" / "mechanics" / "lidar_blacksite.js"
    ).read_text(encoding="utf-8")
    for environment_time_branch in (
        "time_mode",
        "WEIRD_CAPTCHA_TIME_MODE",
        "WeirdCaptchaTime",
    ):
        assert environment_time_branch not in mechanic_source


def test_consequences_real_time_settings_use_single_frames_for_untimed_memory_actions() -> None:
    settings = load_real_time_settings("consequences_boss")
    assert settings == RealTimeSettings(
        play_time_seconds=180,
        observation_window_ms=0,
        frames_per_observation=1,
    )
    assert CAPTURE.frame_targets(
        0,
        settings.observation_window_ms,
        settings.frames_per_observation,
    ) == [0]

    controls = json.loads(
        (
            BENCHMARK
            / "environments"
            / "consequences_boss_env"
            / "controls.json"
        ).read_text(encoding="utf-8")
    )
    assert controls["real_time"] == settings.__dict__

    mechanic_source = (
        BENCHMARK
        / "shared_runtime"
        / "app"
        / "mechanics"
        / "consequences_boss.js"
    ).read_text(encoding="utf-8")
    assert mechanic_source.count("window.setTimeout") == 1
    assert "window.setTimeout(() => {" in mechanic_source
    assert "OPEN FRESH LEDGER" in mechanic_source
    assert "outcome.state && model.helpers.render(outcome.state), 850" not in mechanic_source
    for environment_time_branch in (
        "time_mode",
        "WEIRD_CAPTCHA_TIME_MODE",
        "WeirdCaptchaTime",
    ):
        assert environment_time_branch not in mechanic_source


def test_fake_desktop_real_time_settings_use_one_static_observation_frame() -> None:
    settings = load_real_time_settings("fake_desktop_automation_inversion")
    assert settings == RealTimeSettings(
        play_time_seconds=150,
        observation_window_ms=0,
        frames_per_observation=1,
    )
    assert CAPTURE.frame_targets(0, settings.observation_window_ms, settings.frames_per_observation) == [0]

    controls = json.loads(
        (
            BENCHMARK
            / "environments"
            / "fake_desktop_automation_inversion_env"
            / "controls.json"
        ).read_text(encoding="utf-8")
    )
    assert controls["real_time"] == settings.__dict__

    mechanic_source = (
        BENCHMARK
        / "shared_runtime"
        / "app"
        / "mechanics"
        / "fake_desktop_automation_inversion.js"
    ).read_text(encoding="utf-8")
    for environment_time_branch in (
        "time_mode",
        "WEIRD_CAPTCHA_TIME_MODE",
        "WeirdCaptchaTime",
    ):
        assert environment_time_branch not in mechanic_source


def test_forced_perspective_uses_one_static_observation_frame() -> None:
    settings = load_real_time_settings("forced_perspective_moving_day")
    assert settings == RealTimeSettings(
        play_time_seconds=180,
        observation_window_ms=0,
        frames_per_observation=1,
    )
    assert CAPTURE.frame_targets(0, settings.observation_window_ms, settings.frames_per_observation) == [0]

    controls = json.loads(
        (
            BENCHMARK
            / "environments"
            / "forced_perspective_moving_day_env"
            / "controls.json"
        ).read_text(encoding="utf-8")
    )
    assert controls["real_time"] == settings.__dict__

    mechanic_source = (
        BENCHMARK
        / "shared_runtime"
        / "app"
        / "mechanics"
        / "forced_perspective_moving_day.js"
    ).read_text(encoding="utf-8")
    assert "movementTick() { if (!model || model.held || model.completed || model.submitting || model.keys.size === 0) return;" in mechanic_source


def test_clockwork_real_time_settings_expose_coupled_phase_motion_through_the_shared_clock() -> None:
    settings = load_real_time_settings("clockwork_clutch_safe")
    assert settings == RealTimeSettings(
        play_time_seconds=180,
        observation_window_ms=600,
        frames_per_observation=5,
    )
    assert CAPTURE.frame_targets(
        0,
        settings.observation_window_ms,
        settings.frames_per_observation,
    ) == [0, 150, 300, 450, 600]

    controls = json.loads(
        (
            BENCHMARK
            / "environments"
            / "clockwork_clutch_safe_env"
            / "controls.json"
        ).read_text(encoding="utf-8")
    )
    assert controls["real_time"] == settings.__dict__

    task_path = (
        BENCHMARK
        / "environments"
        / "clockwork_clutch_safe_env"
        / "tasks"
        / "clockwork_clutch_safe_seed_0001"
        / "task.json"
    )
    public_state, _ = generate_task_state(
        json.loads(task_path.read_text(encoding="utf-8")),
        "clockwork-real-time-contract",
    )
    tick_ms = int(public_state["physics"]["tick_ms"])
    maximum_drive_ms = int(public_state["physics"]["max_ticks"]) * tick_ms
    assert 7 * tick_ms <= settings.observation_window_ms < 8 * tick_ms
    assert settings.play_time_seconds * 1000 > maximum_drive_ms

    mechanic_sources = [
        (
            BENCHMARK
            / "shared_runtime"
            / "app"
            / "mechanics"
            / name
        ).read_text(encoding="utf-8")
        for name in ("clockwork_clutch_safe.js", "_interaction_vii_viii.js")
    ]
    assert "setInterval(tick, state.physics.tick_ms)" in mechanic_sources[1]
    for mechanic_source in mechanic_sources:
        for environment_time_branch in (
            "time_mode",
            "WEIRD_CAPTCHA_TIME_MODE",
            "WeirdCaptchaTime",
        ):
            assert environment_time_branch not in mechanic_source


def test_clockwork_doppelganger_real_time_settings_expose_recorded_motion_without_task_time_branches() -> None:
    settings = load_real_time_settings("clockwork_doppelganger_customs")
    assert settings == RealTimeSettings(
        play_time_seconds=180,
        observation_window_ms=800,
        frames_per_observation=6,
    )
    assert CAPTURE.frame_targets(
        0, settings.observation_window_ms, settings.frames_per_observation
    ) == [0, 160, 320, 480, 640, 800]
    controls = json.loads(
        (
            BENCHMARK
            / "environments"
            / "clockwork_doppelganger_customs_env"
            / "controls.json"
        ).read_text(encoding="utf-8")
    )
    assert controls["real_time"] == settings.__dict__
    source = (
        BENCHMARK
        / "shared_runtime"
        / "app"
        / "mechanics"
        / "clockwork_doppelganger_customs.js"
    ).read_text(encoding="utf-8")
    for environment_time_branch in (
        "time_mode",
        "WEIRD_CAPTCHA_TIME_MODE",
        "WeirdCaptchaTime",
    ):
        assert environment_time_branch not in source


def test_blind_dice_real_time_settings_settle_each_roll_without_redundant_frames() -> None:
    settings = load_real_time_settings("blind_dice_courier")
    assert settings == RealTimeSettings(
        play_time_seconds=120,
        observation_window_ms=400,
        frames_per_observation=1,
    )
    assert CAPTURE.frame_targets(
        0,
        settings.observation_window_ms,
        settings.frames_per_observation,
    ) == [400]

    controls = json.loads(
        (
            BENCHMARK
            / "environments"
            / "blind_dice_courier_env"
            / "controls.json"
        ).read_text(encoding="utf-8")
    )
    assert controls["real_time"] == settings.__dict__

    mechanic_source = (
        BENCHMARK
        / "shared_runtime"
        / "app"
        / "mechanics"
        / "blind_dice_courier.js"
    ).read_text(encoding="utf-8")
    mechanic_styles = (
        BENCHMARK
        / "shared_runtime"
        / "app"
        / "mechanics"
        / "blind_dice_courier.css"
    ).read_text(encoding="utf-8")
    assert "window.setTimeout(submitDelivery, 240)" in mechanic_source
    assert "transition: left .16s" in mechanic_styles
    assert settings.observation_window_ms > 240
    for environment_time_branch in (
        "time_mode",
        "WEIRD_CAPTCHA_TIME_MODE",
        "WeirdCaptchaTime",
    ):
        assert environment_time_branch not in mechanic_source


def test_bomb_manual_real_time_settings_use_one_static_frame_and_shared_clock() -> None:
    settings = load_real_time_settings("bomb_manual_from_hell")
    assert settings == RealTimeSettings(
        play_time_seconds=180,
        observation_window_ms=0,
        frames_per_observation=1,
    )
    assert CAPTURE.frame_targets(
        0,
        settings.observation_window_ms,
        settings.frames_per_observation,
    ) == [0]

    controls = json.loads(
        (
            BENCHMARK
            / "environments"
            / "bomb_manual_from_hell_env"
            / "controls.json"
        ).read_text(encoding="utf-8")
    )
    assert controls["real_time"] == settings.__dict__

    mechanic_source = (
        BENCHMARK
        / "shared_runtime"
        / "app"
        / "mechanics"
        / "bomb_manual_from_hell.js"
    ).read_text(encoding="utf-8")
    for ambient_time_primitive in (
        "requestAnimationFrame(",
        "setInterval(",
        "setTimeout(",
        "Date.now(",
    ):
        assert ambient_time_primitive not in mechanic_source
    assert "performance.now()" in mechanic_source
    for environment_time_branch in (
        "time_mode",
        "WEIRD_CAPTCHA_TIME_MODE",
        "WeirdCaptchaTime",
    ):
        assert environment_time_branch not in mechanic_source


def test_signature_real_time_settings_settle_the_exposed_signature_before_capture() -> None:
    settings = load_real_time_settings("bureaucratic_signature_trap")
    assert settings == RealTimeSettings(
        play_time_seconds=120,
        observation_window_ms=240,
        frames_per_observation=1,
    )
    assert CAPTURE.frame_targets(
        0,
        settings.observation_window_ms,
        settings.frames_per_observation,
    ) == [240]

    controls = json.loads(
        (
            BENCHMARK
            / "environments"
            / "bureaucratic_signature_trap_env"
            / "controls.json"
        ).read_text(encoding="utf-8")
    )
    assert controls["real_time"] == settings.__dict__

    mechanic_source = (
        BENCHMARK
        / "shared_runtime"
        / "app"
        / "mechanics"
        / "bureaucratic_signature_trap.js"
    ).read_text(encoding="utf-8")
    mechanic_styles = (
        BENCHMARK
        / "shared_runtime"
        / "app"
        / "mechanics"
        / "bureaucratic_signature_trap.css"
    ).read_text(encoding="utf-8")
    for ambient_time_primitive in (
        "requestAnimationFrame(",
        "setInterval(",
        "Date.now(",
        "performance.now(",
    ):
        assert ambient_time_primitive not in mechanic_source
    assert mechanic_source.count("window.setTimeout(") == 1
    assert "window.setTimeout(() => outcome.state && model.helpers.render(outcome.state), 850)" in mechanic_source
    assert "@keyframes" not in mechanic_styles
    assert "animation:" not in mechanic_styles
    assert "transition:opacity .18s" in mechanic_styles
    assert settings.observation_window_ms > 180
    for environment_time_branch in (
        "time_mode",
        "WEIRD_CAPTCHA_TIME_MODE",
        "WeirdCaptchaTime",
    ):
        assert environment_time_branch not in mechanic_source


def test_slot_reel_real_time_settings_expose_multiple_symbol_frames_through_the_shared_clock() -> None:
    settings = load_real_time_settings("slot_reel_capture")
    assert settings == RealTimeSettings(
        play_time_seconds=90,
        observation_window_ms=800,
        frames_per_observation=6,
    )
    assert CAPTURE.frame_targets(
        0,
        settings.observation_window_ms,
        settings.frames_per_observation,
    ) == [0, 160, 320, 480, 640, 800]

    controls = json.loads(
        (
            BENCHMARK
            / "environments"
            / "slot_reel_capture_env"
            / "controls.json"
        ).read_text(encoding="utf-8")
    )
    assert controls["real_time"] == settings.__dict__

    app_source = (
        BENCHMARK / "shared_runtime" / "app" / "app.js"
    ).read_text(encoding="utf-8")
    slot_source = app_source[
        app_source.index("function animateSlotReels"):
        app_source.index("function dominoAxisAngle")
    ]
    assert "requestAnimationFrame(animateSlotReels)" in slot_source
    assert "performance.now()" in slot_source
    for environment_time_branch in (
        "time_mode",
        "WEIRD_CAPTCHA_TIME_MODE",
        "WeirdCaptchaTime",
    ):
        assert environment_time_branch not in slot_source


def test_craftcha_real_time_settings_capture_the_transient_recipe_without_task_clock_branches() -> None:
    settings = load_real_time_settings("craftcha_alchemy_bench")
    assert settings == RealTimeSettings(
        play_time_seconds=180,
        observation_window_ms=1200,
        frames_per_observation=8,
    )
    assert CAPTURE.frame_targets(
        0,
        settings.observation_window_ms,
        settings.frames_per_observation,
    ) == [0, 1200 / 7, 2400 / 7, 3600 / 7, 4800 / 7, 6000 / 7, 7200 / 7, 1200]
    controls = json.loads(
        (
            BENCHMARK
            / "environments"
            / "craftcha_alchemy_bench_env"
            / "controls.json"
        ).read_text(encoding="utf-8")
    )
    assert controls["real_time"] == settings.__dict__
    source = (
        BENCHMARK
        / "shared_runtime"
        / "app"
        / "mechanics"
        / "craftcha_alchemy_bench.js"
    ).read_text(encoding="utf-8")
    assert "window.setTimeout" in source
    for environment_time_branch in (
        "time_mode",
        "WEIRD_CAPTCHA_TIME_MODE",
        "WeirdCaptchaTime",
    ):
        assert environment_time_branch not in source


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


def test_authoritative_capture_preserves_the_native_desktop_resolution() -> None:
    source = (BENCHMARK / "shared_scripts" / "capture_observation_window.py").read_text(
        encoding="utf-8"
    )
    assert '"-vf", "scale=' not in source
    assert '"resolution": [width, height]' in source


def test_puzzle_browser_launches_full_screen() -> None:
    source = (BENCHMARK / "shared_scripts" / "open_puzzle_browser.sh").read_text(
        encoding="utf-8"
    )
    assert "--kiosk" in source
    assert "--window-size=" not in source
    assert "fullscreen,maximized_vert,maximized_horz" in source
    assert "xdpyinfo" in source
    assert "wmctrl -lG" in source
    assert "Puzzle browser fullscreen verified" in source
    assert "Puzzle browser fullscreen verification failed" in source
    assert "Reusing existing puzzle browser window" in source


def test_puzzle_browser_requires_the_task_window_and_exact_display_geometry(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()

    def executable(name: str, source: str) -> None:
        path = fake_bin / name
        path.write_text(source, encoding="utf-8")
        path.chmod(0o755)

    executable(
        "google-chrome-stable",
        "#!/usr/bin/env bash\nsleep \"${FAKE_BROWSER_DELAY:-0}\"\necho launch >> \"$FAKE_BROWSER_MARKER\"\nexit 0\n",
    )
    executable("xhost", "#!/usr/bin/env bash\nexit 0\n")
    executable(
        "xdpyinfo",
        "#!/usr/bin/env bash\necho '  dimensions:    1920x1080 pixels'\n",
    )
    executable(
        "wmctrl",
        """#!/usr/bin/env bash
if [ "$1" = "-lx" ] && { [ "${FAKE_WMCTRL_MODE:-success}" = "success" ] || { [ "${FAKE_WMCTRL_MODE:-success}" = "after-launch" ] && [ -f "$FAKE_BROWSER_MARKER" ]; }; }; then
  echo '0x001 0 google-chrome.Google-chrome host Weird CAPTCHA Gym'
elif [ "$1" = "-lG" ]; then
  echo '0x001 0 0 0 1920 1080 host Weird CAPTCHA Gym'
fi
exit 0
""",
    )
    script = BENCHMARK / "shared_scripts" / "open_puzzle_browser.sh"
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "WEIRD_CAPTCHA_BROWSER_COMMAND": str(fake_bin / "google-chrome-stable"),
        "WEIRD_CAPTCHA_BROWSER_USER": "root",
        "WEIRD_CAPTCHA_BROWSER_HOME": str(tmp_path / "home"),
        "WEIRD_CAPTCHA_STATE_DIR": str(tmp_path / "state"),
        "FAKE_BROWSER_MARKER": str(tmp_path / "browser-launched"),
        "WEIRD_CAPTCHA_WINDOW_ATTEMPTS": "200",
        "WEIRD_CAPTCHA_WINDOW_POLL_SECONDS": "0.02",
        "WEIRD_CAPTCHA_GEOMETRY_ATTEMPTS": "1",
        "WEIRD_CAPTCHA_GEOMETRY_POLL_SECONDS": "0",
        "WEIRD_CAPTCHA_BROWSER_LOCK_ATTEMPTS": "200",
        "WEIRD_CAPTCHA_BROWSER_LOCK_POLL_SECONDS": "0.02",
    }

    accepted = subprocess.run(
        [str(script)],
        env={**environment, "FAKE_WMCTRL_MODE": "after-launch"},
        check=False,
    )
    assert accepted.returncode == 0
    assert (tmp_path / "browser-launched").exists()
    (tmp_path / "browser-launched").unlink()
    reused = subprocess.run([str(script)], env=environment, check=False)
    assert reused.returncode == 0
    assert (tmp_path / "browser-launched").exists() is False

    concurrent_environment = {
        **environment,
        "FAKE_WMCTRL_MODE": "after-launch",
        "FAKE_BROWSER_DELAY": "0.25",
    }
    first = subprocess.Popen([str(script)], env=concurrent_environment)
    second = subprocess.Popen([str(script)], env=concurrent_environment)
    assert first.wait(timeout=10) == 0
    assert second.wait(timeout=10) == 0
    assert (tmp_path / "browser-launched").read_text(encoding="utf-8").splitlines() == [
        "launch"
    ]
    (tmp_path / "browser-launched").unlink()

    rejected = subprocess.run(
        [str(script)],
        env={**environment, "FAKE_WMCTRL_MODE": "no-window"},
        check=False,
    )

    assert rejected.returncode != 0


def test_puzzle_browser_suppresses_the_firefox_data_notice(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()

    def executable(name: str, source: str) -> None:
        path = fake_bin / name
        path.write_text(source, encoding="utf-8")
        path.chmod(0o755)

    executable(
        "firefox",
        "#!/usr/bin/env bash\necho launch >> \"$FAKE_BROWSER_MARKER\"\nexit 0\n",
    )
    executable("xhost", "#!/usr/bin/env bash\nexit 0\n")
    executable(
        "pgrep",
        "#!/usr/bin/env bash\nif [ ! -f \"$FAKE_FIREFOX_STOPPED\" ]; then echo 123; exit 0; fi\nexit 1\n",
    )
    executable(
        "pkill",
        "#!/usr/bin/env bash\ntouch \"$FAKE_FIREFOX_STOPPED\"\nexit 0\n",
    )
    executable(
        "xdpyinfo",
        "#!/usr/bin/env bash\necho '  dimensions:    1920x1080 pixels'\n",
    )
    executable(
        "wmctrl",
        """#!/usr/bin/env bash
if [ "$1" = "-lx" ] && [ -f "$FAKE_BROWSER_MARKER" ]; then
  echo '0x001 0 firefox.Firefox host Weird CAPTCHA Gym'
elif [ "$1" = "-lG" ]; then
  echo '0x001 0 0 0 1920 1080 host Weird CAPTCHA Gym'
fi
exit 0
""",
    )
    home = tmp_path / "home"
    profile_root = home / "snap" / "firefox" / "common" / ".mozilla" / "firefox"
    profile = profile_root / "test.default"
    profile.mkdir(parents=True)
    (profile_root / "profiles.ini").write_text(
        "[Profile0]\nName=default\nIsRelative=1\nPath=test.default\nDefault=1\n",
        encoding="utf-8",
    )
    script = BENCHMARK / "shared_scripts" / "open_puzzle_browser.sh"
    completed = subprocess.run(
        [str(script)],
        env={
            **os.environ,
            "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
            "WEIRD_CAPTCHA_BROWSER_COMMAND": str(fake_bin / "firefox"),
            "WEIRD_CAPTCHA_BROWSER_USER": "root",
            "WEIRD_CAPTCHA_BROWSER_HOME": str(home),
            "WEIRD_CAPTCHA_STATE_DIR": str(tmp_path / "state"),
            "FAKE_BROWSER_MARKER": str(tmp_path / "browser-launched"),
            "FAKE_FIREFOX_STOPPED": str(tmp_path / "firefox-stopped"),
            "WEIRD_CAPTCHA_WINDOW_ATTEMPTS": "100",
            "WEIRD_CAPTCHA_WINDOW_POLL_SECONDS": "0.02",
            "WEIRD_CAPTCHA_GEOMETRY_ATTEMPTS": "1",
            "WEIRD_CAPTCHA_GEOMETRY_POLL_SECONDS": "0",
        },
        check=False,
    )
    repeated = subprocess.run(
        [str(script)],
        env={
            **os.environ,
            "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
            "WEIRD_CAPTCHA_BROWSER_COMMAND": str(fake_bin / "firefox"),
            "WEIRD_CAPTCHA_BROWSER_USER": "root",
            "WEIRD_CAPTCHA_BROWSER_HOME": str(home),
            "WEIRD_CAPTCHA_STATE_DIR": str(tmp_path / "state"),
            "FAKE_BROWSER_MARKER": str(tmp_path / "browser-launched"),
            "FAKE_FIREFOX_STOPPED": str(tmp_path / "firefox-stopped"),
            "WEIRD_CAPTCHA_WINDOW_ATTEMPTS": "100",
            "WEIRD_CAPTCHA_WINDOW_POLL_SECONDS": "0.02",
            "WEIRD_CAPTCHA_GEOMETRY_ATTEMPTS": "1",
            "WEIRD_CAPTCHA_GEOMETRY_POLL_SECONDS": "0",
        },
        check=False,
    )

    assert completed.returncode == 0
    assert repeated.returncode == 0
    assert (tmp_path / "firefox-stopped").is_file()
    assert (tmp_path / "browser-launched").read_text(encoding="utf-8").splitlines() == [
        "launch"
    ]
    assert (profile / "user.js").read_text(encoding="utf-8") == (
        'user_pref("datareporting.policy.dataSubmissionEnabled", false);\n'
    )


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
        _, settled_pause = request_json(
            f"{base}/time-control", {"command": "settle_pause"}
        )
        _, window = request_json(
            f"{base}/time-control",
            {"command": "run_for", "milliseconds": 500, "start_delay_ms": 50},
        )
        assert pause["sequence"] == 1
        assert settled_pause["sequence"] == 2
        assert window["sequence"] == 3

        request_json(f"{base}/time-control/status", {
            "sequence": 3,
            "state": "paused",
            "phase": "completed",
            "task_time_ms": 500,
        })
        _, current = request_json(f"{base}/time-control")
        _, status = request_json(f"{base}/time-control/status")
        assert current["sequence"] == 3
        assert current["command"] == "pause"
        assert status["phase"] == "completed"
        assert status["task_time_ms"] == 500
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
