"""Measure sandbox scheduling through an existing Gym master and HTTP gateway.

No model inference. Use an isolated worker allocation, not a production run.
--connection-file supplies master_url and optional staged runtime mounts.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import time

import requests
from gym_anything.remote import RemoteGymEnv
from weird_captcha_gym.evaluation.codex_cli import WeirdCodexActionGateway


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connection-file", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--recording", action="store_true")
    parser.add_argument("--local-browser-probe", action="store_true",
                        help="Run on the worker node and verify trusted browser events too")
    args = parser.parse_args()
    ready = json.loads(args.connection_file.read_text())
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    overrides = {
        "runner_options": {"inner": "sandweave", "time_mode": "live", "start_paused": True,
                           "frames_per_observation": 1, "observation_window_ms": 0, "play_time_seconds": 0},
        "recording": {"enable": args.recording, "output_dir": str(output)},
    }
    if "mounts" in ready:
        overrides["mounts"] = ready["mounts"]
    if args.local_browser_probe:
        from gym_anything.api import from_config
        from gym_anything.runtime.runners.registry import register_runner
        from weird_captcha_gym.runner import WeirdCaptchaRunner
        register_runner("weird_captcha", WeirdCaptchaRunner, replace=True)
        env = from_config("weird_captcha_gym/environments/rotating_keyboard_env",
                          "rotating_keyboard_d3_full_seed_0001", fast_io=True, overrides=overrides)
    else:
        env = RemoteGymEnv.from_benchmark(ready["master_url"], "weird_captcha_gym", "rotating_keyboard_env",
                                        "rotating_keyboard_d3_full_seed_0001", fast_io=True, timeout=1200, overrides=overrides)
    gateway, rows = None, []
    try:
        print("Resetting isolated sandbox", flush=True)
        env.reset(seed=42)
        env.set_episode_limits(max_steps=2000, timeout_sec=1200)
        gateway = WeirdCodexActionGateway(env, (1920, 1080), 1000, "timing-test",
            temporal_mode="live_timestamped_execution", timing_path=output / "timing.jsonl")
        url = f"http://127.0.0.1:{gateway.start(host='127.0.0.1')}"

        def request(command):
            started = time.perf_counter()
            response = requests.post(url, json={"command": json.dumps(command)},
                                     headers={"X-Gateway-Token": "timing-test"}, timeout=300)
            response.raise_for_status()
            result = response.json()
            assert not result.get("error"), result
            return result, (time.perf_counter() - started) * 1000

        first, _ = request({"action": "screenshot"})
        assert len(first["screenshots_b64"]) == 1
        print("Sandbox input service ready", flush=True)
        cases = [
            ("key_down", {"keyboard": {"keys_down": ["SHIFT"]}}),
            ("key_up", {"keyboard": {"keys_up": ["SHIFT"]}}),
            ("click", {"mouse": {"left_click": [100, 500]}}),
        ]
        for index in range(args.samples):
            for kind, action in cases:
                target = (time.time_ns() / 1e6 - gateway._t0_ms) / 1000 + .25
                result, elapsed = request({"actions": [action], "execute_at_s": target})
                receipt = result["input_receipt"]
                assert receipt["queued_at_s"] < target, receipt
                assert receipt["action_executed_at_s"] >= target, receipt
                assert result["screenshots_b64"] == []
                rows.append({"kind": kind, "iteration": index, "http_ms": elapsed, **receipt,
                             "http_excluding_queue_wait_ms": elapsed - (receipt["action_executed_at_s"] - receipt["queued_at_s"]) * 1000,
                             "lateness_ms": (receipt["action_executed_at_s"] - target) * 1000,
                             "execution_to_fence_ms": (receipt["action_completed_at_s"] - receipt["action_executed_at_s"]) * 1000,
                             "fence_to_ack_send_ms": (receipt["ack_sent_at_s"] - receipt["action_completed_at_s"]) * 1000})
                (output / "samples.json").write_text(json.dumps(rows, indent=2) + "\n")
            print(f"Scheduled samples {index + 1}/{args.samples}", flush=True)

        # A later-deadline request arrives first. An immediate action and a
        # screenshot must still proceed while it waits inside the sandbox.
        target = (time.time_ns() / 1e6 - gateway._t0_ms) / 1000 + 1
        with ThreadPoolExecutor(3) as pool:
            later = pool.submit(request, {"actions": [{"keyboard": {"keys_up": ["SHIFT"]}}], "execute_at_s": target})
            time.sleep(.05)
            image = pool.submit(request, {"action": "screenshot"})
            earlier, earlier_ms = request({"keyboard": {"keys_down": ["SHIFT"]}})
            assert earlier["input_receipt"]["action_executed_at_s"] < target
            later_response, _ = later.result()
            screenshot, _ = image.result()
            assert screenshot["screenshots_b64"]
        checks = {"earlier": earlier["input_receipt"], "earlier_http_ms": earlier_ms,
                  "later": later_response["input_receipt"], "episode_dir": env.get_session_info().artifacts_dir}

        # Delay the return path after the worker response. The execution
        # timestamp must remain the guest receipt, not shift by this delay.
        original = getattr(env, "_request", None)

        def delayed_reply(*args, **kwargs):
            response = original(*args, **kwargs)
            if args[1].endswith("/weird/input"):
                time.sleep(.2)
            return response

        if original is not None:
            env._request = delayed_reply
        delayed, elapsed = request({"mouse": {"move": [100, 500]}})
        assert delayed["timing"]["action_executed_at_s"] == delayed["input_receipt"]["action_executed_at_s"]
        checks["delayed_reply"] = {"http_ms": elapsed, "receipt": delayed["input_receipt"]}
        if original is not None:
            env._request = original
        (output / "checks.json").write_text(json.dumps(checks, indent=2) + "\n")
        print("PASS concurrent requests, independent screenshot, delayed reply timestamps", flush=True)
        if args.local_browser_probe:
            browser_rows = []
            for index in range(5):
                for kind, action in cases:
                    category = "keyboard" if kind.startswith("key") else "mouse"
                    armed = env.runner.input_command("arm", category=category)
                    target = (time.time_ns() / 1e6 - gateway._t0_ms) / 1000 + .25
                    result, elapsed = request({"actions": [action], "execute_at_s": target})
                    delivered = env.runner.input_command("complete", arm_sequence=armed["arm_sequence"])
                    event = next(e for e in delivered["observed_events"] if e["type"] == {
                        "key_down": "keydown", "key_up": "keyup", "click": "click"}[kind])
                    event_wall_ms = armed["native_date_ms"] + event["native_time_ms"] - armed["native_time_ms"]
                    browser_rows.append({"kind": kind, "iteration": index,
                        "deadline_to_browser_ms": event_wall_ms - gateway._t0_ms - target * 1000,
                        "receipt": result["input_receipt"], "armed": armed, "delivered": delivered})
                    (output / "browser.json").write_text(json.dumps(browser_rows, indent=2) + "\n")
            print("PASS 15 trusted browser-event receipts", flush=True)
            semantics = []
            for action, event_type, expected_key in [
                ({"keyboard": {"keys_down": ["w"]}}, "keydown", "w"),
                ({"keyboard": {"keys_up": ["w"]}}, "keyup", "w"),
                ({"keyboard": {"keys": ["shift", "w"]}}, "keydown", "W"),
                ({"mouse": {"buttons": {"left_down": True}}}, "mousedown", None),
                ({"mouse": {"buttons": {"left_up": True}}}, "mouseup", None),
                ({"mouse": {"left_click_drag": [[100, 500], [150, 550]]}}, "mouseup", None),
            ]:
                category = "keyboard" if "keyboard" in action else "mouse"
                armed = env.runner.input_command("arm", category=category)
                result, _ = request(action)
                delivered = env.runner.input_command("complete", arm_sequence=armed["arm_sequence"])
                assert any(e["type"] == event_type and (expected_key is None or e["key"] == expected_key)
                           for e in delivered["observed_events"]), delivered
                semantics.append({"action": action, "delivery": delivered, "receipt": result["input_receipt"]})
                (output / "semantics.json").write_text(json.dumps(semantics, indent=2) + "\n")
            print("PASS letter holds, chord, mouse holds and drag", flush=True)
            # Text correctness is the value entered in an editable control,
            # not Firefox's keydown.key for a temporary X11 Unicode keymap.
            request({"keyboard": {"keys": ["ctrl", "l"]}})
            request({"keyboard": {"text": "héllo + 世界"}})
            request({"keyboard": {"keys": ["ctrl", "a"]}})
            request({"keyboard": {"keys": ["ctrl", "c"]}})
            entered = env.runner.inner.exec_capture(
                "DISPLAY=:1 XAUTHORITY=/home/ga/.Xauthority python3 -c \""
                "import gi; gi.require_version('Gtk', '3.0'); from gi.repository import Gtk,Gdk; "
                "print(Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).wait_for_text(), end='')\"")
            (output / "text-entry.json").write_text(json.dumps({"expected": "héllo + 世界", "actual": entered}, ensure_ascii=False))
            assert entered == "héllo + 世界", repr(entered)
            request({"keyboard": {"keys": ["Escape"]}})
            print("PASS exact Unicode text entry", flush=True)
    finally:
        if gateway:
            gateway.stop()
        env.close()


if __name__ == "__main__":
    main()
