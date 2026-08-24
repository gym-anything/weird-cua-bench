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
