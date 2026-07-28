# Gemini 3.5 Flash random-15 Full-HD rerun audit

## Registered primary run

- UT Lab: `R2` in set `s-k5zxfg`
- Experiment: `gemini-3.5-flash-random15-ui-only-fhd-request-retry-20260715T201206Z`
- Started: `2026-07-15T20:20:32.044344+00:00`
- Finished: `2026-07-16T02:09:50.262472+00:00`
- Contract: `manifest.json`
- Runtime summary: `runtime/summary.json`

The primary run is immutable. Its raw registered counts are:

| Outcome | Count |
|---|---:|
| Verifier failure | 11 |
| Verifier pass | 1 |
| Model API error (explicit safety block) | 2 |
| Infrastructure error | 1 |

| # | Task | Primary outcome |
|---:|---|---|
| 1 | Wrong Number | failed |
| 2 | Three-Camera Claw Machine | failed |
| 3 | Polyrhythm Customs | failed |
| 4 | Shadow Crime Lab | failed |
| 5 | Four-Tab Robot Handshake | model API error: explicit safety block at turn 55 |
| 6 | Blind Dice Courier | infrastructure error: AVF SSH reset at turn 22 |
| 7 | Blind Corridor Oscilloscope | failed |
| 8 | Impossible Ecology | failed |
| 9 | Insider Trading CAPTCHA | failed |
| 10 | Marionette Checkpoint | failed |
| 11 | Motion-Only Ghost Jigsaw | failed |
| 12 | Parallax Orchard | failed |
| 13 | Hologram Silhouette Foundry | failed |
| 14 | Isometric Voxel Extraction Mine | passed |
| 15 | Scroll-Cage Checkbox | model API error: explicit safety block at turn 0 |

## Infrastructure replacement

Blind Dice Courier's primary trajectory had no verifier verdict because the AVF
VM reset its SSH connection during action injection. A separate, predeclared
replacement was therefore run without modifying the primary record:

- UT Lab: `R3` in set `s-k5zxfg`
- Experiment: `gemini-3.5-flash-blind-dice-infra-replacement-20260716T021634Z`
- Contract: `../gemini_3_5_flash_blind_dice_infra_replacement_20260716/manifest.json`
- Finished: `2026-07-16T02:47:21.551066+00:00`
- Result: verifier failure after all 100 turns
- Provider retries: none
- Model API errors: none
- Infrastructure errors: none

Using the replacement only for the infrastructure-invalid primary cell gives 13
valid verifier outcomes: 1 pass and 12 failures. The two explicit safety blocks
remain separately reported model API errors. The valid-outcome pass rate is
`1/13` (7.69%); the registered primary run itself is not rewritten to this
derived view.

## Retry evidence

Hologram Silhouette Foundry received a Google `504 DEADLINE_EXCEEDED` at logical
turn 20. The agent recorded `MODEL_API_RETRY` attempt `1/5`, waited 1.2537
seconds, and then recorded a successful click at the same logical turn. The task
continued normally and produced a verifier verdict. No nested SDK retries were
enabled.

Every request used a 180,000 ms deadline. The sole retry layer allowed exactly
five total attempts for HTTP 408/429/500/502/503/504 and all HTTPX transport
errors. Explicit safety, authentication, authorization, and invalid-request
errors were not retried.

## Resolution and policy audit

- All 75 environment specs declare one `1920x1080` RGB screen.
- All 1,265 saved screenshots across the 15 primary trajectories and the one
  infrastructure replacement are exactly `1920x1080`.
- The patched Gemini agent SHA-256 matches both manifests:
  `01516147ee4d85ad79a97fcc18f0b9009215dce2af57a022db5227e8a28143e8a`.
- All 16 trajectories used only the declared visible computer-use action set.
  No navigation, Developer Tools shortcut, terminal, code, source/DOM access,
  address-bar edit, external application, or unsupported action was observed.
- No benchmark task file or verifier was changed for this rerun. The benchmark
  difficulty and 100-turn limit were unchanged.

## Verification

- Weird CUA Bench: `49 passed, 1 skipped`
- Gemini agent unit tests in the actual evaluation virtual environment:
  `32 passed`
- Frozen manifest/dry run: 15 primary commands in original draw order; one
  separately labeled replacement command
- Gym Anything's broader suite excluding its absent `modal_native` test module:
  `249 passed, 22 skipped, 4 unrelated runner-registry failures`. The full suite
  cannot collect on this checkout because `tests/test_modal_native_runner.py`
  imports a module not present on the branch; none of those failures touch the
  Gemini agent or AVF path used here.
