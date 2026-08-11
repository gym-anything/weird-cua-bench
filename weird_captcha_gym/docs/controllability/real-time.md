# Real Time

## What changes

Real time is an evaluation setting rather than another generated task. The task, seed, difficulty, interaction mode, observation settings, and play-time allowance remain the same between live and paused runs.

The only experimental difference is whether the environment advances while the model produces its next action:

- In live mode, the environment continues during frame collection, model inference, and action execution.
- In paused mode, browser task time advances only during the configured frame-collection window. Native input and synchronous browser event dispatch happen while task time is frozen.

Do not add live-versus-paused branches to an environment. Use the shared clock and evaluation framework.

## Environment settings

Set three values from the behavior of the environment:

- `observation_window_ms` is the task time covered by one observation.
- `frames_per_observation` is the number of chronological frames captured across that window.
- `play_time_seconds` is the maximum task-active time available for the episode.

Choose the window and frame count with two separate checks:

1. Determine whether any valid solution needs task-clock progress. This includes action-triggered timers, animation or physics ticks, held-input movement, and duration-based gestures even when the agent does not need temporal reasoning. Use a zero-length window only when every required transition can complete synchronously at the paused action boundary.
2. Determine what the agent must observe during that progress. Use one endpoint frame when only the resulting state matters. Use multiple chronological frames when direction, trajectory, phase, or a transient visual state is needed for the next action.

Choose `observation_window_ms` against the environment's actual time constants at all five difficulties, not against whether the task is described as static or temporal. Keep it short enough to preserve useful control opportunities and transient information, but long enough that required progress completes in a practical number of fixed windows. Set `play_time_seconds` so the complete interaction remains feasible and finite.

The latest captured frame remains `obs["screen"]`. The complete chronological sequence is `obs["frames"]`.

Both values remain ordinary Gym-Anything observations. Local runs store the frames in the Gym-Anything episode directory. Remote runs use the normal Gym-Anything master and worker routing, then download the captured frame window into the remote client's local artifact cache. The Weird CUA Qwen 3.5 adapter subclasses Gym-Anything's current `Qwen35VLAgent` and changes only image ingestion so paths, in-memory FastIO images, remote base64 images, and chronological frame sequences are accepted.

## Paused action cycle

The shared paused cycle is:

1. Run the environment for the observation window and capture the configured frames.
2. Pause the environment.
3. Keep it paused throughout model inference and request retries.
4. Arm a browser-visible input barrier while task time remains paused.
5. Deliver the complete native action and confirm trusted browser event dispatch plus synchronous handler completion.
6. Re-scan and pause CSS or Web Animations created by the action.
7. Advance exactly `observation_window_ms`, capture the configured frames, and pause at the exact virtual endpoint.

A click or drag therefore lands on the same virtual world shown at the final observation frame. Native input latency is recorded as wall-time telemetry but does not move the task. A handler can start a timer, animation, or physical transition while paused; that asynchronous effect begins advancing only inside the next fixed observation window. If it is unfinished at the endpoint, the next model observation exposes the unfinished state. The evaluator does not wait for environment-specific action settlement outside the window.

Task time includes continuous wall time in live mode and fixed observation windows in paused mode. Model response time and native input-transport time are excluded only in paused mode. A final provider timeout or failure terminates the episode without advancing paused task time.

The public browser inspector exposes the same settings for visual inspection. It is a demonstration surface rather than an authoritative evaluation run.
