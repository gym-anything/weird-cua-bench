# Interaction VII–VIII design audit (new cohort)

Date: 2026-07-14

## Why this is a new cohort

The dashboard no longer contains an unimplemented Incubator queue. All 43
historical Incubator and Interaction III–VI selections are built. The ten
mechanics below are a newly selected cohort from unused or weakly explored
survey mechanics. They must not be described as pre-existing cards.

The selection assumes a solver with excellent OCR, recognition, world
knowledge, logic, and static visual reasoning. Each task therefore starts from
a control-loop weakness rather than a question whose answer happens to be
shown in a browser.

## Selection gate

Every selected mechanic must satisfy all of these before implementation:

1. One clean screenshot is insufficient to determine and execute the answer.
2. The dominant interaction bottleneck is materially different from the 63
   built candidates.
3. Visible geometry, hit testing, simulation, and independent replay can share
   a precise contract.
4. Difficulty can be increased through state, dynamics, and manipulation—not
   tiny targets, hostile latency, hidden quotas, or tutorial suppression.
5. A human can diagnose failure and recover without guessing at arbitrary
   verifier state.

## The ten

### 1. `specular_lighthouse_relay` — Specular Lighthouse Relay

- **Interaction bottleneck:** precision reflected-ray steering across four
  regenerated optical benches, three gimballed mirrors, and four receivers
  that must be charged in order.
- **Why a static genius still pays:** every mirror adjustment changes every
  downstream bounce; each shutter begins from a different geometry; charge is
  accumulated only while the real reflected beam stays on target.
- **Physical contract:** analytic line/segment reflection, finite mirror
  intersection, one-degree gimbal steps, receiver dwell, and ordered charge
  replay without consulting the hidden authored angle plan.
- **Source anchors:** CAPTCHA Royale `mirror` and `gears`; NextGen-CAPTCHAs
  `Shadow_Direction`.
- **Original transformation:** turn static mirror/shadow selection into a live
  optical bench whose full ray path is manipulated and replayed.

### 2. `wind_tunnel_seed_courier` — Wind-Tunnel Seed Courier

- **Interaction bottleneck:** indirect closed-loop control through four local
  fans while a light seed pod carries momentum through moving gates and every
  fan accumulates irreversible heat while armed.
- **Why a static genius still pays:** the action controls a force field, not the
  pod; observations become stale while drag, gusts, fan spool-up, aperture
  motion, and thermal debt continue.
- **Physical contract:** fixed-step force integration, fan falloff and spool,
  thermal trips, tick-driven gate motion, swept crossings, ordered gates, and
  dock capture.
- **Source anchors:** OpenCaptchaWorld `Path_Finder` and `Hold_Button`;
  CaptchaWare `fishingGame`.
- **Original transformation:** replace direct point-and-click path finding with
  a persistent aerodynamics control loop.

### 3. `hologram_silhouette_foundry` — Hologram Silhouette Foundry

- **Interaction bottleneck:** construct one 3D arrangement from three linked
  orthographic silhouettes by translating and reorienting four rods.
- **Why a static genius still pays:** every translation constrains two projections,
  every rotation changes projected occupancy, and all three projections must be
  reconciled before the cast can be sealed.
- **Physical contract:** shared 3D voxel/rod geometry, three camera
  projections, discrete translations and axis rotations, intentional
  holographic interpenetration, and exact silhouette masks.
- **Source anchors:** NextGen-CAPTCHAs `3D_Viewpoint`, `Layered_Stack`, and
  `Box_Folding`; CAPTCHA Royale `spatial` and `cubefolding`.
- **Original transformation:** turn static spatial multiple choice into an
  inverse-construction workbench.

### 4. `orbital_docking_customs` — Orbital Docking Customs

- **Interaction bottleneck:** inertial translation and rotation with limited
  thruster authority, fuel, and a rotating target port.
- **Why a static genius still pays:** knowing the desired trajectory does not
  execute it; braking, attitude, relative velocity, and contact timing require
  many observe–act corrections.
- **Physical contract:** deterministic fixed-step inertial integration,
  thruster impulses, finite fuel, circle-contact debris collision,
  docking-normal alignment, and relative speed tolerance.
- **Source anchors:** OpenCaptchaWorld `Coordinates` and `Path_Finder`; the
  parking-control lineage in Neal's *I'm Not a Robot*.
- **Original transformation:** replace coordinate placement with an inertial
  rendezvous whose final docking request is accepted only at low relative
  speed and the live port attitude.

### 5. `gravity_room_freight` — Gravity-Room Freight

- **Interaction bottleneck:** rotate an entire chamber while a sealed capsule
  repeatedly slides to hard support in the changing room frame.
- **Why a static genius still pays:** each quarter-turn rewrites support and
  traversability; the capsule's next resting contact depends on the entire wall
  topology.
- **Physical contract:** one shared quarter-turn transform,
  slide-until-support collision geometry, ordered airlocks, and exact terminal
  delivery. This is intentionally a deterministic support puzzle, not a claim
  of continuous rigid-body gravity.
- **Source anchors:** CAPTCHA Royale `rotation` and `pathtracing`;
  OpenCaptchaWorld `Path_Finder`; Neal's parking challenges.
- **Original transformation:** make orientation itself the continuously
  consequential world control rather than an answer label.

### 6. `floodgate_archive_rescue` — Floodgate Archive Rescue

- **Interaction bottleneck:** route a floating evidence capsule through a
  multi-lock building by opening gates, operating individual pumps, and
  advancing mass-conserving flow in four-tick bursts.
