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

Use the existing Gym master and the benchmark worker entry point. On each allocated CPU node,
activate the environment containing both packages and export `SANDWEAVE_HOME`:

```bash
weird-cua-worker --master-url http://MASTER:5900 --max-envs 2 \
  --must-support-runner weird_captcha,sandweave
```

Choose capacity to fit allocated CPU and RAM. There is no KVM prerequisite.
Keep the SDK worker in this long-lived worker job step: Slurm can remove a
detached child when the step that launched it exits. Do not share an SDK worker
launched by a short-lived diagnostic step with independent client steps.

The evaluator forwards `inner=sandweave` through the normal remote override
payload. The worker resolves the benchmark by name and checks task identity.
The entry point adds fixed benchmark input/receipt routes to the Gym worker.
It does not replace the master, registry, transport, or worker allocation.
An old `gym-anything-worker` does not expose these routes and must be relaunched
with this entry point before running the live Codex adapter.

## Scheduled input

The wrapper uploads and starts one input service inside each live task sandbox.
Sandweave carries commands and receipts over that process's authenticated SDK
stdin/stdout streams, including when guest networking is disabled. No new
privileged model-facing operation is exposed. QEMU retains its existing input
and host-side scheduling path; this service is specific to Sandweave.

Actions are validated and queued before their deadline. The sandbox waits on
its monotonic clock, relative to the environment start, and injects through a
persistent copy of Sandweave's installed native XTEST helper. Neither the master nor the gateway waits until the deadline
before sending input. A later queued release does not block an immediate press.
An explicit wait within a batch yields to other requests while preserving that
batch's ordering. Equal deadlines use arrival order. Past deadlines run when
the input executor is available. This is not a hard real-time guarantee under
CPU contention or a busy input executor.

The Sandweave path uses the installed helper's protocol v1, tested with SDK
0.2.14. This is an internal native protocol dependency: an unsupported helper
version is rejected during preparation, rather than falling back to host-side
waiting. The helper retains Sandweave's Unicode keymap allocation and browser
drain behavior. The benchmark does not patch the SDK or its helper. Input uses
a separate helper connection from screenshots; it does not trigger frame capture.

With Sandweave, all three live Codex modes return input acknowledgements without capturing an
image. Request `screenshot` separately for one frame. Paused mode retains its
frame window. Timestamped modes expose sandbox queue, injection-start, X-server
completion, and acknowledgement-send timestamps; pure live does not expose them.
X-server completion means X11 processed the batch, not that the browser rendered
another frame. Screenshot capture has its own timestamp and never substitutes
for an input receipt. Retrying the same request ID does not inject or count it
twice. Connection loss returns an error, not an automatic input replay.

Gateway closure and the post-task hook cancel queued input and release held
keys/buttons before verification. The sandbox confirms shutdown over the same
channel. No queued input is retained for the next episode.

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

The original integration smoke checks used a gateway-side deadline wait. Their
3 ms local and 44 ms remote target-to-return samples did not establish
sandbox-side scheduling. They are not measurements of the input service above.
CPU-memory checkpointing was not exercised.

On the pre-sync feature branch, the full benchmark suite was **not green**: three historical tests in
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

## Sandbox scheduling verification (2026-09-12)

The follow-up change is confined to `weird-cua-bench`. It does not modify
Gym-Anything or Sandweave, and it preserves QEMU's previous input path. Tests
used a separate 8-CPU/64-GB allocation on `babel-w9-32`, SDK 0.2.14, and
Rotating Keyboard D3 Full with no inference model. Sandboxes had networking
disabled; control used the authenticated SDK process stream.

Each remote run sent 60 batches, each 250 ms before its requested execution
time, through an HTTP action gateway, Gym master, and benchmark worker.
Times below are milliseconds, reported as median / p95:

| Interval | Recording off | Recording on |
| --- | ---: | ---: |
| Requested time → sandbox injection starts | 0.45 / 1.57 | 0.19 / 1.92 |
| Injection starts → X-server acknowledgement | 1.16 / 1.76 | 5.64 / 58.76 |
| Full HTTP round trip, subtracting time spent waiting in the guest queue | 55.40 / 101.07 | 49.05 / 92.29 |

The last row includes transport, input execution, step accounting, and response
logging. It is not pure network latency or deadline error. Recording increases
the X-server acknowledgement tail; recording remains off by default. These
samples do not establish a hard upper bound under contention.

A separate browser probe recorded 15 trusted keyboard/click events. Requested
time → browser event was 3.24 ms median and 12.64 ms maximum. Browser event
timestamps have approximately 1 ms precision. Held letter keys, a Shift chord,
held mouse buttons, a drag, and exact text entry of `héllo + 世界` passed.
The initial libxdo attempt dropped Unicode characters; it was removed, not
retained as a fallback.

Both remote runs also checked that a later scheduled release does not block an
immediate press or a screenshot, and that delaying the response by 200 ms does
not change the guest execution timestamp. Unit tests cover queue ordering,
invalid batches, duplicate requests, cancellation, independent screenshot/input
requests, step accounting, and event-by-event agreement with the SDK serializer.

To repeat the remote checks, supply a JSON connection file containing
`{"master_url": "http://MASTER:PORT"}`. It can also contain CPU-local `mounts`
for staged runtime inputs. Use a new output directory for every invocation:

```bash
python -m weird_captcha_gym.tools.profile_scheduled_input \
  --connection-file CONNECTION.json --output-dir outputs/scheduled-off
python -m weird_captcha_gym.tools.profile_scheduled_input \
  --connection-file CONNECTION.json --output-dir outputs/scheduled-on --recording
```

`--local-browser-probe` runs the trusted browser-event and text-entry checks on
the worker node. It uses a local sandbox and requires that node's
`SANDWEAVE_HOME`; it is a diagnostic, not part of the model's action interface.

Raw samples, receipts, browser events, and input checks are retained under
`outputs/sandweave_integration_20260912/scheduled-input-native/` in `off/`,
`on/`, and `browser/`. This directory is Git-ignored.

The targeted scheduler, gateway, action-contract, and runner suites passed
**280 tests, with 1 skipped** (`contracts.xml`). The final four-mode smoke run
passed (`four-modes/results.json`): paused returned six frames with no idle
clock advance, while each live mode returned one frame with a running clock.
The timestamped-execution case also exercised scheduled input through
`env.step`, not only the Codex gateway. A fresh master/worker smoke after the
final transport cleanup passed another nine scheduled inputs and the concurrency
checks, saved in `../scheduled-input-verified/remote/`.

On that pre-sync checkout, the last full-suite attempt stopped at six failures
after 427 passes: the three frozen
75-task manifest assertions and three Compass Vault verifier subprocess import
failures. A separate real-time suite run had 24 passes and one browser-window
readiness timeout. Those tests and environment files were not modified to hide
the failures. These results precede synchronization with `main` at `aa085c8`;
the integration PR checks validate the combined tree, including main's newer
manifest tests and isolated-browser dependencies.
