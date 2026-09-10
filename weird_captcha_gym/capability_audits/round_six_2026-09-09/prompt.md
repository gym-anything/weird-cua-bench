# Capability audit of one new environment

You are reviewing exactly one environment from PR #52 at revision
`48e86f5950c056bfa0f2822fa430f9762c5fc29c`.
The assignment supplies `AUDIT_ROOT`, `CASE_INDEX`, `ENVIRONMENT_ID`, and
`PUBLIC_NAME`. These are the only per-review substitutions.

The source snapshot is `AUDIT_ROOT/source`. It is a copy of source files from
the immutable revision, verified against Git blob hashes. Work from that
snapshot rather than the older checkout that may be your default directory.

## Task

Audit the four core capabilities required by a normal screenshot-only UI
solution of this environment's canonical baseline. Read its baseline
difficulty and interaction mode from `controls.json`; do not default to D3
or Full. Examine every difficulty and interaction profile and explicitly
record any configuration whose capability requirements differ. The main
output is one baseline classification per environment. Temporal labels in
this pass are provisional; the dedicated configuration-wide temporal audit
is deferred. Do not assign real-time labels or reassess difficulty levels.

Read the snapshot's complete `AGENTS.md`,
`weird_captcha_gym/docs/capability-annotation-guidelines.md`, and
`weird_captcha_gym/docs/controllability/temporal.md`.
Then read the complete environment `env.json`, canonical `task.json`,
`controls.json`, generator, browser JS and relevant CSS, grader, exported
verifier, and solver when present. Follow shared imports that implement
relevant task behavior. Do not classify from descriptions, source titles,
keyword searches, comments, metadata capability tags, or private-state
solver strategies alone. Read long files in successive chunks through EOF.

Use these existing broad categories:

- Visual understanding: 2D or 3D, according to the spatial understanding
  required to solve the task. Decorative perspective alone is insufficient
  for 3D.
- Temporal understanding and memory: a solution requires interpreting change,
  motion, duration, relevant hidden earlier state, or a nontrivial temporal
  relationship; sustained action timing/control also counts under the
  current temporal guideline. A simple visible sequence or an automatic
  animation followed by an actionable static result does not suffice.
- Reasoning and planning: solving requires inferring constraints or choosing
  actions whose consequences matter later. Explain the concrete decision or
  dependency involved. Basic visual recognition alone does not establish it.
- Exploration and interface understanding: the agent must interact to reveal
  relevant information or learn how the interface behaves before solving.
  A visible transition that simply supplies the next required information,
  routine feedback, or following explicit controls does not suffice alone.

Base each label on what the visible UI solution actually needs. Check whether
relevant information persists on screen, is automatically revealed, or is
available through a simpler legitimate UI solution. Distinguish solver access
to hidden truth from information the agent can see. Where the code leaves a
material uncertainty, use `unresolved` and say what evidence is missing.

This is an audit, not an implementation assignment. Do not edit any source,
run a creator, add new task behavior, or change stored creator labels. Do not
control the user's desktop or browser. Any optional runtime check must be
headless, isolated, and run against the snapshot. Do not claim gameplay
verification based on source reading.

## Deliverable

Using apply_patch, write `AUDIT_ROOT/reviews/CASE_INDEX_ENVIRONMENT_ID.json`
(CASE_INDEX is padded to three digits). Return a brief final message with its
path and labels. Preserve the first-pass result; any follow-up will be saved
separately. Do not inspect other reviewers' outputs. Do not spawn subagents.

Use this schema (include every required field):

```json
{
  "case_index": 1,
  "environment_id": "example_env",
  "public_name": "Exact public name",
  "revision": "48e86f5950c056bfa0f2822fa430f9762c5fc29c",
  "baseline": {"difficulty": 3, "interaction": "full"},
  "labels": {
    "visual": "2D | 3D | unresolved",
    "temporal": "yes | no | unresolved",
    "reasoning_planning": "yes | no | unresolved",
    "exploration_interface": "yes | no | unresolved"
  },
  "temporal_status": "provisional_baseline_audit",
  "visible_solution": "Concrete sequence explaining how a screenshot-only agent can solve.",
  "reasoning": {
    "visual": "Specific necessary spatial information.",
    "temporal": "Specific temporal demand, or a solution that avoids it.",
    "reasoning_planning": "Specific inference or action dependency, or why neither is required.",
    "exploration_interface": "What must be revealed or learned through interaction, or why the visible state/instructions suffice."
  },
  "source_evidence": [
    {"capability": "visual", "path": "relative/source/path", "lines": "10-25", "claim": "What the implementation establishes."}
  ],
  "configuration_exceptions": [
    {"difficulties": [1], "interaction_modes": ["simplified"], "capability": "reasoning_planning", "label": "no", "reason": "Specific implemented difference", "source_evidence": []}
  ],
  "observation_only_temporal": false,
  "files_read_completely": ["relative/source/path"],
  "runtime_checks": [],
  "uncertainties": []
}
```

Give source evidence for all four decisions, including No labels. An empty
configuration_exceptions list means you examined the profiles and found no
supported exception; if you could not establish a profile's requirements,
record that limitation in uncertainties. Do not invent an exception merely
to make the audit look productive.
