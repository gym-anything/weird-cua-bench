#!/usr/bin/env python3
"""Exercise the Codex HTTP action contract in a fresh, isolated task VM.

No model calls or scores. All tested input goes through the gateway. A
read-only X11 probe independently checks the guest's actual held input state.
Run only in a CPU allocation with /dev/kvm and a staged Gym QEMU cache.
"""

from __future__ import annotations

import argparse
import base64
import json
import time
import urllib.request
from pathlib import Path

from gym_anything.api import from_config

from weird_captcha_gym.evaluation.codex_cli import WeirdCodexActionGateway
from weird_captcha_gym.evaluation.temporal_modes import TEMPORAL_MODES, world_time_mode
from weird_captcha_gym.runner import guest_json


X11_STATE = """
import json
from Xlib import display, XK
d = display.Display(':1')
bits = d.query_keymap()
pointer = d.screen().root.query_pointer()
held = {}
for name in ['w', 'Shift_L', 'Control_L']:
    code = d.keysym_to_keycode(XK.string_to_keysym(name))
    held[name] = bool(bits[code // 8] & (1 << (code % 8)))
print(json.dumps(dict(keys=held, mask=pointer.mask, x=pointer.root_x, y=pointer.root_y)))
d.close()
"""


def run_mode(args, mode):
    root = args.output / mode
    root.mkdir(parents=True, exist_ok=True)
    paused = mode == "paused"
    env = from_config(
        args.env_dir,
        task_id=args.task,
        fast_io=True,
        overrides={
            "runner_options": {
                "time_mode": world_time_mode(mode),
                "play_time_seconds": 0,
                "observation_window_ms": 500 if paused else 0,
                "frames_per_observation": 6 if paused else 1,
            },
            "recording": {"enable": False, "output_dir": str(root / "episodes")},
        },
    )
    proxy = None
    records = []
    try:
        env.reset(seed=42, use_cache=True, cache_level="pre_start")
        env.set_episode_limits(max_steps=100, timeout_sec=900)
        proxy = WeirdCodexActionGateway(
            env,
            (1920, 1080),
            100,
            "local-smoke-token",
            temporal_mode=mode,
            timing_path=root / "timing.jsonl",
        )
        port = proxy.start(host="127.0.0.1")

        def computer(actions):
            request = urllib.request.Request(
                f"http://127.0.0.1:{port}",
                data=json.dumps({"command": json.dumps(actions)}).encode(),
                headers={
                    "X-Gateway-Token": "local-smoke-token",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(request, timeout=180) as response:
                payload = json.load(response)
            if payload.get("error"):
                raise AssertionError(payload["error"])
            images = payload.pop("screenshots_b64")
            payload.pop("screenshot_b64", None)
            assert len(images) == (6 if paused else 1), len(images)
            for index, image in enumerate(images):
                path = root / f"obs-{payload['observation']:03d}-{index}.png"
                path.write_bytes(base64.b64decode(image))
            records.append({"command": actions, "response": payload})
            print(
                json.dumps({"mode": mode, "command": actions, "step": payload["step"]}),
                flush=True,
            )
            return payload

        def state():
            value = guest_json(env, ["python3", "-c", X11_STATE])
            records.append({"guest_input_state": value})
            return value

        computer([])
        computer([{"keyboard": {"keys_down": ["w"]}}])
        assert state()["keys"]["w"], "W was not held in the guest"
        computer([])
        assert state()["keys"]["w"], "observation released W"
        computer([{"keyboard": {"keys_up": ["w"]}}])
        assert not state()["keys"]["w"], "W release was lost"

        for button, mask in (("left", 256), ("middle", 512), ("right", 1024)):
            computer(
                [
                    {"mouse": {"move": [20, 20]}},
                    {"mouse": {"buttons": {f"{button}_down": True}}},
                ]
            )
            assert state()["mask"] & mask, f"{button} button was not held"
            computer([{"mouse": {"move": [30, 30]}}])
            observed = state()
            assert observed["mask"] & mask, f"move released {button}"
            assert abs(observed["x"] - 45) <= 2 and abs(observed["y"] - 45) <= 2, (
                observed
            )
            computer([{"mouse": {"buttons": {f"{button}_up": True}}}])
            assert not state()["mask"] & mask, f"{button} release was lost"
            computer([{"keyboard": {"keys": ["escape"]}}])

        computer([{"keyboard": {"keys_down": ["shift"]}}])
        computer([{"mouse": {"scroll": 1}}])
        assert state()["keys"]["Shift_L"], "wheel action released the modifier"
        computer([{"keyboard": {"keys_up": ["shift"]}}])
        assert not state()["keys"]["Shift_L"]

        for field in (
            "left_click",
            "right_click",
            "middle_click",
            "double_click",
            "triple_click",
        ):
            computer([{"mouse": {field: [20, 20]}}])
            assert not state()["mask"] & (256 | 512 | 1024)
            computer([{"keyboard": {"keys": ["escape"]}}])
        for field in ("left_click_drag", "right_click_drag"):
            computer([{"mouse": {field: [[20, 20], [35, 35]]}}])
            assert not state()["mask"] & (256 | 512 | 1024)
            computer([{"keyboard": {"keys": ["escape"]}}])

        computer(
            [
                {"keyboard": {"keys_down": ["ctrl"]}},
                {"mouse": {"buttons": {"left_down": True}}},
                {"mouse": {"move": [35, 20]}},
                {"action": "wait", "time": 0.05},
                {"mouse": {"move": [20, 35]}},
                {"mouse": {"buttons": {"left_up": True}}},
                {"keyboard": {"keys_up": ["ctrl"]}},
            ]
        )
        assert not state()["keys"]["Control_L"]
        if mode == "live_timestamped_execution":
            current = computer([])["timing"]["current_time_s"]
            computer(
                {
                    "actions": [{"keyboard": {"keys_down": ["shift"]}}],
                    "execute_at_s": current + 0.2,
                }
            )
            assert state()["keys"]["Shift_L"]
            current = computer([])["timing"]["current_time_s"]
            computer(
                {
                    "actions": [{"keyboard": {"keys_up": ["shift"]}}],
                    "execute_at_s": current + 0.2,
                }
            )
            assert not state()["keys"]["Shift_L"]
        return {
            "mode": mode,
            "passed": True,
            "steps": proxy.steps_taken,
            "episode_dir": str(env.episode_dir),
        }
    finally:
        if proxy is not None:
            proxy.stop()
            (root / "gateway_transcript.json").write_text(
                json.dumps(proxy.transcript, indent=2)
            )
        (root / "checks.json").write_text(json.dumps(records, indent=2))
        env.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-dir", type=Path, required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--modes", nargs="+", choices=TEMPORAL_MODES, default=list(TEMPORAL_MODES)
    )
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    started = time.time()
    try:
        for mode in args.modes:
            result = run_mode(args, mode)
            results.append(result)
            print(json.dumps(result), flush=True)
    finally:
        (args.output / "results.json").write_text(
            json.dumps(
                {"results": results, "wall_seconds": time.time() - started}, indent=2
            )
        )


if __name__ == "__main__":
    main()
