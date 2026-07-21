# Environment behavior notes

These notes describe what each environment actually requires before any replacement taxonomy is proposed. The previous seven-category annotation was removed from the catalog and dashboard in commit `bb609fc`.

For every environment the review reads the task contract, challenge generator, visible runtime, submitted result, and verifier. It records requirements that are enforced by the implementation. It also records strategies that remove an intended requirement while still passing.

## Environments 1–5

### 1. Motion-Only Ghost Jigsaw

**Passing behavior.** Place nine moving-noise tiles into the exact permutation encoded by their source positions.

**What must be observed.** A hidden shape is defined by opposite motion inside and outside its boundary. A single frame contains noise but does not reveal the relevant boundary reliably. Multiple frames must be compared to recover motion-defined form in the reference and in each tile.

**What must be done.** Match every partial boundary to its location in the complete reference. Preserve the tile-to-location correspondence while performing nine drag operations.

**What is actually enforced.** Exact spatial assembly is enforced. Fast action is not enforced because observation can continue for the full task budget. The temporal requirement is visual integration across frames rather than rapid control or long-term memory.

### 2. Cursor Constellation Hunt

**Passing behavior.** Click within 28 pixels of a hidden point on a 680 by 410 canvas.

**What must be observed.** Cursor position changes the star field. Stars approach a coherent global shape near the hidden point. Two other regions create weaker distorted alternatives.

**What must be done.** Search cursor positions using the resulting visual changes. Distinguish global shape coherence from partial coherence. Refine the location before clicking.

**What is actually enforced.** Observation depends on action. Rapid continuous motion is not enforced because an agent can move to a location and inspect a new screenshot before continuing a systematic search.

### 3. Parallel Grillmaster

**Passing behavior.** Move six foods from the grill to the tray after each has cooked for its assigned duration. Each acceptable interval is 2.3 to 2.7 seconds wide.

**What must be observed.** Every food changes through visible raw, warming, ready, burning, and burnt states.

**What must be done.** Start cooking an item. Detect its ready state. Complete a drag to the tray before the interval closes.

**What is actually enforced.** Timely response to a visual state transition is enforced. Parallel monitoring is not enforced because foods may be cooked sequentially without penalty or global deadline.

### 4. Rotating On-Screen Keyboard

**Passing behavior.** Enter a visible five-character code by clicking the corresponding on-screen keys.

**What must be observed.** The keyboard begins a periodic three-dimensional tumble after the first click. Its period is 8.8 to 10 seconds.

**What must be done.** Locate and click four remaining keys while their screen positions change.

**What is actually enforced.** Correct target acquisition on the transformed keyboard is enforced. Continuous tracking is not enforced because the target code remains visible and the agent can wait for the keyboard to return to its original orientation on every cycle.

### 5. Slot-Reel Character Capture

**Passing behavior.** Capture five reels in order with fewer than three incorrect responses.

**What must be observed.** The active reel cycles through six non-alphanumeric symbols and one target character. Each symbol remains centered for approximately 360 to 540 milliseconds.

**What must be done.** Recognize the transient character. Select the matching keyboard response before it disappears. Repeat for five sequentially activated reels.

**What is actually enforced.** Transient visual recognition followed by rapid response selection is enforced. Multi-reel monitoring is not enforced because only one reel accepts a response at a time. Remembering the final sequence is not required.

## Environments 6–10

### 6. Domino Autopsy

**Passing behavior.** Add three movable dominoes to a chain of eight fixed dominoes so a Matter.js simulation transfers collision impulse from the first domino to a suspended bell. Every domino and the bell must belong to the recorded collision graph. The bell must swing by at least 0.03 radians.

**What must be observed.** Placement quality is revealed by the subsequent rigid-body simulation. A failed run visibly shows where propagation stopped.

**What must be done.** Place and rotate the three missing bodies. Run the simulation. Inspect the resulting motion. Rewind and change the configuration when the chain fails.

**What is actually enforced.** A physically functioning causal chain is enforced rather than a stored target arrangement. No action is required while the simulation is running. The environment therefore requires spatial configuration plus intervention-based physical diagnosis. It permits genuine same-instance revision after observed failure.

### 7. Consequences Boss

**Passing behavior.** For each of five visually identified scenes choose a left or right socket plus one of four seal orientations. After a 1.5-second occlusion reconstruct the same scene-state pairs in a shuffled order.

**What must be observed.** Each scene has a persistent identity expressed by its glyph and visual design. The chosen socket and seal disappear during the storm.

**What must be done.** Associate five scene identities with five self-created two-part states. Retrieve those associations after occlusion and reordering.

**What is actually enforced.** The verifier checks reconstruction consistency but does not require the five states to differ. An agent can deliberately choose the same socket and seal for every scene. That strategy passes while reducing the task to remembering one repeated response. A direct grader check confirmed that five identical covenants receive a pass.

### 8. Popup Exorcist

**Passing behavior.** Close windows until the hidden parasite is provoked. That action activates a visible containment region and creates two infected echoes. Drag an infected window into the containment region to purge the desktop.

**What must be observed.** The parasite is not visually identified before interaction. Its different behavior is revealed only when its close button is clicked. Overlap can hide windows and their controls.

**What must be done.** Manipulate window order or close accessible windows. Detect the replication event. Select a visibly infected window. Drag it so its center enters the containment region.

**What is actually enforced.** Hidden behavior must be discovered through interaction. Echo discovery is not enforced because the original parasite also becomes visibly infected and may be dragged directly into containment. A direct grader check confirmed that containing the original parasite receives a pass.

### 9. Funeral With No Instructions

