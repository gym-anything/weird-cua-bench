from __future__ import annotations

import json
import os
import subprocess
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from weird_captcha_gym.realtime import (
    RealTimeSettings,
    load_real_time_settings,
    mechanic_id_from_env_dir,
)
from weird_captcha_gym.shared_scripts import capture_observation_window as CAPTURE
from weird_captcha_gym.shared_scripts.setup_task import generate_task_state
from weird_captcha_gym.shared_runtime.server.weird_captcha_server import PuzzleServer


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"


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


def test_existing_env_runner_options_match_canonical_real_time_settings() -> None:
    keys = ("play_time_seconds", "observation_window_ms", "frames_per_observation")
    for path in (BENCHMARK / "environments").glob("*_env/env.json"):
        mechanic_id = path.parent.name.removesuffix("_env")
        options = json.loads(path.read_text(encoding="utf-8"))["runner_options"]
        assert {key: options[key] for key in keys} == load_real_time_settings(
            mechanic_id
        ).__dict__


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


def test_consequences_real_time_settings_advance_the_storm_with_one_result_frame() -> None:
    settings = load_real_time_settings("consequences_boss")
    assert settings == RealTimeSettings(
        play_time_seconds=180,
        observation_window_ms=800,
        frames_per_observation=1,
    )
    assert CAPTURE.frame_targets(
        0,
        settings.observation_window_ms,
        settings.frames_per_observation,
    ) == [800]

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
    task_path = (
        BENCHMARK
        / "environments"
        / "consequences_boss_env"
        / "tasks"
        / "consequences_boss_seed_0001"
        / "task.json"
    )
    public_state, _ = generate_task_state(
        json.loads(task_path.read_text(encoding="utf-8")),
        "consequences-real-time-contract",
    )
    storm_ms = int(public_state["storm_ms"])
    assert settings.observation_window_ms < storm_ms
    assert 2 * settings.observation_window_ms >= storm_ms
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


def test_flat_pack_real_time_settings_advance_every_difficulty_load_without_redundant_frames() -> None:
    settings = load_real_time_settings("flat_pack_compliance")
    assert settings == RealTimeSettings(
        play_time_seconds=180,
        observation_window_ms=800,
        frames_per_observation=1,
    )
    assert CAPTURE.frame_targets(
        0,
        settings.observation_window_ms,
        settings.frames_per_observation,
    ) == [800]

    controls = json.loads(
        (
            BENCHMARK
            / "environments"
            / "flat_pack_compliance_env"
            / "controls.json"
        ).read_text(encoding="utf-8")
    )
    assert controls["real_time"] == settings.__dict__
    load_tick_ms = 72
    load_durations = [
        int(profile["parameters"]["load_step_count"]) * load_tick_ms
        for profile in controls["difficulty"].values()
    ]
    windows_needed = [
        (duration + settings.observation_window_ms - 1)
        // settings.observation_window_ms
        for duration in load_durations
    ]
    assert load_durations == [864, 1440, 2016, 2592, 3456]
    assert windows_needed == [2, 2, 3, 4, 5]

    mechanic_source = (
        BENCHMARK
        / "shared_runtime"
        / "app"
        / "mechanics"
        / "flat_pack_compliance.js"
    ).read_text(encoding="utf-8")
    assert "model.loadTimer = setInterval(() => {" in mechanic_source
    assert "}, 72);" in mechanic_source


def test_forced_perspective_exposes_held_key_movement_across_four_frames() -> None:
    settings = load_real_time_settings("forced_perspective_moving_day")
    assert settings == RealTimeSettings(
        play_time_seconds=180,
        observation_window_ms=400,
        frames_per_observation=4,
    )
    assert CAPTURE.frame_targets(
        0,
        settings.observation_window_ms,
        settings.frames_per_observation,
    ) == [0, 400 / 3, 800 / 3, 400]

    task_path = (
        BENCHMARK
        / "environments"
        / "forced_perspective_moving_day_env"
        / "tasks"
        / "forced_perspective_moving_day_seed_0001"
        / "task.json"
    )
    public_state, _ = generate_task_state(
        json.loads(task_path.read_text(encoding="utf-8")),
        "forced-perspective-real-time-contract",
    )
    tick_ms = int(public_state["world"]["tick_ms"])
    assert settings.observation_window_ms == 8 * tick_ms

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
    assert "setInterval(movementTick, state.world.tick_ms)" in mechanic_source


