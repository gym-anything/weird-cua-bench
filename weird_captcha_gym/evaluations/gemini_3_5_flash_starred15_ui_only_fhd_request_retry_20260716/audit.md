# Gemini 3.5 Flash — curator-starred 15 audit

## Run identity

- Experiment: `gemini-3.5-flash-starred15-ui-only-fhd-request-retry-20260716T034352Z`
- UT Lab run: `R4` (`full` policy)
- Started: `2026-07-16T03:47:42.772399+00:00`
- Finished: `2026-07-16T10:35:15.531611+00:00`
- Selection: the exact 15-environment `?stars=` snapshot supplied by the curator, in URL order
- Population at selection: 75 checked-in task specs; population SHA-256 `3f89acb8a989f82e4f710c3bd0fa7b58a664c0ca46fa85a5a3615d48b37336da`
- Primary trajectories: one per task; no task replacements

The run completed all 15 primary tasks. UT Lab records exit status 1 because two tasks ended in model API outcomes; this is not an infrastructure abort and the complete primary summary was written.

## Frozen protocol

- Agent/model: `GeminiComputerUseAgent`, `gemini-3.5-flash`
- Desktop: AVF, 1920×1080, `fast_io=false`
- Model settings: high thinking, temperature 1.0, no model seed
- Environment seed: 42
- Budget: at most 100 logical model turns; model could stop early
- Execution: sequential, one trajectory per task, full untruncated history, 3-second post-reset observation delay
- Tasks were not changed for the evaluation or for replay generation.
- The instruction required visible task UI only and prohibited code, terminal, DevTools, source/DOM inspection, address-bar or URL edits, reloads, unrelated tabs, other applications, and external tools. Ordinary browser zoom was permitted only for resizing the visible UI.
- Candidate-less responses could retry after 2 and 5 seconds unless Google returned an explicit prompt block.
- Each provider request had five total attempts and a 180-second deadline. HTTP 408/429/500/502/503/504 and HTTPX transport failures were retryable with bounded exponential backoff and jitter. Safety, authentication, and invalid-request outcomes were not retryable.
- A verifier failure remained a benchmark outcome. A model/provider error was excluded from the benchmark pass/fail denominator. Only benchmark-independent infrastructure failure could trigger one separately registered same-task replacement.

The exact selection and provenance are in [manifest.json](manifest.json). The inherited protocol is recorded in `../gemini_3_5_flash_random15_ui_only_fhd_request_retry_20260715/manifest.json`.

## Outcome summary

| Category | Count | Fraction of all 15 |
|---|---:|---:|
| Verifier pass | 1 | 6.67% |
| Verifier failure | 12 | 80.00% |
| Explicit provider safety block | 2 | 13.33% |
| Infrastructure failure | 0 | 0.00% |

Excluding the two provider safety blocks, the benchmark pass rate is **1/13 = 7.69%** and the verifier-failure rate is **12/13 = 92.31%**. The sole pass was policy-compliant.

| # | Task | Recorded outcome | Steps | Policy audit | Gemini-attempt replay |
|---:|---|---|---:|---|---|
| 1 | Gyroscopic Tilt Board | Failed | 100 | Compliant | [video](replays/01-board_game_captcha_seed_0001-gemini-attempt-replay.mp4) |
| 2 | Cursor-Controlled Constellation Hunt | Provider safety block; excluded | 16 | Compliant until block | [video](replays/02-cursor_constellation_hunt_seed_0001-gemini-attempt-replay.mp4) |
| 3 | Polarized Palimpsest | Failed | 100 | Compliant | [video](replays/03-cursor_lens_reveal_seed_0001-gemini-attempt-replay.mp4) |
| 4 | Exact-Change Candy Cascade | Failed | 100 | Compliant | [video](replays/04-exact_change_candy_cascade_seed_0001-gemini-attempt-replay.mp4) |
| 5 | Flat-Pack Compliance Test | Failed | 100 | Compliant | [video](replays/05-flat_pack_compliance_seed_0001-gemini-attempt-replay.mp4) |
| 6 | The Flat Prisoner | Failed | 100 | Compliant | [video](replays/06-flat_prisoner_seed_0001-gemini-attempt-replay.mp4) |
| 7 | Input-Lag Forklift | Failed | 100 | Compliant | [video](replays/07-input_lag_forklift_seed_0001-gemini-attempt-replay.mp4) |
| 8 | Insider Trading CAPTCHA | Failed | 100 | Deviation: unrelated pre-existing tab at steps 90–91 | [video](replays/08-insider_trading_captcha_seed_0001-gemini-attempt-replay.mp4) |
| 9 | Isometric Voxel Extraction Mine | **Passed**, verifier 100 | 12 | Compliant | [video](replays/09-minecraft_block_grid_seed_0001-gemini-attempt-replay.mp4) |
| 10 | Motion-Only Ghost Jigsaw | Failed | 100 | Deviation: unrelated pre-existing tab at steps 84–85 | [video](replays/10-motion_only_ghost_jigsaw_seed_0001-gemini-attempt-replay.mp4) |
| 11 | Rotate The Wrong Thing Upright | Failed | 100 | Compliant | [video](replays/11-rotate_wrong_thing_upright_seed_0001-gemini-attempt-replay.mp4) |
| 12 | Rotating On-Screen Keyboard | Provider safety block; excluded | 17 | Compliant until block | [video](replays/12-rotating_keyboard_seed_0001-gemini-attempt-replay.mp4) |
| 13 | Slime Commute | Failed | 100 | Compliant | [video](replays/13-slime_commute_seed_0001-gemini-attempt-replay.mp4) |
| 14 | Specular Lighthouse Relay | Failed | 100 | Compliant | [video](replays/14-specular_lighthouse_relay_seed_0001-gemini-attempt-replay.mp4) |
| 15 | Parallax Orchard | Failed | 100 | Compliant | [video](replays/15-surreal_apple_on_tree_grid_seed_0001-gemini-attempt-replay.mp4) |

