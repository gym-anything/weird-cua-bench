# Random One-Configuration Audit of All 75 Environments

Date: 2026-08-13

This is a source-based application of the definition in
`docs/controllability/real-time.md`. It samples one configuration for every
environment: an independently random difficulty in D1-D5 and an independently
random interaction mode. The frozen manifest is `random_all_75.json`, generated
with seed `weird-cua-real-time-all75-2026-08-13`.

This is 75 sampled configurations from the full set of 750. It establishes one
judgment per environment; it does not classify the other nine configurations of
each environment.

## Result

- Real-time: 25
- Not real-time: 50

Manual recheck completed 2026-08-13: every sampled configuration was traced
again through its selected difficulty parameters, selected interaction surface,
visible runtime behavior, and grading consequences. The later 750-configuration
audit corrected row 12 after comparing the D2 motion bounds directly with its
lock radius. This was a source review of each concrete mechanic, not an agent
gameplay evaluation.

`Yes` means that, in the sampled configuration, a bounded recent visual window
is needed and sufficient to choose a delayed action, and the same visibly
evidenced autonomous state change makes an available action less effective or
unavailable within a mechanic-scale delay. `No` is followed by the decisive
failed condition rather than by every property of the task.

## Cases

| # | Environment | Configuration | Real-time | Decisive evidence |
|---:|---|---|:---:|---|
| 1 | Blind Dice Courier | D1, Simplified | No | Die changes are discrete consequences of submitted actions; no outcome-affecting state evolves while awaiting the next action. |
| 2 | Gyroscopic Tilt Board | D2, Simplified | Yes | The ball retains momentum in generated geometry. Recent motion predicts the delayed tilt, and a tilt that is useful now loses its advantage as the ball moves. |
| 3 | Bomb Manual From Hell | D1, Simplified | No | The bomb is solved through static, synchronous manipulation; no relevant action opportunity autonomously degrades. |
| 4 | Bureaucratic Signature Trap | D2, Full | No | Signature construction and reproduction advance through the agent's drag actions, not through autonomous task-state evolution between actions. |
| 5 | Clockwork Clutch Safe | D4, Simplified | Yes | Visible shaft phases advance autonomously from generated initial conditions. Recent phase motion predicts a delayed clutch action, whose timing advantage expires. |
| 6 | Clockwork Doppelgänger Customs | D5, Full | No | The master performance is a fixed recorded interval with work controls unavailable; the agent can time its own recording actions without observing an expiring controllable opportunity. |
| 7 | Live Control-Flow Wiring Lab | D5, Full | No | Program state advances only when the agent steps the debugger; wiring remains static between submitted actions. |
| 8 | Consequences Boss | D1, Simplified | No | State transitions are consequences of discrete choices, with no relevant autonomous evolution between choices. |
| 9 | CRAFTCHA: Alchemy Bench | D3, Full | No | The recipe presentation supplies information for later static work; the information remains actionable and no concurrent action opportunity expires. |
| 10 | Crash-Deadline Hovercar | D2, Full | Yes | Held driving inputs persist while the vehicle and hazards move. Recent motion and geometry determine a delayed release or redirect, and the old control can become a collision. |
| 11 | Cursor-Controlled Constellation Hunt | D4, Simplified | No | Constellation revelation and target acquisition are driven by the submitted pointer/proxy actions; there is no autonomous expiring target state. |
| 12 | Polarized Palimpsest | D2, Simplified | No | Its only echo moves at most about 22 pixels from its known base while the D2 lock radius is 40 pixels. A fixed base coordinate remains valid over the full orbit, so motion observation is unnecessary. |
| 13 | Dead Man's Switch | D2, Simplified | No | The proxy automatically tracks the pressure center and route changes are discrete button effects; the required hold duration is schedulable from the agent's own action clock. |
| 14 | Domino Autopsy | D2, Simplified | No | The autonomous domino run is not a concurrent control opportunity; the actionable reconstruction/diagnosis state is static. |
| 15 | Elastic Membrane Sorter | D2, Simplified | Yes | The released marble keeps moving under live physics while post controls remain active. Recent velocity predicts the delayed correction, and the same correction loses value downstream. |
| 16 | Exact-Change Candy Cascade | D5, Simplified | No | Each board change is the synchronous result of an accepted swap; nothing relevant evolves while no action is supplied. |
| 17 | Modal Terminal Escape | D3, Full | No | Terminal state changes only through submitted keystrokes and commands. |
| 18 | Fake Desktop / Automation Inversion | D1, Simplified | No | The desktop puzzle advances through discrete interface actions; no visible autonomous change makes a current action expire. |
| 19 | Flat-Pack Compliance Test | D2, Simplified | No | Assembly is action-driven, and controls are unavailable during the deterministic load animation; later certification can be scheduled from the load-start time. |
| 20 | The Flat Prisoner | D1, Simplified | Yes | Once movement starts, prisoner physics continues under held controls. Recent position and velocity in the generated projection determine a delayed release or jump, which can become too late. |
| 21 | Floodgate Archive Rescue | D4, Full | No | The archive and gate state are changed through the agent's controls; no relevant action independently deteriorates between inputs. |
| 22 | Forced-Perspective Moving Day | D1, Full | Yes | A held movement action continues changing the camera and collision geometry. Recent views reveal the delayed release/redirect point, while continued motion can overshoot or fall. |
| 23 | Funeral With No Instructions | D3, Full | No | The ritual is learned and performed through discrete interactions; waiting does not autonomously reduce the usefulness of the next correct action. |
| 24 | Gravity-Room Freight | D4, Simplified | No | Bodies settle only after a submitted room rotation while further controls are blocked; there is no intervenable autonomous control mode. |
| 25 | Hologram Silhouette Foundry | D4, Simplified | No | Rod and view transformations are synchronous consequences of manipulation, with no autonomous action expiry. |
| 26 | Impossible Ecology | D3, Simplified | Yes | Organisms keep moving with inertia and coupled responses while lure controls remain active. Recent trajectories determine the delayed lure coordinate, and an old coordinate loses influence. |
| 27 | Impossible Panorama | D3, Full | Yes | The photographic target and event window move autonomously. Recent motion predicts the delayed shutter action, whose qualified capture opportunity closes. |
| 28 | Input-Lag Forklift | D1, Full | No | The queued machine state advances synchronously when commands are issued; the agent's own action history determines the queue without a recent visual-motion requirement. |
| 29 | Insider Trading CAPTCHA | D3, Full | Yes | The visible tape/chart evidences the evolving price process. It predicts delayed order value, and the advantage of the same buy/sell action can disappear as prices move. |
| 30 | Parallax / Inertial Jigsaw Alignment | D5, Simplified | No | A submitted nudge starts coast, but controls are blocked until coast ends; afterward the placement state is static. Hold timing is available from the agent's own clock. |
| 31 | LIDAR Blacksite | D4, Simplified | Yes | Held movement persists through generated geometry while scans fade. Recent motion and obstacles determine a delayed release/turn, and the old movement can collide or overshoot. |
| 32 | Magnetic-Stripe Purgatory | D3, Full | No | Swipe motion and duration are produced by the agent's own gesture, so the necessary timing is available from its action history rather than autonomous visible evolution. |
| 33 | Marionette Checkpoint | D2, Simplified | No | A fixed observation-free policy setting both active strings to 65 remains within the D2 tolerance for every generated sway phase; clause (i) fails. |
| 34 | Five-System Verification Reactor | D3, Full | Yes | Its live subsystems include an autonomously moving packet interception opportunity while the intercept control is active; recent motion predicts a click whose window expires. |
| 35 | Isometric Voxel Extraction Mine | D5, Full | No | Voxel inspection and extraction progress through discrete pointer actions; the relevant spatial state is static between them. |
| 36 | Kinetic Restoration Press | D2, Simplified | No | The film presents information that is retained for later work; work controls are unavailable during playback and the later manipulation state is static. |
| 37 | Motion-Only Ghost Jigsaw | D1, Simplified | No | Animation identifies the pieces, but the resulting placement actions remain valid indefinitely and are otherwise synchronous/static. |
| 38 | Scroll-Cage Checkbox | D4, Full | Yes | The target moves under live physics and cursor repulsion while pointer controls remain active. Recent target motion predicts the delayed click, and the old location loses its hit advantage. |
| 39 | Occlusion Shell Swindle | D2, Simplified | Yes | Shell and cover geometry advances automatically. The recent sequence identifies the delayed inspection target, and its short inspection opportunity closes as the shell moves. |
| 40 | Orbital Docking Customs | D5, Simplified | No | Impulses and coast are explicit discrete controls that advance a fixed simulation tick; state does not continue autonomously while the agent waits. |
| 41 | Parallel Grillmaster | D3, Simplified | Yes | Food cooks continuously with generated target times while serve controls remain active. Visible cooking history predicts the delayed serve action, whose doneness advantage expires into under/overcooking. |
| 42 | Pheromone Dispatch | D1, Simplified | No | At D1, the fixed field refresh can be scheduled from the agent's own dispatch clock, and a delayed refresh remains the same effective action rather than a lost opportunity. |
| 43 | The Photograph Eats the Room | D1, Full | Yes | A held movement input persists as the camera traverses generated room geometry. Recent movement/collisions determine a delayed release, turn, or capture, and continued motion can pass the useful point. |
| 44 | Polyrhythm Customs | D1, Simplified | No | A fixed preview is followed by reproduction; it tests timing memory, but no controllable action opportunity expires during the preview. |
| 45 | Popup Exorcist | D1, Simplified | No | Popup progression is governed by discrete dismissals; waiting does not make the same next correct dismissal less effective through relevant visible evolution. |
| 46 | Portal Freight: Oversized Parcel | D2, Full | No | Portal placement, parcel pushes, rotations, and transformed samples occur synchronously in action handlers. |
| 47 | Recursive Dollhouse Smuggling | D3, Simplified | No | Canonical nesting state changes only through submitted proxy moves; it is static between actions. |
| 48 | Dual-Projection Sculpture Rig | D4, Full | Yes | Sculptures move on an autonomous carousel while direct drag controls remain available. Recent motion predicts the delayed acquisition point, while the old point stops hitting the object. |
| 49 | Reload Interruption | D3, Simplified | No | Simplified mode uses a fixed stabilizer hold; spark position is irrelevant to grading and release timing is determined by the agent's own pointer-down time. |
| 50 | Four-Tab Robot Handshake | D3, Simplified | Yes | The pulse and receiver move while contact/direction controls remain active. Recent relative motion predicts a delayed correction, and the old contact setting loses charge advantage. |
| 51 | Ribbon Switchboard | D3, Simplified | No | Routing and switch state change only through submitted controls; there is no autonomous expiring action. |
| 52 | Robot Art Critic | D5, Simplified | No | The relevant comparison and judgment state is static between selections. |
| 53 | Rorschach / Subjective Prompt With A Fixed Rubric | D5, Full | No | A fixed response cycle later re-enables controls and permanently archives its result; it creates information, not an expiring controllable opportunity. |
| 54 | Rotate The Wrong Thing Upright | D2, Full | No | Every gimbal and view change is synchronous with the agent's drag actions. |
| 55 | Rotating On-Screen Keyboard | D1, Simplified | No | Simplified mode uses physical-key actions; the required key does not move even though the displayed keyboard rotates. |
| 56 | Semantic Drag-And-Drop Absurdity | D2, Full | No | Probe duration is known from the agent's own hold clock, and successful probe eligibility persists after the visual response fades. |
| 57 | Shadow Crime Lab | D2, Simplified | No | Lamp, shadow, and sample state change only in response to submitted controls. |
| 58 | Live Shattered-Scene Synchronizer | D5, Full | No | Moving shards reveal phase/spatial information, but the later matching actions remain valid; synchronization holds are timed from the agent's own actions. |
| 59 | Slime Commute | D5, Simplified | Yes | Lanes and hazards advance every tick independently of direction clicks. Recent motion predicts the delayed hop, while the same hop can become a collision or water failure. |
| 60 | Slot-Reel Character Capture | D2, Full | Yes | The required physical-key action is the currently visible reel symbol. The generated token cycle changes autonomously, so an old key becomes wrong after the symbol switches. |
| 61 | Specular Lighthouse Relay | D5, Simplified | Yes | The receiver moves from generated sinusoidal phase while gimbal controls remain active. Recent motion predicts a delayed adjustment, and the same adjustment can cease to hit/charge it. |
| 62 | Parallax Orchard | D2, Full | No | Parallax observation supports a later spatial solution, but the resulting selection/manipulation opportunity remains actionable rather than expiring. |
| 63 | Temporal Memory / First-Change Evidence | D1, Full | Yes | Full mode exposes the lens during one-shot live carrier motion. Recent motion is needed to capture the required evidence, and each pre/change hit opportunity disappears as the target advances. |
| 64 | Thirty-Year Time Wheel | D2, Full | No | Coast is deterministically caused by the agent's own release and can be handled by the universal policy “brake after a fast release”; recent visual evidence is not necessary. |
| 65 | Three-Camera Claw Machine | D5, Simplified | No | Physics advances only through explicit coast/brake tick controls in this interaction mode, not autonomously while awaiting the next action. |
| 66 | Tiny FPS Customs | D3, Simplified | No | Movement, turning, and firing are discrete step controls; the world does not keep evolving between actions. |
| 67 | Tomographic Baggage Surgery | D2, Full | No | Slice, probe, and extraction state changes only through the agent's controls. |
| 68 | Top-Face Dice Arithmetic | D5, Simplified | No | Dice rolls and arithmetic progress through discrete submitted actions, with no expiring autonomous control opportunity. |
| 69 | Blind Corridor Oscilloscope | D2, Simplified | No | Drift advances by submitted trace-sample index rather than task time; sonar fading removes visible information but does not reduce the effectiveness of a later sonar action. |
| 70 | Trajectory Catcher | D1, Full | Yes | The visible flight tail predicts the delayed catcher transform/arm action, and autonomous flight closes the catcher commit window. |
| 71 | Wind-Tunnel Seed Courier | D3, Full | Yes | Apertures and seed motion continue under live physics. Recent trajectories predict a delayed steering action, while the relevant opening and correction expire. |
| 72 | Wizard Interception Observatory | D5, Simplified | Yes | The coordinate net must lead an autonomously moving/occluded target. Recent trajectory predicts the delayed aim, and the old aim loses its intercept opportunity. |
| 73 | Wonky Text Under Hostile Rendering | D3, Full | No | The distorted visual content is static while the agent enters its answer. |
| 74 | Wrong Number | D1, Full | Yes | Carrier phase drifts autonomously during the lock trial while sliders remain active. Recent waveform motion predicts a correction, and an old phase setting loses lock quality. |
| 75 | Zero-G Cable Autopsy | D5, Full | No | Cable physics is stepped synchronously after gripper movement or an explicit settle action; it does not evolve autonomously between actions. |