def test_ribbon_switchboard_exposes_transient_weave_and_supports_longest_trace() -> None:
    settings = load_real_time_settings("ribbon_switchboard")
    assert settings == RealTimeSettings(
        play_time_seconds=120,
        observation_window_ms=500,
        frames_per_observation=4,
    )
    targets = CAPTURE.frame_targets(
        0,
        settings.observation_window_ms,
        settings.frames_per_observation,
    )
    assert targets == [0, 500 / 3, 1000 / 3, 500]

    controls = json.loads(
        (
            BENCHMARK
            / "environments"
            / "ribbon_switchboard_env"
            / "controls.json"
        ).read_text(encoding="utf-8")
    )
    assert controls["real_time"] == settings.__dict__
    trace_durations = [
        int(profile["parameters"]["min_trace_ms"])
        for profile in controls["difficulty"].values()
    ]
    assert trace_durations == [220, 350, 460, 560, 760]
    assert max(trace_durations) <= 2 * settings.observation_window_ms

    mechanic_source = (
        BENCHMARK
        / "shared_runtime"
        / "app"
        / "mechanics"
        / "ribbon_switchboard.js"
    ).read_text(encoding="utf-8")
    assert "model.hoverExpiry=performance.now()+650" in mechanic_source
    assert max(targets) < 650


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
    assert "suppressClickUntil" not in mechanic_source
    assert "suppressNextCanvasClick" in mechanic_source
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
    assert 'dataSubmissionPolicyBypassNotification", true' in source
    assert 'browser.link.open_newwindow", 3' in source
    assert 'browser.link.open_newwindow.restriction", 0' in source
    assert "--new-instance --kiosk" in source
    assert 'profile_dir="$home_dir/weird-captcha-profile"' in source
    assert "--profile '$profile_dir'" in source
    assert "--disable-backgrounding-occluded-windows" in source
    assert "--disable-renderer-backgrounding" in source
    assert "--disable-features=AutomaticTabDiscarding,MemorySaverMode" in source


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
        "#!/usr/bin/env bash\n"
        "echo '  dimensions:    1920x1080 pixels'\n"
        "for _ in $(seq 1 10000); do echo 'visual metadata'; done\n",
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

        _, armed = request_json(
            f"{base}/input-control",
            {"command": "arm", "category": "mouse", "required": True},
        )
        _, completed_input = request_json(
            f"{base}/input-control",
            {"command": "complete", "arm_sequence": armed["arm_sequence"]},
        )
        assert armed["sequence"] == armed["arm_sequence"]
        assert completed_input["sequence"] == armed["sequence"] + 1
        request_json(
            f"{base}/input-control/status",
            {
                "command_sequence": completed_input["sequence"],
                "arm_sequence": armed["arm_sequence"],
                "phase": "completed",
                "receipt_confirmed": True,
                "task_time_ms": 500,
            },
        )
        _, input_command = request_json(f"{base}/input-control")
        _, delivered = request_json(f"{base}/input-control/status")
        assert input_command["command"] == "complete"
        assert delivered["receipt_confirmed"] is True
        assert delivered["task_time_ms"] == 500
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_state_refresh_is_idempotent_for_one_task_window_token(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    server = object.__new__(PuzzleServer)
    server.state_dir = state_dir
    server.app_dir = tmp_path / "shared_runtime" / "app"
    generated: list[str] = []

    class FakeSetup:
        @staticmethod
        def generate_task_state(task: dict, seed: str) -> tuple[dict, dict]:
            generated.append(seed)
            challenge_id = f"challenge-{len(generated)}"
            public = {
                "mechanic_id": "token_refresh_test",
                "task_id": task["id"],
                "challenge_id": challenge_id,
            }
            return public, dict(public)

    server._load_setup_module = lambda: FakeSetup
    server._write_json(
        state_dir / "current_task.json",
        {"task": {"id": "token-refresh-task"}, "attempt": 0},
    )
    monkeypatch.setenv("WEIRD_CAPTCHA_CHALLENGE_SEED", "fixed")

    first = server._try_regenerate_current_task(
        reason="refresh",
        client_task_token="window-a",
    )
    repeated = server._try_regenerate_current_task(
        reason="refresh",
        client_task_token="window-a",
    )
    assert repeated == first
    assert len(generated) == 1

    second_window = server._try_regenerate_current_task(
        reason="refresh",
        client_task_token="window-b",
    )
    assert second_window != first
    assert len(generated) == 2

    failed_retry = server._try_regenerate_current_task(reason="fail")
    repeated_after_failure = server._try_regenerate_current_task(
        reason="refresh",
        client_task_token="window-b",
    )
    assert repeated_after_failure == failed_retry
    assert len(generated) == 3
    assert json.loads((state_dir / "current_task.json").read_text(encoding="utf-8"))[
        "client_task_token"
    ] == "window-b"

    app_source = (BENCHMARK / "shared_runtime" / "app" / "app.js").read_text(
        encoding="utf-8"
    )
    assert 'new URLSearchParams(window.location.search).get("task")' in app_source
    assert "task=${encodeURIComponent(taskToken)}" in app_source
