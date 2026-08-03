from __future__ import annotations

import base64
import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from benchmarks.weird_captcha_gym.evaluation.control import LocalEvaluationControl
from benchmarks.weird_captcha_gym.evaluation.control import capture_observation_window
from benchmarks.weird_captcha_gym.evaluation.corpus import evaluation_pairs
from benchmarks.weird_captcha_gym.evaluation.qwen35vl import (
    WeirdQwen35VLAgent,
    image_from_screen,
    observation_frames,
)
from benchmarks.weird_captcha_gym.evaluation.remote import (
    RemoteEvaluationControl,
    WEIRD_CUA_WORKER_CAPABILITY,
    WeirdRemoteGymEnv,
)
from benchmarks.weird_captcha_gym.evaluation import remote_worker
from benchmarks.weird_captcha_gym.tools import run_realtime_evaluation as evaluator


class JsonResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def json(self) -> dict:
        return self.payload


def test_evaluator_parser_accepts_gym_remote_and_fast_io_options() -> None:
    args = evaluator.build_parser().parse_args(
        [
            "--env-dir",
            "environment",
            "--task",
            "task",
            "--agent",
            "Qwen35VLAgent",
            "--agent-args",
            "{}",
            "--time-mode",
            "paused",
            "--fast-io",
            "--remote-url",
            "http://master:5000",
            "--remote-worker-reset-policy",
            "baseline_setup",
        ]
    )
    assert args.fast_io is True
    assert args.remote_url == "http://master:5000"
    assert args.remote_worker_reset_policy == "baseline_setup"


def test_evaluator_can_disable_the_task_clock_limit() -> None:
    args = evaluator.build_parser().parse_args(
        [
            "--env-dir",
            "environment",
            "--task",
            "task",
            "--agent",
            "Qwen35VLAgent",
            "--agent-args",
            "{}",
            "--time-mode",
            "live",
            "--no-play-time-limit",
        ]
    )
    settings = SimpleNamespace(play_time_seconds=120)
    assert evaluator._play_time_limit_seconds(args, settings) is None
    assert evaluator._play_time_exhausted(10**12, None) is False


def test_evaluator_keeps_the_configured_task_clock_limit_by_default() -> None:
    args = evaluator.build_parser().parse_args(
        [
            "--env-dir",
            "environment",
            "--task",
            "task",
            "--agent",
            "Qwen35VLAgent",
            "--agent-args",
            "{}",
            "--time-mode",
            "paused",
        ]
    )
    settings = SimpleNamespace(play_time_seconds=120)
    assert evaluator._play_time_limit_seconds(args, settings) == 120
    assert evaluator._play_time_exhausted(119_999, 120) is False
    assert evaluator._play_time_exhausted(120_000, 120) is True


def test_evaluator_sends_the_controlled_task_instruction_to_the_agent() -> None:
    env = SimpleNamespace(
        task_spec=SimpleNamespace(
            natural_language="Solve the L1 task.",
            description="Generic environment description.",
        )
    )
    args = SimpleNamespace(env_dir="unused", task="unused")
    description = evaluator._task_description(env, args)
    assert description.startswith("Solve the L1 task.\n\n")
    assert evaluator.VISIBLE_UI_ONLY_RULE in description


def test_evaluator_falls_back_to_task_description() -> None:
    env = SimpleNamespace(
        task_spec=SimpleNamespace(
            natural_language=None,
            description="Fallback task description.",
        )
    )
    args = SimpleNamespace(env_dir="unused", task="unused")
    assert evaluator._task_description(env, args).startswith(
        "Fallback task description.\n\n"
    )


def test_make_env_uses_the_gym_remote_environment_contract(monkeypatch) -> None:
    sentinel = object()
    received = {}

    def fake_from_config(**kwargs):
        received.update(kwargs)
        return sentinel

    monkeypatch.setattr(evaluator.WeirdRemoteGymEnv, "from_config", fake_from_config)
    args = SimpleNamespace(
        remote_url="http://master:5000",
        env_dir="environment",
        task="task",
        remote_timeout=123,
        remote_worker_reset_policy="baseline_setup",
        fast_io=True,
    )
    assert evaluator._make_env(args) is sentinel
    assert received == {
        "remote_url": "http://master:5000",
        "env_dir": "environment",
        "task_id": "task",
        "timeout": 123,
        "worker_reset_policy": "baseline_setup",
        "fast_io": True,
    }


