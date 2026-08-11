# Game Action-Handling Audit

Date: 2026-08-10

## Scope

This audit concerns only the games' action handling. It does not attribute the findings to FastIO, Gym Anything, the live-versus-paused observation schedule, or the paused clock implementation.

The audit covered all 75 environments, both interaction modes, and the action-handler branches used by the five difficulty profiles. It combined source inspection with isolated headless differential tests. The representative games were then run through the authoritative paused evaluator with untouched QEMU input and screenshot-only computer-use agents.

The initial audit found concrete action-handling defects in eighteen environments. Every primary defect identified here affects the Full interaction surface. The completed repair pass fixes all eighteen inside their browser-side game handlers, with matching generator, grader, solver, and control changes where the broken rule had entered the task contract. The public mouse and keyboard action contract is unchanged.

| Defect | Affected environments |
|---|---|
| Native HTML5 drag-and-drop | Motion-Only Ghost Jigsaw; Parallel Grillmaster; Funeral With No Instructions; Exact-Change Candy Cascade; Live Shattered-Scene Synchronizer |
| Action depends on asynchronous physics or artificial event timing | Flat-Pack Compliance Test; The Flat Prisoner |
| Ordinary transfer requires an arbitrary move-event count or duration | CRAFTCHA: Alchemy Bench; Kinetic Restoration Press; Dual-Projection Sculpture Rig; Magnetic-Stripe Purgatory; Parallax Orchard; Rorschach / Subjective Prompt With A Fixed Rubric |
| Large pointer deltas are clipped, discarded, or interpreted once per event | Anamorphic Registration Press; Rotate The Wrong Thing Upright; Tiny FPS Customs; Thirty-Year Time Wheel; The Photograph Eats the Room |

## Implementation status

Each primary repair is inside the game's browser-side action handling. No game hardcodes a Gym-Anything action type or calls a private evaluator action path.

| Category | Repaired environments | Result |
|---|---|---|
| Native HTML5 drag-and-drop | Motion-Only Ghost Jigsaw; Parallel Grillmaster; Funeral With No Instructions; Exact-Change Candy Cascade; Live Shattered-Scene Synchronizer | All five use ordinary Pointer Events for their Full interaction surface. |
| Asynchronous or filtered execution | Flat-Pack Compliance Test; The Flat Prisoner | Both consume the delivered pointer endpoint synchronously instead of depending on later wall-time physics or a minimum event delay. |
| Arbitrary transfer event-count or duration gate | CRAFTCHA: Alchemy Bench; Kinetic Restoration Press; Dual-Projection Sculpture Rig; Magnetic-Stripe Purgatory; Parallax Orchard; Rorschach / Subjective Prompt With A Fixed Rubric | Ordinary transfers depend on pickup, path geometry where meaningful, and a valid release target—not an arbitrary transport-specific move count or duration. Intended continuous mechanics remain continuous. |
| Per-event clipping or dropping | Anamorphic Registration Press; Rotate The Wrong Thing Upright; Tiny FPS Customs; Thirty-Year Time Wheel; The Photograph Eats the Room | Large delivered deltas are consumed geometrically rather than clipped, dropped, or reduced to one fixed increment per event. |

Interrupted-gesture cleanup remains a separate secondary audit category. Reload Interruption and Anamorphic Registration Press have explicit cancellation regressions; the primary eighteen-environment claim does not treat cancellation coverage as complete across every game.

The representative implementations were exercised in isolated headless Chromium with fresh profiles. These are scripted wiring regressions, not computer-use-agent evaluations:

- Motion-Only Ghost Jigsaw completed from raw pointer down, one pointer move, and pointer up.
- Flat-Pack Compliance Test completed in Full and Simplified modes with one move event per part and no physics-settling wait.
- Kinetic Restoration Press completed in Full and Simplified modes with one move event and no held delay for each ordinary module transfer. The continuous restoration rail remains unchanged.
- Anamorphic Registration Press completed in Full mode with single move events larger than the former 28 px clipping limit; all plate errors were 0.00 degrees. Simplified mode also passed through its visible step controls.
- Reload Interruption deliberately canceled a lever gesture and the first overload hold, then retried and completed in both Full and Simplified modes.

## Actual computer-use-agent evidence

These runs used the unchanged runner action contract and FastIO implementation in real QEMU. The evaluator injected the visible-task-UI-only rule into both the model system instruction and task description. Each run used a finite 120-second provider-request deadline, at most three total request attempts through one retry layer, and did not consume an environment step for a failed provider request.