## Cross-checks

The sampled interaction mode changes several judgments that would be wrong if
the environment name alone were classified:

- Polarized Palimpsest is `No` in sampled D2 Simplified mode because its single
  echo never leaves the lock radius around the known base coordinate. Dead
  Man's Switch is also `No` in sampled Simplified mode because its proxy tracks
  automatically and only the agent-timed hold remains.
- Rotating On-Screen Keyboard is `No` in sampled Simplified mode because the
  required physical key is stationary. The mouse-controlled Full mode is the
  reference `Yes` case.
- Temporal Memory / First-Change Evidence is `Yes` in sampled Full mode because
  the lens is usable during live motion. Its Simplified mode instead exposes its
  coordinate controls during static review and was `No` in the pilot.
- Thirty-Year Time Wheel, Blind Corridor Oscilloscope, and D1 Pheromone Dispatch
  contain timers or temporal behavior but are `No`: their useful schedules are
  determined by the agent's own actions or sample indices, so a recent visual
  window is not necessary.
- Clockwork Doppelgänger Customs has an autonomous master cycle, but the agent
  cannot act on it as an expiring opportunity; it records its own fixed-duration
  choreography. It is therefore `No` rather than being labeled from animation
  alone.

These cases exercise the intended boundaries: real-time is not synonymous with
animation, a timer, temporal memory, physics that runs only inside an action, or
an action whose duration is known from the agent's own clock.

