# Gemini 3.5 Flash random-15 visible-UI-only audit

Experiment: `gemini-3.5-flash-random15-ui-only-20260715T063148Z`
UT Lab run: `R2`
Started: `2026-07-15T06:40:11.223428+00:00`
Finished: `2026-07-15T11:05:24.855965+00:00`

## Headline result

- All 15 frozen tasks launched in their original random draw order.
- Raw runner outcome: **0 passed, 9 verifier failures, 6 model/provider errors**.
- Raw pass rate among tasks that reached a verifier outcome: **0/9 (0%)**.
- Five provider exclusions were explicit Gemini `BlockedReason.SAFETY` responses. One was a Gemini `500 INTERNAL` response.
- Post-run QA found one benchmark presentation defect in task 14. Excluding that invalid task leaves **0/8 (0%)** across valid verifier-bearing outcomes. This audit does not retroactively convert the task to an official pass.

## Task outcomes

| # | Task | Executed actions | Raw outcome | Audit classification |
|---:|---|---:|---|---|
| 1 | Wrong Number | 100 | failed | valid verifier failure |
| 2 | Three-Camera Claw Machine | 100 | failed | valid verifier failure; two view-only browser zoom-outs |
| 3 | Polyrhythm Customs | 9 | model_api_error | excluded: explicit Gemini safety block |
| 4 | Shadow Crime Lab | 100 | failed | valid verifier failure; three view-only browser zoom-outs |
| 5 | Four-Tab Robot Handshake | 66 | model_api_error | excluded: Gemini HTTP 500; task-created tabs were allowed |
| 6 | Blind Dice Courier | 100 | failed | valid verifier failure |
| 7 | Blind Corridor Oscilloscope | 0 | model_api_error | excluded: explicit Gemini safety block on first response |
| 8 | Impossible Ecology | 0 | model_api_error | excluded: explicit Gemini safety block on first response |
| 9 | Insider Trading CAPTCHA | 58 | model_api_error | excluded: explicit Gemini safety block; unrelated-tab deviation at steps 54–55 |
| 10 | Marionette Checkpoint | 100 | failed | valid verifier failure |
| 11 | Motion-Only Ghost Jigsaw | 0 | model_api_error | excluded: explicit Gemini safety block on first response |
| 12 | Parallax Orchard | 100 | failed | valid verifier failure |
| 13 | Hologram Silhouette Foundry | 85 | failed | valid verifier failure after an in-task submission/near miss |
| 14 | Isometric Voxel Extraction Mine | 14 | failed | benchmark-invalid at 1280×720; see below |
| 15 | Scroll-Cage Checkbox | 100 | failed | valid verifier failure |

## Visible-UI policy audit

The mandatory policy was injected into both the Gemini system instruction and the user task description. Across **932 executed action calls**, the logs contain:

- no code, scripts, Python, terminal, or shell use;
- no Developer Tools, console, debugger, inspector, network panel, DOM/source/page-state inspection, or implementation inspection;
- no address-bar use, URL/query editing, reload, or navigation action;
- no external-application action;
- allowed task-created tab use in Four-Tab Robot Handshake;
- five view-only `Ctrl+-` browser zoom actions (two in task 2, three in task 4), which exposed no hidden state;
- one actual policy deviation in task 9: the model clicked the pre-existing Firefox Privacy Notice tab at step 54 and returned to the task at step 55. It obtained no task information there. Task 9 was independently excluded because Gemini later returned an explicit safety block.

The strict instruction materially prevented the pilot's prior DevTools/terminal strategy drift. Several trajectories explicitly considered and rejected those routes in their reasoning; only executed actions, not reasoning text, were used for this audit.

The durable repository rule now adds an explicit sentence for future runs: **“Do not switch to or interact with any pre-existing, unrelated, blank, browser-settings, or non-task tab.”** Task-created tabs opened by visible task controls remain allowed. The completed R2 manifest remains unchanged.

## Task 14 benchmark defect

The final screenshot for Isometric Voxel Extraction Mine visibly shows:

- `4/4` targets extracted;
- pick durability `6/10`;
- the yellow fragile support still present;
- all four camera viewpoints visited in the trajectory.

The model then attempted to scroll for a submission control, but the page did not scroll. At the authoritative AVF resolution of 1280×720, browser chrome leaves less than the mechanic's CSS `min-height: 620px`. The page sets `body[data-mechanic="voxel-extraction-mine"] { overflow: hidden }`, placing the footer's `EXIT MINE` button below the visible viewport and making it unreachable through the permitted visible task controls. The task description also does not mention the required exit action.

Because the model called `mark_done` without the inaccessible `EXIT MINE` click, no mechanic payload was submitted and the verifier returned the generic `mechanic mismatch`. The raw result remains unchanged for reproducibility, but this task should be excluded from scientific scoring and rerun only after a separately reviewed UI fix.

## Evidence

- Locked manifest: `manifest.json`
- Authoritative machine-readable outcomes: `runtime/summary.json`
- Per-task streamed transcripts: `runtime/*.log`
- Gym run artifacts: `all_runs/gemini-3.5-flash-random15-ui-only-20260715T063148Z/`
- Task 14 final screenshot: `all_runs/gemini-3.5-flash-random15-ui-only-20260715T063148Z/gemini-3.5-flash/minecraft_block_grid_seed_0001/run_0/observation_13.png`