| Public environment name | Model and condition | What the run verified | What it did not verify |
|---|---|---|---|
| Motion-Only Ghost Jigsaw | Gemini 3.5 Flash; Full; L4; paused | A raw pointer drag moved one tile from the tray into the top-left slot; the move persisted in all following frames. Native down, move, and up receipts were confirmed and task time advanced by 0 ms during the action. | The agent did not complete or submit the puzzle. |
| Flat-Pack Compliance Test | GPT-5.4 computer use; Full; L4; paused | Against the final standard-Pointer-Events implementation, the agent selected part 02 and issued a nine-command move/down/move/up gesture. The next screenshot visibly showed part 02 relocated from the rack into the blueprint; it then performed two more visible part drags. A separate exact split-command replay of the same final code confirmed every native event receipt and 0 ms of task-time advancement. | The agent run was stopped after the repaired action behavior was visible; it did not complete or submit the assembly. |
| Kinetic Restoration Press | Gemini 3.5 Flash; Full; L3; paused | Three endpoint drags, each with only one or two move events and 22-38 ms from down to up, placed all three ordinary modules and exposed `INVERSE STACK READY`. Every drag would have failed the removed four-move and 80 ms gate. | The later continuous rail was incomplete and the task was not submitted successfully. |
| Anamorphic Registration Press | Gemini 3.5 Flash; Full; L3; paused | One 81 px drag was consumed in full and visibly brought the plate layers close to alignment. Native receipts were confirmed and task time advanced by 0 ms during the action. | The agent did not finish or submit the puzzle. |
| Reload Interruption | Gemini 3.5 Flash and GPT-5.4 computer use; Full; L1/L4; paused | Nothing about the repaired cancellation branch. The agents clicked or used unrelated controls but never produced the required interrupted lever or hold gesture. | Agent verification of cancellation cleanup remains open. |

The complete QEMU episodes and screenshot artifacts are retained outside the repository. They are intentionally not part of the installable benchmark source tree.

## Complete programmatic oracle evidence

One independently sampled difficulty, interaction mode, and challenge seed was retained for every environment. The completed paused matrix contains 75 accepted passes. Every input, empty observation window, and wait was executed through `GymAnythingEnv.step`; every result matched the oracle-generated world. Privileged state was used only to select the solution.

This establishes that the sampled tasks have executable oracle solutions through the public environment API. It is not a human-usability result or a claim that an unassisted screenshot-only model can solve every task.

## Native HTML5 drag-and-drop

Before repair, five Full interaction surfaces used Chromium's native HTML5 drag-and-drop state machine through `draggable`, `dragstart`, `dataTransfer`, `dragover`, and `drop`:

- Motion-Only Ghost Jigsaw: `shared_runtime/app/app.js`
- Parallel Grillmaster: `shared_runtime/app/app.js`
- Funeral With No Instructions: `shared_runtime/app/app.js`
- Exact-Change Candy Cascade: `shared_runtime/app/mechanics/exact_change_candy_cascade.js`
- Live Shattered-Scene Synchronizer: `shared_runtime/app/mechanics/single_scene_split_boxes.js`

On untouched real QEMU input, a normal fast drag in Motion-Only Ghost Jigsaw produced `dragstart` but no `dragover` or `drop`. A deliberately paced gesture worked. The result was the same in live and paused modes.

Before repair, all five environments were validated with Playwright `Locator.drag_to()`. That mechanism drives Chromium's native drag state differently from the real QEMU pointer stream. All five now use Pointer Events and their solvers record raw pointer down, move, and up input that can be replayed through `env.step`.

## Asynchronous or filtered action execution

### Flat-Pack Compliance Test

Source: `shared_runtime/app/mechanics/flat_pack_compliance.js`

Before repair, pointer-down attached the selected Matter.js body to a spring. Pointer movement changed only the spring anchor. The body reached the anchor during later physics ticks. Pointer release immediately removed the spring, zeroed velocity, and froze the body.

An isolated differential test requested a 556.22 px displacement:

- Immediate move and release: the body moved 0 px.
- The same endpoint held for 500 ms: the body moved 556.22 px.

The action result therefore depends on allowing physics to run while the pointer remains held.

Implementation: dragging now applies the pointer endpoint synchronously to the actual Matter.js body. A long sparse segment is geometrically resampled inside the game only to keep its rigid-body audit trace within replay bounds. Release consumes its endpoint before mating. Visible socket rings participate in hit testing even when they extend outside the Matter polygon. Action-induced Canvas changes are painted synchronously at the paused input boundary; later load-test physics advances only inside the configured observation window.

