# Temporal Classification Pilot — 25 Random Configurations

Date: 2026-08-13

The sample is frozen in `pilot_25.json`. It was drawn uniformly without
replacement from the 750 difficulty-by-interaction configurations using seed
`weird-cua-temporal-pilot-2026-08-13`.

Each case received one source-based subagent review. The primary reviewer then
checked all 25 exact configurations against the generator, browser runtime,
controls, grader, verifier, and solver where present. The adjudicated labels
below apply `docs/controllability/temporal.md`.

## Results

| # | Exact configuration | Temporal | Required temporal form | Legacy label agrees? |
|---:|---|:---:|---|:---:|
| 1 | Slime Commute — simplified D2 | Yes | Motion and action timing | Yes |
| 2 | Crash-Deadline Hovercar — simplified D4 | Yes | Motion, duration, time-extended control | Yes |
| 3 | Floodgate Archive Rescue — simplified D4 | No | — | Yes |
| 4 | LIDAR Blacksite — full D3 | Yes | Time-extended control | Yes |
| 5 | Fake Desktop / Automation Inversion — simplified D1 | No | — | Yes |
| 6 | Domino Autopsy — simplified D1 | No | — | Yes |
| 7 | Gyroscopic Tilt Board — simplified D5 | Yes | Motion and time-extended control | Yes |
| 8 | Marionette Checkpoint — full D3 | Yes | Motion and duration | Yes |
| 9 | Wind-Tunnel Seed Courier — full D3 | Yes | Motion and time-extended control | Yes |
| 10 | Wind-Tunnel Seed Courier — simplified D2 | Yes | Motion and time-extended control | Yes |
| 11 | Five-System Verification Reactor — full D2 | Yes | Motion, order, duration, time-extended control | Yes |
| 12 | Three-Camera Claw Machine — full D5 | No | — | **No** |
| 13 | Top-Face Dice Arithmetic — full D4 | Yes | Order and hidden past state | Yes |
| 14 | Consequences Boss — full D1 | No | — | **No** |
| 15 | Dual-Projection Sculpture Rig — full D2 | Yes | Moving screen target | Yes |
| 16 | Parallax Orchard — full D4 | No | — | Yes |
| 17 | Gyroscopic Tilt Board — simplified D4 | Yes | Motion and time-extended control | Yes |
| 18 | Tomographic Baggage Surgery — simplified D4 | No | — | **No** |
| 19 | The Flat Prisoner — full D5 | Yes | Motion and time-extended control | Yes |
| 20 | Impossible Panorama — full D5 | Yes | Motion, duration, time-extended control | Yes |
| 21 | Dead Man's Switch — full D3 | Yes | Motion, duration, time-extended control | Yes |
| 22 | Parallax Orchard — simplified D4 | No | — | Yes |
| 23 | Robot Art Critic — simplified D5 | No | — | Yes |
| 24 | Live Control-Flow Wiring Lab — full D3 | Yes | Order and hidden past state | Yes |
| 25 | Parallax Orchard — full D2 | No | — | Yes |

Totals: **15 temporal**, **10 not temporal**.

The subagent and primary labels agreed on 24 of 25 cases. The primary review
changed case 16 from Yes to No: the required orbit can be a fixed sweep, and a
single nonzero endpoint image separates every detached branch tip from its
stem. Where one endpoint is occluded, the two orbit extremes cannot both hide
the same attached junction because the generated fruits are horizontally
separated while the projection reverses the depth displacement. The agent can
harvest from each current frame, and harvested state remains visible. The
earlier views do not have to be interpreted or remembered
(`shared_scripts/incubator_generators/surreal_apple_on_tree_grid.py`,
`shared_runtime/app/mechanics/surreal_apple_on_tree_grid.js`).

## Legacy disagreements

The legacy environment-level Boolean agrees with 22 of the 25 exact sampled
configurations. These three do not:

- **Three-Camera Claw Machine — full D5:** physics advances only on discrete
  actions. Current speed, tick, and all three delayed feed states are visible
  together. A cautious policy can brake until the feeds stabilize and then
  position one axis at a time without comparing screenshots or remembering a
  vanished state (`shared_runtime/app/mechanics/three_camera_claw_machine.js`,
  `shared_runtime/server/incubator_graders/three_camera_claw_machine.py`).
- **Consequences Boss — full D1:** D1 allows the same socket and seal state for
  every covenant. Repeating that state in both phases ignores the shuffled
  scene mapping entirely (`environments/consequences_boss_env/controls.json`,
  `shared_runtime/app/mechanics/consequences_boss.js`).
- **Tomographic Baggage Surgery — simplified D4:** after fixed exhaustive quota
  scans, the final hot X slice at quarter-turn one exposes all three target
  coordinates. Locking resets the internal rotation but leaves that slice
  visibly intact, so prior slices need not be remembered
  (`shared_runtime/app/mechanics/tomographic_baggage_surgery.js`, especially
  `worldCenter`, `intersections`, and `lockCase`).

The first two are configuration effects. The third is an implementation-level
shortcut in the current visible workflow. The old labels remain unchanged in
`dashboard/capability_annotations.py` and preserved verbatim in
`legacy_environment_annotations_2026-08-13.json`.

Machine-readable judgments and concise evidence are in
`pilot_25_results.json`.
