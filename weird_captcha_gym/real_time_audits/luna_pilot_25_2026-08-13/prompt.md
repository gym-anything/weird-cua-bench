# Independent real-time classification prompt

Prompt version: `luna-pilot-v1`

Frozen definition source: `weird_captcha_gym/docs/controllability/real-time.md`

Frozen definition SHA-256: `2600c072c11d77c9d3fca1f05774e8398f0cbc098b874086a8eee1495d3e94f1`

The four values in `CONFIGURATION` are the only per-review substitutions.

---

You are an independent reviewer classifying exactly one Weird CUA Bench configuration.

## Configuration

- Public environment name: `{public_environment_name}`
- Environment ID: `{environment_id}`
- Difficulty: `{difficulty}`
- Interaction mode: `{interaction_mode}`

Decide whether this exact configuration is real-time under the frozen mathematical definition below.

Do not use an existing classification, capability annotation, audit result, result matrix, or another reviewer's answer. Do not infer the answer from the environment name or task description.

Read `AGENTS.md` and `weird_captcha_gym/docs/controllability/real-time.md` completely. Then read the complete relevant implementation:

1. the exact difficulty and interaction profile in `controls.json`;
2. the generator;
3. the visible browser implementation and relevant CSS;
4. the grader and verifier; and
5. the solver, when present.

Study a normal screenshot-only solution using visible task controls. Private state and scripted solvers are implementation evidence, not information available to the policy.

## Frozen mathematical definition

```text
H_t              visible interaction history through task time t
I_t              the agent's own prior actions and task times in H_t
W_t^w            the visible window from t-w through t
u                 terminal task outcome, with less task-active continuation
                  time after delivery of the next action used only to break
                  ties between equal outcomes
D                 one grouped control mode
C_Delta(D)        histories in D from which success remains possible after Delta
                  of no new action
A*_Delta(H_t)     actions maximising expected u when delivered at t+Delta,
                  followed by optimal continuation
H_t^tau           history tau later if the agent supplies no new action
Q(H_t, a)         expected u if a is the next action, followed by optimal continuation
```

Expectations use only visible task information and average over future randomness; private generator or page state is not available to the policy. For a fixed difficulty and interaction configuration, `D` contains every occurrence across seeds, rounds, and attempts of the same outcome-affecting control mode. It is not a hand-picked early interval. `C_Delta(D)` removes only histories whose outcome is already unsalvageable after the delay.

A fixed difficulty and interaction configuration of `E` is real-time iff there are a grouped control mode `D`, a delay `Delta > 0`, and a bounded visual window `w` such that `C_Delta(D)` is nonempty and:

```text
(i)    there is no q : I_t -> a
       with q(I_t) in A*_Delta(H_t) for every H_t in C_Delta(D)

(ii)   there is a g : (I_t, W_t^w) -> a
       with g(I_t, W_t^w) in A*_Delta(H_t)
       for every H_t in C_Delta(D)

(iii)  for some H_t in C_Delta(D), action a, and 0 < tau < Delta,
       the environment changes autonomously from H_t to H_t^tau,
       success remains possible from H_t^tau, and

       Q(H_t^tau, a) < Q(H_t, a)

       or

       Q(H_t^tau, a) - Q(H_t^tau, no-op)
         < Q(H_t, a) - Q(H_t, no-op).
```

An unavailable or ineffective action has the value of `no-op`. The strict loss in clause (iii) must be caused by non-clock task-state evolution, not merely by less remaining deadline or later completion. An action becoming enabled or more effective after a fixed wait does not satisfy the clause. A fixed animation that later enables controls or permanently archives its result is not an expiring opportunity.

The three clauses must be witnessed by the same phenomenon. The autonomous evolution in clause (iii) must be visibly evidenced within `W_t^w`, and that evidence must be what makes the delayed-optimal action depend on observation in clauses (i) and (ii). The window must support prediction of the evolution's effect at `t+Delta`; unrelated idle animation or future randomness independent of the window cannot supply clause (iii).

The evidence may appear across consecutive frames or as an accumulated visible trace, chart, or trajectory in one screenshot. A single screenshot is allowed when it visibly contains the relevant temporal evidence. This does not admit a static puzzle next to an unrelated animation.

`Delta` is a reported witness horizon on the time scale of the task behavior, not the current provider's response latency. It must begin inside a nontrivial active control opportunity and may extend across the point at which that opportunity gets worse or closes. The configured `observation_window_ms` and `frames_per_observation` bound `w`; they do not force every environment to need every captured frame.

The conjunction has these required consequences:

- Clause (i) rules out a fixed schedule or a policy driven only by the agent's own action clock.
- Clause (ii) requires a bounded recent visual window to be sufficient. This excludes unobservable randomness and information that must be recalled only from outside the window.
- Clause (iii) requires a useful action opportunity to get worse inside the delay because the task state changes. This excludes fixed waits, minimum-duration holds solvable from the agent's own clock, and information that remains actionable indefinitely.
- A stationary visual policy is allowed. It can map the currently evidenced changing state to an action without using absolute task time.
- All three clauses must use one common `D`, `Delta`, `w`, and visible autonomous process.

## Review procedure

1. State the controls available in this exact difficulty and interaction mode.
2. Describe every period in which the task changes without a new agent action.
3. State whether an outcome-affecting control remains available during each such period.
4. Enumerate the legitimate grouped control modes `D`.
5. Try to construct an observation-free policy `q` using only `I_t`.
6. Try to construct a bounded-window policy `g` using only `I_t` and `W_t^w`.
7. Check whether the same visible autonomous process causes an available action to become unavailable or strictly less effective within some `Delta`.
8. For `yes`, give one concrete common witness: `D`, `Delta`, `w`, the visible process, why `q` fails, why `g` succeeds, and the expiring or degrading action.
9. For `no`, identify the failed clause and explain why no legitimate choice of `D`, `Delta`, and `w` repairs it.
10. Return `unresolved` instead of guessing when the complete source does not determine the answer.

Return exactly one JSON object:

```json
{
  "public_environment_name": "{public_environment_name}",
  "environment_id": "{environment_id}",
  "difficulty": "{difficulty}",
  "interaction_mode": "{interaction_mode}",
  "label": "yes | no | unresolved",
  "controls_available": [],
  "autonomous_processes": [],
  "grouped_control_modes": [],
  "delta_ms": null,
  "window_ms": null,
  "clause_i": {"holds": true, "reason": ""},
  "clause_ii": {"holds": true, "reason": ""},
  "clause_iii": {"holds": true, "reason": ""},
  "common_visible_process": "",
  "files_read_completely": [],
  "source_evidence": [
    {"path": "", "lines": "", "claim": ""}
  ],
  "uncertainties": []
}
```

Do not edit repository files. Your JSON response is the preserved first-pass review.
