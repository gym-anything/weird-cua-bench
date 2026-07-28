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

## Controllability plan

Before adding difficulty, interaction, or real-time variants, read `benchmarks/weird_captcha_gym/docs/controllability-plan.md` in full. Do not assume that the current interface is the full-interaction variant. Do not assume that the current difficulty is level 3. Both must be judged independently for every environment.

Environment-by-environment implementation work must also follow every file in `benchmarks/weird_captcha_gym/docs/controllability/`. That directory contains the reusable assignment prompt and the practical decision and validation rules distilled from the completed fifteen-environment implementation.

## Capability annotation guidelines

- Use the exact public environment name shown by the dashboard.
- Treat real time, interaction, and difficulty or complexity as controllable knobs. Do not present them as core capabilities.
- Classify visual understanding as 2D or 3D. Spatial understanding belongs inside visual understanding.
- Count temporal understanding and memory only when a solution needs change across frames, motion, duration, hidden past state, or another nontrivial temporal relationship. A simple visible sequence does not count.
- Combine reasoning and planning into one broad capability.
- Count exploration and interface understanding when the agent must interact to reveal relevant information or learn how the interface behaves before it can solve the task.
- A visible state transition that supplies the next required information does not by itself count as exploration and interface understanding.
- Read the generator, visible browser implementation, grader, verifier, and solver where present before assigning labels. Do not classify from the task description alone.
- Describe what a normal screenshot-only UI solution requires. A solver that reads private state is implementation evidence rather than the behavior being classified.
- Record when continuous frames are needed only for observation even though the physical action itself is untimed.

## Binding design doctrine

Before changing or adding a puzzle, read `benchmarks/weird_captcha_gym/docs/interaction-puzzle-field-notes.md` in full. Its one-sentence principle, human-feedback ledger, fairness rules, prohibited shortcuts, validation boundaries, and definition of done are binding.

The benchmark is not a CAPTCHA security product and is not a collection of OCR, classification, static grid, arithmetic, or standard slider tasks. Useful tasks can require motion across frames, active cursor vision, temporal state, motor control, physical or spatial reasoning, causal probing, recovery, or changing interfaces.

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

## Computer-use evaluation boundary

For every benchmark evaluation, inject a mandatory visible-task-UI-only rule at both the model system-instruction level and in every task description. The model must solve only from screenshots and visible controls in the task webpage. Explicitly forbid code, scripts, automation, Developer Tools, console/debugger/inspector/network/source/DOM/page-state inspection, terminal/shell/Python, address-bar or URL/query edits, reload/navigation, browser extensions, external applications, and all other implementation or hidden-state access.

Do not let the model switch to or interact with any pre-existing, unrelated, blank, browser-settings, or non-task tab. Tabs opened by a visible task control are allowed only when they are part of the task itself, and only their visible controls may be used.

The restriction must not reveal solution information, simplify the puzzle, mutate the task, or change the approved step budget. Audit executed actions separately from model reasoning. Report verifier failures, provider/model errors, infrastructure errors, policy deviations, and benchmark defects as separate outcome classes; never turn an excluded or invalid run into a claimed pass after the fact.

Every approved evaluation protocol must record a finite provider-request deadline and its request-retry policy. Retry transient transport failures—including timeouts, connection/read/write errors, and server disconnects or protocol errors—plus HTTP 408/429 and HTTP 5xx responses without consuming an environment step; do not retry explicit safety blocks, authentication/authorization failures, or invalid requests. Use one retry layer with an explicit total-attempt limit so nested client retries cannot multiply the declared budget.

## Research purpose

The project evaluates computer-use agents that must operate while a visual world continues changing. Video games and physical robots are motivating applications. Weird CAPTCHAs and short interactive puzzles provide smaller controlled environments between static grounding benchmarks and large video-game benchmarks.

The benchmark should expose specific failures in real-time computer use. Procedural generation provides varied instances plus task-specific controls over interaction and difficulty. The value is not that the tasks are CAPTCHAs. The value is a diverse controllable testbed for perception and action in changing environments.

The selection of benchmark capabilities still needs a convincing data-backed justification. An arbitrary survey paper does not provide that justification merely because it was published. Do not claim that the seven-part framework was derived from psychology, robotics, biology, economics, O*NET, or CAPTCHA surveys unless the derivation has actually been completed and the evidence supports every category.

## Difficulty assignment rules