def test_weird_remote_environment_requests_a_weird_worker() -> None:
    env = object.__new__(WeirdRemoteGymEnv)
    assert env._infer_runner_hint() == WEIRD_CUA_WORKER_CAPABILITY


def test_local_control_configures_the_gym_environment_spec() -> None:
    env = SimpleNamespace(
        env_spec=SimpleNamespace(
            security=SimpleNamespace(resolved_env={"EXISTING": "yes"})
        )
    )
    LocalEvaluationControl(env).configure({"WEIRD_CAPTCHA_TIME_MODE": "paused"})
    assert env.env_spec.security.resolved_env == {
        "EXISTING": "yes",
        "WEIRD_CAPTCHA_TIME_MODE": "paused",
    }


def test_capture_returns_absolute_paths_for_remote_fetching(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)

    class FakeRunner:
        @staticmethod
        def exec_capture(_command):
            return json.dumps(
                {
                    "frames": [
                        {
                            "path": "/guest/frame.png",
                            "offset_ms": 0,
                            "target_offset_ms": 0,
                        }
                    ],
                    "resolution": [1920, 1080],
                    "time_status": {"task_time_ms": 0},
                }
            )

        @staticmethod
        def copy_from(_source, destination):
            path = Path(destination)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"file")

    observation = capture_observation_window(
        SimpleNamespace(
            runner=FakeRunner(),
            env_spec=SimpleNamespace(
                observation=[SimpleNamespace(resolution=[1920, 1080])]
            ),
        ),
        mode="paused",
        duration_ms=0,
        frames_per_observation=1,
        turn=0,
        host_dir=Path("relative-artifacts"),
    )
    assert Path(observation["screen"]["path"]).is_absolute()
    assert Path(observation["capture_manifest"]).is_absolute()
    assert observation["screen"]["resolution"] == [1920, 1080]


def test_capture_rejects_a_resolution_that_cannot_share_action_coordinates(
    tmp_path: Path,
) -> None:
    class FakeRunner:
        @staticmethod
        def exec_capture(_command):
            return json.dumps(
                {
                    "frames": [
                        {
                            "path": "/guest/frame.png",
                            "offset_ms": 0,
                            "target_offset_ms": 0,
                        }
                    ],
                    "resolution": [1280, 720],
                    "time_status": {"task_time_ms": 0},
                }
            )

        @staticmethod
        def copy_from(_source, destination):
            path = Path(destination)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"file")

    env = SimpleNamespace(
        runner=FakeRunner(),
        env_spec=SimpleNamespace(
            observation=[SimpleNamespace(resolution=[1920, 1080])]
        ),
    )
    try:
        capture_observation_window(
            env,
            mode="paused",
            duration_ms=0,
            frames_per_observation=1,
            turn=0,
            host_dir=tmp_path / "artifacts",
        )
    except RuntimeError as error:
        assert "captured [1280, 720], configured [1920, 1080]" in str(error)
    else:
        raise AssertionError("capture accepted incompatible observation coordinates")


def test_remote_control_uses_the_standard_remote_environment_transport(tmp_path: Path) -> None:
    remote_observation = {
        "screen": {"path": "/worker/turn/frame-001.png"},
        "frames": [
            {"path": "/worker/turn/frame-000.png", "offset_ms": 0},
            {"path": "/worker/turn/frame-001.png", "offset_ms": 100},
        ],
        "capture_manifest": "/worker/turn/manifest.json",
        "time": {"task_time_ms": 100},
    }

    class FakeRemoteEnv:
        env_id = "env-1"
        local_artifacts_dir = tmp_path

        def __init__(self):
            self.requests = []
            self.fetches = []

        def _request(self, method, endpoint, **kwargs):
            self.requests.append((method, endpoint, kwargs))
            return JsonResponse({"observation": json.loads(json.dumps(remote_observation))})

        def fetch_path(self, remote_path, local_path):
            self.fetches.append((remote_path, local_path))
            Path(local_path).parent.mkdir(parents=True, exist_ok=True)
            Path(local_path).write_bytes(b"file")
            return local_path

    env = FakeRemoteEnv()
    control = RemoteEvaluationControl(env)
    observation = control.capture(
        mode="paused",
        duration_ms=100,
        frames_per_observation=2,
        turn=3,
    )
    assert env.requests[0][1] == "/envs/env-1/weird/capture-window"
    assert len(env.fetches) == 3
    assert observation["screen"]["path"] == observation["frames"][-1]["path"]
    assert Path(observation["capture_manifest"]).is_file()


