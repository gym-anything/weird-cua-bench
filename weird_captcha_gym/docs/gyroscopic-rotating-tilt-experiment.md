# Gyroscopic Tilt Board: rotating external tilt

This separate experiment tests whether an agent can steer while the board keeps
applying a changing force. It does not replace the original Gyroscopic Tilt Board
or change its difficulty profiles, benchmark splits, or recorded results.

## Mechanic

The player's tilt is added to an external tilt vector of magnitude 0.22, relative
to the player's maximum magnitude of 1. The external vector rotates once every
14 seconds of simulated physics. Its starting phase and rotation direction come
from the challenge seed. The same acceleration, friction, speed limit, contacts,
wells, ordered lamps, and goal-cup rules remain in effect.

A red arrow on the interface shows the external vector. Centering the knob or
selecting LEVEL removes only the player's tilt. Reset returns the ball to the
start but does not reset the external rotation. Paused execution freezes both
the ball and the rotation through the existing environment clock. Completing
the puzzle still locks the ball in the goal cup.

This is a predictable disturbance, not an opponent that reacts to the agent.
It removes neutral-control resting in open space. It does not forbid braking,
countersteering, or making use of walls. A controller can oppose the external
force, but the required counter-tilt changes with time. Whether an agent finds
another useful resting strategy is an experimental outcome, not something this
implementation claims to rule out.

Games do not universally prohibit stopping. Moving ground and obstacles can make
waiting unsafe: for example, SEGA describes moving platforms and obstacles that
appear over time in [Super Monkey Ball Banana Rumble's Twinkle Arena](https://asia.sega.com/bananarumble/en/news/detail/20240918-02.html).
That is the motivation for this variant, rather than a claim that the original
board's stopping strategy was invalid.

## Code and materialization

- `shared_scripts/incubator_generators/board_game_captcha.py`: optional external
  tilt parameters and seeded rotation, absent in all existing profiles.
- `shared_runtime/app/mechanics/board_game_captcha.js` and `.css`: physics,
  input controls, force indicator, and event evidence.
- `shared_runtime/server/incubator_graders/board_game_captcha.py`: independent
  reconstruction of each external force and physics tick. Reset preserves the
  replay tick count.
- `tools/materialize_gyroscopic_variant.py`: creates an experimental task from
  an existing difficulty and interaction profile without changing that profile.

From the repository root:

```bash
python -m weird_captcha_gym.tools.materialize_gyroscopic_variant \
  --tasks-root weird_captcha_gym/environments/board_game_captcha_env/tasks \
  --difficulty 5 --interaction full
```

The task is `board_game_captcha_d5_full_rotating_tilt_seed_0001`. The command
refuses to overwrite an existing task directory. Generated task directories and
validation recordings are git-ignored. The materializer and all implementation
and test code are tracked in Weird CUA Bench, not Gym-Anything.

## Validation

```bash
python -m pytest tests/test_gyroscopic_rotating_tilt.py tests/test_weird_captcha_controls.py -q
python -m weird_captcha_gym.tools.check_gyroscopic_variant \
  --out-dir outputs/gyroscopic_rotating_tilt_check \
  --seeds 42 43 44 --interactions full simplified
```

The browser check uses isolated headless Chromium. It checks motion with neutral
controls, pause/resume, reset without stopping the disturbance, rejection and
fresh-challenge recovery, and completion through ordinary mouse inputs. It
checks server grading, independent replay, and the exported task verifier, and
saves continuous video, screenshots, and the submitted event evidence.

The reference controller reads internal ball state and waypoints to establish
implementation solvability. It is not a screenshot-only agent evaluation and
does not establish human usability or model difficulty. The experiment remains
pending human and agent evaluation. No Astra evaluation was launched as part of
creating the variant.

### Recorded checks (2026-09-06)

- Targeted tests: 123 passed.
- Final headless D5 check: full and simplified control both passed with evaluator
  seeds 42, 43, and 44. All six server grades, independent replays, and exported
  verifiers passed. Reference-controller completion took 12.3–13.8 seconds.
- Neutral control moved the ball 71–107 board pixels over 85 ticks, approximately
  three seconds. Both modes had identical neutral trajectories for each seed.
- Baseline generator comparison: 33 outputs matched pre-change `31f8563`
  exactly, covering the base task and all difficulty/interaction combinations
  across three seeds.
- Static export/browser check: 85 environments rendered, 85 WebAssembly graders
  exercised, no failures.
- Full suite: 676 passed, 5 skipped, 5 failed. Three frozen-sample tests reject
  the existing generated-task population, one hook-count test expects only base
  task folders, and one ghost-jigsaw legacy/server parity test disagrees about
  invalid-input feedback. These failures were left outside this experiment's
  scope. The first four occurred before this variant was materialized locally.
- The quality audit still reports the original board as a prototype pending
  human review. Its status was not promoted.

Final screenshots, continuous browser recordings, submitted event evidence, and
per-run summaries are in
`outputs/gyroscopic_rotating_tilt_verified_20260906/`. The displayed neutral,
active, and passed states were inspected. The red arrow, board geometry, analog
controls, and certification button are visible at 1920×1080.