The first real agent run exposed both the visible-socket mismatch and the stale-Canvas problem; the part was selected and its internal Matter position changed, but the screenshot remained unchanged. After both game-side fixes, GPT-5.4's ordinary split-command drag visibly relocated part 02 while task time remained at 0 ms. This verifies the repaired drag action. It is not a completed Flat-Pack task run.

Domino Autopsy does not have this defect. Its pointer-move handler directly changes the body's position, and release preserves the resulting pose.

### The Flat Prisoner

Source: `shared_runtime/app/mechanics/flat_prisoner.js`

Before repair, the camera handler accumulated pointer displacement but refused to process it until at least 20 ms had passed. Pointer release cleared the drag without applying any remaining accumulated displacement. Its solver deliberately inserted 24-25 ms waits around camera movement.

In real QEMU testing, a complete fast drag produced the expected pointer events but a byte-identical screenshot. A split gesture with a delay changed the camera yaw.

Implementation: every delivered camera move consumes its complete geometric delta immediately. The handler no longer filters moves by a 20 ms wall-time threshold, does not discard a pending release delta, and does not require a wall-time settling interval before freezing a valid projection.

## Arbitrary event-count and duration gates on ordinary transfers

These failures are separate from each environment's legitimate continuous mechanic. They affect ordinary object placement or transfer.

### CRAFTCHA: Alchemy Bench

Source: `shared_runtime/app/mechanics/craftcha_alchemy_bench.js`

Before repair, every ingredient transfer required a duration of at least 35 ms and at least four recorded samples. A one-move version of the solver completed 0 of 9 required transfers. Transfers now require a valid pickup and an available visible destination; their outcome no longer depends on transport event density or wall time.

### Kinetic Restoration Press

Source: `shared_runtime/app/mechanics/modifier_stack_image_grid.js`

Before repair, module placement at L3 required at least four move events and 80 ms. This was separate from the restoration rail's intended continuous-contact requirement.

With the same valid endpoints and a 100 ms hold:

- One move event: the module was rejected.
- Seven move events: the module was placed.

Implementation: ordinary module placement now depends only on a valid pickup and release inside an empty visible slot. `minimum_chip_moves` and `minimum_chip_drag_ms` were removed from the game, generated requirements, difficulty profiles, grader, and solver. The intended continuous rail still checks samples, path, gates, and held duration. The agent run verified the ordinary transfers but did not pass the continuous rail or the task.

### Dual-Projection Sculpture Rig

Source: `shared_runtime/app/mechanics/relation_prompt_grounding.js`

Before repair, moving an object from the carousel to a valid point on the worktable required at least two move events.

- One move event: `drag_cancel`; the object returned to the carousel.
- Three move events: `drag_end`; the object remained on the worktable.

Implementation: a valid pickup released inside the worktable is accepted regardless of move count. The depth rail records the samples actually delivered and no longer synthesizes missing moves on release.

### Magnetic-Stripe Purgatory

Source: `shared_runtime/app/mechanics/magnetic_stripe_purgatory.js`

Before repair, inserting a card into its matching reader at L3 required four move events and 90 ms. This gate was separate from the intentionally timed magnetic-stripe swipe.

With the same card, matching reader, valid endpoints, and 110 ms hold:

- One move event: invalid insertion.
- Five move events: card inserted.

Implementation: ordinary card insertion depends only on card identity, the matching unoccupied reader, and the release target. The intended swipe remains temporal, but its active sample clock caps transport latency so event-delivery overhead is not mistaken for gesture duration.

### Parallax Orchard

Source: `shared_runtime/app/mechanics/surreal_apple_on_tree_grid.js`

Before repair, after completing the actual parallax exploration requirement, moving a correctly attached fruit into the basket required four move events and 90 ms.

- One move event: false-contact strike.
- Five move events: the same fruit was harvested.

Implementation: once the real parallax attachment requirement is satisfied, release inside the basket is sufficient; move count and drag duration no longer affect the harvest.

### Rorschach / Subjective Prompt With A Fixed Rubric

Source: `shared_runtime/app/mechanics/rorschach_fixed_rubric.js`

Before repair, a fold sweep could cover the required physical distance but was rejected unless at least three pointer-move events were delivered.

- One move event: `fold_cancel`.
- Five move events: `fold_end` and the response cycle started.

Implementation: the fold depends on its visible start and end distance. No extra move-count quota remains.

## Per-event clipping or dropping

### Anamorphic Registration Press

Source: `shared_runtime/app/mechanics/wonky_text_hostile_rendering.js`

