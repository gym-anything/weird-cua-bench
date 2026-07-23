# AGENTS.md

This repository contains only Weird CUA Bench: interaction-first visual puzzles for evaluating screenshot-driven computer-use agents.

## Current benchmark framework

Preserve the following framework verbatim. Do not replace these broad categories with narrower hand-engineered definitions.

cool! so i think, the way it should work is following:

there are three controllable knobs that we can control in any game:
1. real time: sometimes without even changing code, we can pause frames or provide a set of continous frames to model,a dn while we wait for its actions we pause the whole game.
2. interaction: example, does it need to drag and rop, are there buttons on the side, etc
3. difficulty/complexity: we can add more stages, more variables to handle simultaneously, etc etc at a per app level.

there there are 3 or 4 core capabilities that each game is trying to test:
1. visual understanding: can be again classified into 2d vs 3d. basically 2d would be present in almost all games. in general visaul understanding means spatial understanding etc etc generally.
2. temporal understanding and memory. simple sequence is not really counted here. but say which direction is fish moving, is temporal understanding.
3. reasoning and planning. kind of many things other than this benchmark also test it. but still a category of its own.
4. exploration and interface understanding: this to some extent is also controllable, but still i would consider a part of game itself. can contain things like model has to explore the game and figure out things, or even for understanding the game rules, it has to do some exploration, etc.

## Capability annotation guidelines

- Use the exact public environment name shown by the dashboard.
- Treat real time, interaction, and difficulty or complexity as controllable knobs. Do not present them as core capabilities.
- Classify visual understanding as 2D or 3D. Spatial understanding belongs inside visual understanding.
- Count temporal understanding and memory only when a solution needs change across frames, motion, duration, hidden past state, or another nontrivial temporal relationship. A simple visible sequence does not count.
- Combine reasoning and planning into one broad capability.
- Count exploration and interface understanding when the agent must interact to reveal relevant information or learn how the interface behaves before it can solve the task.
- Do not count ordinary feedback, a routine state transition, or reacting to a new visible state as exploration and interface understanding.
- Read the generator, visible browser implementation, grader, verifier, and solver where present before assigning labels. Do not classify from the task description alone.
- Describe what a normal screenshot-only UI solution requires. A solver that reads private state is implementation evidence rather than the behavior being classified.
- Record when continuous frames are needed only for observation even though the physical action itself is untimed.

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
