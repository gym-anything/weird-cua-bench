# Capability audit: the 80 new environments

Adjudicated 2026-09-09 from source revision `7d4cbc854c78925ef597424c5d089cab9278ab5e` (PR #50). This covers the 80 environments added after the original 75, not a reassessment of those earlier environments.

## Decisions and scope

All four core capability labels are decided: visual understanding is 2D or 3D; temporal understanding and memory, reasoning and planning, and exploration and interface understanding are Yes or No. Source-review limitations are recorded as evidence notes, not a third label. These are implementation-based judgments of normal screenshot-only solutions, not claims of human or agent calibration.

The review read each generator, visible browser implementation, grader, verifier, solver where present, and control profiles. Each environment received a first pass and a primary review. The first 46 reviewers inherited the parent model; the remaining 34 used explicitly selected Luna/xhigh. This was not a uniform-model experiment. Follow-up source checks resolved competing interpretations; original first-pass files and the pre-adjudication report were preserved separately. Each portable record includes its original first-pass SHA-256.

The [portable audit](../capability_audits/new_environments_2026-09-08.json) is the source of truth for the baseline labels, configuration exceptions, per-capability reasoning, source-file/line evidence, and limitations. Its 800 difficulty-by-interaction configurations are expanded from 80 baseline reviews plus reviewed exceptions; they are not 800 independent full audits.

Real time and difficulty assignment were not re-audited. Live and paused observation schedules do not create different capability labels here. The dedicated temporal audit and empirical calibration remain separate work. The original 75 legacy temporal annotations and frozen temporal pilot remain unchanged.

## Baseline labels

Baseline totals: visual understanding 76 × 2D and 4 × 3D; temporal understanding and memory 37 Yes / 43 No; reasoning and planning 75 Yes / 5 No; exploration and interface understanding 28 Yes / 52 No.

| Public environment name | Baseline | Visual | Temporal understanding and memory | Reasoning and planning | Exploration and interface understanding |
|---|---|---|---|---|---|
| After Hours at the Reliquary | L3 · full | 2D | Yes | Yes | Yes |
| Anthill Front | L3 · full | 2D | Yes | Yes | Yes |
| Apothecary Dead Reckoning | L2 · full | 2D | Yes | Yes | Yes |
| Ballast Lantern | L4 · full | 2D | Yes | Yes | No |
| Bandaged Rose Window | L4 · full | 2D | No | Yes | Yes |
| Branch Repair | L4 · full | 3D | No | Yes | Yes |
| Cell Gatekeeper | L3 · full | 2D | No | Yes | No |
| Chain of Appetite | L4 · simplified | 2D | No | Yes | No |
| Charter of the Nine Cantons | L3 · full | 2D | Yes | Yes | Yes |
| Circle Limit Twist | L3 · full | 2D | No | Yes | Yes |
| Clockbeat Catacomb | L4 · full | 2D | Yes | Yes | No |
| Clockwork Courier Works | L2 · full | 2D | No | Yes | No |
| Cockpit Preflight Checklist | L2 · full | 2D | No | Yes | No |
| Collision Chimes | L4 · full | 2D | Yes | Yes | No |
| The Comparator Engine | L1 · simplified | 2D | No | Yes | No |
| Compass Vault | L3 · full | 2D | No | Yes | No |
| Concertina Courier | L3 · full | 2D | Yes | Yes | No |
| Confectioner's Ink | L4 · full | 2D | No | Yes | No |
| Consent Gauntlet | L3 · full | 2D | Yes | Yes | No |
| Coordinates by Another Name | L2 · full | 2D | No | No | Yes |
| Courtesy Junction | L4 · full | 2D | Yes | Yes | No |
| Crackglaze Crossing | L3 · full | 2D | Yes | Yes | Yes |
| Einstein Loop | L3 · full | 2D | No | Yes | No |
| Elbow Engine | L4 · full | 2D | Yes | Yes | No |
| Ember Anvil | L3 · simplified | 3D | No | Yes | Yes |
| Ember Mosaic | L4 · full | 2D | No | Yes | No |
| Fence the Fox | L3 · simplified | 2D | No | Yes | No |
| Firewatch Fold | L4 · full | 2D | Yes | Yes | Yes |
| Five-Second Rule | L4 · full | 2D | Yes | No | No |
| Flip-Gate Cascade | L4 · simplified | 2D | No | Yes | Yes |
| Fluke Census | L4 · full | 2D | Yes | Yes | Yes |
| Four-Pane Pilgrimage | L4 · full | 2D | No | Yes | Yes |
| Knotless Starmap | L3 · full | 2D | No | Yes | No |
| Lantern Lane | L4 · full | 2D | No | Yes | No |
| The Last Carbon Isles | L2 · full | 2D | No | No | No |
| Last Seats in the Lagoon | L4 · full | 2D | No | Yes | No |
| The Leaning Tower of Panels | L4 · simplified | 2D | Yes | Yes | Yes |
| Letter Rapids | L4 · full | 2D | Yes | No | No |
| Living Scaffold | L2 · full | 2D | No | Yes | Yes |
| The Load-Bearing Idol | L3 · full | 2D | No | Yes | No |
| The Long Way Home | L3 · full | 2D | No | Yes | No |
| Loopmaker's Trial | L3 · full | 2D | No | Yes | No |
| Maskmaker's Dispatch | L2 · full | 2D | No | Yes | No |
| Museum of Lost Gestures | L1 · full | 2D | Yes | No | No |
| Nonogram Denouement | L3 · full | 2D | Yes | Yes | Yes |
| One-Stroke Atelier | L3 · full | 2D | Yes | Yes | No |
| Passphrase Under Siege | L4 · full | 2D | Yes | Yes | No |
| Pendulum Post | L4 · full | 2D | Yes | Yes | No |
| Pocket Animation Studio | L4 · full | 2D | Yes | Yes | No |
| Pocket Locksmith | L4 · full | 3D | No | Yes | Yes |
| Polarity Run | L3 · full | 2D | Yes | Yes | No |
| Prismfall Kiln | L3 · full | 2D | No | Yes | No |
| Punchcutter's Bench | L4 · full | 2D | No | Yes | No |
| Quiet Transfer | L3 · full | 2D | No | Yes | No |
| Rayglass Vault | L4 · full | 2D | No | Yes | Yes |
| Reflected Rival | L4 · full | 2D | Yes | Yes | No |
| Reflow Vitrine | L4 · full | 2D | No | Yes | Yes |
| The Residual Telescope | L4 · full | 2D | No | Yes | No |
| The Restless Piston | L3 · simplified | 2D | Yes | Yes | No |
| Reveal to Identify | L2 · full | 2D | No | Yes | Yes |
| Ribbon Consensus | L4 · simplified | 2D | No | Yes | No |
| Rube's Last Piece | L3 · full | 2D | Yes | Yes | No |
| The Silent Colleague | L4 · full | 2D | Yes | Yes | No |
| Sorting Belt Logic Bench | L4 · full | 2D | No | Yes | No |
| Statute Yard | L3 · full | 2D | No | Yes | No |
| Switchline Heist | L3 · full | 2D | Yes | Yes | No |
| Teach the Stencil | L2 · simplified | 2D | No | Yes | No |
| Terrarium Order of Operations | L3 · full | 2D | Yes | Yes | Yes |
| Threshold Grapevine | L4 · full | 2D | No | Yes | No |
| Tin Duelist | L4 · full | 2D | Yes | Yes | No |
| Tomorrow's Marble | L2 · full | 2D | Yes | Yes | Yes |
| Turtle Forger | L3 · full | 2D | Yes | Yes | No |
| Twin-Groove Seal | L3 · full | 2D | No | Yes | No |
| Two-Lamp Dyeworks | L4 · full | 2D | No | Yes | Yes |
| Two-Season Strand | L4 · full | 2D | Yes | Yes | Yes |
| The Unlabeled Drawer | L4 · full | 2D | No | Yes | Yes |
| Unmarked Landfall | L4 · full | 2D | Yes | Yes | Yes |
| The Unwatched Wing | L4 · full | 3D | Yes | Yes | Yes |
| Valence Caravan | L4 · full | 2D | No | Yes | No |
| Waggle Dispatch | L4 · full | 2D | Yes | Yes | No |

## Configuration exceptions

Only the listed capability changes from its baseline label. All other labels carry through. Both input modes means Full and Simplified.

| Public environment name | Difficulties | Interaction | Capability | Label | Reason |
|---|---|---|---|---|---|
| Anthill Front | L1 | Both | Exploration and interface understanding | No | D1 sets hidden_opening to false and scout_ticks to zero, and starts with the brood ready. Contact and rival queen information are available from the start; outposts and formations appear automatically as their scheduled world events occur. The later CONTACT IN BAND status is ordinary progression, and the disclosed map/minimap plus explicit controls suffice. In full mode the agent may pan to click the rival marker, but its position and HP are already available on the minimap/HUD; no scout reveal or interface experiment is necessary. |
| Apothecary Dead Reckoning | L1, L2, L3, L4, L5 | simplified | Temporal understanding and memory | No | Across every difficulty, Simplified selects jars by click and sets curvature with a stationary notch button. Each candidate can be judged against the persistent current guide from a static screenshot; no earlier candidate must be remembered because it can be selected again. Stirring and recovery are discrete actions, the revealed map accumulates rather than disappearing, and the next guide is directly displayed after route completion. A general solution can repeatedly inspect static candidate paths and commit a match without interpreting motion, sustaining an evolving input, or recalling hidden earlier route state. This exception is provisional with the rest of the temporal audit. All five difficulty profiles retain the same planar path/guide constraints and the need to reveal jar behavior, so no other capability exception is supported. |
| Cell Gatekeeper | L1 | Both | Reasoning and planning | No | Difficulty 1 requires only the named sodium pump, no passive leak, three pump cycles and an ATP burst of exactly three units. Installing that pump, supplying one burst and waiting for READY TO LOCK follows the visible instructions and reaches the generated target for every seed. There is no shared-fuel allocation across species, leak/pump dependency, or necessary correction decision. The unused leak card need not be tried. Both interaction modes retain the same automatic route. |
| Cockpit Preflight Checklist | L1 | Both | Reasoning and planning | No | Difficulty 1 has only the LOW-to-HIGH coupling. LOW is generated away from its visible target and correcting it releases the only sealed target. HIGH has no outgoing lock to release, so being placed directly on its target by LOW needs no detour. The independent dial and visible circuit states can then be matched directly. The prescribed low-then-high progression does not itself establish planning. |
| The Comparator Engine | L2, L3, L4, L5 | Both | Temporal understanding and memory | Yes | Provisional: all four metered profiles clear the comparison lamp on carriage travel and have no displayed comparison history. Same-size specimens cannot be ordered by their drawings. The implemented visible-information solutions reuse earlier learned identity relations or an ordered-prefix search state to select later comparisons and exchanges while conserving readings. The baseline's always-read-current-pair policy is explicitly excluded by the generated allowance. D4 and D5 additionally reject the tested greedy direct-pair-cache strategy, and the provided solution uses binary insertion. These are memory demands, not motion observation or timed action demands; Full uses the same information and only changes the fixed control gesture. |
| The Comparator Engine | L2, L3, L4, L5 | Both | Exploration and interface understanding | Yes | The selected adjacent pair starts NOT WEIGHED and travel does not reveal its relation. A limited WEIGH action reveals the heavier specimen. The agent must choose which previously unknown comparisons to obtain and use those observations to arrange further comparisons and finish the order. This is active information gathering through the comparator; the control meanings themselves are explicit. D2/D3 can reuse direct pair relations, whereas D4/D5 impose a tighter planned-comparison regime. Both interaction modes preserve this requirement. |
| Concertina Courier | L1 | simplified | Temporal understanding and memory | No | A general route can click RIGHT at the initial height of 80 and let the parcel stop at the right room boundary, collecting the two low seals en route. It can then click TALLER and let height reach its cap of 200, followed by LEFT, which collects both elevated seals before reaching the tunnel. Difficulty 1 has continuous floor and clearance 105, so the first traverse fits and the tall return cannot fall into a gap. All intermediate decisions can be made at static endpoints; no hold, precisely timed release, velocity estimate, or remembered transient is required. A 100-seed Python physics replay of these three latched commands passed all cases; that check is implementation evidence, not browser gameplay verification. |
| Consent Gauntlet | L1, L2 | full | Temporal understanding and memory | No | Both profiles have stationary gateways and one drawer without links or reset controls. Direct switch drags connect fixed endpoints; the browser and grader impose movement geometry but no holding duration or coordination with an evolving state. The timer's 180-second submission limit alone does not establish temporal understanding. |
| Consent Gauntlet | L1, L2, L3, L4, L5 | simplified | Temporal understanding and memory | No | Every gateway label is duplicated on a stationary proxy and every answer can be set using fixed NO/YES buttons. At D4/D5, linked sources can be corrected during a pass through the drawers, followed by a pass correcting the other current visible answers. Links are disjoint directed pairs, sources start incorrect, and visible notes identify source and target roles; this solution does not require recalling a disappeared answer, interpreting motion, or sustaining an action. Labeled drawer traversal and reinspection do not independently constitute a nontrivial temporal relationship. |
| Consent Gauntlet | L1 | Both | Reasoning and planning | No | D1 has only one action at each gateway, three affirmative permission statements whose requested answer is uniformly NO, and no reset or linked controls. The agent can directly apply the stated refusal goal to each independent visible switch and use the sole final action. It need not resolve inverted statements, discriminate competing consent outcomes, or choose an order that affects later answers. |
| Ember Anvil | L1, L2 | Both | Exploration and interface understanding | No | These profiles cap every column at two layers and use a one-layer target without socket relief. In the implemented initial projection, a one-layer top retains an exposed upper patch even behind surrounding two-layer columns; the higher tops are also exposed. Thus the current column information and complete flat target can be read from the initial view without an information-revealing orbit or probing action. The visible tool descriptions suffice in both modes. Heights and constrained redistribution still require 3D visual understanding and reasoning/planning. |
| Fence the Fox | L1, L2, L3, L4, L5 | full | Temporal understanding and memory | Yes | Every full-mode placement requires an uninterrupted held pointer gesture. The pointer must remain held over a candidate until the driver arms after a 90 ms timer, stay held while the generated numbered marks are visited, and be released only after returning to center. The duration and continuation of the action are necessary even though the revealed marks are static and explicitly numbered. This is temporal control under the current guideline, and is not observation-only temporal demand. |
| Firewatch Fold | L1 | Both | Temporal understanding and memory | No | With zero seam crossings, one ladder per landing, no walls or decoys, and one route fire, an affordable north-face route to the north-face resident is visible throughout. The agent can leave the initial map selected, move toward each visible upward ladder, clear the single blocking fire and reach the visible resident. Player, stock, facing and cleared fire remain displayed, so hidden-map memory, motion interpretation and timed control can all be avoided. |
| Firewatch Fold | L1 | Both | Reasoning and planning | No | A simpler general visible solution stays on the north face and follows its sole upward ladder on each floor. With no walls, no decoys, a single required fire and exactly one available canister, this route requires no comparison of competing passages or allocation of resources between later choices. Approaching each visible ladder and clearing the one obstruction is direct visual navigation; the optional alternate-face route need not be considered. |
| Firewatch Fold | L1 | Both | Exploration and interface understanding | No | The initial north-face map already contains the resident and a complete affordable ladder route. The eye may reveal an optional alternative, but no reveal or experiment is needed before following the visible north-face route. |
| Fluke Census | L1 | Both | Reasoning and planning | No | D1 has exactly one animal of each species, so each of the two listed species identifies a unique target. Photograph the first listed species when the visible count is zero and the second when it is one. This reduces selection to species recognition and a simple visible progress sequence, without distinguishing competing individuals or planning an identity-coverage strategy. |
| Fluke Census | L1 | Both | Temporal understanding and memory | No | A general D1 procedure can use the current count to request the first, then second, listed species, reading the current lens species without recalling earlier individual identities. After aiming at the chosen animal, retry the shutter at the same coordinates if it has drifted out of the lens: empty shutters do nothing, the periodic animal returns, swept regions cannot admit a different animal, and a successful shutter clears the aim. This removes any need to infer motion, retain earlier selections, or time the action; the visible count alone determines the next target species. |
| The Last Carbon Isles | L3, L4, L5 | Both | Reasoning and planning | Yes | D3 changes the independent home matches into a donor chain: an island must first be cleared and have 106 crews before it can transfer six crews to enable the next island. D4 adds branches, so consuming a donor's reserve on one destination can strand another. D5 also requires choosing between cheaper policies leaving four spare crews and costlier training leaving eight, against three- or seven-crew transfer requirements and an exact shared budget. These are actual prerequisite and allocation dependencies enforced by browser and grader. D1 remains the same No label as the baseline: all three sufficient home policies are already in hand, with no research and additional budget slack. |
| The Last Carbon Isles | L4, L5 | Both | Exploration and interface understanding | Yes | The current research stage exposes only its own destination's offers, but a valid branch/training choice can depend on future destinations' donor options and transfer requirements. The agent must open POLICY ATLAS and inspect its complete offer table before irreversible research choices to obtain that relevant information. The atlas remains accessible, so it need not be treated as an unrecoverable earlier-state memory test. D3 also offers an atlas, but does not require it: each stage has a single cheap chain relay and an unaffordable local academy, so the agent can research each relay and subsequently use the visible hand requirements to follow the donor chain. |
| Last Seats in the Lagoon | L1 | Both | Reasoning and planning | No | Difficulty 1 has one horizontal boat, two available seats, two passengers, route_span 2, and no reefs. With the implemented before-and-after rope-contact candidate construction and exclusion of initial rope cells, the only two passenger candidates are the cells directly above and below x = initial boat x + 2. Both are selected. Moving the boat one cell east therefore boards both at once, and the grader permits immediate certification. This is one spatial alignment with no competing allocation, obstacle-routing decision, or later action dependency; the eight-step stored route is not required for success. |
| Living Scaffold | L1 | Both | Reasoning and planning | No | Every certifiable D1 layout has one automatically selected creature, one fruit immediately ahead on the same row, and its blossom farther along that row. A general screenshot-only strategy is to keep taking the single horizontal direction toward the fruit/blossom for three or four moves and submit. Exhaustive evaluation of all 18 pre-reflection layout combinations found that all 12 layouts accepted by the exact certifier pass this direct strategy; the remaining six are not certifiable and cannot be generated. Reflection only reverses the direction. Thus D1 does not require choosing a support arrangement, a food allocation, an alternate route, or an exit order despite implementing the same underlying physics. |
| Living Scaffold | L1 | Both | Exploration and interface understanding | No | D1's direct path along the visible fruit and matching blossom works across all accepted layouts without discovering the support, growth, or exit-gating rules. There is one creature and it starts selected, so the player can use the visible direction cue or arrow button until it reaches the blossom, then Check garden. Observing food collection and disappearance along this successful route is routine progress rather than a necessary exploratory probe. |
| Museum of Lost Gestures | L1, L2, L3, L4, L5 | simplified | Temporal understanding and memory | No | Each gesture is a discrete labeled button. Hold and dwell start automatic delayed completion, disable the vocabulary while pending, and re-enable it after recognition; the agent need not sustain, release, or time an input. At levels 2-5 the recipe prefix remains visibly listed, opened cards retain title-to-gesture mappings, and the latest gesture is captioned. Following that visible sequence does not require hidden earlier-state recall or nontrivial temporal interpretation. This exception is provisional under the deferred temporal audit. |
| Museum of Lost Gestures | L2, L3, L4, L5 | Both | Reasoning and planning | Yes | Later cases require a particular ordered prefix of already recovered gestures followed by the new case's gesture. The agent must select an available target, map its displayed earlier-exhibit titles to their permanent found gesture labels, and arrange those inputs before the final action. Other recognized gestures interrupt that prefix, so the choice of preparatory actions determines whether the later final gesture succeeds. Independent vocabulary sweeps that solve level 1 do not meet these composed constraints. |
| Nonogram Denouement | L1, L2, L3, L4, L5 | simplified | Exploration and interface understanding | No | The simplified interface replaces undisclosed left/right cell marking and slug dragging with a selected-cell display, labeled INK/CLEAR/RESET buttons, and labeled stationary direction buttons. Clues remain visible while marking, and pressing DEVELOP automatically supplies the next question and proof-light; these are explicit controls and a routine stage transition, with no additional hidden information that needs probing. All difficulties use these same interaction handlers. The visual, temporal, and reasoning/planning labels otherwise remain the same across all profiles. |
| One-Stroke Atelier | L1, L2, L3, L4, L5 | simplified | Temporal understanding and memory | No | BEGIN starts a logical proxy stroke; each independent stage click adds a straight segment, and END finishes it. No physical hold, timed release, motion interpretation, or vanished task information is required. All geometry changes occur on the click-driven command progression. The target, selections, and ink remain visible; at D4/D5 the relevant spent bars also remain visibly present. A general solution can therefore plan each segment from the current static state. Other labels remain 2D / reasoning and planning Yes / exploration and interface understanding No across all ten difficulty-interaction configurations. |
| Pocket Locksmith | L1 | Both | Exploration and interface understanding | No | Difficulty 1 has one rotatable bond and sets handle_occlusion to false. All full-mode handles are therefore available without camera discovery, while simplified mode exposes the single torsion through a labelled button; the initial rendered sites, obstacles, and key are available without an interface-reveal step. |
| The Restless Piston | L1, L2 | Both | Temporal understanding and memory | No | The lower profiles combine coarse state adjustments, lower pressure noise and wider goal tolerances, supporting current-frame signed corrections. Waiting for automatic settling after the final correction does not by itself require temporal understanding. |
| Rube's Last Piece | L1 | Both | Temporal understanding and memory | No | Difficulty 1 has one link, no decoy, zero crosswind, a forgiving receiver, drawn angle stops, and exact failure feedback. A screenshot-only solution can use the static station/receiver geometry and fixed angle stops, run the automatic single flight, and use the resulting static direction or energy message if correction is needed; it does not need to interpret a changing trajectory or remember an earlier rollout. The simplified and full modes change only how the same deflector is placed and rotated. |
| Rube's Last Piece | L2 | Both | Temporal understanding and memory | No | D2 retains the exact static miss-direction or impact-energy diagnosis available at D1. The agent can run and wait, read the failed LINK and diagnosis, rewind, and change its material or angle. Mild wind and two serial automatic flights do not themselves force interpretation of motion when that feedback supports repair. |
| Teach the Stencil | L1 | Both | Reasoning and planning | No | The paper/leaf/petal feature boxes are strictly separated under the classifier metric: maximum within-class squared distance 0.026963 is below the minimum cross-class bound 0.186009, including rounding. Correctly identifying and marking each material therefore guarantees the full mask without representative-sample planning or corrective inference. Full mode can use a compact retraced stroke within a correct material; the path-length condition is spatial and does not require distinct pixels or endpoint displacement. |
| The Unwatched Wing | L1 | Both | Temporal understanding and memory | No | D1 removes all marked probe handoffs and ambient lights. A visible route can observe a current W plinth, release it with the lamp off, open the empty viewer to see corridor and plinth geometry without re-observing the exhibit, move to the next ordered W plinth, and re-establish observation. The final darkness condition can be chosen from the current pedestal and equipment state. This provisional No does not rely on navigating while the entire screen is black. |

## Runtime integration

- Dashboard catalog filters use the canonical baseline labels. The environment detail panel uses the selected difficulty and interaction mode and labels that scope explicitly.
- The existing real-time annotations are preserved. Newly audited environments without a prior real-time assessment display “Not reviewed”; no real-time value is inferred from capability labels or clock support.
- Canonical task metadata records baseline capabilities and the audit reference. Controlled-task materialization resolves the selected profile so its capability list does not silently retain baseline labels.
- This update changes annotation data and its consumers only. It does not change generated worlds, task instructions, input controls, grading, verification, step budgets, or quality status.

## Implementation validation

On 2026-09-09, the focused capability, task-metadata, legacy-temporal, dashboard,
and updated metadata-assertion tests passed: 50 passed, 1 skipped. The static-site
export included all 155 environments. The required static-browser smoke rendered
all 155 environments and executed all 155 Pyodide graders without failures. A
separate headless dashboard smoke checked the 800-profile schema, baseline filters,
and selected difficulty/interaction label changes; its rendered panels and filter
results were visually inspected. These checks validate annotation integration,
not empirical capability requirements or puzzle quality.

The full `python -m pytest tests -q` run was attempted but stopped after repeated
evaluation-runtime compatibility failures. The installed Gym-Anything
`ActionGateway.__init__` does not accept the `temporal_mode` argument required by
this branch. The evaluation adapter and its failing tests are unchanged by this
annotation update. The full suite is therefore not claimed to pass.