**Passing behavior.** Complete the fixed event sequence inspect, brush, light, gather, and offer. At least 17 of 24 moss cells must be cleared. All four flowers must be collected. The resulting bouquet must be dragged to the grave.

**What must be observed.** The only prompt is `Grieve.` The next usable object becomes visually available after the preceding event. Clicking the tombstone reveals the epitaph and brush. Brushing reveals the candle. Lighting the candle activates the flowers. Gathering every flower reveals the bouquet.

**What must be done.** Discover the sequence from visual affordances and state changes. Execute clicking, a brushing path, repeated object selection, and a final drag.

**What is actually enforced.** Ordered interface exploration under an underspecified goal is enforced on a first encounter. The event sequence is constant across generated variants, so a solver that already knows the environment can execute a memorized procedure without further discovery. No timing constraint is present.

### 10. Slime Commute

**Passing behavior.** Move from row 10 to a specified home position on row 0 within 2,400 world ticks and fewer than four wipeouts. The submitted key history is replayed by the grader against the same deterministic world.

**What must be observed.** Roads and rail lines contain continuously moving hazards. Water rows require support from moving logs. The world advances every 100 milliseconds. A hop creates a two-tick movement cooldown. A player standing on a log is carried horizontally on every tick.

**What must be done.** Track moving occupancy. Predict whether the destination of the next hop will remain safe. Time keyboard actions around traffic gaps. Enter and leave moving supports before collision, drowning, or being carried beyond the field.

**What is actually enforced.** Online navigation in a changing spatial state is enforced. Unlike the preceding four environments, waiting does not freeze relevant state after the crossing begins. Water sections require continued interaction with a moving support. This environment directly requires real-time observation and control.

## Environments 11–15

### 11. Semantic Drag-Drop Absurdity

**Passing behavior.** Match four specimens to four receivers. Every specimen must first be tested with both the thermal probe and the polarity probe. Each probe must remain on the specimen for at least 420 milliseconds.

**What must be observed.** A thermal probe produces either bloom or contraction. A polarity probe produces either leftward or rightward motion. Each receiver can display the same two-part response when its control is pressed. These responses are transient but may be elicited repeatedly.

**What must be done.** Apply both probes to every specimen. Determine the conjunction of its two binary responses. Find the receiver with the same conjunction. Drag each specimen to its matching receiver.

**What is actually enforced.** The environment requires controlled intervention and matching by two observed attributes. It does not require semantic knowledge despite its title. All eight specimen probes are explicitly enforced, so the fourth match cannot be completed solely by elimination. The environment is stepwise because probes and receiver responses may be repeated without a time limit.

### 12. Reload Interruption

**Passing behavior.** Reproduce a seven-direction gesture sequence after a single preview. After gestures two and five, clear a moving overload before continuing. Each overload requires at least 1.15 seconds of pointer tracking with at least ten samples and no sample gap above 180 milliseconds.

**What must be observed.** The preview moves a lever in one of four directions for 260 milliseconds per item, with a new item beginning every 420 milliseconds. The preview cannot be replayed. During each interruption a spark moves continuously around a generated elliptical path.

**What must be done.** Extract the seven directions in order and retain them while reproducing the lever gestures. At each interruption, acquire the spark and keep the pointer near it throughout approximately one orbit. Resume the remembered sequence at the correct position.

**What is actually enforced.** The once-only preview requires sufficiently frequent observation of a transient sequence. Exact sequence retention is checked after the preview disappears. The two interruptions require continuous visual tracking and pointer correction rather than a stationary hold. This environment combines temporal sequence retention with real-time target tracking.

### 13. Rotate the Wrong Thing Upright

**Passing behavior.** Bring the outer, middle, and inner gimbal angles within six degrees of zero after their generated initial rotations. Visit all three available projections. Submit a replayable sequence of horizontal control drags whose coupled effects produce the final state.

**What must be observed.** Each projection shows the same three-axis object from a different direction. A needle angle and bead displacement expose mixtures of the underlying axis angles. Dragging one axis also changes a second axis according to a fixed coupling rule.

**What must be done.** Switch among the front, side, and top projections. Adjust the three axis controls. Compensate for the effect of one adjustment on another until all axes are aligned.

**What is actually enforced.** The verifier reconstructs the coupled state from the drag transcript and checks all three final angles. It also requires a recorded visit to every projection. It cannot verify that information from all three projections was necessary or used. There is no time constraint, so repeated observation and correction are permitted.

### 14. Bureaucratic Signature Trap

**Passing behavior.** Translate four carbon sheets until every sheet aperture is within eight pixels of its generated target. Then copy the exposed autograph in one continuous stroke and certify it.

**What must be observed.** Each sheet has a displaced circular window with a colored partial ring. When all four windows are registered, the hidden multi-loop trace appears and remains visible. The trace includes a marked starting point.

**What must be done.** Use four independent two-dimensional drags to superimpose the windows. Follow the visible trace from the marked point without releasing the pointer. Return near the starting point and cover most of the reference path.

**What is actually enforced.** The verifier replays every sheet translation and requires the registered state before drawing begins. It compares the submitted stroke with the generated reference using endpoints, path length, resampled deviation, and coverage. The task requires precise spatial registration and continuous path following. It does not require remembering the autograph because the reference remains visible during drawing.

### 15. Anamorphic Registration Press

**Passing behavior.** Rotate three color plates until every angular setting is within 7.5 degrees of its generated target. Lock all three plates and press the mechanism.

**What must be observed.** Each wheel changes the position and orientation of one colored rendering of the same five glyphs. Misregistration produces three displaced and warped impressions. Correct registration makes the impressions coincide into a single sharp image.

