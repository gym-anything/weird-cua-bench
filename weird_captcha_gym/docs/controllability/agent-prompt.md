# Environment Agent Prompt

```text
Implement controllability for `<ENVIRONMENT>` after reading `AGENTS.md` and every file in `weird_captcha_gym/docs/controllability/`.
Inspect the controlled environments including the fifteen originally starred examples. Use their control files, materializer integration, browser wiring, grading, verification, and tests as working examples. For difficulty work, also inspect every reference environment's actual current task and the code that determines its visible problem and success condition. Do not calibrate from `controls.json` summaries alone. Then read this environment's task, generator, browser runtime, grader, verifier, solver, and existing controls end to end without copying the examples' task-specific decisions.
Assign the current configuration to its actual difficulty level, preserve it exactly at that level, then construct the other four profiles around it.
If historical task text objectively contradicts the historical generator and grader, repair only that text and document the old and corrected contracts. This exception does not permit changing mechanics, timing, or level.
Implement simplified and full interaction modes for the same generated world, then set the environment's observation window, frame count, and play time through the shared real-time framework.
Validate all ten task variants in live and paused modes through browser interaction, grading, verification, and the required repository tests.
```
