# Round-three quality fixes and current browser evidence

This directory supersedes `../round_three_v1/solution_videos/manifest.json`
for the corrected versions of the 35 environments introduced in PR #49.
The original films and hashes remain unchanged as historical evidence.

## Corrections

- Ballast Lantern, Anthill Front, Confectioner's Ink, Apothecary Dead
  Reckoning and The Silent Colleague advance from the existing task clock,
  not the number of timer callbacks that happened to execute. Delayed
  callbacks catch up through the same fixed simulation steps. Inputs first
  synchronize the affected simulation or held pestle to the current time.
  The shared clock, runners, adapters and task physics are unchanged.
- The 26 conflicting task/control descriptions permit programs in the
  isolated agent sandbox to process screenshots and send mouse/keyboard
  actions through the gateway. Task internals, DOM inspection, task-terminal
  access and unrelated tabs remain forbidden. No evaluator exception or
  task-specific prompt parsing was added.
- Passphrase Under Siege now honors `hidden` on its grain tray. Its flex
  styling previously kept the tray displayed and interfered with character
  selection at 1280x720. Mouse selection and formatting are checked in both
  interaction modes at 1280x720 and 1920x1080.
- Ballast Lantern's reference solver uses current cage/specimen state,
  checks the current challenge, and does not pause live time for screenshots.
  Live control checks each simulation tick; paused control retains 600 ms
  observation windows. A failed attempt is reported, not silently replaced
  by a later successful attempt.
- Ballast Lantern's grader accepts valid high-frequency input transcripts.
  A native D5 solve reached the secured state after 285 key transitions but
  was rejected by an undocumented 240-event limit. The malformed-input
  safeguard is now 10,000 events, consistent with other task graders. Every
  transition, input source, physics tick and final state is still replayed
  and checked. The task's success condition and scoring are unchanged.

## Browser evidence

All 35 baseline configurations have a fresh 1280x720 Chromium solution
recording and exported result. Server grading, direct replay and the task
verifier agree on a pass. There are no console errors and no
`pause`/`resume`/`runFor` calls during these recorded live solves.
`recovery.json` separately records successful deliberate-failure, fresh
challenge and subsequent solution checks for all 35 families.

`solution_videos/manifest.json` contains one entry per family with its seed,
baseline, viewport, browser version, three grading results, MP4/WebM/export
hashes, and a consistently nested map of source-path SHA-256 values. Source
hashes were collected before and after each capture and required to agree.
They were also checked against the corrected checkout when publishing this
directory. The recorded Git head is the parent of the uncommitted fixes;
the per-file hashes identify the exact bytes actually tested.

These are privileged reference-solver browser checks using mouse/keyboard
input. They establish executable solutions, recovery and grading agreement
at the tested baselines. They are not model trials, human trials, VNC tests,
or 350 independent browser solutions. No task was promoted from prototype
status on the strength of these checks.

## Reproduction

Install the repository's test dependencies and Playwright with Chromium.
From the repository root, use a new output directory for each recording:

```bash
PR49_OUTPUT="$(mktemp -d /tmp/round-three-evidence.XXXXXX)" \
PR49_RECORD_VIDEO=1 \
python weird_captcha_gym/evidence/round_three_v2/reproduce.py batch \
  --seed round-three-verification --recovery
```

The script uses fresh headless profiles and its own loopback servers. It
never connects to an existing browser or VM and does not manipulate jobs.
It saves per-case source hashes, recordings, exports and verifier results.
The task list is fixed by the base/head commits of PR #49.

The focused regressions are:

```bash
python -m pytest tests/test_round_three_task_clocks.py \
  tests/test_round_three_gateway_instructions.py \
  tests/test_passphrase_under_siege_browser.py \
  tests/test_ballast_lantern_browser.py tests/test_ballast_lantern.py -q
```

The five task-clock probes use split observation windows, repeat with a
main-thread stall, and check exact advancement plus the paused endpoint.
They retain 12 Ballast ticks / 600 ms, 6 Anthill ticks / 600 ms, 30 Ink
ticks / 600 ms, 7 pestle notches / 1,800 ms, and 5 Colleague ticks / 3,000 ms.
The instruction test checks each canonical task and all ten materialized
difficulty/interaction variants: 385 actual gateway prompts.

## Final validation, 2026-09-06

- Full source-only suite: **1,259 passed, 4 skipped, 2 failed** in 1,150.24 s.
  The two failures are the pre-existing missing Marionette fixtures
  `evidence_docs/audit_passive_clearance.py` and
  `evidence_docs/smoke_target_static_browser_play.py`. Marionette is not one
  of these 35 additions. The fixtures were already missing from PR #49's
  base and head. See `pytest-source-final.log`.
- Ballast's focused suite: **15 passed**, including native D5 full and
  simplified solutions under both live and paused schedules, and the
  high-frequency transcript regression.
- Static browser export: **120/120 environments rendered**, **120/120
  Python graders executed through Pyodide**, no failures. See
  `static-browser-check.json`.
- All **35 live recordings**, **35 exported results**, and **35 recovery
  checks** passed. All **105 MP4/WebM/export hashes** and every recorded
  source-file hash were checked after copying the artifacts here.
- The actual final screenshots and decoded beginning/middle/ending video
  frames of all six visually affected tasks were inspected.

The source-only run used an ordinary archive of the branch plus its fixes,
not a Git worktree. Existing ignored materialized task directories in the
working checkout were left intact. They affect older tests that count all
task folders, reconstruct the historical 75-task sample, or choose the
first task in a family. The archive excludes these generated files without
deleting any user data. Runtime changes, new tests and source contents are
the same as the corrected checkout.

No core runner, evaluator, adapter, shared clock/server, upstream
Gym-Anything source, existing job or live human-play server was modified.
The strict quality gate still requires human/VNC evidence and empirical
calibration; prototype metadata was not weakened or promoted.
