# Weird CUA Bench

Interaction-first visual puzzles for evaluating screenshot-driven computer-use agents.

The benchmark starts from CAPTCHA-like and internet puzzle mechanics, but its target is broader: strange, human-manageable tasks whose real difficulty comes from acting over time. The current candidate corpus contains 75 built puzzle environments. Two early rejected pilots remain documented as implementation history, but both were later replaced end to end with interaction-first designs.

[Explore the dashboard](https://gym-anything.github.io/weird-cua-bench/)

Every built puzzle can be opened from that site with one click. The task UI and its existing Python grader run entirely in the browser through WebAssembly; ordinary exploration needs no clone, terminal, pairing key, localhost helper, or VNC.

All 75 environment dossiers include a successful solution film. Seventy-four were recorded against frozen task contracts with live-server, independent-grader, and exported-verifier agreement; the earlier Semantic Drag-Drop walkthrough remains clearly labeled as the one pre-freeze recording.

## Repository scope

This is the standalone home of the Weird CUA benchmark. It contains only:

- the Weird CUA environment and task folders;
- procedural generators, browser runtime, graders, and exported verifiers;
- the evidence-backed dashboard and solution media;
- benchmark-specific tests and design documentation.

It deliberately excludes CUA-World, other Gym-Anything environments, the mined Survey archive, and Gym-Anything's core source tree. Gym-Anything remains an optional runtime dependency for isolated VNC sessions and agent evaluations.

The `verified` split is intentionally empty. Scripted browser success proves wiring, not human usability or agent difficulty.

## Optional local controls

The public dashboard is enough to browse and play all 75 built puzzles. Clone and run locally only when you need persistent reviews, fresh authoritative challenges, VNC sessions, evaluation execution, filesystem paths, or process controls:

```bash
python run.py
```

This opens the complete dashboard at <http://127.0.0.1:8767>. There is no pairing step in local mode. To enable runner-backed VNC sessions, install the optional runtime:

```bash
python -m pip install -e ".[runtime]"
```

To attach those advanced local controls to the hosted dashboard:

```bash
python run.py --hosted
```

The launcher starts the authenticated loopback companion and opens an automatically paired dashboard tab. No pairing key needs to be copied. Browser play remains static and zero-setup; reviews, evaluation execution, VNC credentials, filesystem paths, and administrative controls stay on the collaborator's own computer.

The public browser runtime is an exploration surface, not a secure evaluation endpoint: because it has no server, its finite challenge pool and grading truth are inspectable in developer tools. Use the local/VNC benchmark path for authoritative agent runs.

## Temporal evaluation modes

Every environment has a task-time limit, observation-window duration, and frame count in `weird_captcha_gym/real_time.json`. All four modes use the same frame schedule. `paused` freezes task time during both the model response and native input delivery, then advances exactly one configured observation window after the browser confirms the input event. The other three modes keep the task running continuously. `live_timestamped` adds frame timestamps and measured action-latency metadata. `live_timestamped_execution` adds the same metadata and lets the model request an absolute `execute_at_s` on that clock. Plain `live` provides neither timestamps nor scheduled execution.

Install the evaluation dependencies, then choose the condition with the single `--temporal-mode` flag:

```bash
python -m pip install -e ".[evaluation]"
weird-cua-evaluate \
  --env-dir weird_captcha_gym/environments/rotating_keyboard_env \
  --task rotating_keyboard_seed_0001 \
  --agent GeminiComputerUseAgent \
  --agent-args '{"model":"gemini-3.5-flash"}' \
  --temporal-mode live_timestamped_execution
```

Public browser play includes an observation inspector. Choose live or paused mode inside the puzzle tab, then capture one configured observation window to inspect the same frame count used by evaluation. Authoritative evaluation preserves the environment's native desktop resolution so screenshot coordinates and action coordinates share one space. In paused browser play, mouse and keyboard handlers run against the frozen state; timers, physics, and animations advance only when the next observation window is captured. The browser will ask you to share the current tab before its first pixel capture; the inspector is hidden from the captured frames.

This browser control is for inspection. Authoritative evaluation uses `--temporal-mode` and records its frames and timing manifest in the episode artifacts.

The benchmark's world behavior lives in `WeirdCaptchaRunner`, registered with Gym-Anything's runner registry under the key `weird_captcha` and declared by every environment's `env.json`. It composes the inner VM runner and owns the puzzle clock, frame-window observation capture, guest configuration, and benchmark artifact collection. The evaluator is a thin turn scheduler over the standard `env.reset`/`env.step` doors. Gym-Anything creates the environment, applies actions, records the trajectory, runs the verifier, and owns remote scheduling. `Qwen35VLAgent` automatically uses the Weird CUA adapter so all chronological frames reach the model while retaining the latest Gym-Anything implementation.

Remote evaluation uses the plain Gym-Anything master and worker. The worker advertises the `weird_captcha` runner through the registry, the client creates environments by benchmark name with a task-content digest, and the run condition travels as spec overrides:

```bash
gym-anything-master --port 5000
gym-anything-worker --master-url http://master:5000 --must-support-runner weird_captcha
weird-cua-evaluate \
  --env-dir weird_captcha_gym/environments/rotating_keyboard_env \
  --task rotating_keyboard_seed_0001 \
  --agent Qwen35VLAgent \
  --agent-args '{"model":"Qwen/Qwen3.5-397B-A17B"}' \
  --temporal-mode paused \
  --remote-url http://master:5000
```

There is no benchmark-specific worker, route, or remote client anymore. Clock commands ride the standard action channel and answer through `info["world_action_results"]`; observation frames come back over the standard `fetch_path` route into `~/.captcha-bench/remote-episodes/`.

Add `--fast-io` when the selected Gym-Anything runner reports FastIO support. AVF does not support it.

## Validate

```bash
python -m pip install -e ".[test]"
python -m pytest tests -q
python weird_captcha_gym/tools/smoke_realtime_control.py
python weird_captcha_gym/tools/smoke_realtime_environments.py
```

The strict promotion audit is deliberately red while the corpus remains candidate-only:

```bash
python weird_captcha_gym/tools/audit_quality.py --strict
```

Its blockers are the human/VNC/agent evidence still required before anything enters the empty `verified` split; do not weaken task status merely to make this command green.

Read [`weird_captcha_gym/docs/interaction-puzzle-field-notes.md`](weird_captcha_gym/docs/interaction-puzzle-field-notes.md) before changing any puzzle. It records the binding interaction-first doctrine, human feedback, prohibited shortcuts, and current validation limits.

## License

The repository is MIT licensed. Third-party runtime notices, including Matter.js, are stored beside the vendored assets that use them.
