# GPT-5.6 Luna real-time classification: all 750 configurations

Status: historical first-pass audit. Its recorded labels and comparison matrix
have not been rewritten. The authoritative matrix was updated on 2026-08-17
using a 50% pre-run-solution threshold: Wind-Tunnel Seed Courier D1-D2 and all
Dual-Projection Sculpture Rig configurations are now Not real-time. See
`../all_750.md`.

## Protocol

- Population: 750 configurations (75 environments x 5 difficulties x 2 interaction modes).
- One fresh GPT-5.6 Luna context per configuration, high reasoning effort.
- Every reviewer received the same frozen prompt and settled mathematical definition.
- No reviewer saw the prior classification matrix or another reviewer's answer.
- No corrective follow-up occurred before a first-pass result was recorded.
- The prior matrix is used only for the independent comparison below; first-pass labels are not changed.

## Result

- Luna: 241 yes, 509 no.
- Prior matrix: 267 yes, 483 no.
- First-pass agreement: 706/750 (94.13%).
- First-pass disagreement: 44/750 (5.87%).
- Direction: 35 prior-yes/Luna-no; 9 prior-no/Luna-yes.

No disagreement was corrected, adjudicated, or converted into agreement.

## Disagreements by difficulty and interaction

| Group | Count |
|---|---:|
| D1 | 16 |
| D2 | 9 |
| D3 | 5 |
| D4 | 7 |
| D5 | 7 |
| full | 25 |
| simplified | 19 |

## Disagreements by environment

| Environment | Count |
|---|---:|
| Parallel Grillmaster | 6 |
| Forced-Perspective Moving Day | 5 |
| LIDAR Blacksite | 5 |
| Temporal Memory / First-Change Evidence | 5 |
| The Photograph Eats the Room | 4 |
| Thirty-Year Time Wheel | 4 |
| Occlusion Shell Swindle | 3 |
| Polarized Palimpsest | 3 |
| Specular Lighthouse Relay | 2 |
| Wrong Number | 2 |
| Impossible Ecology | 1 |
| Scroll-Cage Checkbox | 1 |
| Slot-Reel Character Capture | 1 |
| Trajectory Catcher | 1 |
| Wizard Interception Observatory | 1 |

## All 44 first-pass disagreements

| # | Environment | Difficulty | Interaction | Prior | Luna | Clauses (i/ii/iii) |
|---:|---|---|---|---|---|---|
| 111 | Polarized Palimpsest | D1 | full | no | yes | T/T/T |
| 113 | Polarized Palimpsest | D2 | full | no | yes | T/T/T |
| 114 | Polarized Palimpsest | D2 | simplified | no | yes | T/T/T |
| 211 | Forced-Perspective Moving Day | D1 | full | yes | no | T/T/F |
| 212 | Forced-Perspective Moving Day | D1 | simplified | yes | no | F/F/F |
| 213 | Forced-Perspective Moving Day | D2 | full | yes | no | F/T/F |
| 215 | Forced-Perspective Moving Day | D3 | full | yes | no | F/F/F |
| 218 | Forced-Perspective Moving Day | D4 | simplified | yes | no | T/T/F |
| 252 | Impossible Ecology | D1 | simplified | yes | no | T/F/T |
| 301 | LIDAR Blacksite | D1 | full | yes | no | T/T/F |
| 302 | LIDAR Blacksite | D1 | simplified | yes | no | T/T/F |
| 304 | LIDAR Blacksite | D2 | simplified | yes | no | T/T/F |
| 305 | LIDAR Blacksite | D3 | full | yes | no | T/T/F |
| 310 | LIDAR Blacksite | D5 | simplified | yes | no | T/F/F |
| 378 | Scroll-Cage Checkbox | D4 | simplified | yes | no | T/T/F |
| 382 | Occlusion Shell Swindle | D1 | simplified | yes | no | F/T/T |
| 384 | Occlusion Shell Swindle | D2 | simplified | yes | no | F/T/F |
| 386 | Occlusion Shell Swindle | D3 | simplified | yes | no | F/T/T |
| 401 | Parallel Grillmaster | D1 | full | yes | no | T/F/F |
| 402 | Parallel Grillmaster | D1 | simplified | yes | no | T/T/F |
| 403 | Parallel Grillmaster | D2 | full | yes | no | T/T/F |
| 405 | Parallel Grillmaster | D3 | full | yes | no | T/T/F |
| 408 | Parallel Grillmaster | D4 | simplified | yes | no | T/T/F |
| 410 | Parallel Grillmaster | D5 | simplified | yes | no | T/T/F |
| 423 | The Photograph Eats the Room | D2 | full | yes | no | T/T/F |
| 428 | The Photograph Eats the Room | D4 | simplified | yes | no | T/T/F |
| 429 | The Photograph Eats the Room | D5 | full | yes | no | T/T/F |
| 430 | The Photograph Eats the Room | D5 | simplified | yes | no | T/T/F |
| 597 | Slot-Reel Character Capture | D4 | full | yes | no | T/F/T |
| 601 | Specular Lighthouse Relay | D1 | full | no | yes | T/T/T |
| 602 | Specular Lighthouse Relay | D1 | simplified | no | yes | T/T/T |
| 621 | Temporal Memory / First-Change Evidence | D1 | full | yes | no | T/T/F |
| 623 | Temporal Memory / First-Change Evidence | D2 | full | yes | no | F/F/F |
| 625 | Temporal Memory / First-Change Evidence | D3 | full | yes | no | T/T/F |
| 627 | Temporal Memory / First-Change Evidence | D4 | full | yes | no | T/T/F |
| 629 | Temporal Memory / First-Change Evidence | D5 | full | yes | no | T/T/F |
| 631 | Thirty-Year Time Wheel | D1 | full | no | yes | T/T/T |
| 633 | Thirty-Year Time Wheel | D2 | full | no | yes | T/T/T |
| 637 | Thirty-Year Time Wheel | D4 | full | no | yes | T/T/T |
| 639 | Thirty-Year Time Wheel | D5 | full | no | yes | T/T/T |
| 692 | Trajectory Catcher | D1 | simplified | yes | no | T/T/F |
| 719 | Wizard Interception Observatory | D5 | full | yes | no | T/F/T |
| 731 | Wrong Number | D1 | full | yes | no | T/T/F |
| 732 | Wrong Number | D1 | simplified | yes | no | T/T/F |

## Protocol error

Cases 171-180 were initially assigned with the wrong environment name. Those ten answers were invalid, excluded, and rerun in fresh Luna contexts with the correct Fake Desktop / Automation Inversion configuration. Only the replacement first-pass answers are counted.

## Artifacts

- `manifest.json`: frozen population and prompt/definition hashes.
- `ledger.json`: recorded first-pass labels, clause booleans, timing witnesses, uncertainties, and baseline comparison.
- `results.json`: complete joined 750-row matrix plus summary counts.
- `protocol_errors.json`: excluded invalid assignments and replacement disposition.

The ledger stores structured first-pass decisions rather than the reviewers' complete prose responses.