- **Why a static genius still pays:** opening the correct gate at the wrong
  level floods an archive or strands the capsule; every pump, gate, and flow
  burst changes the state needed by the next lock.
- **Physical contract:** mass-conserving chamber levels, gate conductance,
  fixed pump increments, equalization thresholds, archive flood limits, and
  lock-by-lock capsule transfer.
- **Source anchors:** OpenCaptchaWorld `Path_Finder`; CaptchaWare
  `fishingGame`; Captcha RPG's blocking-and-delivery interactions.
- **Original transformation:** replace direct navigation with a causal fluid
  control system whose state changes only through the solver's pump, gate, and
  fixed-duration flow actions.

### 7. `elastic_membrane_sorter` — Elastic Membrane Sorter

- **Interaction bottleneck:** reshape a bilinear membrane through four tension
  posts so three sequential marbles roll into three different wells.
- **Why a static genius still pays:** changing one post perturbs the entire
  surface; each release carries persistent momentum and a bad slope can pin the
  marble against the rim until the round is reset.
- **Physical contract:** bilinear surface heights, fixed-step damped slope
  forces, rim clamping, circular well capture, and exact post-control replay.
- **Source anchors:** CAPTCHA Royale `balance` and `overlap`; NextGen-CAPTCHAs
  `Layered_Stack`.
- **Original transformation:** turn static balance/overlap reasoning into a
  deformable-surface manipulation problem.

### 8. `pheromone_dispatch` — Pheromone Dispatch

- **Interaction bottleneck:** steer a swarm indirectly by painting one safe
  trail and then repainting the complete route repeatedly as it evaporates.
- **Why a static genius still pays:** the carriers keep moving; a one-shot
  route expires long before eight separated ants can collect the key and reach
  the dock.
- **Physical contract:** deterministic separated carrier motion, global trail
  lifetime, repeated brush resampling, salt-block collision, key pickup state,
  and tick-exact delivery replay.
- **Source anchors:** Neal's runaway-duck challenge; CaptchaWare
  `fishingGame` and `touchGrass`.
- **Original transformation:** replace direct target capture with distributed
  indirect control over many persistent agents.

### 9. `clockwork_clutch_safe` — Clockwork Clutch Safe

- **Interaction bottleneck:** release three signed-ratio clutches while their
  live seal rings cross one narrow witness window, then brake and unlock the
  synchronized set.
- **Why a static genius still pays:** phases continue evolving at different
  rates and directions, so the final state depends on three separate release
  times under one shared clock.
- **Physical contract:** signed ratio integration, clutch state, maximum wind,
  frozen released phase, simultaneous tolerance, and event-time replay. It
  tests live phase synchronization rather than mutual load redistribution.
- **Source anchors:** CAPTCHA Royale `gears` and `clock`; Captcha RPG's
  time-wheel lineage.
- **Original transformation:** replace gear-direction prediction with a
  stateful mechanical synchronization instrument.

### 10. `marionette_checkpoint` — Marionette Checkpoint

- **Interaction bottleneck:** manipulate four coupled strings to guide a
  jointed puppet's hands and feet through four moving inspection frames.
- **Why a static genius still pays:** string changes couple multiple joints;
  the target frame keeps moving; each limb needs a sustained geometric hold,
  not one click.
- **Physical contract:** deterministic coupled limb kinematics, bounded
  string-length controls, independent moving target rings, uninterrupted
  four-point dwell, and pose replay.
- **Source anchors:** NextGen-CAPTCHAs `3D_Viewpoint`; Captcha RPG's fingertip
  and drag-Nimbet-home interactions.
- **Original transformation:** turn landmark clicking and direct dragging into
  coupled whole-body kinematic control.

## Pack-level diversity audit

| Mechanic | Primary debt | Nearest existing task | Why it is not a reskin |
| --- | --- | --- | --- |
| Specular Lighthouse | reflected optics | Shadow Crime Lab | steers a multi-bounce live beam instead of diagnosing one shadow |
| Wind Tunnel | indirect force-field control | Gyroscopic Tilt Board | controls spatially distributed forces with fan lag, not global tilt |
| Hologram Foundry | inverse 3D construction | Tomographic Baggage Surgery | creates geometry to satisfy projections rather than locating/extracting it |
| Orbital Docking | attitude + momentum | Slime Commute | continuous rigid-body rendezvous, not grid/world navigation |
| Gravity Room | world-frame rotation | Forced Perspective Moving Day | changes gravity/support topology, not object scale through projection |
| Floodgate Archive | fluid-state control | CRAFTCHA | mass-conserving realtime flow rather than a discrete recipe chain |
| Elastic Membrane | deformable-surface control | Zero-G Cable Autopsy | controls a coupled bilinear slope and damped rolling bodies, not cable topology |
| Pheromone Dispatch | multi-agent indirect control | Wizard Critter Capture | paints a decaying field for a swarm rather than shooting one target |
| Clockwork Clutch | coupled phase control | Thirty-Year Time Wheel | synchronizes moving shafts through timed coupling, not calendar selection |
| Marionette Checkpoint | constrained kinematics | Three-Camera Claw | controls coupled articulated limbs rather than one rigid teleoperator |

## Implementation and acceptance contract

All ten require deterministic generators, meaningful structural variation,
ordinary mouse/keyboard interaction, visible failure/recovery, live server
grading, independent exported replay, original presentation, source provenance,
multi-seed browser evidence, and a pending-human status. A hidden solver route
may guide automated evidence, but the accepted browser transcript must still
contain the same primitive actions available to a human. No task may enter the
verified split from this implementation pass.
