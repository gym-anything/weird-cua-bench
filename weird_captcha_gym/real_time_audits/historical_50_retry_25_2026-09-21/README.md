# Historical 50: retry the 25 usage-limit failures

This is the user-authorized second overall attempt for exactly 25 failed games / 250 configurations from `historical_50_rerun_2026-09-20`. Parent game and configuration indices are retained. The original 25 completed game reviews, the failed Dead Man's Switch artifact, all original receipts and logs, and parent summaries remain untouched and hash-pinned in `preserved_parent_files.json`.

## Protocol

The prompt is byte-identical to the parent prompt. Reviewer: `gpt-5.6-luna`, reasoning `max`; one fresh context per game, all ten configurations together. The same verified source snapshot is reused. Four concurrent reviewers maximum, 2,700-second outer deadline per game, no automatic further retries. The existing launcher retains its built-in provider transport policy. Receipts use local process attempt 1 in this separate directory; `manifest.json` records overall attempt 2 and the parent attempt links.

The first assigned game, Dead Man's Switch (13), starts alone as the actual retry, not an extra test request. If it immediately fails on usage/authentication, the other 24 remain pending. Once provider activity is established, the first queue waits for game 13 before taking its next game; the other three queues run normally.

No new adjudications, prompt corrections, source changes, or historical/catalog label updates are authorized by this retry. The parent's Rotating On-Screen Keyboard identity-field flags remain visible and are outside the retry set.

## Launch

The first attempt is started once:

```bash
python weird_captcha_gym/difficulty_audits/remaining_39_2026-09-10/run_reviewer.py 13 --audit-dir weird_captcha_gym/real_time_audits/historical_50_retry_25_2026-09-21
```

Only after successful provider startup, start each slot once:

```bash
python weird_captcha_gym/difficulty_audits/remaining_39_2026-09-10/run_queue.py --audit-dir weird_captcha_gym/real_time_audits/historical_50_retry_25_2026-09-21 --wait-for-case 13 23 28 33 39 44 49
python weird_captcha_gym/difficulty_audits/remaining_39_2026-09-10/run_queue.py --audit-dir weird_captcha_gym/real_time_audits/historical_50_retry_25_2026-09-21 17 24 29 35 40 45
python weird_captcha_gym/difficulty_audits/remaining_39_2026-09-10/run_queue.py --audit-dir weird_captcha_gym/real_time_audits/historical_50_retry_25_2026-09-21 20 25 31 36 41 47
python weird_captcha_gym/difficulty_audits/remaining_39_2026-09-10/run_queue.py --audit-dir weird_captcha_gym/real_time_audits/historical_50_retry_25_2026-09-21 21 27 32 37 43 48
```

Monitoring remains in chat with one-hour foreground sleeps and no intermediate wake-up messages. Raw outputs and failure attempts remain separate from valid completed reports.

## Completed retry results

All 25 retries completed: 44 Yes and 206 No judgments, with no retry process failures or report flags. Together with the preserved original completions, all 50 games / 500 configurations now have completed reviews: 129 Yes and 371 No. There are 48 historical-label disagreements across ten games. The original ten Rotating On-Screen Keyboard identity-field flags remain unchanged.

See [report.md](report.md) and [combined_results.json](combined_results.json). All 211 original audit artifacts and all 2,231 frozen source files were reverified unchanged. No historical or catalog labels were updated.
