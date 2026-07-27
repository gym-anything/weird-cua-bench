# Environment Agent Prompt

```text
Implement controllability for `<ENVIRONMENT>` after reading `AGENTS.md` and every file in `benchmarks/weird_captcha_gym/docs/controllability/`.
Inspect the controlled environments including the fifteen originally starred examples. Use their control files, materializer integration, browser wiring, grading, verification, and tests as working examples. Then read this environment's task, generator, browser runtime, grader, verifier, solver, and existing controls end to end without copying the examples' task-specific decisions.
Assign the current configuration to its actual difficulty level, preserve it exactly at that level, then construct the other four profiles around it.
Implement simplified and full interaction modes for the same generated world, then set the environment's observation window, frame count, and play time through the shared real-time framework.
Validate all ten task variants in live and paused modes through browser interaction, grading, verification, and the required repository tests.
```