## Manual recheck notes

The 25 `Yes` cases all have an outcome-affecting control available while the
relevant world state continues to change. Their recent visible motion either
changes where the delayed action must land, changes the value of that action,
or closes the action's availability window.

The 50 `No` cases separated into four recurring reasons:

- the world is static between actions, or its physics advances only inside an
  action handler;
- an animation or simulation runs while the relevant controls are unavailable;
- timing is recoverable from the agent's own action clock, so recent frames are
  unnecessary; or
- moving/temporary information is needed for memory or observation, but the
  eventual action remains valid rather than expiring.

The closest decisions were checked at the event-handler and grader level.
Held-input movement counts in Crash-Deadline Hovercar, The Flat Prisoner,
Forced-Perspective Moving Day, LIDAR Blacksite, and The Photograph Eats the
Room because the already-issued input keeps changing the world before the next
action. By contrast, Thirty-Year Time Wheel, Three-Camera Claw Machine,
Blind Corridor Oscilloscope, and Zero-G Cable Autopsy advance from explicit
agent actions or simulation steps. Live Shattered-Scene Synchronizer has a
moving display, but its spatial and phase corrections remain effective and its
hold is timed from the agent's own pointer-down. Trajectory Catcher is `Yes`
because flight closes the transform/arm commit window even though its swept
catch calculation evaluates the later path.

## Evidence reviewed

For every row, the sampled controls were checked against the environment's
generator/configuration, visible browser runtime, and grader/verifier. Solvers
were used only as implementation evidence, not as a substitute for the visible
task policy. The most configuration-sensitive rows were additionally traced
through their concrete event handlers and control availability: Clockwork
Clutch Safe, Clockwork Doppelgänger Customs, Polarized Palimpsest, Dead Man's
Switch, The Flat Prisoner, Impossible Ecology, Parallax / Inertial Jigsaw
Alignment, LIDAR Blacksite, Marionette Checkpoint, Parallel Grillmaster,
Pheromone Dispatch, Temporal Memory / First-Change Evidence, Thirty-Year Time
Wheel, Blind Corridor Oscilloscope, Trajectory Catcher, Wrong Number, and Zero-G
Cable Autopsy.
