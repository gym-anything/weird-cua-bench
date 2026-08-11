# Real Time

## What changes

Real time is an evaluation setting rather than another generated task. The task, seed, difficulty, interaction mode, observation settings, and play-time allowance remain the same between live and paused runs.

The only experimental difference is whether the environment advances while the model produces its next action:

- In live mode, the environment continues during frame collection, model inference, and action execution.
- In paused mode, browser task time advances only during the configured frame-collection window. Native input and synchronous browser event dispatch happen while task time is frozen.

Do not add live-versus-paused branches to an environment. Use the shared clock and evaluation framework.

## Diagnostic definition of a real-time environment

This definition was settled on 2026-08-06. It classifies which environments actually have a real-time component: recent visual change must be used to choose an action that remains correct when it takes effect. The classification is diagnostic and does not appear in result plots unless explicitly requested.

### Symbols

```text
s, a            state, action
o(s)            what the agent sees (a screenshot)
s_tau           state tau later if the agent does nothing
v(s) in {0,1}   the verifier, read at the end
A*(s)           actions maximising P[v = 1 at the end], starting from s
Delta           delay: the agent sees o(s) at t, its action takes effect at t+Delta
w_0             declared consecutive-frame observation window
R               states reachable under an optimal policy with P[v = 1] > 0
T(s)            inf { tau > 0 : A*(s_tau) != A*(s) }
```

### Definition

An environment `E` is real-time at `(Delta, w_0)` iff:

```text
(i)    there is no f : o -> a
       with f(o(s)) in A*(s_Delta) for every s in R

(ii)   there is a g : o[t-w_0, t] -> a
       with g(o[t-w_0, t]) in A*(s_Delta) for every s in R

(iii)  inf_{s in R} T(s) < Delta
```

One frame is not enough to act on; the declared consecutive-frame window is enough; and the right action expires inside one delay.

For the benchmark runs that motivated the definition, `Delta` is approximately 30--90 seconds of measured step latency and `w_0` is six frames spanning 800 ms (`observation_window_ms: 800` and `frames_per_observation: 6`). Real-timeness is evaluated at the declared observation and action loop rather than treated as an absolute label independent of that loop.

### Required interpretation

The conjunction isolates a specific property:

- Clause (i) makes temporal visual information necessary. A single screenshot does not determine the action that will be correct when execution occurs.
- Clause (ii) makes that information available in a bounded recent window. This excludes unobservable randomness, a deadline with no precursor, and information that must be recalled from outside the declared window.
- Clause (iii) makes the temporal information operationally relevant. The optimal action changes on the timescale of the delay, so merely measuring something once and acting much later is insufficient.

Together, the model must infer motion or another changing latent state from recent frames, predict the state in which its delayed action will land, and act on a target that becomes stale during that delay. This is the real-time component being diagnosed. It is not the broader property that task-clock progression can affect an outcome.

A stationary policy is not disqualifying. It can be stationary over the dynamically inferred state; stationary does not mean single-frame. Likewise, pausing may affect a deadline, timed script, idle animation, random process, or memory task without making that task real-time under this definition.

In live mode, task time advances during `Delta`, so the prediction problem remains. In paused mode, the game-time delay from the final observation frame through model inference and native input delivery is zero. The live-versus-paused comparison therefore removes this prediction problem specifically for environments satisfying the definition, rather than merely granting extra wall-clock time.

### Principles

```text
P1   Every optimal policy must choose its action from BOTH state and time.
P2   No invented words. Standard terms only.
P3   The verifier reads the OUTCOME. Real-timeness is about how you reach it.
P4   Fixed timed schedule (up 1s, down 1s, right 1s) = NOT real-time.
     The model never looks at the state.
P5   It is a property of the ENVIRONMENT: how it changes between two of
     your actions.
P6   Time-sensitive: waste time, lose something.
P7   Act, wait 100s, act again, no penalty => NOT real-time.
P8   Constant change that only defeats fixed schedules is randomness,
     not real-timeness.
P9   Motion must be studied by the model for the optimal policy to act.
P10  An optimal stationary policy existing is NOT disqualifying.
P11  As short as possible. Mathematics, not prose.
```

P6 means action expiry rather than value loss. For example, waiting need not reduce the eventual verifier value in Rotating On-Screen Keyboard; the correct mouse target still moves. The observation-window bound is declared because an unbounded history would incorrectly admit memory tasks such as a code flashed once and typed much later.

### Reference cases

| Case | Result | Reason |
|---|---|---|
| Static CAPTCHA | No | Clauses (i) and (iii) fail. |
| CAPTCHA with an idle animation | No | Clauses (i) and (iii) fail. |
| Fixed up/down/right timed schedule | No | A solution need not study the state. |
| Card shown once and recalled later | No | The declared recent window is insufficient. |
| Code flashed for 200 ms and typed later | No | The declared recent window is insufficient. |
| Tilt maze whose ball retains momentum | Yes | Position alone is insufficient, recent motion predicts the delayed state, and the correct control expires. |
| Rotating keyboard controlled by mouse | Yes | Recent motion determines the future location of the required key. |
| The same keyboard controlled by physical keys | No | The correct physical key does not move. |
| Wind tunnel with moving apertures | Yes | Recent motion is needed to predict a time-sensitive opening. |
| Two-second deadline with no precursor | No | No observation window makes the delayed action knowable. |

The clauses are intentionally independent. Dropping (i) admits known-speed motion solvable by a schedule; dropping (ii) admits deadlines with no observable precursor; dropping (iii) admits measurements that remain actionable indefinitely; and leaving the observation window unbounded admits long-term memory tasks.

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