The voxel-mine pass was accepted by the independent verifier with: `diamonds 4/4; durability 6; rotations 5; viewpoints 4; resets 0; support stable`.

## Provider, retry, and infrastructure audit

- Cursor-Controlled Constellation Hunt returned explicit `BlockedReason.SAFETY` after step 15. The runner preserved the event, stopped without retrying the safety verdict, and classified the trajectory as a model API outcome.
- Rotating On-Screen Keyboard returned explicit `BlockedReason.SAFETY` after step 16 and was handled identically.
- There were no request-level transient retry events, no exhausted transient request failures, no authentication failures, and no benchmark-independent infrastructure failures.
- No replacement was permitted or needed under the frozen replacement policy.

## Visible-UI policy audit

The recorded action stream was scanned for keyboard shortcuts, browser-chrome coordinates, navigation intents, and interactions with non-task UI.

- Insider Trading CAPTCHA briefly selected the pre-existing Firefox Privacy Notice tab and returned to the task at steps 90–91.
- Motion-Only Ghost Jigsaw explicitly selected the same pre-existing Privacy Notice tab and returned at steps 84–85.
- Both trajectories were already verifier failures. Neither deviation produced or influenced a pass.
- No trajectory used DevTools, Console, terminal, shell, code, source/DOM inspection, address-bar edits, URL edits, reload, browser extensions, or another application.
- No forbidden browser shortcut was issued. Task-facing Tab/Shift+Tab, arrows, space, letters, and text entry were retained as ordinary visible-UI interaction.

Thus, 13/15 complete trajectories were policy-compliant; the one successful trajectory was compliant.

## Replay evidence

The `replays/` directory contains exactly 15 videos, one for every primary Gemini attempt, including the two provider-blocked attempts. Each replay is an accelerated reconstruction from the exact saved Gym-Anything observation PNGs in trajectory order and the exact recorded Gemini actions. It is **not** a continuous real-time screen recording. The videos do not expose stored private model reasoning.

Every video was re-probed and verified as:

- H.264
- `yuv420p`
- 1920×1080
- 30 fps

All 15 SHA-256 digests were recomputed after the final contrast pass and match [replays/index.json](replays/index.json). The replay index also records duration, frame count, source trajectory, source log, verifier result, and the disclosure above. Intro, representative action, and terminal outcome frames from all 15 videos were visually inspected. The pass, failures, and provider safety endings are visibly and correctly labeled.

## Validation performed

- Benchmark/manifest/runner suite before launch: 55 passed, 1 skipped
- Gemini wrapper suite before launch: 32 passed
- Replay renderer tests after the final overlay change: 5 passed
- Ruff: passed
- `git diff --check`: passed
- Replay inventory: 15/15 files
- Replay hashes: 15/15 match `replays/index.json`

Primary machine-readable results are in [runtime/summary.json](runtime/summary.json); per-task logs are in `runtime/`; exact saved screenshots and action trajectories are under the run directories named by `replays/index.json`.
