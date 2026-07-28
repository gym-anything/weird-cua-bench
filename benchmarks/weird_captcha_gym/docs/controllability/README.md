# Controllability Agent Guide

Use this directory when assigning one environment to an implementation agent. The long-form design record remains in `../controllability-plan.md`. The benchmark doctrine and prior implementation lessons remain in `../interaction-puzzle-field-notes.md`.

Read the files in this order:

1. The repository `AGENTS.md`.
2. `../interaction-puzzle-field-notes.md`.
3. `../controllability-plan.md`.
4. `difficulty.md`.
5. `interaction.md`.
6. `real-time.md`.
7. `validation.md`.

Copy `agent-prompt.md` into the assignment and replace `<ENVIRONMENT>` with the exact public environment name. One assignment covers one environment. The agent must inspect that environment independently rather than copying the choices made for another puzzle.

For an axis-specific implementation run, use:

```bash
benchmarks/weird_captcha_gym/tools/run_controllability_agent.sh \
  <interaction|difficulty|realtime> <environment_dir>
```

The launcher runs GPT-5.6 Sol through `codex exec --yolo` and instructs it to preserve the other two axes.

For complete environment work with independent evidence-based audits, use:

```bash
python -m extras.research.controllability.creation_audit.method \
  --env-dir <environment_dir>
```

This keeps one creation session across fixes and uses a fresh agent session for every audit round. The complete workflow is documented in `extras/research/controllability/creation_audit/README.md`.
