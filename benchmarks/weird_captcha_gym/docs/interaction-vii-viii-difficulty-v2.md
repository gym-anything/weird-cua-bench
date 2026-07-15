# Interaction VII–VIII: natural-difficulty v2 contracts

Status: implementation contract. These ten candidates remain human-review pending.

This document is subordinate to `interaction-puzzle-field-notes.md`. Its purpose is to prevent a difficulty pass from degenerating into small hit targets, opaque deadlines, lag, repetitive clicking, or grader traps.

## Shared contract

The v1 concepts were sound, but several demonstrations ended immediately after the mechanic became legible. Version 2 must create interaction debt after comprehension: the solver repeatedly observes a changing world, acts, sees a consequence, and corrects. A brilliant static-image reasoner should still face a substantial control, temporal, physical, or three-dimensional problem.

Every v2 task must satisfy all of the following:

- The visible world, hit testing, simulation, transcript, Python replay, and stated rules describe the same mechanic.
- There is no hidden click quota, hostile latency, unexplained timer, deliberately tiny target, input jitter, disabled correction, or exact-reference-transcript requirement.
- Multiple legitimate control histories may pass whenever the physical end state is valid.
- Failure is attributable to a visible physical cause and returns a fresh deterministic trial through the normal benchmark boundary.
- A solution requires a causal chain, not simply discovering one value and copying it.
- The authored reference is used to guarantee solvability; the grader independently replays the submitted history and never trusts client claims or the reference action list.
- Existing v1 videos are historical evidence only. They must not be presented as current solutions after the first v2 mechanic lands.

## Per-puzzle contracts

### 1. Specular Lighthouse Relay — live moving receiver

**v1 weakness:** three mirrors could be solved as a static alignment and the charge button froze all optical controls.

**v2 interaction debt:** align the three-bounce path, open a toggle shutter, then continuously steer the final gimbal while the receiver moves through a visible deterministic patrol. Charge grows on illumination and visibly leaks on a miss; it never resets invisibly. Four ordered receivers use distinct paths and patrols.

**Acceptance:** the independent replay recomputes every reflection and moving receiver position at each charge sample. A round passes only after its accumulated charge reaches the public threshold. Mirror changes while the shutter is open are legal and required.

### 2. Wind-Tunnel Seed Courier — two different pods, one shared plant

**v1 weakness:** one seed crossed four gates with four isolated fan pulses.

**v2 interaction debt:** a light pod and a heavy pod launch with a large visible stagger through separate moving apertures. Four shared fans have spool and thermal memory, so controlling one pod alters the field inherited by the other. Both pods must cross all four gates and reach their own funnels.

**Acceptance:** fixed-step replay advances both pod plants, fan spool, heat, every moving aperture, and both docks. Either collision, a thermal trip, or either missed dock fails. The gap sizes remain generous enough for recoverable steering.

### 3. Hologram Silhouette Foundry — colored, occluding 3-D inverse projection

**v1 weakness:** four rods in a 5³ grid reduced to sparse binary silhouettes.

**v2 interaction debt:** place and rotate six uniquely colored rods in a 7³ volume. The three dies show the frontmost colored cell in every ray, so depth order and occlusion matter, not just occupancy. All pieces remain directly selectable with large controls.

**Acceptance:** the grader reconstructs all occupied cells, rejects overlap/out-of-bounds placements, computes depth-aware front/side/top color maps, and compares those maps exactly. It accepts any arrangement producing the three dies.

### 4. Orbital Docking Customs — timed S-rendezvous

**v1 weakness:** one long pre-authored detour and a static station position made the sequence mostly open-loop.

**v2 interaction debt:** negotiate two debris fields, cross two ordered scan beacons, and rendezvous with a station whose port rotates and whose position visibly oscillates. Inertial corrections, fuel allocation, arrival time, velocity, position, and attitude are coupled.

**Acceptance:** replay checks swept collision segments, ordered beacon crossings, fuel, the station's position at the actual arrival tick, relative speed, distance, and port angle. Any collision-free rendezvous satisfying those public tolerances passes.

### 5. Gravity-Room Freight — shared rotation, dual cargo

