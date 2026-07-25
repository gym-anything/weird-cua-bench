# Controllability Plan

Status: design recorded; ten starred environments have difficulty controls

This document records how Weird CUA Bench should vary difficulty, interaction, and real time without duplicating puzzle implementations.

## Basic structure

Each environment keeps one generator, one browser implementation, one grader, and one verifier.

Difficulty and interaction create task variants. Real time remains an evaluation setting controlled by the framework.

| Dimension | Values | Controlled by |
|---|---|---|
| Difficulty | Levels 1 through 5 | Task generation |
| Interaction | Simplified or full | Task interface |
| Real time | Paused or live | Evaluation framework |

Five difficulty levels crossed with two interaction modes produce ten tasks per environment. Running each task in paused and live modes produces twenty evaluation settings per seed.

Seeds remain separate from tasks. A task identifies a condition. A runtime seed identifies a generated puzzle instance.

## Implemented difficulty pilot

The first pilot covered five environments selected from the starred set:

1. Input-Lag Forklift
2. Parallax Orchard
3. Rotating On-Screen Keyboard
4. Rotate The Wrong Thing Upright
5. Insider Trading CAPTCHA

The second set adds five more starred environments:

1. Flat Prisoner
2. Board Game CAPTCHA
3. Flat Pack Compliance
4. Specular Lighthouse Relay
5. Motion-Only Ghost Jigsaw

Each environment now has a `controls.json` file with an independently assigned baseline and five difficulty profiles. The profiles change several relevant parameters where appropriate. This includes task size, required precision, action delay, motion speed, available information, visual ambiguity, and the number of variables that must be handled.

The existing task remains unchanged. Controlled tasks are materialized into a separate output directory with:

```bash
python3 benchmarks/weird_captcha_gym/tools/materialize_controlled_tasks.py \
  --all-controlled \
  --output-root /tmp/weird-cua-controlled
```

The command currently writes five tasks per controlled environment because only each environment's existing interaction mode has been implemented. It writes 50 tasks in total. It will write both interaction modes after those interfaces exist.

The selected condition is copied into the task metadata, public state, and hidden state. Difficulty-specific instructions replace the baseline instructions when a profile changes a rule that the agent must know.

Focused tests are in `tests/test_weird_captcha_controls.py`. They check deterministic materialization, baseline preservation, profile parameters, challenge identity, and successful grader replay across all five levels.

The public dashboard exposes these five levels through a selector on each controlled environment dossier. Static browser play ships four generated challenges per level. Local browser play creates the selected controlled task inside the temporary session directory. Neither path adds generated task folders to the original corpus.

## The current task is a reference point

The current difficulty level must be judged independently for every environment after inspecting its generated problem size and solution requirements. The current implementation might belong at any of the five levels. It must not automatically be placed at level 3.

Whichever level is assigned to the current implementation should reproduce the current puzzle parameters for a fixed seed. The remaining levels are then defined above or below it as appropriate.

The current interaction interface must not automatically be called full. Some current environments already use simplified controls. Each environment must explicitly record whether its current interface is simplified or full.

The current real-time behavior is live.

The reference condition for an environment is therefore:

```text
difficulty = the current implementation's independently assigned level
interaction = the current interface classification
real_time = live
```

For example, LIDAR Blacksite currently has a simplified interaction interface. Its spatial problem is difficult, but its actions are exposed through six labelled movement controls, one scan action, one pickup action, and one verification action. The interface performs the scanner operation and determines when pickup and verification are available. The difficulty of understanding the lightless world does not make the interaction interface full.

## One control specification per environment

Each environment should contain one `controls.json` file. It is the source for every controlled task in that environment.

```json
{
  "baseline": {
    "difficulty": null,
    "interaction": "simplified",
    "real_time": "live"
  },
  "difficulty": {
    "1": {
      "label": "very_easy",
      "parameters": {}
    },
    "2": {
      "label": "easy",
      "parameters": {}
    },
    "3": {
      "label": "medium",
      "parameters": {}
    },
    "4": {
      "label": "hard",
      "parameters": {}
    },
    "5": {
      "label": "very_hard",
      "parameters": {}
    }
  },
  "interaction": {
    "simplified": {},
    "full": {}
  },
  "real_time": {
    "play_time_seconds": 90,
    "observation_window_ms": 800,
    "frames_per_observation": 6
  }
}
```

The `null` baseline difficulty in this example must be replaced with an integer from 1 through 5 after inspecting that environment. It is not a default value.

The parameter names inside each difficulty level remain specific to the environment. The common structure is the five ordered levels rather than a universal set of puzzle parameters.

## Difficulty

The five difficulty values are ordered within an environment.

Levels can vary the number of objects, number of stages, number of variables, route length, simultaneous events, or other appropriate parameters. The independently assigned baseline level preserves the current generated task. Lower levels reduce relevant parameters. Higher levels increase them.

The same number does not initially claim equal human difficulty across different environments. Human completion rates and completion times can later calibrate those relationships.

The existing dashboard annotations already list potential difficulty parameters for all 75 environments. They provide the starting checklist for each `controls.json` file.

