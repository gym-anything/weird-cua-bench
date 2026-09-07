# Controllability creation and audit

This workflow gives one Weird CUA Bench environment to a persistent creation agent. The creator implements difficulty, interaction, and real-time controllability and writes visible evidence under the environment's `evidence_docs/` directory.

After the initial pass and one blind recheck, a fresh audit agent explores the repository and audits the implementation from the code, running environment, and evidence. The auditor writes a report without fixing anything. The creator receives that report and fixes the supported issues. A new audit session is used for every audit round.

All browser checks must run as isolated headless background processes with fresh temporary profiles. Creation and audit agents are forbidden from controlling the user's live browser, desktop, mouse, keyboard, foreground applications, or existing browser profiles. A check that cannot run in isolation remains missing evidence.

Run it from the repository root:

```bash
python -m extras.research.controllability.creation_audit.method \
  --env-dir rotating_keyboard_env
```

The installed command is:

```bash
weird-cua-creation-audit --env-dir rotating_keyboard_env
```

The default agent is `gpt-5.6-luna` with `max` reasoning, for both the creator and every auditor. The default workflow has one blind recheck and up to three audit rounds, stopping on a passing audit. Generated evidence, audit reports, and run logs are ignored by Git.

The existing round-four batch of 35 environments remains on `gpt-6-astra` with `low` reasoning for consistency, including its remaining creation and audit phases. Preserve `--model gpt-6-astra --reasoning-effort low` when resuming that batch. Future batches use the Luna defaults.

For a new environment, use the construction prompts and supply the selection and survey paths. The selection JSON must contain exactly one `picks` entry whose `env_dir` matches the target. Both agents receive these paths, including on resumed runs. For example, from this checkout's repository root:

```bash
mkdir -p weird_captcha_gym/environments/long_way_home_env
.venv/bin/python -m extras.research.controllability.creation_audit.method \
  --env-dir long_way_home_env \
  --memory-dir extras/research/controllability/creation_audit/memory_construction \
  --selection-file outputs/selection_round4_20260906/ROUND4_SELECTION.json \
  --survey-root outputs/selection_round4_20260906/inputs \
  --model gpt-6-astra --reasoning-effort low \
  --audits-dir audits/construction_round4 \
  --logs-dir creation_audit_logs/construction_round4
```

The CLI is resolved from `--codex-bin`, then `CODEX_BIN`, then `PATH`. Exit 0 means audit PASS. Exit 2 means the final audit still has unresolved findings; it does not mean the environment passed. Environment creation is separate from publishing solution videos and updating deployment counts.

Useful options:

```bash
# Resume an existing creator session at the first audit round.
weird-cua-creation-audit \
  --env-dir rotating_keyboard_env \
  --session-id <creator-session-id> \
  --start-idx 2

# Change the number of independent audits.
weird-cua-creation-audit \
  --env-dir rotating_keyboard_env \
  --audit-rounds 3
```