**v1 weakness:** a single sliding token on a small board admitted a short sequence.

**v2 interaction debt:** every room rotation moves both the archive capsule and a visibly distinct under-deck counterweight. The capsule must collect four ordered seals and reach its dock while the counterweight simultaneously reaches its own dock. One rotation that helps one body can strand the other.

**Acceptance:** the generated 8×8 board has a verified 14–30 move joint solution. Replay applies each rotation to both bodies against the same wall topology and validates seal order plus both final docks. The UI explicitly labels the counterweight as an isolated rail layer, so the two bodies do not pretend to collide.

### 6. Floodgate Archive Rescue — conserved water, opposing capsules

**v1 weakness:** independent chamber pumps created or destroyed water and one capsule walked monotonically across three locks.

**v2 interaction debt:** five chambers share visible bidirectional transfer circuits that conserve total water. Two archive capsules travel in opposite directions through four locks. Equalising one lock changes the water available for future locks and for the capsule approaching from the other side.

**Acceptance:** a discrete reference search guarantees a nontrivial route. Replay conserves water on every pump step, enforces public safe bands and source/destination capacity, opens only commanded locks, and advances either capsule only across an equalised adjacent pair. Both capsules must reach their opposite docks.

### 7. Elastic Membrane Sorter — steer during flight

**v1 weakness:** each marble could be launched after entering one static corner preset.

**v2 interaction debt:** post heights remain adjustable while the marble moves. In each of three rounds, the marble must pass two large ordered inspection rings and then enter its assigned well at capture speed. Inertia makes early steering affect later corrections.

**Acceptance:** fixed-step replay applies every timestamped post change, integrates the same force and drag plant, records ring crossings in order, and checks the assigned well and capture velocity. Any successful closed-loop trajectory passes.

### 8. Pheromone Dispatch — two decaying routes

**v1 weakness:** one route was painted once and then fully retraced on a simple TTL cadence.

**v2 interaction debt:** two ant teams use two independently decaying colored fields on the same obstacle map. The operator paints both nest→cache→dock routes, dispatches both swarms, then alternates complete refresh strokes while watching two freshness gauges and two moving flows.

**Acceptance:** replay validates each route against obstacles and its own required cache, reconstructs the two freshness timelines from field-tagged strokes, advances both teams only while their own field is live, and requires both delivery totals. Refreshes of one color never refresh the other.

### 9. Clockwork Clutch Safe — real load redistribution

**v1 weakness:** three shafts had independent constant speeds despite the interface claiming coupling.

**v2 interaction debt:** four shafts share one drive. Releasing or re-engaging any clutch redistributes load and immediately changes every still-coupled shaft's speed. The operator must adapt timing after each intervention and may legitimately re-engage to correct overshoot.

**Acceptance:** replay derives each tick's speeds from the active clutch set, applies all timestamped clutch changes, and accepts any final state in which all four clutches are released and all seals are within the public phase tolerance. The reference schedule merely proves the generated initial phases are solvable.

### 10. Marionette Checkpoint — continuous moving inspections

**v1 weakness:** four static slider vectors could be copied and held.

**v2 interaction debt:** each inspection act has four slowly moving target rings generated by a visible periodic motion. Four coupled strings remain adjustable throughout. Progress accumulates while all limbs track their rings and visibly leaks during misses, forcing sustained coordinated correction rather than one static pose.

**Acceptance:** replay reconstructs target positions and coupled limb positions at every tick-bound control/sample event, recomputes progress, and clears all three acts only after their public tracking requirement. Large rings, slow motion, continuous progress feedback, and legal mid-act correction keep the difficulty physical rather than adversarial UI design.

## Evidence gate

For every mechanic and for at least three independent seeds:

1. generate public state and private truth;
2. solve through the browser using ordinary inputs;
3. submit through the HTTP result boundary and receive a pass from the Python grader;
4. show at least one plausible shortcut or falsified client claim is rejected;
5. visually inspect initial, mid-interaction, failure, and success states;
6. record a fresh complete solution video after the final code change;
7. keep the dashboard status at human-review pending until a person actually completes and reviews it.
