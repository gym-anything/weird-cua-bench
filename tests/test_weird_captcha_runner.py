"""WeirdCaptchaRunner behind the public Gym-Anything doors.

Mirrors gym-anything's stranger test: a fake inner VM runner emulates the
guest (time controller, observation capture script, artifact files), and a
full episode runs through ``from_config`` wired only through the runner
registry, ``EnvSpec.runner_options``, and the ``frame_window`` modality.
"""

from __future__ import annotations

import json
import shlex
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from gym_anything.api import from_config
from gym_anything.runtime.runners import registry as runner_registry
from gym_anything.runtime.runners.base import BaseRunner
from gym_anything.specs import EnvSpec

from weird_captcha_gym.runner import WeirdCaptchaRunner

FAKE_INNER_KEY = "fake_vm"


class FakeVMRunner(BaseRunner):
    """Emulates the guest: clock commands, window capture, artifact files."""

    instances: list = []

    def __init__(self, spec):
        super().__init__(spec)
        FakeVMRunner.instances.append(self)
        self.calls: list = []
        self.clock_running = False
        self.ready_waits = 0
        self.task_time_ms = 0.0
        self.capture_resolution = [1920, 1080]
        self.guest_files = {
            "/tmp/weird_captcha_gym/public_state.json": b'{"public": true}',
            "/tmp/weird_captcha_gym/current_task.json": b'{"task": true}',
        }

    # lifecycle
    def start(self, seed=None):
        self.calls.append(("start", seed))

    def stop(self):
        self.calls.append(("stop", None))

    def run_reset(self, reset_script, seed=None):
        self.calls.append(("run_reset", reset_script))

    def run_task_init(self, init_script):
        self.calls.append(("run_task_init", init_script))

    def run_hook(self, command, *, stage, timeout=None, use_pty=True):
        self.calls.append(("run_hook", stage))
        return 0

    # actions and observations
    def inject_action(self, action):
        self.calls.append(("inject", action))
        if self.clock_running:
            self.task_time_ms += 50

    def capture_observation(self):
        return {}

    def capture_screenshot(self, host_path) -> bool:
        Path(host_path).write_bytes(b"fake-png")
        return True

    # guest access
    def _time_status(self):
        return {
            "state": "running" if self.clock_running else "paused",
            "task_time_ms": self.task_time_ms,
        }

    def exec_capture(self, cmd: str) -> str:
        self.calls.append(("exec_capture", cmd))
        parts = shlex.split(cmd)
        if "time_control.py" in cmd:
            command = parts[2]
            if command == "wait-ready":
                self.ready_waits += 1
            elif command == "resume":
                self.clock_running = True
            elif command in ("pause", "settle-pause"):
                self.clock_running = False
            self.calls.append(("time", command))
            return json.dumps(self._time_status())
        if "capture_observation_window.py" in cmd:
            duration = int(parts[parts.index("--duration-ms") + 1])
            frames = int(parts[parts.index("--frames") + 1])
            out_dir = parts[parts.index("--output-dir") + 1]
            # A scheduled observation window advances the task clock in both
            # modes; in paused mode the capture script owns the brief run.
            self.task_time_ms += duration
            manifest = {
                "frames": [
                    {
                        "path": f"{out_dir}/frame-{i:03d}.png",
                        "offset_ms": i * (duration // max(frames, 1)),
                        "target_offset_ms": i * (duration // max(frames, 1)),
                    }
                    for i in range(frames)
                ],
                "time_status": self._time_status(),
                "resolution": list(self.capture_resolution),
            }
            self.guest_files[f"{out_dir}/manifest.json"] = json.dumps(manifest).encode()
            self.calls.append(("capture_window", out_dir))
            return json.dumps(manifest)
        if cmd.startswith("test -s"):
            path = shlex.split(cmd)[2]
            return "present" if path in self.guest_files else ""
        return ""

    def exec(self, cmd, env=None, user=None, use_pty=True, timeout=600):
        self.calls.append(("exec", cmd))
        return 0

    def copy_from(self, container_src, host_dst):
        Path(host_dst).write_bytes(self.guest_files.get(container_src, b"fake-frame"))


def build_benchmark(root: Path, episodes: Path, *, time_mode: str,
                    resolution=(1920, 1080)) -> Path:
    env_dir = root / "environments" / "fake_weird_env"
    task_dir = env_dir / "tasks" / "t1"
    task_dir.mkdir(parents=True)
    (env_dir / "env.json").write_text(json.dumps({
        "id": "fake_weird_env",
        "image": "unused:latest",
        "observation": [
            {"type": "frame_window", "resolution": list(resolution), "fps": 10}
        ],
        "action": [{"type": "mouse"}, {"type": "keyboard"}],
        "synchronous": False,
        "runner": "weird_captcha",
        "runner_options": {
            "inner": FAKE_INNER_KEY,
            "time_mode": time_mode,
            "observation_window_ms": 800,
            "frames_per_observation": 3,
            "play_time_seconds": 90,
        },
        "recording": {"enable": False, "output_dir": str(episodes)},
    }))
    (task_dir / "task.json").write_text(json.dumps({
        "id": "t1",
        "description": "Solve the fake weird puzzle.",
        "init": {"timeout_sec": 600, "max_steps": 20},
        "success": {"mode": "program", "spec": {"program": "verifier.py::verify"}},
    }))
    (task_dir / "verifier.py").write_text(
        "def verify(traj, env_info, task_info):\n"
        "    return {'passed': True, 'score': 100, 'feedback': 'ok'}\n"
    )
    return env_dir


def make_spec(**runner_options) -> EnvSpec:
    options = {
        "inner": FAKE_INNER_KEY,
        "time_mode": "paused",
        "observation_window_ms": 800,
        "frames_per_observation": 3,
    }
    options.update(runner_options)
    return EnvSpec.from_dict({
        "id": "fake_weird_env",
        "image": "unused:latest",
        "observation": [{"type": "frame_window", "resolution": [1920, 1080]}],
        "action": [{"type": "mouse"}],
        "runner": "weird_captcha",
        "runner_options": options,
    })


class WeirdCaptchaRunnerTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        runner_registry.register_runner(FAKE_INNER_KEY, FakeVMRunner, replace=True)

    def setUp(self):
        FakeVMRunner.instances.clear()


class CorpusMigrationTest(unittest.TestCase):
    """Every environment declares the runner, and its options mirror
    real_time.json so the two sources cannot drift."""

    def test_env_specs_declare_runner_and_mirror_real_time_settings(self):
        from gym_anything.registry import resolve_benchmark_root

        from weird_captcha_gym.realtime import mechanic_id_from_env_dir

        root = resolve_benchmark_root("weird_captcha_gym")
        real_time = json.loads((root / "real_time.json").read_text())["environments"]
        env_dirs = sorted(
            d for d in (root / "environments").iterdir() if d.name.endswith("_env")
        )
        self.assertEqual(len(env_dirs), 75)
        for env_dir in env_dirs:
            spec = json.loads((env_dir / "env.json").read_text())
            settings = real_time[mechanic_id_from_env_dir(str(env_dir))]
            self.assertEqual(spec.get("runner"), "weird_captcha", env_dir.name)
            self.assertEqual(
                spec.get("runner_options"),
                {
                    "observation_window_ms": settings["observation_window_ms"],
                    "frames_per_observation": settings["frames_per_observation"],
                    "play_time_seconds": settings["play_time_seconds"],
                },
                env_dir.name,
            )
            errors = WeirdCaptchaRunner.validate_options(
                EnvSpec.from_dict(spec)
            )
            self.assertEqual(errors, [], env_dir.name)


class RegistryAndOptionsTest(WeirdCaptchaRunnerTestCase):
    def test_entry_point_resolves(self):
        self.assertIs(
            runner_registry.resolve_runner_class("weird_captcha"), WeirdCaptchaRunner
        )
        self.assertEqual(runner_registry.registry_conflicts(), {})

    def test_validate_options_accepts_good_options(self):
        self.assertEqual(WeirdCaptchaRunner.validate_options(make_spec()), [])

    def test_validate_options_rejects_bad_options(self):
        spec = make_spec(time_mode="warp", typo_key=1, frames_per_observation=0)
        errors = "\n".join(WeirdCaptchaRunner.validate_options(spec))
        self.assertIn("typo_key", errors)
        self.assertIn("time_mode", errors)
        self.assertIn("frames_per_observation", errors)

    def test_validate_options_rejects_unknown_inner(self):
        errors = WeirdCaptchaRunner.validate_options(make_spec(inner="no_such_runner"))
        self.assertTrue(any("inner" in e for e in errors))

    def test_inner_spec_sees_rgb_screen(self):
        runner = WeirdCaptchaRunner(make_spec())
        self.assertEqual(runner.spec.observation[0].type, "frame_window")
        self.assertEqual(runner.inner.spec.observation[0].type, "rgb_screen")
        self.assertEqual(runner.inner.spec.observation[0].resolution, (1920, 1080))

    def test_declines_preset_merged_rgb_screen(self):
        # The base preset injects rgb_screen and the config merge keeps it
        # alongside frame_window. The world declines the convenience entry:
        # core must not capture its own stale screen ahead of the window.
        spec = EnvSpec.from_dict({
            "id": "fake_weird_env",
            "image": "unused:latest",
            "observation": [
                {"type": "rgb_screen", "resolution": [1920, 1080], "fps": 10},
                {"type": "frame_window", "resolution": [1920, 1080], "fps": 10},
            ],
            "action": [{"type": "mouse"}],
            "runner": "weird_captcha",
            "runner_options": {
                "inner": FAKE_INNER_KEY,
                "time_mode": "paused",
                "observation_window_ms": 800,
                "frames_per_observation": 3,
            },
        })
        runner = WeirdCaptchaRunner(spec)
        self.assertEqual([e.type for e in spec.observation], ["frame_window"])
        self.assertEqual(
            [e.type for e in runner.inner.spec.observation], ["rgb_screen"]
        )


class StateMachineTest(WeirdCaptchaRunnerTestCase):
    def _runner(self, **options) -> WeirdCaptchaRunner:
        runner = WeirdCaptchaRunner(make_spec(**options))
        self._tmp = TemporaryDirectory()
        runner.on_episode_start({
            "episode_dir": self._tmp.name,
            "env_id": "fake_weird_env",
            "task_id": "t1",
            "seed": 7,
        })
        self.addCleanup(self._tmp.cleanup)
        return runner

    def _time_events(self, fake):
        return [c[1] for c in fake.calls if c[0] == "time"]

    def test_episode_start_injects_guest_env(self):
        runner = self._runner()
        resolved = runner.inner.spec.security.resolved_env
        self.assertEqual(resolved["WEIRD_CAPTCHA_TIME_MODE"], "paused")
        self.assertEqual(resolved["WEIRD_CAPTCHA_START_PAUSED"], "1")
        self.assertEqual(resolved["WEIRD_CAPTCHA_CHALLENGE_SEED"], "7")
        self.assertEqual(resolved["SEED"], "7")

    def test_challenge_seed_option_overrides_episode_seed(self):
        runner = self._runner(challenge_seed=1234)
        resolved = runner.inner.spec.security.resolved_env
        self.assertEqual(resolved["WEIRD_CAPTCHA_CHALLENGE_SEED"], "1234")

    def test_paused_turn_cycle(self):
        runner = self._runner()
        fake = runner.inner

        obs = runner.capture_observation()
        self.assertEqual(self._time_events(fake), ["wait-ready"])
        self.assertEqual(len(obs["frames"]), 3)
        self.assertTrue(Path(obs["screen"]["path"]).exists())
        self.assertTrue(Path(obs["capture_manifest"]).exists())
        self.assertFalse(fake.clock_running)

        runner.inject_action({"mouse": {"left_click": [5, 5]}})
        runner.inject_action({"mouse": {"left_click": [6, 6]}})
        events = self._time_events(fake)
        # One resume for the whole action group, before the first injection.
        self.assertEqual(events, ["wait-ready", "resume"])
        injects = [c for c in fake.calls if c[0] == "inject"]
        self.assertEqual(len(injects), 2)
        self.assertTrue(fake.clock_running)

        obs = runner.capture_observation()
        self.assertEqual(
            self._time_events(fake), ["wait-ready", "resume", "settle-pause"]
        )
        self.assertFalse(fake.clock_running)
        self.assertIn("turn-0001", obs["screen"]["path"])

    def test_live_mode_resumes_once(self):
        runner = self._runner(time_mode="live")
        fake = runner.inner
        runner.capture_observation()
        runner.inject_action({"mouse": {"left_click": [5, 5]}})
        runner.capture_observation()
        events = self._time_events(fake)
        self.assertEqual(events, ["wait-ready", "resume"])
        self.assertTrue(fake.clock_running)

    def test_time_action_reports_result(self):
        runner = self._runner()
        runner.inject_action({"action": "time", "command": "status"})
        self.assertIn("task_time_ms", runner.last_action_result)
        with self.assertRaises(ValueError):
            runner.inject_action({"action": "time", "command": "nuke"})

    def test_wait_action_runs_clock_in_paused_mode(self):
        runner = self._runner()
        fake = runner.inner
        runner.inject_action({"action": "wait", "time": 0})
        self.assertEqual(self._time_events(fake), ["wait-ready", "resume"])
        self.assertTrue(fake.clock_running)

    def test_resolution_mismatch_raises(self):
        runner = self._runner()
        runner.inner.capture_resolution = [1280, 720]
        with self.assertRaises(RuntimeError):
            runner.capture_observation()

    def test_collect_artifacts_copies_present_files(self):
        runner = self._runner()
        runner.collect_artifacts()
        episode = Path(self._tmp.name)
        self.assertTrue((episode / "public_state.json").exists())
        self.assertTrue((episode / "current_task.json").exists())
        self.assertFalse((episode / "slot_reel_witness_ledger.json").exists())


class FullEpisodeTest(WeirdCaptchaRunnerTestCase):
    """A complete episode through from_config, the Phase 1 gate in miniature."""

    def setUp(self):
        super().setUp()
        self._tmp = TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self.episodes = tmp / "episodes"
        self.episodes.mkdir()
        self.env_dir = build_benchmark(tmp / "bench", self.episodes, time_mode="paused")
        self.addCleanup(self._tmp.cleanup)

    def test_full_paused_episode(self):
        env = from_config(self.env_dir, task_id="t1")
        self.assertIsInstance(env.runner, WeirdCaptchaRunner)
        self.assertIsInstance(env.runner.inner, FakeVMRunner)
        fake = env.runner.inner

        obs = env.reset(seed=7)
        self.assertEqual(len(obs["frames"]), 3)
        self.assertIn("turn-0000", obs["screen"]["path"])
        self.assertIsNotNone(obs["time"]["task_time_ms"])
        self.assertEqual(
            fake.spec.security.resolved_env["WEIRD_CAPTCHA_CHALLENGE_SEED"], "7"
        )

        obs, _reward, done, info = env.step(
            [{"mouse": {"left_click": [5, 5]}}], wait_between_actions=0.0
        )
        self.assertFalse(done)
        self.assertIn("turn-0001", obs["screen"]["path"])
        time_events = [c[1] for c in fake.calls if c[0] == "time"]
        self.assertEqual(
            time_events, ["wait-ready", "resume", "settle-pause"]
        )

        obs, _reward, done, _info = env.step(
            [{"action": "time", "command": "status"}],
            capture_observation=False,
            settle_after_actions=False,
        )
        self.assertEqual(obs, {})
        self.assertIn("task_time_ms", env.runner.last_action_result)

        _obs, _reward, done, info = env.step([], mark_done=True, capture_observation=False)
        self.assertTrue(done)
        self.assertTrue(info["verifier"]["passed"])

        episode_dir = Path(env.episode_dir)
        env.close()
        self.assertTrue((episode_dir / "public_state.json").exists())
        self.assertTrue((episode_dir / "traj.jsonl").exists())
        observations = sorted((episode_dir / "observations").iterdir())
        self.assertEqual(
            [d.name for d in observations], ["turn-0000", "turn-0001"]
        )


# The importable Gym-Anything conformance suite, run against the composed
# runner with the fake guest so CI needs no VM.
from gym_anything.testing import build_conformance_case  # noqa: E402

runner_registry.register_runner(FAKE_INNER_KEY, FakeVMRunner, replace=True)

WeirdCaptchaConformance = build_conformance_case(
    "weird_captcha",
    env_spec={
        "image": "unused:latest",
        "observation": [{"type": "frame_window", "resolution": [1920, 1080], "fps": 10}],
        "action": [{"type": "mouse"}, {"type": "keyboard"}],
        "runner_options": {
            "inner": FAKE_INNER_KEY,
            "time_mode": "paused",
            "observation_window_ms": 800,
            "frames_per_observation": 3,
        },
    },
    actions=[{"mouse": {"left_click": [5, 5]}}],
    class_name="WeirdCaptchaConformance",
)


if __name__ == "__main__":
    unittest.main()
