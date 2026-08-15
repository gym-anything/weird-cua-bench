# GPT-5.6 Luna real-time pilot

The frozen sample contains 25 uniformly sampled configurations from the 750-configuration population. One independent GPT-5.6 Luna reviewer at high reasoning effort reviewed each configuration from complete source under the same frozen prompt. The primary reviewer recorded all 25 labels before receiving the remaining Luna responses. No reviewer received a correction or follow-up prompt before scoring.

## First-pass result

- Agreement: 24/25 (96%)
- Luna labels: 10 yes, 15 no, 0 unresolved
- Primary pre-review labels: 9 yes, 16 no, 0 unresolved
- Disagreement: case 23 only

| # | Environment | Configuration | Luna first pass | Primary pre-review | Agreement | Post-review label |
|---:|---|---|---|---|---|---|
| 1 | Recursive Dollhouse Smuggling | D1 full | No | No | Yes | No |
| 2 | Live Control-Flow Wiring Lab | D1 full | No | No | Yes | No |
| 3 | Ribbon Switchboard | D2 simplified | No | No | Yes | No |
| 4 | Portal Freight: Oversized Parcel | D4 simplified | No | No | Yes | No |
| 5 | Consequences Boss | D2 full | No | No | Yes | No |
| 6 | Gyroscopic Tilt Board | D3 simplified | Yes | Yes | Yes | Yes |
| 7 | Five-System Verification Reactor | D4 full | Yes | Yes | Yes | Yes |
| 8 | Slime Commute | D2 simplified | Yes | Yes | Yes | Yes |
| 9 | Orbital Docking Customs | D3 full | No | No | Yes | No |
| 10 | Robot Art Critic | D5 simplified | No | No | Yes | No |
| 11 | Portal Freight: Oversized Parcel | D1 simplified | No | No | Yes | No |
| 12 | Motion-Only Ghost Jigsaw | D1 full | No | No | Yes | No |
| 13 | Input-Lag Forklift | D3 full | No | No | Yes | No |
| 14 | Trajectory Catcher | D4 full | Yes | Yes | Yes | Yes |
| 15 | Wizard Interception Observatory | D3 full | Yes | Yes | Yes | Yes |
| 16 | Flat-Pack Compliance Test | D3 simplified | No | No | Yes | No |
| 17 | Cursor-Controlled Constellation Hunt | D3 simplified | No | No | Yes | No |
| 18 | Gyroscopic Tilt Board | D1 simplified | Yes | Yes | Yes | Yes |
| 19 | Forced-Perspective Moving Day | D3 simplified | Yes | Yes | Yes | Yes |
| 20 | Wind-Tunnel Seed Courier | D4 simplified | Yes | Yes | Yes | Yes |
| 21 | Cursor-Controlled Constellation Hunt | D3 full | No | No | Yes | No |
| 22 | Isometric Voxel Extraction Mine | D2 simplified | No | No | Yes | No |
| 23 | Thirty-Year Time Wheel | D2 full | Yes | No | **No** | Yes |
| 24 | Tomographic Baggage Surgery | D4 full | No | No | Yes | No |
| 25 | Scroll-Cage Checkbox | D3 full | Yes | Yes | Yes | Yes |

## Case 23 review

The Luna label is supported by the frozen definition and implementation; the primary pre-review label was wrong.

In full mode, a sufficiently fast drag starts autonomous inertial coast. The interface visibly reports the current date, coast direction, and remaining detents while BRAKE remains available. An always-brake policy is safe, but it is not always delayed-optimal under `A*_Delta`: if coast is usefully moving toward the target, allowing it to continue can reduce continuation time. Conversely, when coast is moving away from the target, each autonomous 95 ms detent makes a later brake save less momentum and leaves more corrective work. A bounded 600 ms window exposes the state needed to choose; the loss comes from the changed calendar state rather than from elapsed time alone.

The post-review pilot labels are therefore 10 yes and 15 no. The raw first-pass agreement remains 24/25.

## Reproducibility files

- `prompt.md`: exact prompt template and frozen mathematical definition
- `manifest.json`: population, sampling method, seed, model, and the 25 configurations
- `manual_review.json`: primary labels frozen before the Luna responses
- `results.json`: first-pass comparison and post-review decision

The directory name records the frozen sampling run date. The reviews completed on 2026-08-14.
