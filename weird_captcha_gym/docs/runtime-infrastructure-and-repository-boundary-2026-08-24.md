Clear: from now on, `gym-anything` is an immutable upstream dependency. I will not edit, commit, push, or open PRs against it for this project. All benchmark behavior, Codex-agent logic, prompts, temporal modes, launch scripts, and evaluation code belong in `weird-cua-bench`.

## What is running now

- **Inference Fleet:** run `f230d34f`, `Qwen/Qwen3.8-27B-FP8`
  - 20 running single-GPU vLLM jobs; 20 endpoints ready
  - Config: [qwen38_27b_serve_rtx6000.toml](/data/user_data/pranjala/fleet_restore/qwen38_27b_serve_rtx6000.toml)
  - Materialized config: [config.toml](/data/user_data/pranjala/fleet_restore/rundirs/qwen38-27b-serve-rtx6000/config.toml)
  - vLLM config: [inference.toml](/data/user_data/pranjala/fleet_restore/rundirs/qwen38-27b-serve-rtx6000/configs/inference.toml)
  - SLURM launcher: [inference.sbatch](/data/user_data/pranjala/fleet_restore/rundirs/qwen38-27b-serve-rtx6000/sbatch/inference.sbatch)
  - Logs: `/data/user_data/pranjala/fleet_restore/rundirs/qwen38-27b-serve-rtx6000/inference_<job-id>.out`
  - Settings include GPU utilization `0.95`, max model length `262144`, prefix caching, and MTP with 3 tokens.

- **Prompt-prefix proxy:** port `8600`
  - Code: [proxy.py](/data/user_data/pranjala/fleet_restore/rollout_proxy/proxy.py)
  - It routes using the longest exact prefix of the OpenAI `messages` array.
  - Current snapshot: 26 requests/min, 528.5 generation tokens/sec, 95.7% instantaneous prefix-cache hit rate, 14.9% KV usage, 16 running requests, none waiting.

- **Environment master:** port `5900`
  - Currently 13 healthy workers, 39 total slots, 23 occupied environments.
  - Workers exist on `babel-m9-32`, `babel-l9-32`, `babel-l9-28`, `babel-n9-20`, and `babel-z5-32`.
  - Two occupied environments were unresponsive in this snapshot.
  - These are not separate submitted jobs: each Fleet inference job starts a CPU/QEMU sidecar from [inference.sbatch](/data/user_data/pranjala/fleet_restore/rundirs/qwen38-27b-serve-rtx6000/sbatch/inference.sbatch:38).
  - The master and workers currently execute code from:
    `/data/user_data/pranjala/weird_cua_restore/repo-modularity`

- **Full-1500 sweep**
  - Launcher: [run_full1500_27b_mtp3_low.sh](/data/user_data/pranjala/weird_cua_restore/run_full1500_27b_mtp3_low.sh)
  - Running with `PARALLEL=20`
  - 586 summaries completed at the snapshot.
  - Output: `/data/user_data/pranjala/weird_cua_restore/evaluations/qwen38_27b_full1500_mtp3_low`
  - This sweep also uses the legacy `repo-modularity` checkout—not the clean `weird-cua-bench` clone.

That last point is the operational mess: the current production evaluation stack is still executing the legacy checkout. The clean canonical Weird checkout is:

[weird-cua-bench](/data/user_data/pranjala/weird-cua-bench)

It is clean, tracks `https://github.com/gym-anything/weird-cua-bench.git`, and is pushed on `recovery/timed-codex-20260824`.

## Why Gym Anything was edited

Those edits were not required by the intended ownership contract. They happened because the Codex harness was initially implemented inside Gym Anything, after which subsequent changes naturally kept modifying the same misplaced implementation.

- `36774e17a` added the Codex HTTP gateway, four temporal modes, scheduled execution, session persistence, and the independent action/observation architecture. These were Weird evaluation-harness features and should have lived in `weird-cua-bench`.
- `4f34a1cc5` exposed remote benchmark overrides because the Weird evaluator needed to pass temporal runner options through `RemoteGymEnv`. Under the boundary, Weird should have supplied a downstream adapter over Gym’s public remote protocol.
- `924f769a6` excluded bytecode caches from task digests because `__pycache__` caused client/worker task-digest mismatches. That is a legitimate generic upstream defect, but our project could have prevented bytecode generation or cleaned packaging inputs instead of modifying Gym directly.
- `06fe21d23` changed the paused-mode prompt. It landed in Gym only because the earlier Codex prompt implementation had already been placed there. It belongs unambiguously in Weird.

So the technical changes were motivated by real problems, but putting them in Gym violated the repository boundary. The first large Codex-harness commit created that dependency, and the later edits followed it.

The Gym branch is already pushed as `codex/weird-cua-temporal-harness`; it is clean, not merged, and has no PR. I will treat it as frozen. Future deployment should run an immutable checkout of `weird-cua-bench`, with Gym installed and pinned as an upstream dependency.
