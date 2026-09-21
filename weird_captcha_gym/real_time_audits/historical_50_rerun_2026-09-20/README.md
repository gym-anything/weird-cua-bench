# Historical 50: fresh real-time audit

User-requested repeat of the prior per-game audit for the other 50 historically skipped environments in the selected 100. All five difficulties and both interaction modes are included: 50 fresh game-level reviews and 500 configuration judgments. Forced-Perspective Moving Day is excluded; its completed fresh report is hash-pinned in the manifest.

## Protocol

The mathematical definition, 50% pre-run threshold, and per-game prompt are unchanged. Each game receives one fresh Luna/max process, with four concurrent sequential queues, a 2,700-second outer deadline per game, and no automatic outer retries. The source snapshot is a Git archive at `aa085c8caa6575cde1353272b94118b7903a62a3`; every archived file was verified against that revision. Reviewers do not receive old labels, other reviews, or the parent conversation. The manifest is parent-only.

First-pass reports live in `first_pass/`, process receipts in `provenance/`, and ignored execution logs in `outputs/`. Monitoring stays in the active chat. Failed processes, unresolved judgments, structural report flags, and label disagreements remain separate. This batch does not modify puzzles, definitions, historical audit reports, or catalog labels.

## Launch

Run each queue once from the repository root:

```bash
python weird_captcha_gym/difficulty_audits/remaining_39_2026-09-10/run_queue.py --audit-dir weird_captcha_gym/real_time_audits/historical_50_rerun_2026-09-20 1 5 9 13 17 21 25 29 33 37 41 45 49
python weird_captcha_gym/difficulty_audits/remaining_39_2026-09-10/run_queue.py --audit-dir weird_captcha_gym/real_time_audits/historical_50_rerun_2026-09-20 2 6 10 14 18 22 26 30 34 38 42 46 50
python weird_captcha_gym/difficulty_audits/remaining_39_2026-09-10/run_queue.py --audit-dir weird_captcha_gym/real_time_audits/historical_50_rerun_2026-09-20 3 7 11 15 19 23 27 31 35 39 43 47
python weird_captcha_gym/difficulty_audits/remaining_39_2026-09-10/run_queue.py --audit-dir weird_captcha_gym/real_time_audits/historical_50_rerun_2026-09-20 4 8 12 16 20 24 28 32 36 40 44 48
```

## Validation

Setup checks require 50 unique environments, exactly 500 unique difficulty/interaction configurations matching the historical selection, no overlap with Forced-Perspective Moving Day, disjoint queue slots covering every game once, unchanged prompt and definition hashes, and preserved historical/completed-report hashes. On completion, each report is checked with the existing per-configuration validator plus game identity, coverage, and receipt hashes. Validation does not rewrite first-pass labels.

Setup validation passed. All 2,231 archived source files match their recorded Git blobs. The existing source-review launcher and grouped-audit tests pass: 39 passed. All four sequential queues were launched, beginning with game indices 1–4.

## Attempt results

All four queues have finished. Of 50 first attempts, 25 completed and 25 failed on the reviewer usage limit. Completed reviews contain 85 Yes and 165 No judgments, with 21 disagreements across six games. Ten configuration entries have missing identity fields and remain flagged. No retries or label adjudications were applied.

See [report.md](report.md) for the per-game summary and [results.json](results.json) for hash-bound records, flags, and failure details. The audit is incomplete until the 25 failed games receive separately authorized retries.