- A level describes the exact current configuration. It does not describe the environment name or everything the environment could become.
- Read the generator, browser runtime, grader, verifier, and solver before assigning a level.
- Determine which parameters and rules are active in the current task. Do not credit inactive options, unused metadata, grader quotas, or minimum-action checks as task difficulty.
- Repeating an independent action, adding more rounds, or adding more steps does not by itself make the underlying problem harder.
- A repeated step can matter when it changes the state needed for later decisions. Exact-Change Candy Cascade is an example because each accepted swap changes the later board.
- Compare the current task with concrete easier and harder configurations. State what changes inside the actual decision or control problem.
- The current task can be any level. Never place it at L3 by default.
- L5 does not mean the hardest imaginable version of an environment. An environment can be made substantially harder than its L5 profile.
- Difficulty labels remain subject to comparable human and computer-use-agent measurements. Parameter magnitude alone does not prove a level.

## Approved baselines for the twenty controlled environments

| Public environment name | Baseline |
|---|---:|
| Gyroscopic Tilt Board | L3 |
| Cursor-Controlled Constellation Hunt | L2 |
| Polarized Palimpsest | L3 |
| Exact-Change Candy Cascade | L5 |
| Flat-Pack Compliance Test | L4 |
| The Flat Prisoner | L4 |
| Input-Lag Forklift | L4 |
| Insider Trading CAPTCHA | L2 |
| LIDAR Blacksite | L4 |
| Blind Dice Courier | L4 |
| Bomb Manual From Hell | L4 |
| Bureaucratic Signature Trap | L4 |
| Clockwork Clutch Safe | L3 |
| Isometric Voxel Extraction Mine | L1 |
| Motion-Only Ghost Jigsaw | L4 |
| Rotate The Wrong Thing Upright | L4 |
| Rotating On-Screen Keyboard | L4 |
| Slime Commute | L4 |
| Specular Lighthouse Relay | L3 |
| Parallax Orchard | L4 |

## Approved interaction baselines for the twenty controlled environments

| Public environment name | Current interface |
|---|---|
| Gyroscopic Tilt Board | Full |
| Cursor-Controlled Constellation Hunt | Full |
| Polarized Palimpsest | Full |
| Exact-Change Candy Cascade | Simplified |
| Flat-Pack Compliance Test | Simplified |
| The Flat Prisoner | Simplified |
| Input-Lag Forklift | Simplified |
| Insider Trading CAPTCHA | Simplified |
| LIDAR Blacksite | Simplified |
| Blind Dice Courier | Full |
| Bomb Manual From Hell | Simplified |
| Bureaucratic Signature Trap | Full |
| Clockwork Clutch Safe | Simplified |
| Isometric Voxel Extraction Mine | Simplified |
| Motion-Only Ghost Jigsaw | Full |
| Rotate The Wrong Thing Upright | Simplified |
| Rotating On-Screen Keyboard | Full |
| Slime Commute | Full |
| Specular Lighthouse Relay | Simplified |
| Parallax Orchard | Full |

Both interaction modes are implemented for all twenty. The exact environment-specific mappings are recorded in `benchmarks/weird_captcha_gym/docs/controllability-plan.md`. Preserve the generated world, information, goal, and action effects across each pair. Bind browser events and grading to the selected input surface so one mode cannot pass with the other mode's transcript.

## Collaboration rules learned from the project

- When asked to explore the repository, explain its purpose, principles, architecture, components, and current state before listing small defects. Ongoing experiments are unfinished work rather than evidence against the project.
- Answer the question that was asked. Do not replace it with unsolicited recommendations.
- When the user points out a problem, inspect the evidence and improve the work. Agreement or a restatement is not a correction.
- Read complete source files for task judgments. Do not rely on descriptions, names, keyword searches, or private-state solvers alone.
- Read a referenced paper end to end including its appendix before using it as a research foundation.
- Random audits are checks rather than searches for a required number of mistakes. It is valid for all sampled annotations to be correct.
- Never invent an environment name or silently substitute a related task.
- Use public environment names in tables and user-facing text.
- Use plain established technical language. Do not invent research constructs such as “interaction debt” or use decorative words such as “genuine” and “ordinary” to create distinctions that the implementation does not define.
- Avoid self-certifying phrases such as “clean formulation,” “conclusion,” or “inference.” Present the evidence and the specific claim instead.
- Do not turn differences in wording such as difficulty versus complexity into unnecessary theory when the implementation question is already clear.
- Simplicity, generality, modularity, and scalability guide the controllability system. Add task-specific parameters behind one shared control structure rather than creating a new conceptual framework for every puzzle.
