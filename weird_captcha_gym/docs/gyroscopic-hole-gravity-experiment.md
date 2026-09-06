# Gyroscopic Tilt Board: nearest-hole gravity

The user proposed replacing the rotating external tilt in the experimental
board with attraction toward the nearest hole. This variant uses the original
D5/full board with that change. The original board and the earlier rotating-tilt
variant remain reproducible, with separate task identities and saved results.

## Force and interface

At each physics tick, select the hole whose center is closest to the ball's
center. Only that hole attracts the ball. The acceleration points toward its
center and has magnitude `0.5 * physics.acceleration`, independent of distance.
The player's acceleration is added to it before the existing friction and
speed limit are applied. There is no rotating force in this variant.

An orange outline and PULL label identify the attracting hole. The indicator
shows the pull direction and its 50% strength. The selection is recomputed when
the ball moves or resets, so the highlight matches the displayed ball position.
Walls do not block attraction. Exact distance ties use generator list order.
At a hole's exact center the direction is zero rather than undefined; the
existing hole collision rule then returns the ball to the start.

Centering the knob does not turn off gravity. Countersteering can overcome or
balance the force. Walls can still support the ball. These are allowed physical
strategies, not reasons to reject a run. Paused execution freezes the simulation
through the existing clock, and reaching the goal after all lamps locks the ball
as before. All other geometry, controls, collision rules, and grader limits are
unchanged.

## Reproduction

```bash
python -m weird_captcha_gym.tools.materialize_gyroscopic_variant \
  --tasks-root weird_captcha_gym/environments/board_game_captcha_env/tasks \
  --variant nearest_hole_gravity --difficulty 5 --interaction full
```

Task: `board_game_captcha_d5_full_nearest_hole_gravity_seed_0001`.
The generator parameter is `hole_gravity: 0.5`. The generator rejects combining
hole gravity with rotating tilt. Other difficulty profiles and simplified
control can use the same optional variant without editing the base profiles.

```bash
python -m pytest tests/test_gyroscopic_hole_gravity.py tests/test_gyroscopic_rotating_tilt.py -q
python -m weird_captcha_gym.tools.check_gyroscopic_variant \
  --variant nearest_hole_gravity --seeds 42 43 44 \
  --interactions full simplified --out-dir outputs/gravity-check
```

## Evidence (2026-09-06)

- All 30 force-variant unit tests passed, including nearest-hole selection,
  distance ties, constant strength, neutral motion, balancing, escape, and
  rejection of false force evidence.
- All six D5 reference-controller checks passed: three seeds each under full
  and simplified controls. Server replay, independent replay, and exported
  verification all accepted the recorded mouse inputs. Controller completion
  took 13.4–15.3 seconds. This is implementation validation with privileged
  state observation, not an Astra or screenshot-only agent result.
- Every recorded gravity vector had magnitude 0.5. Each run switched attraction
  among all five holes, with the selecting hole independently checked by replay.
- All 85 environments passed static browser export/render and WebAssembly
  grading checks. Original and rotating-tilt generators matched the preceding
  commit in all 63 baseline comparisons.
- Full suite: 693 passed, 5 skipped, and the same five previously observed
  failures remained: three frozen-sample population checks, the hook-count check
  that includes materialized task folders, and ghost-jigsaw invalid-input
  feedback parity. Those checks were not changed as part of this experiment.
- The quality audit still requires human review. No task was promoted and no
  Astra evaluation was launched.

Screenshots, continuous browser recordings, and submitted event evidence are in
`outputs/gyroscopic_hole_gravity_validation_20260906/`.

The human-play service uses loopback port 8876 on `babel-p9-28`, forwarded through
UT to the user's Mac. Its state and results are saved separately in
`outputs/gyroscopic_hole_gravity_human_20260906/state/`. The previous rotating
human-play service was stopped, but its saved state and results were retained.
The replacement page was checked in an isolated headless browser for live
motion, analog drag/release, the attracting-hole highlight, and visible controls.
