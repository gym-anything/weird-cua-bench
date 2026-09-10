# Round-four task fixes and solution evidence

This batch adds the 35 environments listed in `environments.json`. The four
paused round-five environments are not part of this release.

## Task fixes

- Teach the Stencil accepts an accurate mask without requiring unnecessary
  correction history. The reference solver no longer deliberately starts with
  bad examples. Accuracy, coverage, input-surface and transcript checks remain.
- Pocket Animation Studio treats a line's endpoints as unordered in both the
  grader and the visible comparison. Incorrect geometry or width still fails.
- Twin-Groove Seal starts with its declared 400-unit link length. Tests check
  generated reference paths across all five difficulties and multiple seeds.
- Tomorrow's Marble settles each drag action once, including cancelled and
  rejected drops. Removing a piece invalidates the previous simulation result
  and clears its visible completion label.
- Collision Chimes shows multiple wall hits on the same rail during one beat.
- Last Carbon Isles displays rejected-action feedback in its visible footer.

The consistency changes complete the 20-condition splits, align baseline labels
and instructions with their configured profiles, use 1920x1080 observations,
remove task-level forced-live overrides, restore Loopmaker asset provenance and
readiness metadata, and exclude new tasks from the frozen historical 75-task
sample. Tests generate controlled fixtures from the public materializer rather
than depending on ignored local task directories.

## Recordings

`solution_videos/manifest.json` indexes 35 MP4/WebM pairs recorded after these
fixes. Each recording used a fresh isolated headless Chromium session and a
loopback task server at 1920x1080. The server grader, direct grader and exported
verifier all passed for each recorded baseline. No browser console errors were
recorded. Source hashes were identical before and after every run.

The reference solvers read privileged task state to choose actions and then
operate the browser controls. Some use the framework's clock controls; those
calls are preserved in each source manifest. These are implementation witnesses,
not screenshot-only model evaluations, human validation or proof of difficulty.
Each film covers its baseline configuration, not all 20 conditions.

Exports and original recording reports are included with file hashes. The raw
construction records and superseded recordings remain in ignored local storage.
Capability annotation and human calibration remain separate, deferred work.
Task quality status has not been promoted to bypass those requirements.

## Reproduce

From the repository root, with Playwright Chromium and FFmpeg installed:

```bash
python weird_captcha_gym/evidence/round_four_v2/reproduce.py batch --seed fresh-recording-name
python -m pytest tests/test_round_four_publication.py tests/test_round_four_browser_regressions.py -q
```

Use a new seed label to preserve previous recordings. The batch runs four
headless browser workers by default; `ROUND4_WORKERS` changes that count.
It does not launch model agents or VMs and returns nonzero if a recording fails.