**What must be done.** Adjust each wheel while using the rendered composite as feedback. Reduce the color separation and distortion. Lock the three controls after alignment and press.

**What is actually enforced.** The verifier replays the three angular adjustments and checks their final errors. This requires iterative visual alignment of three independently controlled image layers. It does not require reading or entering the five-character token. Nothing changes unless the agent moves a wheel, so the environment does not require real-time observation or action.

## Environments 16–20

### 16. First Change Memory

**Passing behavior.** Start the field and wait for its one live run to finish. During the subsequent review, place the lens over the target carrier at least once shortly before the first change and at least twice while that change is active. Return to the settled field and select the same carrier after the nine carriers have been rearranged.

**What must be observed.** The lens reveals a distinct glyph inside each otherwise anonymous moving circle. Five temporary changes occur at different times. After the live run, the interface exposes the complete recording through a scrubber and places a visible marker at every change time. The settled field preserves the glyph identities in a shuffled grid.

**What must be done.** Use the earliest visible event marker to select a review time. Search locally with the lens to identify the carrier before and during that event. Retain its glyph. Return to the settled grid and scan for the same glyph before selecting it.

**What is actually enforced.** The grader requires genuine lens observations around the hidden target event and an identity-consistent final selection. The live run may be ignored because the full recording is available afterward. Finding the first event from an unmarked video is also unnecessary because the event markers reveal its time. The carrier need not be tracked through either occluder because the final task is glyph matching across a rearrangement.

### 17. Parallax Orchard

**Passing behavior.** Record at least 18 orbit samples spanning 96 degrees, travelling 155 degrees in total, and entering at least four angular sectors. Then drag exactly the three attached fruits into the basket and seal the harvest.

**What must be observed.** Every branch tip appears to meet its fruit stem from the initial view. Orbiting changes the projections. True contacts remain joined while false contacts separate because their branch tips occupy different depths.

**What must be done.** Drag empty canvas space horizontally to orbit the scene. Identify which three branch tips remain joined to their stems. Drag those fruits into the basket using at least four pointer movements per fruit.

**What is actually enforced.** The verifier checks both the orbit transcript and the final set of harvested fruit. It does not require a clean harvest. A false fruit produces an explicit rejection and the reset button preserves the same challenge plus the completed orbit inspection. An agent can therefore test fruits, remember the accept or reject result, reset, and finally harvest the three accepted fruits without interpreting parallax. A direct grader test passed with an invalid pluck followed by a reset and a correct harvest.

### 18. Polarized Palimpsest

**Passing behavior.** Produce at least 32 lens movements across at least 14 coarse cells. Change the polarizer at least four times. Capture five echoes in their generated order using the correct polarization. Each capture must last at least 460 milliseconds and contain at least four pointer-movement samples within 31 pixels of the echo.

**What must be observed.** Only the current echo is active. Its location emits a global pulse for 220 milliseconds every 1.45 seconds even when the lens is elsewhere or incorrectly tuned. The echo itself becomes visible when the lens covers it at the correct one of four polarization settings. A short directional cue appears after a successful capture.

**What must be done.** Move the lens broadly enough to satisfy the sampling requirement. Locate the active pulse. Select its polarization by trying the four settings. Press on the echo and keep producing nearby pointer movements until the hold completes. Repeat for all five echoes.

**What is actually enforced.** Ordered target acquisition, polarization search, and a timed pointer hold are enforced. Broad scanning is only a coverage quota because the global pulse exposes the current target location. Continuous target following is not necessary because the echo moves slowly relative to the 31-pixel acceptance radius. A direct grader test passed when every hold kept the pointer at its initial position apart from one-pixel movements. No dropped hold or recovery is required; the same passing test used zero misses and zero resets.

### 19. Kinetic Restoration Press

**Passing behavior.** For each of three artifacts, wait for a transformation film lasting at least 2.9 seconds. Place the three visible modifier modules in the reverse of their film order and toggle every module to its inverse setting. Pull the artifact along a straight rail using at least 24 samples over at least 680 milliseconds. Repeat for all three artifacts and seal the log.

**What must be observed.** During the film all three transformations are labeled with their sequence numbers at the same time. The active transformation is highlighted. After the film, the same three labeled modules appear in a shuffled rack. The interface visibly announces when the inverse arrangement is correct.

**What must be done.** Preserve the three-item order across the film shutter. Drag the modules into three reversed slots and toggle their inverse switches. Then hold the artifact and move monotonically through three fixed gates to the end of the rail.

**What is actually enforced.** The verifier checks the exact reversed arrangement, all three inverse switches, and the sampled rail trajectory. Watching and remembering the film is not necessary for a passing strategy. There are only six possible module orders, the interface reveals when an arrangement is correct, and workbench resets are unlimited. The film can therefore be replaced by permutation testing. The rail requires a sustained dense drag but presents a static straight path rather than a changing control problem.

### 20. Gyroscopic Tilt Board

**Passing behavior.** Control a ball in a simulation that advances every 50 milliseconds. Reach three lamps in their numbered order and then enter the goal cup. The accepted transcript must contain at least 72 physics ticks, eight tilt changes, and one seal event.

**What must be observed.** The ball retains velocity as tilt changes. Walls cause deterministic bounces. Three wells return the ball to the start and clear lamp progress. The currently required lamp is visually emphasized.

**What must be done.** Use the two-dimensional tilt pad to accelerate, steer, and brake the ball. Repeatedly update the control from the changing position and velocity. Navigate around walls and wells while reaching the ordered targets.