## Interaction

Interaction has two values: simplified and full.

**Interaction is how the computer-use agent uses mouse and keyboard to make an intended action happen in the interface.**

Interaction controls how the agent produces an action. It does not control what the puzzle asks the agent to perceive, understand, remember, or plan.

Simplified interaction exposes proxy controls that produce an action's effect directly. Examples include click-to-place instead of dragging, sequential controls instead of simultaneous controls, or explicit action buttons instead of direct manipulation.

Full interaction requires the task-appropriate mouse or keyboard manipulation that produces the same effect. This may involve mouse movement, dragging, holding, tracing, direct object manipulation, or another input appropriate to that particular environment.

The simplified and full variants should not create different visual, temporal, or reasoning problems merely to make one variant harder. They should preserve the generated world, available information, goal, and action effects while changing how the agent carries out those actions.

These labels describe the interface rather than the overall difficulty of the puzzle. An environment can require difficult visual understanding, exploration, or planning while still using simplified interaction.

For a fixed seed and difficulty, the simplified and full tasks should use the same generated world and the same goal. Only the interaction interface and the corresponding grading requirements should change.

Each environment must state two things:

1. Whether its current interface is simplified or full.
2. What changes between its simplified and full variants.

No global assumption should replace this environment-level decision.

### LIDAR Blacksite example

The current LIDAR Blacksite interface is simplified because side-panel controls directly trigger movement, scanning, pickup, and verification.

Its full interaction variant should preserve the same facility, scan behavior, beacon, exit, and success condition. The proxy controls should be replaced with direct task-surface interaction. The agent would turn and aim through viewport mouse movement, use the appropriate held movement input, operate the scanner through a direct viewport gesture, pick up the beacon through the scene, and complete extraction by physically entering the gate.

This is only the mapping for LIDAR Blacksite. Other environments require their own simplified-to-full mapping based on the actions represented in their interfaces. The benchmark should not impose LIDAR's gestures on unrelated tasks.

## Real time

Real time does not create more tasks. The runner should accept:

```text
--time-mode live
--time-mode paused
```

In live mode, the environment continues while the model produces its next action.

In paused mode, the framework should:

1. Advance the environment for `observation_window_ms`.
2. Capture `frames_per_observation` frames across that interval.
3. Pause the environment.
4. Send the frames to the model.
5. Keep the environment paused during model inference.
6. Resume the environment while applying the action.
7. Begin the next observation interval.

The environment may advance for at most `play_time_seconds`. Model inference time does not consume this time in paused mode. It does consume real elapsed time in live mode.

The observation should retain the latest screenshot for existing agents and add a frame sequence for agents that accept several images:

```json
{
  "screen": "latest-frame.png",
  "frames": [
    "frame-1.png",
    "frame-2.png",
    "frame-3.png"
  ]
}
```

Static environments can use one frame and a zero-length observation window.

The current Gym Anything `synchronous` field only waits between an action and the next screenshot. It does not pause the environment. The framework therefore needs explicit operations equivalent to:

```text
pause_environment()
advance_environment(milliseconds)
resume_environment()
```

Pausing must stop the puzzle clock. The clock must not jump forward by the duration of model inference when the environment resumes.

## Generated tasks

A deterministic repository tool should eventually expand `controls.json` into ten task specifications:

```text
puzzle_d1_simplified
puzzle_d1_full
puzzle_d2_simplified
puzzle_d2_full
...
puzzle_d5_simplified
puzzle_d5_full
```

Each generated task carries its selected condition and parameters in task metadata. The condition also appears in public state and hidden state. The grader binds its result to the task and condition.

Generated task directories do not copy the generator, browser code, grader, or verifier. All variants reuse the same environment implementation.

For interaction pairs, random generation must not depend on the interaction mode. This ensures that both modes receive the same world for the same seed and difficulty.

## Required checks

The controlled benchmark should verify all of the following:

1. Every environment generates exactly ten task conditions.
2. The independently assigned baseline difficulty with the recorded current interaction mode reproduces the current task for a fixed seed.
3. Simplified and full interaction variants share the same generated world and goal for a fixed seed and difficulty.
4. The condition is preserved through generation, browser state, grading, export, and verification.
5. An artificial delay in model inference advances the live environment but does not advance the paused environment.
6. Generated task files are deterministic and match their source `controls.json` files.
7. The existing benchmark tests, browser smoke tests, and strict quality audit continue to exercise the relevant paths.

## Implementation order

1. Add the control specification and deterministic task generator. Ten starred environments are complete.
2. Add framework pause, advance, and multi-frame observation support.
3. Test the complete structure on Board Game CAPTCHA, Motion-Only Ghost Jigsaw, Dead Man's Switch, Domino Autopsy, and Tiny FPS Customs.
4. Use the existing difficulty annotations to define the five levels for the remaining environments.
5. Classify the current interaction interface of every environment before designing its missing interaction variant.
6. Generate the complete task matrix.
7. Calibrate the levels with human completion rates and completion times.

The current evaluation manifests fingerprint the existing 75-task corpus. The controlled benchmark must use a new version so existing evaluation results remain reproducible.
