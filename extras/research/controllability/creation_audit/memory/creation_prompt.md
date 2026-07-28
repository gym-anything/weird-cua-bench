# Controllability creation

Implement difficulty, interaction, and real-time controllability for the target Weird CUA Bench environment.

Read `AGENTS.md`, `benchmarks/weird_captcha_gym/docs/interaction-puzzle-field-notes.md`, `benchmarks/weird_captcha_gym/docs/controllability-plan.md`, and every file in `benchmarks/weird_captcha_gym/docs/controllability/` before acting. Inspect the approved controlled environments as working examples. Read the target environment's task, generator, browser runtime, grader, verifier, solver, and existing controls end to end before making any decisions.

Assign the existing configuration to its actual difficulty level and preserve it exactly there. Construct the other four levels around that configuration. Implement simplified and full interaction for the same generated world. Configure real-time behavior through the shared framework without adding task-level live and paused branches.

Do not change the original task or the uncontrolled generator behavior to justify a preferred level. If the original belongs at L1 then preserve it at L1. Changing the original and comparing the controlled baseline against that changed version is not preservation.

One exception is an objective pre-existing task-contract contradiction. If the user-facing task text disagrees with the pre-control generator and grader about what is required to pass, repair only the text to describe the existing mechanics. Do not change the generated world, success condition, timing, or difficulty to create such a repair. Record the exact historical and corrected contracts plus fixed-seed evidence that the mechanics are unchanged.

Validate the complete implementation through visible browser interaction. Check generation, all ten difficulty and interaction combinations, live and paused behavior, grading, export, verification, failure, and retry. For timing-sensitive behavior, repeat any previously failing browser check. One passing run does not establish that a race is fixed. Passing tests establish implementation agreement. They do not establish human usability or empirical difficulty calibration.

Before finishing, create the requested `evidence_docs` directory inside the environment. Include screenshots or recordings of the visible behavior plus exact command outputs or result artifacts supporting the checks above. Show the original task at its assigned level, representative adjacent difficulty changes, both interaction modes on the same generated world, the model's live and paused observations, grading, export, failure, and recovery. Written claims do not replace visible evidence.