**What is actually enforced.** This environment requires control of an inertial system that continues changing between actions. The grader independently replays every physics tick, collision, target contact, and control change. Avoiding wells is not required because deaths are unlimited and do not prevent a later pass. Entering the cup at low speed is also not required because contact immediately sets velocity to zero. Across generated seeds the physical layout has only two versions related by horizontal reflection, which limits route variation but does not remove the real-time control requirement within a run.

## Environments 21–25

### 21. Shadow Crime Lab

**Passing behavior.** Drag the lamp through all four probe zones using at least 16 movements and at least 1,050 pixels of total travel. After all four analytic shadow responses have been sampled, drag the evidence tag with at least three pointer movements onto the current shadow of the forged object and file the finding.

**What must be observed.** Moving the lamp changes the five visible shadows. Four objects obey the same geometric shadow rule. One object uses a generated wrong pivot, wrong scale, or lagged lamp response. Each probe zone preserves a visible snapshot of the shadows at that lamp position.

**What must be done.** Under the intended solution, compare how the five shadows change across distinct lamp positions. Identify the response that is incompatible with the other four. Then locate that object's current shadow and place the tag inside its polygon.

**What is actually enforced.** The verifier reconstructs every lamp position, all four probe snapshots, total motion, and the final polygon hit. However, the visible case number contains the first four hexadecimal characters of the challenge identifier. Its first byte directly determines which zero-based object index is forged, and the five objects are visibly labeled E-01 through E-05 in that same order. An implementation-aware agent can therefore decode the forged object from the case number, satisfy the probe and travel requirements mechanically, and tag the known object's shadow without comparing its causal response. No timing constraint is present.

### 22. CRAFTCHA: Alchemy Bench

**Passing behavior.** Transform three raw materials through their exact generated machine sequences. Assemble the three terminal intermediates into the requested device. Deliver that device after a final run containing exactly the required transforms, no waste, the expected number of drags, and no material left elsewhere on the bench.

**What must be observed.** The complete three-branch recipe is visible for 5.5 to 6.7 seconds before a shutter covers it. One shorter replay is available. Every successful machine cycle produces a visibly named intermediate, while an incorrect machine produces visibly marked waste.

**What must be done.** Under the intended solution, retain the ordered machine sequence for each of three material branches. Route the materials through those sequences while managing four inventory slots. Insert the three resulting terminal states into the assembler and deliver its output.

**What is actually enforced.** The exact final lineage and the physical drag and cycle transcript are enforced. Remembering the shuttered recipe is not necessary because reset restores the same raw materials for the same challenge without preserving the current transform, waste, or drag counts. Correct intermediate output versus waste provides enough feedback to test possible next machines, reset, replay the discovered prefix, and continue until each branch is known. A direct grader test passed after an incorrect transformation, a reset, and a clean correct run. The environment still requires executing a six-to-nine-step symbolic procedure with inventory management, but the transient recipe can be replaced by systematic experimentation.

### 23. Occlusion Shell Swindle

**Passing behavior.** Complete three full shuffle rounds. In every round, record at least three inspection samples during the hidden handoff and select the final token carrier after the shuffle stops. Then certify the three choices.

**What must be observed.** A marked token enters one of four or five shells. Shell letters remain visibly attached to their shells throughout the shuffle. During a seven-tick hidden handoff, the inspection port directly displays the labeled source shell and destination shell for the token transfer.

**What must be done.** Move the pointer over the inspection port during its pulse. Read the transient source-to-destination pair. After the shuffle ends, click the shell carrying the displayed destination label. Repeat this for all three rounds.

**What is actually enforced.** The full generated animation, minimum elapsed observation time, inspection samples, and final choices are replayed by the verifier. Continuous shell tracking is unnecessary because the port reveals the final carrier label and that label remains visible at the end. The pointer also need not be held or corrected over the port. One pointer movement places a stored lens coordinate there, and the runtime automatically records a new sample on every inspection tick because no leave event clears that coordinate. The remaining temporal requirement is reading a simple two-label display during a window of roughly 840 milliseconds.

### 24. Ribbon Switchboard

**Passing behavior.** Probe at least 26 locations across at least 14 coarse cells while covering roughly two thirds of the target path and at least five or six of its crossings. Then hold the pointer from the marked source and trace the target ribbon to its matching terminal with at least 70 samples over at least 560 milliseconds.

**What must be observed.** Four to six colored ribbons cross repeatedly between labeled sources and terminals. The target bus, its unique color, its source, and its matching terminal are all stated visibly. The complete target curve is also drawn faintly across the board. Local hover increases its visibility and displays which ribbon is above at a crossing.

**What must be done.** Move over enough of the target curve to unlock tracing. Start at its source. Follow the long curved centerline in order without releasing, jumping more than 44 pixels, leaving the 18-to-22-pixel corridor, or materially backtracking. Release at the target terminal.

**What is actually enforced.** The exploration phase checks only proximity to target path points and crossing coordinates. It does not test whether the displayed over-under relationships were understood or used. Since target identity, color, endpoints, and the full curve are already visible, local depth reasoning is unnecessary. The strong requirement is a precise continuous trace of a long static path through a dense visual field. Recovery after a failed trace is supported but is not required for a pass.

### 25. Magnetic-Stripe Purgatory

**Passing behavior.** Match three cards to three readers by their visible badges. Insert every card with a sampled drag. Swipe each reader in its displayed direction using at least 14 movement samples, at least 92 percent rail coverage, limited deviation and backtracking, no large sample gap, and an accepted duration. Audit after all three readers lock.

**What must be observed.** Card and reader badges provide a direct one-to-one match. Every rail shows its required direction. An unsuccessful swipe returns BAD READ, TOO FAST, or TOO SLOW, while a successful swipe locks the reader.

