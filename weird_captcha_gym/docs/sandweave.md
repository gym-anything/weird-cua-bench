# Sandweave execution backend

The benchmark continues to own the puzzle clock, action contract, frame windows,
and task artifacts. Sandweave replaces only the inner desktop runner through
Gym-Anything's runner registry. No environment definitions or graders change.

Install the benchmark's `sandweave` extra on Python 3.11+ and prepare a
Sandweave 0.2.14+ runtime containing `gym-anything/ubuntu-qemu-nosnap`.
Set `SANDWEAVE_HOME` to that runtime's writable sandbox home. The imported
Gym Ubuntu image is required; the stock Sandweave GNOME image is not a substitute.

From the repository root, using a virtual environment:

```bash
uv pip install '.[sandweave]'
```

Add `--inner-runner sandweave --fast-io` to an existing `weird-cua-evaluate`
command. `--temporal-mode` retains all four values:

| Mode | Observation | Clock during model computation | Scheduled actions |
| --- | --- | --- | --- |
| `paused` | Configured frame window | Paused | No |
| `live` | One frame | Running | No |
| `live_timestamped` | One timestamped frame | Running | No |
| `live_timestamped_execution` | One timestamped frame | Running | Optional `execute_at_s` |

The environment start remains the clock origin. Existing observation-to-action
latencies, action completion times, and frame capture times remain available.
A zero-duration live observation uses a one-frame capture, not a continuous
FFmpeg window followed by a shutdown wait. Paused frame scheduling is unchanged.

## CPU workers

Use the existing Gym master and worker commands. On each allocated CPU node,
activate the environment containing both packages and export `SANDWEAVE_HOME`:

```bash
gym-anything-worker --master-url http://MASTER:5900 --max-envs 2 \
  --must-support-runner weird_captcha,sandweave
```

Choose capacity to fit allocated CPU and RAM. There is no KVM prerequisite.
Keep the SDK worker in this long-lived worker job step: Slurm can remove a
detached child when the step that launched it exits. Do not share an SDK worker
launched by a short-lived diagnostic step with independent client steps.

The evaluator forwards `inner=sandweave` through the normal remote override
payload. The worker resolves the benchmark by name and checks task identity.
This integration does not replace the master, registry, transport, or scheduler.

`--use-cache --cache-level pre_start` uses the runner's filesystem checkpoints.
`--use-savevm` additionally requests CPU memory checkpoints. The default runner
and all existing QEMU commands remain unchanged.

## Recording and retained data

Recording stays off in the benchmark's environment specifications. To enable it
through the public Python API, pass `recording={"enable": True}` in the environment
overrides alongside `runner_options={"inner": "sandweave", ...}`.

The worker's episode directory receives `recording.mp4` and
`sandweave-recording/`. The latter retains original segments, per-frame timing,
missed-capture counts, and checksums. These are continuous desktop recordings,
not videos assembled from model observations. The recorder starts with the
sandbox, so recordings include setup. Native recording has no separate manual
pause/resume API and no audio track. Neither limitation changes the puzzle clock.
The evaluator's client-side observation mirror is separate from these worker-side
recordings; consult the worker episode path for the original video.

Sandbox homes, caches, outputs, and trajectories remain ignored. Never place
Codex credentials or sessions inside a disposable sandbox home.

## Reproduce integration checks

Run these inside a dedicated CPU allocation, one command after the preceding
command exits. They use no inference model and do not measure puzzle success:

```bash
python -m weird_captcha_gym.tools.smoke_sandweave \
  --output-dir outputs/sandweave-smoke --stage-mounts --recording

python -m weird_captcha_gym.tools.smoke_sandweave \
  --output-dir outputs/sandweave-cache --stage-mounts --recording --use-cache \
  --modes live_timestamped_execution live_timestamped_execution

python -m weird_captcha_gym.tools.smoke_sandweave_remote \
  --output-dir outputs/sandweave-remote
```

The first checks all four modes, held-key delivery, screenshots, scheduled
execution, artifact retention, and teardown. The second checks cold setup and
checkpoint restore. The third starts its own loopback master and worker and
runs paused and scheduled-live puzzles concurrently, including HTTP frame
transfer. It closes only the environments and services it creates.

`--stage-mounts` copies runtime inputs to temporary local storage while excluding
generated Python bytecode. This avoids uploading stale NFS bytecode caches;
the scripts, UI, task definitions, and graders are unchanged. Production source
checkouts should likewise keep disposable caches outside mounted runtime inputs.

## Verified integration (2026-09-12)

The dependency pin is Gym-Anything
`c05bbbbace2c0fa285e32323e4671e9109382cdb`. It combines the previous benchmark
pin (`06fe21d230da6591acacdfeb9d30d9f8496d0dd6`) with upstream Sandweave support
(`774476d752d748a69288f2ead97f75dd9df08ddb`), preserving the runner registry,
remote protocol, and timing/action contracts. Native recording support is an
optional runner capability; it does not introduce Sandweave dispatch in the
benchmark or change task definitions or graders.

Validation used Sandweave 0.2.14, Python 3.12, and an isolated 8-CPU/64-GB job
on `babel-l5-16`, without KVM:

- Core suite: **390 passed, 23 skipped**. The built wheel includes the runner,
  Ubuntu template, and setup module.
- Benchmark runner, evaluator, action-contract, temporal-gateway, and real-time
  regression suites: **269 passed, 1 skipped**.
- Real Rotating Keyboard D3 Full: all four temporal modes passed the smoke
  assertions, including six paused frames, one live frame, paused/live clock
  behavior, input delivery, and optional scheduled execution.
- Filesystem `pre_start` checkpoints: cold creation and a subsequent restore
  both passed, with recordings retained after closure.
- An isolated master and worker ran two sandboxes concurrently, one paused and
  one scheduled-live. Benchmark-name resolution, frame transfer over HTTP,
  actions, teardown, and worker-side recording export passed.
- Screenshots and frames decoded from the continuous MP4 were visually checked.
  A recording inspected with `ffprobe` was H.264, 1920×1080, 10 FPS. Native
  metadata reported missed capture slots, so this is not a claim of ten unique
  captured frames every second.

One final local scheduled action requested at 4.805 s completed at 4.808 s.
In the remote check, an action requested at 2.335 s completed at 2.379 s;
the following frame was timestamped 2.919 s and the gateway response 3.123 s.
These are individual smoke-test measurements, not throughput estimates or
model-evaluation results. CPU-memory checkpointing was not exercised.

The full benchmark suite is **not green**: three historical tests in
`tests/test_agent_sample_runner.py` reject the expanded task population against
their frozen 75-task manifest. The run was interrupted after 17 minutes of NFS
traversal, with 34 passes and those three failures. Historical manifests were
not changed to suppress the failures. The five integration suites above were
run separately to completion.

Raw evidence is retained, Git-ignored, under
`outputs/sandweave_integration_20260912/`: `four-modes-final/results.json`,
`cache-ui-final/results.json`, `remote-final/results.json`, recordings within
their episode directories, and `final-contracts.xml`. The core report is
`outputs/sandweave-core-final.xml` in the Gym-Anything checkout.
