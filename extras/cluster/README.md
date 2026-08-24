# Cluster evaluation launchers

These scripts are the tracked, path-independent replacements for the launch
scripts recovered from `/data/user_data/pranjala/weird_cua_restore`. They assume
the current checkout has been installed into `.venv`; outputs and node-local
cache locations are supplied explicitly instead of pointing back at the
recovered orphan checkout. The launchers materialize the repository's ignored,
generated controlled-task matrix from each environment's tracked
`controls.json` before creating environments.

Run the four Codex temporal conditions together:

```bash
extras/cluster/run_four_codex_modes.sh \
  weird_captcha_gym/environments/rotating_keyboard_env \
  rotating_keyboard_d3_full_seed_0001 \
  /path/to/evaluations/luna-rk-d3 \
  http://babel-p9-28:5900
```

The default agent is `CodexCliAgent` with `gpt-5.6-luna`, `xhigh` reasoning,
and persisted sessions. Each condition writes a separate log and summary. The
summary identifies the episode directory; exported Codex session JSONL files
are under that episode's `cli_harness/codex_home/sessions/` directory.

Run the 75 x 5 x 2 x 2 matrix with a turn-based agent:

```bash
OUTPUT_ROOT=/path/to/evaluations/qwen-full1500 \
VLM_BASE_URL=http://babel-p9-28:8600/v1 \
REMOTE_URL=http://babel-p9-28:5900 \
AGENT=weird_captcha_gym.evaluation.qwen38:WeirdQwen38VLAgent \
AGENT_ARGS='{"model":"Qwen/Qwen3.8-27B","temperature":0.6,"top_p":0.95,"top_k":20,"reasoning_effort":"low"}' \
PARALLEL=20 \
extras/cluster/run_full_matrix.sh
```

Start a persistent QEMU worker after staging its cache to node-local storage:

```bash
extras/cluster/run_qemu_worker.sh 8 worker-p9-28-a http://babel-p9-28:5900
```

Set `SOURCE_QEMU_CACHE` and `LOCAL_QEMU_CACHE` when the defaults do not match
the host. The worker advertises both `weird_captcha` and `qemu` and restarts
after a process-level failure.

## Repository and runtime ownership

The benchmark, controlled-task definitions, evaluator, and cluster launchers
belong to `gym-anything/weird-cua-bench`. The reusable runtime, remote client,
runner contracts, and Codex CLI harness belong to `cmu-l3/gym-anything`.
`pyproject.toml` pins the exact Gym commit that the benchmark expects; update
that pin and `uv.lock` together whenever a required Gym change is published.

Generated controlled-task directories are ignored build products. Recreate
them from the tracked `controls.json` files with:

```bash
.venv/bin/python weird_captcha_gym/tools/materialize_controlled_tasks.py \
  --all-controlled \
  --output-root weird_captcha_gym/environments
```

For the 2026-08-24 recovery, the authoritative clean checkout is
`/data/user_data/pranjala/weird-cua-bench` on branch
`recovery/timed-codex-20260824`. The legacy
`/data/user_data/pranjala/weird_cua_restore/repo-modularity` tree is runtime
input only: do not edit, delete, or replace it while the old master reports
active environments. Cut over the master and workers to the clean checkout
only after active environments reach zero, then archive the legacy tree. Do
not point the clean client at legacy workers during that transition: the task
digest contract changed to exclude runtime bytecode caches, so the master,
workers, and clients must move to the pinned Gym commit together.
