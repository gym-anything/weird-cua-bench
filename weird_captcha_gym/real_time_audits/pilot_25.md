# Real-time classification pilot: 25 random configurations

This is the first source-based audit of the 750-case matrix. The fixed random
sample is recorded in `pilot_25.json` with seed
`weird-cua-real-time-pilot-2026-08-11`.

Three reviewers independently classified all 25 configurations after reading
the relevant generator, browser mechanic, controls, grader, verifier, and
solver where present. Disagreements were resolved from the implementation and
then all three reviewers reapplied the final definition independently.

## Method

The diagnostic definition is in
`weird_captcha_gym/docs/controllability/real-time.md`. Classification is per
fixed difficulty and interaction configuration. A positive case supplies:

1. a grouped control mode and a mechanic-scale delay `Delta`;
2. no successful policy driven only by the agent's own actions and task clock;
3. a bounded recent visual window that does supply a delayed-optimal action;
4. visually evidenced autonomous evolution that strictly reduces that
   action's outcome, advantage, or effectiveness within `Delta`.

The same evolution must witness all three clauses. A chart or trajectory
accumulated in one screenshot can supply temporal evidence. A fixed wait,
minimum-duration hold, unrelated animation, permanently archived response,
unobservable future randomness, or long-term memory requirement cannot.

## Result

**11 of the 25 configurations are real-time and 14 are not.**

| # | Configuration | Result | Example `Delta` or decisive reason |
|---:|---|:---:|---|
| 1 | Kinetic Restoration Press · Simplified · D4 | No | Playback has no work action; afterward the workbench is static, and the bounded window does not contain the complete film order. |
| 2 | Specular Lighthouse Relay · Full · D3 | **Yes** | About 320 ms: visible receiver motion predicts delayed mirror steering, and an old correction loses charge advantage. |
| 3 | Rorschach / Subjective Prompt With A Fixed Rubric · Simplified · D1 | No | Each fixed response is permanently archived and merely re-enables controls; no useful action opportunity gets worse. |
| 4 | Insider Trading CAPTCHA · Simplified · D1 | **Yes** | About 800 ms: the accumulated chart predicts delayed order value, and price evolution changes the order's expected profit. |
| 5 | Insider Trading CAPTCHA · Simplified · D2 | **Yes** | About 800 ms: the faster tape and three-tick settlement preserve the same chart-dependent expiring order opportunity. |
| 6 | Portal Freight: Oversized Parcel · Simplified · D5 | No | Portal and parcel state change synchronously in action handlers; nothing relevant evolves between actions. |
| 7 | The Photograph Eats the Room · Full · D4 | **Yes** | About 350 ms: a persisted held movement keeps changing camera and collision state, so the visible scene determines a delayed release or correction. |
| 8 | Recursive Dollhouse Smuggling · Full · D1 | No | Drags and portal transitions are action-triggered and synchronous. |
| 9 | Occlusion Shell Swindle · Full · D5 | **Yes** | About 300 ms: shell motion identifies the relevant peephole, whose sampling advantage disappears when the inspection window closes. |
| 10 | Trajectory Catcher · Full · D2 | **Yes** | About 800 ms: the accumulated visible flight trace predicts catcher placement while autonomous flight closes the transform-and-arm window. |
| 11 | Occlusion Shell Swindle · Simplified · D3 | **Yes** | About 300 ms: recent shell motion determines the relay, and the action becomes ineffective when the shuffle opportunity closes. |
| 12 | Dead Man's Switch · Full · D4 | **Yes** | About 250 ms: recent plate motion predicts the delayed pointer target, and the old coordinate loses hold advantage. |
| 13 | Marionette Checkpoint · Simplified · D2 | No | An observation-free policy sets active strings 0 and 2 to 65 and remains within both 20 px allowances for every generated phase and tick. |
| 14 | Shadow Crime Lab · Full · D4 | No | Sampling, tagging, and shadows change only in response to actions. |
| 15 | Flat-Pack Compliance Test · Full · D4 | No | Assembly is static; assembly controls are disabled during the deterministic load test. |
| 16 | Kinetic Restoration Press · Full · D3 | No | Playback only enables a later static work phase, and the bounded recent window cannot supply the complete film order. |
| 17 | Flat-Pack Compliance Test · Simplified · D1 | No | Static assembly is followed by a deterministic, non-intervenable load test. |
| 18 | Reload Interruption · Simplified · D5 | No | The moving spark is irrelevant to the simplified fixed stabilizer; release timing comes from the agent's own hold clock. |
| 19 | Temporal Memory / First-Change Evidence · Simplified · D1 | No | Simplified lens controls are unavailable during autonomous playback; the later review is manually scrubbed and selection requires memory. |
| 20 | Hologram Silhouette Foundry · Full · D1 | No | Rod transforms and casting are action-triggered. |
| 21 | Elastic Membrane Sorter · Full · D4 | **Yes** | About 300 ms: recent marble motion reveals momentum, and an old post correction becomes less effective as the marble advances. |
| 22 | Specular Lighthouse Relay · Simplified · D5 | **Yes** | About 320 ms: the moving receiver produces the same observation-dependent loss through simplified mirror controls. |
| 23 | Trajectory Catcher · Simplified · D2 | **Yes** | About 800 ms: the interaction surface changes, but the visible trajectory and expiring commit window are the same as Full. |
| 24 | Rotate The Wrong Thing Upright · Full · D5 | No | Gimbal state changes only through direct actions. |
| 25 | Semantic Drag-And-Drop Absurdity · Full · D5 | No | Probe timing is known from the agent's own press; sampled eligibility persists after the visible response fades, so routing does not expire. |

