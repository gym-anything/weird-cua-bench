# Runner Integration Plan v0

Date: 2026-07-08. Superseded in part on 2026-08-04, see the v1 note below.

This note records how Weird CUA Bench integrates with Gym-Anything. Weird CUA is an installable Gym-Anything benchmark package. It does not fork, vendor, or imitate Gym-Anything.

## v1 note: the modularity migration (2026-08-04)

Gym-Anything's modularity redesign (its `docs/design/modularity.md`) made runners the official third-party "world" door: the runner registry accepts entry points and locators, per-runner facts live on the runner class, `EnvSpec.runner_options` carries world configuration opaquely, unknown observation modalities are delegated to the runner, and worlds that own time receive wait and custom actions.

Under that premise, the v0 rule "do not write a custom Weird CAPTCHA runner" is inverted: the clock, the frame-window observation schedule, guest configuration, and artifact collection are exactly the world-owned behaviors the runner door exists for. They now live in `weird_captcha_gym/runner.py` (`WeirdCaptchaRunner`, registry key `weird_captcha`), which composes the inner VM runner and replaces the former evaluation control layer, the `weird-cua-worker` route extension, and the `WeirdRemoteGymEnv` subclass. `weird-cua-evaluate` schedules turn-based agents over `env.reset`/`env.step` and delegates autonomous CLI agents to Gym-Anything's action gateway. Everything else in v0 stands: no second CLI, no per-mechanic action spaces, no normalized action executor, no bypassing Gym-Anything artifacts or verifier dispatch.

## Ownership boundary

Gym-Anything owns environment loading, runner selection, reset, actions, episode limits, trajectories, verification, artifacts, and remote scheduling. Weird CUA supplies environment and task files plus its live-versus-paused observation schedule.

The `weird-cua-evaluate` entry point exists because the Weird CUA protocol can send a chronological paused frame window and can stop task time during model inference. All live modes instead expose one instantaneous frame per observation request. It creates local environments with `gym_anything.from_config` and remote environments by benchmark name with `RemoteGymEnv.from_benchmark`, forwarding the same runner-option overrides through either path. It does not define another runner or action API.

Remote runs use the normal Gym-Anything master and worker. The client creates an environment by benchmark and environment name, supplies a task-content digest, and sends `EnvSpec.runner_options` through Gym-Anything's runtime override field. Actions, observation capture, artifacts, verification, retries, and cleanup use the standard remote routes. No benchmark-specific worker, client subclass, route, scheduler, or transport is introduced.

## Runner Facts From Code Reading

- `gym_anything.config.loading.from_config()` loads `env.json` plus `tasks/<task_id>/task.json`, resolves mounts relative to the benchmark tree, validates specs, and attaches `env_root`/`task_root` for verifiers.
- `GymAnythingEnv.reset()` selects and starts the configured runner, executes `env.hooks.pre_start`, `env.hooks.post_start`, optional reset hooks, then task `hooks.pre_task`.
- `pre_start` is the right place for package installation and one-time provisioning.
- `post_start` is the right place for long-lived services: local puzzle server, browser launch, desktop setup.
- `pre_task` is the right place to initialize the task state. For CAPTCHA-style mechanics, the long-lived local server may generate the concrete challenge on each `/state` request so browser refresh behaves like a real CAPTCHA refresh.
- `GymAnythingEnv.step()` sends every non-control action directly to `runner.inject_action(action)`, then captures the next screenshot.
- Control actions are already supported: `{"action": "wait"}` and `{"action": "screenshot"}`.
- `_complete_episode()` runs task `hooks.post_task`, waits briefly, captures `post_verification.png`, captures `final.png`, and dispatches the verifier.
- Program verifiers receive `traj`, `env_info`, and `task_info`. `env_info` includes `copy_from_env`, `copy_to_env`, and `exec_capture` when the runner supports them.
- CUA-World tasks commonly use `post_task` to export `/tmp/task_result.json`, then verifiers copy it back through `copy_from_env`.

## Consequences

- Keep Weird-specific world behavior in `WeirdCaptchaRunner`; do not duplicate the VM runner or remote stack.
- Do not write a separate normalized action executor inside the benchmark.
- Do not create a second benchmark CLI that copies `gym-anything benchmark`.
- Keep `weird-cua-evaluate` limited to the Weird CUA observation schedule.
- Do not create per-mechanic action spaces.
- Do not bypass Gym-Anything artifacts or verifier dispatch.
- Use Gym-Anything's existing runner action format:

```json
{"mouse": {"left_click": [x, y]}}
{"mouse": {"right_click": [x, y]}}
{"mouse": {"double_click": [x, y]}}
{"mouse": {"triple_click": [x, y]}}
{"mouse": {"move": [x, y]}}
{"mouse": {"left_click_drag": [[x1, y1], [x2, y2]]}}
{"mouse": {"scroll": dy}}
{"keyboard": {"text": "text"}}
{"keyboard": {"keys": ["ctrl", "s"]}}
```

External model APIs, including APIs that emit normalized coordinates or named computer-use commands, should be adapted in the agent layer before calling `env.step()`.

## Benchmark Layout

The benchmark stays under:

```text
weird_captcha_gym/
```

The existing 25 mechanic folders remain:

```text
weird_captcha_gym/environments/<mechanic_id>_env/
```

Shared code should be added once and mounted into every env:

```text
weird_captcha_gym/shared_runtime/
  app/
  server/
  mechanics/
weird_captcha_gym/shared_scripts/
  install_puzzle_runtime.sh
  setup_puzzle_runtime.sh
  setup_task.py
  export_result.sh
```

Per-env `scripts/*.sh` can be thin wrappers that call the shared scripts. Per-task files should stay small: `task.json`, `setup_task.sh`, `export_result.sh`, `verifier.py`, optional fixtures, and evidence.

## Runtime Design

Use the Linux desktop runner selected by Gym-Anything with `base: ubuntu-gnome-systemd_highres`.

`pre_start`:

- install only stable dependencies needed by every mechanic;
- avoid network after provisioning where possible;
- install Chromium or use the browser already present in the base image if available;
- install Python runtime dependencies for a local server if needed.

`post_start`:

- start a local puzzle server on `127.0.0.1`;
- open the browser in a controlled window size or fullscreen;
- point the browser at a neutral waiting route.

`pre_task`:

- read task metadata;
- initialize `public_state.json` and `ground_truth.json`, if needed;
- write them under `/tmp/weird_captcha_gym/`;
- tell the running browser/server to load the task route;
- remove stale `result.json` and `/tmp/task_result.json`.

During the episode:

- the agent only sees screenshots and acts with mouse/keyboard;
- the browser app renders the mechanic and records final UI state through the local server;
- for dynamic CAPTCHA-style tasks, browser refresh requests a fresh generated challenge from the server;
- hidden ground truth remains outside the rendered DOM and outside agent-visible files.

`post_task`:

- ask the runtime/server to flush final state if necessary;
- combine final UI state and hidden ground truth into `/tmp/task_result.json`;
- include enough fields for outcome scoring and debugging.

`verifier.py`:

- use `env_info["copy_from_env"]("/tmp/task_result.json", local_path)`;
- compare final result against task ground truth;
- return `{"passed": bool, "score": number, "feedback": string}`.

## Runner Decision And Evidence

Use Gym-Anything's normal runner selection path. On the current Apple Silicon macOS host, Docker is unavailable and Gym-Anything selects `AVFRunner` for `base: ubuntu-gnome-systemd_highres`, backed by `vfkit` and `gvproxy`.

Evidence captured on 2026-07-08:

- Runner: `AVFRunner`
- Env: `weird_captcha_gym.reverse_identity_gate_env@0.1`
- Task: `reverse_identity_gate_seed_0001@0.1`
- Guest platform: Linux desktop, 1280x720
- Reset elapsed time after base image provisioning: 23.561 seconds
- Screenshot: `weird_captcha_gym/evidence/reverse_identity_gate_avf_reset.png`
- Session metadata: `weird_captcha_gym/evidence/reverse_identity_gate_avf_session.json`
- Run log: `weird_captcha_gym/evidence/reverse_identity_gate_avf_reset.log`

The captured screenshot shows the browser puzzle running inside the AVF VM. This run was reset/screenshot evidence only; it intentionally did not perform the puzzle solve, so the episode summary records a verifier failure due to no submitted UI result.

## Runner Proof Versus Benchmark Quality

`reverse_identity_gate_env` proved that Gym-Anything can boot the AVF runner, start the local browser runtime, export `/tmp/task_result.json`, and dispatch a program verifier. It is not a benchmark-quality task.

Any future task promoted to `metadata.status = "benchmark_ready"` and the `verified` surface must satisfy a stricter evidence set:

- `from_config(..., task_id=...)` loads the env and task.
- `reset()` runs `pre_start`, `post_start`, and `pre_task`.
- the first screenshot shows the CAPTCHA-like surface, not a blank desktop.
- a failed attempt shows only `FAIL` and loads a new instance.
- a passing run produces a verifier score of 100.
- visible UI contains no partial correctness, hints, debug text, tutorial copy, or "end the episode" wording.
- `traj.jsonl`, screenshots, and `/tmp/task_result.json` copy path all work.
- `weird_captcha_gym/tools/audit_quality.py --task <task_id> --strict` passes.
