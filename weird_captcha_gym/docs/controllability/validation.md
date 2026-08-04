# Validation

Validate the complete environment rather than checking only `controls.json`.

## Difficulty

- Materialize all five profiles deterministically across several seeds.
- Confirm that the assigned baseline reproduces the existing configuration for a fixed seed. A documented repair may change objectively inconsistent task text only when fixed-seed evidence shows that the generated world, success condition, timing, observation surface, and assigned level remain unchanged.
- Confirm that every configured parameter affects the running task and its grader or verifier where applicable.
- Compare adjacent levels in the browser. Record the change in the decision or control problem.
- Do not claim calibrated ordering from parameter inspection alone. Preserve human and agent results as separate evidence when they become available.

## Interaction

- Materialize both modes for every difficulty level.
- Confirm that the same seed and difficulty produce the same world, information, goal, action effects, physics, timing, tolerances, and success condition.
- Complete both modes using their visible mouse and keyboard controls.
- Confirm that a transcript from one mode cannot pass the other mode's grader or verifier.
- Inspect target sizes, drag paths, pointer capture, sparse pointer delivery, key holds, state feedback, and layout at the benchmark viewport.

## Real time

- Run the same task in live and paused modes with the same observation settings.
- Add an artificial model delay. Confirm that task time advances in live mode and remains frozen in paused mode.
- Confirm that the environment runs during the complete action in paused mode.
- Inspect the captured frame sequence in chronological order and confirm that the final frame is also `obs["screen"]`.
- Exercise the environment through the public observation inspector when dashboard behavior changes.

## End-to-end checks

- Generate all ten difficulty and interaction task variants.
- Exercise browser interaction, live grading, result export, and independent verification.
- Test invalid input, stale challenge identity, failure feedback, retry or regeneration, and a successful run.
- Inspect initial, active, failed, solved, and final states when those states exist.
- Run `python -m pytest tests -q` plus the static browser smoke for browser-runtime or dashboard changes.
- Run `python weird_captcha_gym/tools/audit_quality.py --strict` when task quality or status changes. Its known nonzero result must not be hidden by weakening the audit.

Report automated browser evidence, human play, and computer-use-agent evaluation separately. Passing tests establish implementation agreement. They do not establish human usability or model difficulty.
