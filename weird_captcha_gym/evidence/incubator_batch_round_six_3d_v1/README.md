# Fifteen 3D environments

`environments.json` identifies this batch. The paused round-five batch is not
included. These tasks extend the 155-environment base to 170 environments.

## Integration fixes

- Standardize observation resolution to 1920x1080.
- Register each environment with the benchmark inventory, timing settings and
  configuration tests. Exclude it from the frozen historical 75-task sample.
- Publish ten difficulty/interaction task variants per environment. The evaluator
  independently chooses live or paused execution, giving twenty evaluation
  conditions without duplicate paused task directories.
- Repair Cloudpost Circuit's workspace paths and task hooks, and restore the
  shared install/setup hooks for Polycube Parcel, Pearl Lattice and Lantern Loft.
- Stop Cloudpost's reference solver when the displayed contact count confirms
  collection, rather than waiting for its approximate flight estimate to agree.
- Materialize test fixtures in temporary directories so tests also work in a
  fresh checkout without ignored generated tasks.

No core runner, gateway, VM code, shared runtime logic, task physics or grading
thresholds were changed for this integration. The Pages workflow changes only
publication counts.

## Solution evidence

`solution_videos/manifest.json` indexes fifteen MP4/WebM pairs, exported verifier
inputs and the original recording reports, with SHA-256 hashes. Each baseline
was solved in a fresh headless Chromium session against a loopback task server
at 1920x1080. Server grading, direct grading and the exported task verifier
passed for all fifteen. The recordings had no browser console errors, no clock
control calls, and identical source hashes before and after each run.

The reference solvers read privileged state and execute browser mouse/keyboard
actions. These recordings demonstrate implemented solutions, not screenshot-only
model performance, human validation or coverage of all twenty conditions.
Human calibration and capability annotation remain separate work. No quality
status was promoted to bypass human validation. Downsky Causeway and Rising
Causeway retain their final creator-only round history without a new model audit.

The initial and final screenshots are included for the existing dashboard's
evidence discovery. Raw construction logs and superseded recordings remain in
ignored local storage.

## Publication validation

The integration and task-specific tests passed in a clean staged snapshot:
114 tests, with no failures or skips. The static export for this cohort contains
660 challenges (four seeds for each baseline and each controlled profile).
All fifteen dashboard videos played, all 150 difficulty/interaction interfaces
loaded with the requested settings, and all fifteen exported reference solutions
passed the browser's WebAssembly grader. No page errors were recorded.
`browser-validation.json` retains those results.

The strict metadata audit still reports the deferred human/VNC validation status
for each task. It does not certify these as human-reviewed environments.

## Reproduce

With Playwright Chromium and FFmpeg installed, from a clean checkout:

```bash
python -m pytest tests/test_round_six_publication.py tests/test_cloudpost_circuit.py -q
```

The existing recorder supports this batch without changes to shared tooling:

```bash
python weird_captcha_gym/evidence/round_four_v2/reproduce.py one \
  --mechanic cloudpost_circuit --seed fresh-round-six-recording
```

Use any mechanic from `environments.json` (without `_env`) and a fresh seed label.
`ROUND4_OUTPUT` selects the output directory. The recorder launches a headless
browser and loopback server, not a VM or model evaluation.
