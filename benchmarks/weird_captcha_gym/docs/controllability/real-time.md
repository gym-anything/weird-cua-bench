# Real Time

## What changes

Real time is an evaluation setting rather than another generated task. The task, seed, difficulty, interaction mode, observation settings, and play-time allowance remain the same between live and paused runs.

The only experimental difference is whether the environment advances while the model produces its next action:

- In live mode, the environment continues during frame collection, model inference, and action execution.
- In paused mode, the environment runs during frame collection and action execution but stops during model inference.

Do not add live-versus-paused branches to an environment. Use the shared clock and evaluation framework.

## Environment settings

Set three values from the behavior of the environment:

- `observation_window_ms` is the task time covered by one observation.
- `frames_per_observation` is the number of chronological frames captured across that window.
- `play_time_seconds` is the maximum task-active time available for the episode.

A static task uses a zero-length window and one frame. A changing task needs a window long enough to expose the motion or state change needed for action. Its frame count should represent that change without adding redundant copies. Its play time should allow a feasible complete interaction while remaining finite.

The latest captured frame remains `obs["screen"]`. The complete chronological sequence is `obs["frames"]`.

## Paused action cycle

The shared paused cycle is:

1. Run the environment for the observation window and capture the configured frames.
2. Pause the environment.
3. Keep it paused throughout model inference and request retries.
4. Resume the environment before applying the action.
5. Execute the complete action while the environment is running.
6. Pause after the action and begin the next observation cycle.

A click therefore lands on the resumed world. A drag runs while the world is advancing. The task may change between the last observation frame and action execution; paused mode removes model-inference time rather than turning a moving task into a static one.

Task time includes observation windows and action execution in both modes. Model response time is excluded only in paused mode. A final provider timeout or failure terminates the episode without advancing paused task time.

The public browser inspector exposes the same settings for visual inspection. It is a demonstration surface rather than an authoritative evaluation run.