**What must be done.** Drag each card into the matching slot. Move the swipe handle monotonically along the center of the straight rail while controlling the gesture duration. Repeat when a reader rejects the attempt.

**What is actually enforced.** Dense straight dragging and timing are independently replayed by the verifier. The scene does not change during a swipe, so the timed gesture does not require real-time visual interpretation. The generated timing profiles are always the same three intervals: 440–700, 700–1,050, and 1,050–1,420 milliseconds. Their inclusive boundaries permit a fixed strategy: try 700 milliseconds on all readers, then retry the sole failure at 1,050 milliseconds. A direct verifier check confirmed that schedule. Interpreting the calibration feedback or adapting an estimated duration is therefore unnecessary.

## Environments 26–30

### 26. Trajectory Catcher

**Passing behavior.** Catch three projectiles after they emerge from an opaque wall. Every successful attempt must contain at least eight visible trajectory samples spanning at least one second. While the projectile is hidden, place the catcher with at least two drag movements, rotate it in 15-degree increments, choose its aperture, and arm it at least 180 milliseconds before emergence. The later swept trajectory must enter the catcher with no more than 22 degrees of tangent error.

**What must be observed.** Each projectile follows one of three curved trajectory families. Its first 1.55 to 1.85 seconds are visible and leave a persistent dotted trace. The wall then hides at least 2.4 seconds of motion. After a miss, the result view draws the complete post-wall path and reports why the catcher failed.

**What must be done.** Under the intended solution, extrapolate the visible path through the wall. Select a future position and estimate the local direction there. Move, rotate, and size the catcher during the roughly 2.2-second commitment interval before arming it.

**What is actually enforced.** Predicting the hidden continuation from the initial observation is unnecessary. Every missed round can be replayed once with the same trajectory after the result screen has exposed the hidden path. A direct verifier transcript passed after deliberately missing and then replaying each of the three rounds. If the replay also fails, restarting the test preserves the same challenge while restoring all round replay budgets. The remaining requirements are retaining the revealed path across a replay and completing the catcher transformation before the commitment deadline.

### 27. Impossible Panorama

**Passing behavior.** Find one generated target among 32 moving specimens in a 4,800 by 2,400 world. Center it within a 38-pixel reticle at 1.65 to 2.25 times zoom. Set focus within five units of its generated depth. Hold the shutter for at least 940 milliseconds with at least eight automatically recorded samples and no sample gap above 155 milliseconds while the target event remains active throughout the exposure.

**What must be observed.** The target begins outside the initial viewport. It is the only specimen whose vanes lock inside two expanding cyan rings. That event lasts 1.98 seconds and repeats every 5.88 to 6.72 seconds. The target event is rendered only above 1.05 times zoom and within 18 focus units of the correct depth. Blur provides feedback for refining the focal plane.

**What must be done.** Pan through the large field while varying focus enough to make the event detectable. Recognize the transient ring event. Increase zoom, refine focus, center the moving specimen, and begin the shutter hold early enough that the event remains active for the complete exposure.

**What is actually enforced.** The verifier independently reconstructs every camera, zoom, focus, and exposure state at its recorded time. It does not require a particular search path or number of visited sectors. Continuous camera correction during exposure is neither required nor allowed because the camera must remain fixed. The specimen moves only a small distance relative to the reticle once its base position is centered. The temporal requirement is detecting a sufficiently early part of the repeating event and sustaining a stationary button hold through 940 milliseconds of it.

### 28. Flat-Pack Compliance Test

**Passing behavior.** Place seven rigid parts within 22 pixels and 0.14 radians of their generated target poses. Lock the six required pairwise joints with their sockets no more than 26 pixels apart. Avoid more than four pixels of part overlap. Then start a 36-tick compliance simulation whose deterministic maximum strain must remain below 42.

**What must be observed.** The stage displays a complete dashed blueprint. Every target part appears in its final color, shape, position, and orientation. Socket markers move with the solid parts and show when the corresponding connection points coincide. Accepted and rejected lock attempts produce explicit feedback.

**What must be done.** Rotate each part in 90-degree increments and drag it onto its matching blueprint shape. Select pairs that touch in the completed layout and request a lock. After all six joints are accepted, start the compliance test and wait for it to finish.

**What is actually enforced.** Precise two-dimensional pose matching and a complete connected graph are enforced. Inferring the final assembly from unfamiliar loose parts is unnecessary because the blueprint shows every final pose directly. Understanding the joint topology is also unnecessary because rejected pair attempts are unlimited and do not prevent a pass. The load phase requires no action. Its sensor values are fixed by the generated force table, so observing the oscillation cannot change the outcome after a valid assembly has been submitted to it.

### 29. Crash-Deadline Hovercar

**Passing behavior.** Drive a continuously advancing vehicle for 1,400 progress units before tick 330 without leaving the road or colliding with six obstacles. Complete five inspection checks during their generated time windows. Each check requires the stored pointer position to remain within 29 pixels of a moving sigil for 11 to 13 consecutive 50-millisecond physics ticks while the vehicle continues moving.

**What must be observed.** The road and obstacles scroll past the vehicle as speed and lateral velocity respond to held keys. Five sigils appear in overlapping sequential windows and move along small two-dimensional orbits. A visible meter shows consecutive accepted dwell ticks.

**What must be done.** Regulate speed so the vehicle does not finish before the final inspection window. Steer around the moving road boundaries and alternating obstacles. Place the pointer where each sigil will remain inside its acceptance radius long enough to fill the meter.