def test_worker_extension_configures_only_weird_protocol_values(monkeypatch) -> None:
    env = SimpleNamespace(
        env_spec=SimpleNamespace(security=SimpleNamespace(resolved_env={}))
    )
    monkeypatch.setattr(remote_worker, "_environment", lambda _env_id: env)
    client = remote_worker.gym_worker.app.test_client()

    response = client.post(
        "/envs/env-1/weird/configure",
        json={
            "environment": {
                "WEIRD_CAPTCHA_TIME_MODE": "paused",
                "WEIRD_CAPTCHA_START_PAUSED": "1",
                "SEED": "42",
            }
        },
    )
    assert response.status_code == 200
    assert env.env_spec.security.resolved_env["WEIRD_CAPTCHA_TIME_MODE"] == "paused"

    rejected = client.post(
        "/envs/env-1/weird/configure",
        json={"environment": {"ARBITRARY_COMMAND": "not allowed"}},
    )
    assert rejected.status_code == 400
    assert "unsupported environment keys" in rejected.get_json()["error"]


def test_worker_extension_exposes_fixed_clock_commands(monkeypatch) -> None:
    sentinel_env = object()
    monkeypatch.setattr(remote_worker, "_environment", lambda _env_id: sentinel_env)
    monkeypatch.setattr(
        remote_worker,
        "time_command",
        lambda env, command: {"env_matches": env is sentinel_env, "command": command},
    )
    client = remote_worker.gym_worker.app.test_client()

    response = client.post("/envs/env-1/weird/time", json={"command": "settle-pause"})
    assert response.status_code == 200
    assert response.get_json()["status"] == {
        "env_matches": True,
        "command": "settle-pause",
    }

    rejected = client.post("/envs/env-1/weird/time", json={"command": "shell"})
    assert rejected.status_code == 400


def test_worker_advertises_the_weird_cua_capability(monkeypatch) -> None:
    observed = []
    preflight_calls = []
    monkeypatch.setattr(
        remote_worker.gym_worker,
        "run_runner_preflight",
        lambda *, must_support, skip: (
            preflight_calls.append((must_support, skip)) or ["qemu"]
        ),
    )
    monkeypatch.setattr(
        remote_worker.gym_worker,
        "main",
        lambda: observed.extend(
            remote_worker.gym_worker.run_runner_preflight(
                must_support=["qemu"],
                skip=False,
            )
        ),
    )
    remote_worker.main()
    assert preflight_calls == [(["qemu"], False)]
    assert observed == [WEIRD_CUA_WORKER_CAPABILITY]


def test_qwen_screen_loader_accepts_path_image_and_remote_base64(tmp_path: Path) -> None:
    path = tmp_path / "screen.png"
    Image.new("RGB", (20, 10), "red").save(path)
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")

    assert image_from_screen({"path": str(path)}).size == (20, 10)
    assert image_from_screen({"image": Image.new("RGB", (8, 6), "blue")}).size == (8, 6)
    assert image_from_screen({"png_b64": encoded}).size == (20, 10)
    assert observation_frames({"screen": {"path": str(path)}}) == [
        {"path": str(path)}
    ]


def test_qwen_sends_every_frame_at_the_native_display_resolution(tmp_path: Path) -> None:
    source = tmp_path / "native.png"
    Image.new("RGB", (1920, 1080), "navy").save(source)
    agent = object.__new__(WeirdQwen35VLAgent)
    agent.display_resolution = [1920, 1080]
    agent.save_folder_custom = str(tmp_path)
    agent.step_idx = 3
    agent.b64_to_path = {}
    agent.original_sizes = []

    _latest_encoded, latest_path = agent.process_image(str(source))
    _earlier_encoded, earlier_path = agent._process_frame(
        {"path": str(source)},
        step=4,
        index=0,
    )

    with Image.open(latest_path) as latest:
        assert latest.size == (1920, 1080)
    with Image.open(earlier_path) as earlier:
        assert earlier.size == (1920, 1080)
    assert agent.original_sizes == [(1920, 1080)]
    assert agent.processed_size == (1920, 1080)