Before repair, every pointer-move delta was clipped to plus or minus 28 px, after which the previous pointer coordinate was updated. Any excess displacement was discarded.

A 100 px horizontal gesture produced:

- One move event: 17.36 degrees.
- Five move events: 62 degrees.

The earlier solver avoided the defect by subdividing movement into steps of at most 20 px.

Implementation: the wheel now consumes the complete horizontal displacement of every Pointer Event. Cancellation restores the pre-gesture plate angle and removes gesture listeners. The Full-mode regression uses sparse moves larger than 28 px rather than relying on action interpolation. The agent run verified the full-delta action but did not complete the puzzle; cancellation remains covered only by the scripted regression.

### Rotate The Wrong Thing Upright

Source: `shared_runtime/app/mechanics/rotate_wrong_thing_upright.js`

Before repair, this handler used the same plus-or-minus-28-px per-event clipping.

A 100 px horizontal gesture produced:

- One move event: 11.76 degrees.
- Five move events: 42 degrees.

The earlier solver also subdivided movement into steps of at most 20 px.

Implementation: every delivered horizontal delta is applied in full.

### Tiny FPS Customs

Source: `shared_runtime/app/mechanics/tiny_fps_customs.js`

Before repair, mouse-look clipped each delivered event to 36 degrees. The same horizontal start and endpoint produced:

- One move event: final bearing 216 degrees.
- Five move events: final bearing 310 degrees.

Implementation: direct and proxy turns consume the complete delivered angular delta.

### Thirty-Year Time Wheel

Source: `shared_runtime/app/mechanics/thirty_year_time_wheel.js`

Before repair, the wheel discarded an angular delta entirely when its magnitude exceeded 1.1 radians.

- One sparse 2.1-radian move: the date did not change.
- The movement subdivided into five angular segments: the date advanced twenty days.

Implementation: the wheel accumulates the complete angular delta and retains the intended velocity and detent model.

### The Photograph Eats the Room

Source: `shared_runtime/app/mechanics/photograph_eats_the_room.js`

Before repair, each Shift-drag pointer move whose displacement exceeded 12 px applied exactly one rotation increment and reset the anchor. A long movement delivered as one event rotated once; the same geometric travel delivered through multiple events rotated repeatedly.

Implementation: a sparse delta is converted into the corresponding number of geometric 12 px rotation steps, including any unconsumed remainder in the anchor. Development checks the final visible geometry and no longer requires unrelated plane-drag or scale-change event quotas.

## Interrupted-gesture cleanup

A separate source pass found missing `pointercancel` cleanup in active handlers for:

- Live Control-Flow Wiring Lab
- Consequences Boss
- CRAFTCHA: Alchemy Bench
- Five-System Verification Reactor
- Semantic Drag-Drop Absurdity
- Tiny FPS Customs
- Anamorphic Registration Press
- Portal Freight: Oversized Parcel
- Reload Interruption
- Funeral With No Instructions

Depending on the handler, cancellation can leave stale drag state, leaked listeners, an active sampling interval, or incorrect held or dragging visuals. These are not included in the eighteen primary findings because they require an interrupted pointer sequence.

Reload Interruption's cancellation implementation is changed. Lever drags, Full moving-spark holds, and Simplified stabilizer holds now have idempotent `pointercancel` and `lostpointercapture` cleanup. Cancellation removes capture, listeners, intervals, and held or dragging state without treating cancellation as a release or aborting the task. Rerender also clears any active pointer session. Anamorphic Registration Press now restores its pre-gesture angle on cancellation as part of its clipping implementation. Both cancellation paths still require screenshot-only computer-use-agent verification. The other environments in this section have not yet been implemented.

## Validation boundaries

The Five-System Verification Reactor oracle may use privileged state to decide when to act, but its brake and intercept inputs are trusted visible pointer actions and the accepted evaluation replay executes them through `env.step`.

The five former native HTML5 drag-and-drop environments use raw Pointer Event recordings rather than Playwright `drag_to()` as their accepted replay input.

## Repository impact

The audit inventory and repair are repository-wide across the eighteen affected games. The repairs change their handlers and the directly corresponding styles, generators, graders, solvers, controls, and regression smoke where required.

The paused-time work in the same change set is separate from those game repairs. Weird CUA's runner still accepts the standard Gym-Anything action dictionaries. Its implementation now keeps task time frozen during native input delivery, waits for a browser event receipt, and advances only the fixed observation window. Gym-Anything core, FastIO, the worker protocol, and the runner action contract are unchanged.