**What is actually enforced.** Real-time vehicle navigation and speed control are enforced because physics advances every 50 milliseconds and the final window occurs after a full-throttle vehicle would already finish. Continuous pointer tracking is not enforced. The verifier uses the most recently stored pointer coordinate on every physics tick and imposes no pointer-sample requirement during a dwell. A direct passing replay used exactly five pointer movements, one placement per sigil, followed by no corrections during any dwell. An additional calculation found a qualifying stationary interval for every one of 500 generated sigils examined. This removes the intended simultaneous moving-target tracking while leaving the live driving problem intact.

### 30. Robot Art Critic

**Passing behavior.** Draw the requested object within a class-dependent budget of 11 to 15 strokes. Every stroke must contain at least five distinct points, last at least 42 milliseconds, stay within a 46-pixel sample gap, and avoid a sample interval above 180 milliseconds. The independent recognizer must rank the requested class first with a score of at least 74 and a margin of at least nine points over every other class.

**What must be observed.** The brief names one of eight object classes plus one of three lean directions and one of three width styles. The canvas contains no visible solution. After a review, the interface reports a coarse critique such as wrong silhouette, topology, scale, centering, or direction. At most five reviews are allowed.

**What must be done.** Convert the verbal object description into a centered multi-stroke drawing. Preserve the relevant silhouette, direction distribution, closed shapes, intersections, endpoints, and approximate stroke topology. If the first review fails, revise or clear the drawing in response to the critique.

**What is actually enforced.** The verifier rasterizes and scores the submitted pointer paths rather than accepting a text answer or client claim. Iterative revision is available but not required because a correct first drawing passes. More importantly, generated instances contain only 72 behaviorally distinct target forms: eight fixed class templates crossed with three lean values and three width values. A direct recognizer check accepted all 72 corresponding canonical traces on their first attempt. A benchmark-aware agent can therefore select a memorized trace from the visible brief and execute it. On a first encounter, the task instead requires semantic drawing plus precise multi-stroke pointer control.

## Environments 31–35

### 31. The Photograph Eats the Room

**Passing behavior.** Capture a beam that is fully visible in the camera frustum and develop its transformed photograph into a bridge across the void. Then capture an opening and develop it into the divider wall. Walk through both altered collision regions to the terminal. The transcript must contain at least 30 movement samples and 12 world units of travel. Each photograph must also receive a plane drag and at least two scale changes before development.

**What must be observed.** The first-person view shows the two source geometries and the resulting collision changes. A top-down contact sheet shows the void, divider, camera pose, and both target socket centers as colored rings. Numeric readouts expose camera position, camera angle, photograph offset, photograph depth, rotation, and scale. A rejected development explicitly says that position, angle, or scale is wrong while preserving the carried photograph.

**What must be done.** Navigate close enough to frame each complete source. Carry its photograph to the matching colored region. Translate, rotate, and scale the projected plane so its reconstructed world segment has the required position, orientation, and length. The bridge must be created first because it is needed to reach the second source. The opening must then be created before the terminal can be reached.

**What is actually enforced.** The verifier reconstructs camera movement, capture visibility, transformed geometry, collision changes, and terminal contact. No world state changes while the agent is stopped. Placement can therefore be solved through unhurried observation and repeated development attempts. The two source roles, two target roles, and their dependency order are constant across generated instances. The environment enforces navigation and geometric transformation, but it does not enforce rapid reaction or online control of a changing scene.

### 32. Clockwork Doppelgänger Customs

**Passing behavior.** Record three 2.3-second pointer traces. The first must grab and release. The second must grab, stamp, and release. The third must grab and release. Every accepted recording must contain at least 24 timed samples and 90 pixels of travel. Set the three start phases in 50-millisecond increments so one passport is caught from the conveyor, transferred twice within 230 milliseconds, stamped, and released at the exit without a possession error. A complete 5.9-to-6.3-second master cycle must then run before filing.

**What must be observed.** The stage shows the conveyor, five stations, and a guide path for each role. Recording mode displays elapsed local time while preserving the chosen action times and pointer path. Master playback shows the three saved ghosts, the passport, and the resulting possession state. A failed cycle reports possession faults and leaves the recordings available for rephasing or replacement.

**What must be done.** Execute each role as a timed pointer-and-action trace under the live recording clock. Relate the self-chosen local action times to the passport's conveyor arrival and to the preceding ghost's release. Set three phase offsets that make the independently recorded traces form one valid global sequence. Run the complete master clock to test the temporal program.

**What is actually enforced.** Recording timestamps, sample density, pointer continuity, action order, phase edits, handoff windows, and the uncompressed master cycle are all replayed by the verifier. The three recordings are created sequentially, but their saved actions overlap during playback. No corrective input is possible while the master cycle runs. The scene geometry and role sequence remain fixed while station positions and conveyor timing vary. The environment therefore enforces timed trace production and temporal coordination, not online control in response to unpredictable changes during playback.

### 33. Recursive Dollhouse Smuggling

**Passing behavior.** Use the giant projection to move the shared gate completely into its parking region. Move the parcel through the miniature-to-human frame, then through the human-to-giant frame, and finally into the giant bay. Every drag is inverse-mapped into one canonical room and swept against its walls, the gate, the parcel, and room boundaries. A passing transcript must manipulate the parcel through all three projections.

**What must be observed.** Three isometric projections of the same room are visible at once. The active parcel is opaque and labeled in the projection where it can be moved. Its copies in the other projections are explicitly labeled as synchronized ghosts. The gate, parking region, transfer frames, final bay, and fixed obstacles are all drawn. Collision feedback identifies the canonical obstacle that stopped a drag.

**What must be done.** Plan collision-free two-dimensional drag routes through an isometric projection. Move the gate around the walls to its parking region. Then move differently sized parcel footprints around the remaining obstacles to the two frames and final bay. Select the projection corresponding to the parcel's current scale at each stage.