Ordered labels:

```text
N, Y, N, Y, Y, N, Y, N, Y, Y, Y, Y, N, N, N, N, N, N, N, N, Y, Y, Y, N, N
```

## Disagreements resolved from source

### A single screenshot can contain temporal evidence

Insider Trading CAPTCHA remains real-time because the visible chart is an
accumulated record of price evolution. Missing the opportunity changes the
expected value of the delayed order. Requiring two newly captured frames would
incorrectly reject this case.

Trajectory Catcher likewise retains an accumulated flight tail, but that does
not make it static: the tail predicts catcher geometry while flight progress
closes `commitOpen`, after which the same transform or arm action is
ineffective.

### Fixed waits and archived responses do not qualify

Rorschach writes the final response label permanently into the specimen badge
and then re-enables controls. Missing the animation loses no information or
action opportunity. Reload Interruption's simplified hold is scheduled from
the agent's own pointer-down time. Both are non-real-time under different
clauses.

### Marionette D2 has a fixed robust policy

Only strings 0 and 2 are active. Setting both to 65 gives maximum left-hand
and left-foot errors of 15.59 px and 10.89 px, below the 20 px allowance for
every permitted target phase and tick. The moving targets therefore do not
defeat an observation-free policy at this sampled difficulty.

### Available controls must coexist with autonomous evolution

Temporal Memory's simplified coordinate lens is hidden and non-interactive
during live playback. It becomes available only in the manual review phase.
Flat-Pack similarly disables assembly controls during its automatic load
test. Autonomous animation alone is not enough.

### Held input can produce between-step evolution

In The Photograph Eats the Room, a key-down delivered through `env.step`
persists until a later key-up. During no-new-action time the camera continues
through generated geometry. The recent visual window is needed to decide the
later release, redirect, or capture, so the configuration is real-time.

## Evidence locations

- Definition and interpretation:
  `weird_captcha_gym/docs/controllability/real-time.md`
- Exact fixed sample: `weird_captcha_gym/real_time_audits/pilot_25.json`
- Per-environment schedules and interaction contracts: each environment's
  `controls.json` and `env.json`
- Visible behavior: `weird_captcha_gym/shared_runtime/app/mechanics/`
- Outcome replay: `weird_captcha_gym/shared_runtime/server/incubator_graders/`
- Generated state and time constants: `weird_captcha_gym/shared_scripts/`
- Programmatic solution evidence: `weird_captcha_gym/tools/incubator_solvers/`
