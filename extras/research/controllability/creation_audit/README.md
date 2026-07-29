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

The default agent is `gpt-5.6-sol` with `xhigh` reasoning. The default workflow has one blind recheck and two audit rounds. Generated evidence, audit reports, and run logs are ignored by Git.

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