**What is actually enforced.** The verifier checks the inverse transform, swept collision path, full containment, fixed transition order, and use of all three views. There is no timing or drag-density requirement. The canonical room, operation sequence, obstacle locations, and destination locations are identical across seeds. Only projection matrices, mirroring, and presentation vary. Comparing corresponding states across projections is not necessary because the interface marks the active view and every destination directly. The remaining requirement is spatial route construction under a transformed view with changing object footprint.

### 34. The Flat Prisoner

**Passing behavior.** Apply at least 18 primitive camera changes over at least 520 milliseconds. Freeze a projection in which all five core ledges are visible, at least two screen-space joins exist, and the exit is reachable in the derived graph. Then control the prisoner in a 20-millisecond fixed-step platformer for at least 130 ticks. Reach the exit using at least five key transitions and two grounded jumps.

**What must be observed.** Orbiting, panning, and dollying change the projected ledges. The interface exposes the numeric yaw, pitch, distance, and pan coordinates. It also reports the exact join count and changes a separate display from `DISCONNECTED` to `ROUTE DETECTED` when the projection is valid. After freezing, the projected ledges become a conventional two-dimensional platformer with a marked exit.

**What must be done.** Adjust five camera quantities until the displayed graph becomes reachable. Freeze after the camera settles. Hold horizontal movement and time two jumps across the projected gaps while gravity continues to advance. A failed traversal can be thawed before another camera configuration is attempted.

**What is actually enforced.** A solver does not have to determine connectivity from the rendered geometry because the live route display provides the answer. The generated solution camera is always the initial camera corrected by one of two fixed sets of offsets. This invariant held across 1,000 generated seeds. The frozen core geometry has only four layouts, and every layout places the start on the left and exit on the right. A benchmark-aware solver can therefore use a fixed camera correction followed by one of four traversal scripts. The platforming phase still requires correctly timed actions while a jump is in progress, although the prisoner remains stationary whenever it is grounded and no movement key is held.

### 35. Forced-Perspective Moving Day

**Passing behavior.** Pick up the crate while preserving its apparent screen size. Move it to a nearer depth so its reconstructed scale fits inside the visible key slot. Pick up the sign and move it to a farther depth so its reconstructed scale spans the visible floor void. After both readiness indicators activate, move the camera body through the bridge, doorway, and exit within 180 movement ticks.

**What must be observed.** The scene shows the crate, sign, key slot, void, bridge region, door, and perspective floor grid. The prompt states which object belongs in each region. While an object is held, the interface reports its depth and exact derived scale. Separate indicators immediately report whether the bridge is load-bearing and the door is unlocked. A rejected release names the blocking surface and leaves the object held for another attempt.

**What must be done.** Select each projected object. Change its depth in half-unit increments while keeping its screen size fixed. Aim the floor ray at the marked destination and release it with the needed scale and footprint. Then move the camera body beyond the exit.

**What is actually enforced.** The verifier reconstructs every pickup ray, depth change, release pose, rigid footprint, and movement tick. Object placement has no time limit and supports repeated correction. The final navigation does not require visual steering: after valid placements, holding only the forward key reached the exit without collision in all 10,000 generated instances tested, always within 64 ticks. The world otherwise remains static. The environment therefore enforces projective object resizing and placement, followed by a fixed-duration forward key hold rather than perception-guided real-time navigation.

## Environments 36–40

### 36. LIDAR Blacksite

**Passing behavior.** Traverse a lightless corridor system while recording at least four LIDAR scans from at least three positions separated by 2.2 world units. The scan that reveals the beacon must occur at least five units from the first scan position. Approach the revealed beacon within 0.92 units with clear line of sight, pick it up, and carry it to the extraction gate. The accepted run must include at least 12 units of travel, 14 key transitions, and 320 fixed simulation ticks.

**What must be observed.** The viewport begins black. A scan casts 73 nearest-hit rays across a 104-degree field and creates colored world-anchored points for walls, crates, the beacon, and the exit. The points are reprojected as the player moves and disappear after 500 ticks, which is ten seconds. The interface exposes heading, odometry, collision count, scan count, distinct station count, and beacon status. It does not expose a map or player coordinates.

**What must be done.** Scan from the current viewpoint to reveal nearby surfaces. Infer corridor direction and distance from the point cloud. Move and turn through the facility while updating that spatial representation with later scans. Reveal the beacon from a new line of sight. After pickup, continue through the remaining corridor to the differently colored exit return.

**What is actually enforced.** The verifier independently replays fixed-step motion, collision, every ray return, scan positions, beacon visibility, pickup, and extraction. Geometry is static and player state changes only while movement controls are held. An agent can stop after each short movement, inspect the scene, and rescan without a rapid-response requirement. Collisions are counted but do not prevent a pass. There are only four corridor layouts and their horizontal mirrors. A benchmark-aware solver can classify and replay one of eight routes, but a first encounter still requires active sensing and navigation without an ordinary visible map.

### 37. Tomographic Baggage Surgery

**Passing behavior.** Record at least four valid slice observations across at least two suitcase rotations. The selected offsets must span one unit, and at least two distinct observations must intersect the hot target. Lock the suitcase to rotation zero. Move the probe through at least two orthogonal views, overlap the target, close the clamp, and withdraw above y = 4.05 without ever contacting a neutral solid.

**What must be observed.** The slice display shows the exact two-dimensional intersection of the chosen plane with every intersected primitive. Hot target material is visually distinct from neutral material. Separate top, front, and side probe panels show the outlines of all four solids and the probe in co-registered orthographic projections. The target is not distinguished from neutral solids in those probe panels. Collision feedback identifies the neutral volume that stopped a move.