def test_qwen_multiframe_step_serializes_only_native_resolution_images(
    tmp_path: Path,
    monkeypatch,
) -> None:
    frame_paths = []
    for index in range(6):
        path = tmp_path / f"source-{index}.png"
        Image.new("RGB", (1920, 1080), (index * 20, 0, 0)).save(path)
        frame_paths.append(str(path))

    agent = object.__new__(WeirdQwen35VLAgent)
    agent.display_resolution = [1920, 1080]
    agent.save_folder_custom = str(tmp_path)
    agent.step_idx = -1
    agent.b64_to_path = {}
    agent.original_sizes = []
    agent.frame_sequences = []
    agent._current_extra_frames = []
    agent.screenshots = []
    agent.history = []
    agent.responses = []
    agent.history_n = 1
    agent.image_max = 20
    agent.fold_size = 10
    agent.task_description = "Confirm the code."

    def parent_step(self, obs, _action_outputs):
        self.step_idx += 1
        encoded, _path = self.process_image(obs["screen"]["path"])
        self.screenshots.append(encoded)
        return self.build_messages(encoded)

    monkeypatch.setattr(WeirdQwen35VLAgent.__mro__[1], "step", parent_step)
    messages = agent.step(
        {"frames": [{"path": path} for path in frame_paths]},
        [],
    )
    image_urls = [
        item["image_url"]["url"]
        for item in messages[-1]["content"]
        if item["type"] == "image_url"
    ]

    assert len(image_urls) == 6
    for url in image_urls:
        with Image.open(BytesIO(base64.b64decode(url.split(",", 1)[1]))) as image:
            assert image.size == (1920, 1080)


def test_qwen_messages_preserve_chronological_frame_order() -> None:
    agent = object.__new__(WeirdQwen35VLAgent)
    agent._current_extra_frames = ["first", "second"]
    agent.frame_sequences = []
    agent.step_idx = 0
    agent.history_n = 1
    agent.image_max = 20
    agent.fold_size = 10
    agent.screenshots = ["third"]
    agent.history = []
    agent.responses = []
    agent.task_description = "Do the task"
    agent.display_resolution = [1280, 720]

    messages = agent.build_messages(
        "third",
        history_n=1,
        image_max=20,
        fold_size=10,
    )
    user_content = messages[-1]["content"]
    image_urls = [
        item["image_url"]["url"]
        for item in user_content
        if item["type"] == "image_url"
    ]
    assert image_urls == [
        "data:image/png;base64,first",
        "data:image/png;base64,second",
        "data:image/png;base64,third",
    ]
    assert agent.frame_sequences == [["first", "second", "third"]]

    agent.build_messages(
        "third",
        history_n=1,
        image_max=20,
        fold_size=10,
    )
    assert agent.frame_sequences == [["first", "second", "third"]]


def test_qwen_context_backoff_folds_complete_old_observations() -> None:
    agent = object.__new__(WeirdQwen35VLAgent)
    agent._current_extra_frames = ["new-first"]
    agent.frame_sequences = [["old-first", "old-last"]]
    agent.step_idx = 1
    agent.history_n = 100
    agent.image_max = 20
    agent.fold_size = 10
    agent.screenshots = ["old-last", "new-last"]
    agent.history = ["Clicked the old target"]
    agent.responses = ["old response"]
    agent.task_description = "Do the task"
    agent.display_resolution = [1280, 720]

    messages = agent.build_messages(
        "new-last",
        history_n=100,
        image_max=2,
        fold_size=1,
    )
    assert messages[1]["content"][0] == {
        "type": "text",
        "text": "This screenshot has been collapsed.",
    }
    latest_images = [
        item["image_url"]["url"]
        for item in messages[-1]["content"]
        if item["type"] == "image_url"
    ]
    assert latest_images == [
        "data:image/png;base64,new-first",
        "data:image/png;base64,new-last",
    ]


def test_weird_corpus_is_enumerated_by_gym_anything_registry() -> None:
    pairs = evaluation_pairs(split="all")
    assert len(pairs) == 75
    assert len({task_id for _environment, task_id in pairs}) == 75
    assert all(environment.name.endswith("_env") for environment, _task in pairs)
