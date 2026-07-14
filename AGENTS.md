# AGENTS.md

This repository contains only Weird CUA Bench: interaction-first visual puzzles for evaluating screenshot-driven computer-use agents.

## Binding design doctrine

Before changing or adding a puzzle, read `benchmarks/weird_captcha_gym/docs/interaction-puzzle-field-notes.md` in full. Its one-sentence principle, human-feedback ledger, fairness rules, prohibited shortcuts, validation boundaries, and definition of done are binding.

The benchmark is not a CAPTCHA security product and is not a collection of OCR, classification, static grid, arithmetic, or ordinary slider tasks. Difficulty must come from real interaction debt: motion across frames, active cursor vision, temporal state, motor control, physical or spatial reasoning, causal probing, recovery, or changing interfaces.

Never simulate a claimed mechanic with presentation hacks. Visible geometry, hit testing, physics, server grading, and exported verification must agree. A scripted solver and green verifier prove wiring only; they do not prove puzzle quality, human usability, or agent difficulty.

## Repository boundary

- Keep benchmark code under `benchmarks/weird_captcha_gym/`.
- Do not add CUA-World or any unrelated Gym-Anything environment.
- Do not vendor Gym-Anything's core source tree; it is an optional external runtime dependency.
- Do not publish the mined Survey archive. Static exports contain the built catalog and its dashboard media only.
- Preserve the two-tier execution boundary. Ordinary collaborator play is a static browser runtime: the export ships generated challenge pools, the existing interaction UI, and the exact Python graders executed through pinned Pyodide/WebAssembly. This exploration path requires no checkout, clone, pairing key, localhost service, or VNC.
- Do not call public browser play an authoritative or secret evaluation surface: its challenge truth necessarily ships to the browser and is inspectable in developer tools. Reviews, evaluation execution, fresh authoritative generation, VNC credentials, filesystem paths, and process controls remain opt-in local operations through the authenticated loopback companion.

## Required checks

Run the benchmark tests after relevant changes:

```bash
python -m pytest tests -q
```

Also inspect `python benchmarks/weird_captcha_gym/tools/audit_quality.py --strict` when changing task quality or status. It is expected to exit nonzero while candidates still lack the required human/VNC/agent evidence. Never weaken metadata or promote a task merely to make that audit green.

For dashboard or browser-runtime changes, also export the static site and run `tools/smoke_static_browser_play.py`; companion changes still require the shared-dashboard smoke. Real runner/VNC and human calibration remain separate gates from automation.