**What must be done.** Under the intended procedure, sweep slices through multiple orientations and combine their positions and changing cross sections to recover the target's three-dimensional center. After the case is locked, use one projection to set two probe coordinates and a second projection to set the remaining coordinate. Close the clamp only when the probe overlaps the target. Withdraw along a collision-free path while accounting for the target's radius.

**What is actually enforced.** Slice records, rotations, cross-view coordinate mapping, swept collisions, capture, and withdrawal are replayed exactly. The scanning requirement can be satisfied without adaptive search. The four fixed observations rotation 0 at z = -0.50 and z = -0.25 followed by rotation 1 at x = -0.50 and x = 0.50 meet every scan condition for all 10,000 generated instances tested. The target also always occupies a narrow, recognizable region while the other sphere is far away in the opposite region, and all solid outlines are visible in the probe panels. A benchmark-aware solver can therefore bypass volumetric reconstruction. Collision-free registration in at least two projections remains enforced. There is no timing requirement.

### 38. Three-Camera Claw Machine

**Passing behavior.** Move an inertial three-dimensional claw to the visibly marked artifact, close the gripper within capture range, carry the artifact around the obstacle cage, and release it fully inside the delivery chute. Every acceleration, coast, or brake command must be followed by exactly one physics tick. The final transcript must contain frames from the top, front, and side feeds.

**What must be observed.** The overhead feed shows x and z at the current tick. The front feed shows x and y two ticks in the past. The side feed shows z and y four ticks in the past. Every feed labels its displayed tick. The marked artifact, neutral artifacts, obstacles, chute, and claw appear in the applicable orthographic projections. Numeric status shows current speed, gripper state, carried load, and global tick.

**What must be done.** Relate positions across the three projections while accounting for their different delays. Apply axis accelerations, coast steps, and strong brakes to move the claw and cancel its velocity near a target. Close on the marked artifact. Raise it above the cage, move laterally to the chute, lower it, and release it within the three-dimensional containment volume.

**What is actually enforced.** The verifier reconstructs inertia, damping, collision resolution, capture, delayed feed contents, and delivery. Time does not pass between controls. Each button click atomically applies one command and advances one 0.12-second simulation step. The environment is therefore a discrete inertial-control problem rather than a wall-clock real-time task. All three feeds are automatically included after every physics tick, so the `feeds_seen` check does not prove that an agent used them. Collisions and resets are permitted. The high route above the cage is constant while target and chute positions vary within small finite sets.

### 39. Zero-G Cable Autopsy

**Passing behavior.** Attach both grippers at least once. Manipulate a nine-node constrained cable until its two endpoints have crossed their assigned rings, its winding around the central peg is at most 0.12, and neither the cable nor its segments have touched either alarm sphere. At least 40 position-based-dynamics substeps are required, including eight while both grippers are attached.

**What must be observed.** The orbitable view shows the cable, individual nodes, three pegs, two endpoint rings, and two red alarm contacts. The two endpoint nodes have distinct colors. The interface reports each gripper's attached node and exact target coordinate. It also reports both ring-crossing states, alarm state, and current winding.

**What must be done.** Under the intended interpretation, choose useful cable nodes, coordinate two grippers in three dimensions, and revise the deformation after each deterministic physics update. Lift the cable clear of the pegs and alarms. Move both ends through their respective rings while reducing the central winding.

**What is actually enforced.** Every accepted gripper move immediately runs four deterministic physics substeps. Nothing evolves between button presses, so no real-time tracking or control is required. More importantly, one fixed open-loop script passes all 18 distinct physical geometries: attach gripper A to node 0 and gripper B to node 8, move each endpoint upward eight times, move each endpoint outward four times, then settle twice. This was verified across every combination of initial winding, ring height, and central peg radius. Camera orbit is not required. The task can test topological and deformable-body reasoning on first discovery, but repeated instances do not require such reasoning.

### 40. Portal Freight: Oversized Parcel

**Passing behavior.** Ray-cast a blue portal onto the east wall of Chamber A and an orange portal onto the receiver wall in Chamber B. Rotate the 5.2-unit parcel from its initial angle to zero. Push it through the linked frames until every sample lies in the oriented receiver. The transcript must include two accepted portal placements, four aim turns, four rotation events, at least 25 pushes, ten split-frame ticks, ten transformed-velocity ticks, and zero collisions.

**What must be observed.** A top-down view shows both complete chambers, both placement tools and their rays, the parcel, the receiver volume, the portals, and the parcel portions reconstructed in each space. The interface states that blue is the Chamber A source and orange is the Chamber B receiver. It reports each portal's wall, whether the transform is linked, the parcel's exact angle, split tick count, and collision count.

**What must be done.** Aim each tool at the required wall and place its portal with enough clearance. Rotate the parcel until it is perpendicular to the Chamber A source wall. Repeatedly push it along its long axis while the front portion appears in the destination frame. Continue until the transformed parcel is fully contained in the receiver.

**What is actually enforced.** The verifier reconstructs both ray casts, the right-handed portal transform, every parcel sample, swept aperture collision, split occupancy, transformed velocity, and final containment. None of these states advances with wall-clock time. Every rotation or push is a separate button-triggered transition. Across 100 generated instances, the successful action counts were always the same: two aim steps for each portal, four rotations, and 31 forward pushes. The sign of each aim correction and rotation is visible from the rays and parcel angle. An agent need not derive the coordinate transform or react while the parcel spans the frames; it only needs target alignment followed by a fixed action sequence.
