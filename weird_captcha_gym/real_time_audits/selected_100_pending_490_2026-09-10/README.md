# Real-time audit: selected 100, pending 490

Current status: reviews completed and all 14 report-validation flags resolved through explicit, source-checked corrections in `adjudications.json`. Current labels are 378 No and 112 Yes for the 490 new configurations. Combined with the unchanged 510 historical labels, the selected 100 environments have **295 Yes and 705 No configurations (29.5% real-time)**. There are zero current structural/reference flags. This is a source-classification result, not a gameplay measurement or an independent semantic re-audit of all 1,000 labels.

The user-requested per-game continuation in `grouped_2026-09-11/` ran from 06:06 to 08:16 UTC on 2026-09-11. All 33 grouped reviews and all four queues exited successfully, producing the remaining 324 configuration judgments. Together with the preserved first 166 reports, all 490 requested first passes are present: 379 No and 111 Yes. These immutable raw counts included 14 configuration reports with validation flags. The 510 historical classifications remain skipped and unchanged. Final coverage, report hashes, original-artifact hashes, and all 2,230 source-file Git blob hashes were verified at first-pass completion. `completion.json` preserves that earlier snapshot, including its original result/report hashes; `report.md` and `results.json` now distinguish raw and corrected results.

On 2026-09-11 the user stopped the one-configuration-per-reviewer run and requested all ten configurations together. All four old queues and active reviewers were stopped. Their final 166 reports (111 No, 55 Yes, including four report-validation flags) remain unchanged. The four interrupted attempts (163, 164, 173, 174) exited on user cancellation, not spontaneous model or infrastructure failure. Old queue receipts are preserved even where their last recorded state says running; they are superseded by the grouped manifest and are not live processes.

The continuation has 33 game-level reviews: 32 games with all ten configurations, plus the four unfinished configurations of Courtesy Junction, whose six completed reports are preserved. Four games run in parallel with Luna/max, one fresh context per game. Each reviewer reads the shared implementation once and produces a separate judgment for every requested configuration. These are not independent contexts per configuration. The mathematical definition, 50% pre-run threshold, source revision, evidence requirements, 2,700-second outer deadline, and no-automatic-outer-retry policy are unchanged. The new manifest records the previous-artifact hash inventory and the exact grouped assignments. All 2,230 source files and the selection, historical matrix, and definition hashes were reverified before setup.

The 14 original flags are preserved alongside their corrections:

- Anthill Front L1 Simplified: No → Yes. All three clauses were already true and the pre-run threshold was explicitly unmet; the report's final sentence mistakenly applied the exception anyway. The implementation rejects pre-committed defenses and requires a phase-dependent lane commitment after the raid begins. A replay regression confirms an early commitment is rejected, no defense loses, and a formerly correct lane becomes fatal after a visible phase crossing while the opposite lane still permits victory.
- Ballast Lantern L4 Simplified: clause (i)'s Boolean changes from false to true; Yes is unchanged. Its existing reason explicitly says no action-history-only policy can choose correctly across the visible worlds, which is what clause (i) asserts. The correction resolves that inverted field, not the existing uncertainty about bounded-window sufficiency, hidden motion variation, or unrendered meter reserves.
- Apothecary Dead Reckoning L4 Full: correct the verifier's directory in both citations after reading the actual task-level verifier.
- Charter of the Nine Cantons L1 Full: correct the environment bootstrap filename after reading the actual wrapper; leave the valid task-level setup reference unchanged.
- Four-Pane Pilgrimage, all ten configurations: correct `weird_cua_gym` to `weird_captcha_gym` in the definition reference.

Each correction records the original report hash, exact original issues, field-level before/after values, rationale, and checked sources. The builder refuses stale hashes/values, duplicate corrections, identity changes, residual report issues, or attempts to erase provenance failures. The original first-pass files and receipts are never overwritten. Corrected source lists describe the derived reports; they do not establish which files the original reviewer actually opened. No puzzle settings or historical catalog labels changed.

Earlier storage resume: `storage_resume.json` records six explicit fresh attempt-2 replacements, 467 disjoint never-started cases, and preserved hashes of the first 17 completed reports and original receipts after the user cleared disk space. That execution was superseded by the grouped continuation.

Storage interruption (2026-09-10 22:19 UTC): all four replacement queues exited with `OSError: [Errno 28] No space left on device`. Seventeen first-pass reports were completed, two attempts recorded failure, and four processes exited before they could finalize their receipts. Original reports and receipts are preserved. The progress builder detects exited processes instead of reporting their stale receipts as active. Only approximately 143 MiB of temporary pytest data created by this run were removed; those generated fixtures are reproducible. No unrelated files were deleted. The replacements in `storage_resume.json` follow the user's confirmation that disk space was cleared; they are not automatic retries or rewrites of failed attempts.

User-authorized source review of the selected 100 environments, skipping existing real-time classifications. The frozen selection yields 490 new difficulty/interaction configurations across 49 environments. The other 510 configurations across 51 environments are listed in `skipped_existing.json` and are not rerun or relabelled. Historical evidence is preserved, not claimed to have been revalidated against the current implementation.

## Execution

For the current game-level run, use the same launcher and queue below with `--audit-dir weird_captcha_gym/real_time_audits/selected_100_pending_490_2026-09-10/grouped_2026-09-11`. Indices in that manifest identify games, not individual configurations. Grouped reports stay in that directory and are indexed directly by the parent progress builder; no earlier first-pass report or attempt receipt is overwritten. Parent results include both game progress and configuration progress.

The following paragraph describes the preserved first-phase protocol:

Reuse the existing fresh Luna/max reviewer and sequential queue, with `--audit-dir` and a manifest-supplied assignment wrapper. One independent fresh process per configuration. Initially three concurrent reviewers; increased to four at the user's request, recorded in `parallel_4_amendment.json` without modifying the frozen manifest or prompt. The queue's optional `--wait-for-case` preserves active reviews during the handoff before starting the replacement slot's remaining cases. Every process has the existing 2,700-second outer deadline. No automatic outer retry or corrective follow-up. Any failed process and separately approved replacement remain distinct attempts. Built-in provider request limits are not independently asserted; this is source classification, not an empirical benchmark evaluation protocol.

Source revision: `6172cf4baafbd4d1bbcfbb2444e5017edbb8326c`. A Git archive (not a worktree) supplies a frozen source snapshot without previous audit tables. The manifest records its path, aggregate content hash, selection provenance, and exact pending keys.

The prompt reuses the historical real-time pilot, adds the already settled 50% pre-run exception, and requires source evidence. An unresolved pre-run threshold is not guessed. First-pass reports, process receipts, failures, and later validation remain separate. No historical result is overwritten.

Launch one pending configuration from the repository root:

```bash
python weird_captcha_gym/difficulty_audits/remaining_39_2026-09-10/run_reviewer.py --audit-dir weird_captcha_gym/real_time_audits/selected_100_pending_490_2026-09-10 CASE_INDEX
```

Queue explicit pending indices in one slot:

```bash
python weird_captcha_gym/difficulty_audits/remaining_39_2026-09-10/run_queue.py --audit-dir weird_captcha_gym/real_time_audits/selected_100_pending_490_2026-09-10 CASE_INDEX [CASE_INDEX ...]
```

Reports live in `first_pass/`; immutable attempt receipts in `provenance/`; local process logs in ignored `outputs/`. Monitoring stays in the active chat using foreground sleep/check/rearm, reporting every 30 minutes as requested. No detached monitor. This audit does not modify puzzles, baseline difficulty assignments, input modes, real-time settings, or historical catalog labels.

## Setup validation

- Flag correction and pinned-runtime regression check: 219 passed, 1 warning in 12.90 seconds across the launcher, grouped-audit, Codex action-contract, and Codex temporal-gateway tests. Includes 39 audit checks and the Anthill replay regression. Used a temporary virtual environment with the repository-pinned Gym-Anything revision; the user's global dependency installation was not changed. The prior 170 gateway failures do not reproduce with that pin. The full post-correction suite and repository CI results are reported in the pull request.
- Pre-publication diff validation passes for implementation, tests, corrections, and generated indexes. The unrestricted staged whitespace check reports trailing whitespace/extra final blank lines in seven immutable grouped first-pass JSON files and the frozen grouped prompt; those original bytes are retained to preserve their recorded hashes.
- Grouped continuation: `python -m pytest tests/test_source_review_launcher.py tests/test_grouped_real_time_audit.py -q`: 26 passed. Covers one process for ten configuration assignments, exact coverage and identity, partial-game preservation, original-artifact hash protection, unchanged definition/pre-run text, grouped process state, and report flags without label rewriting.
- Grouped-continuation full suite, `python -m pytest tests -q`: 1,991 passed, 170 failed, 2 skipped, 1 warning in 1,268.06 seconds. The 170 failures remain in the two Codex action/temporal gateway test files because the installed Gym-Anything `ActionGateway` rejects `temporal_mode`; the representative failure is unchanged `weird_captcha_gym/evaluation/codex_cli.py:33`. No dependency or production gateway code was changed. The targeted grouped-audit checks passed; the full suite is not green.

- Exact coverage and identity: 490 unique pending configurations plus 510 disjoint historical configurations; all public names checked against the current dashboard catalog.
- Frozen selection, historical matrix, definition, prompt, and source snapshot hashes recorded.
- `python -m pytest tests/test_source_review_launcher.py -q`: 10 passed after the four-slot handoff support, including waiting for completed/failed/deadline-exceeded existing attempts without rerunning them and refusing an expired nonterminal receipt.
- Report-validator probes: valid No accepted; identity mismatch, missing Yes witnesses, pre-run contradiction, and paths outside the snapshot rejected. Citation range parsing accepts comma or semicolon separators and checks every range against the source file without editing first-pass reports.
- `python -m pytest tests -q`: 1,970 passed, 170 failed, 2 skipped in 1,517.50 seconds. The failures are in `test_codex_action_contract.py` and `test_codex_temporal_gateway.py`. The installed Gym-Anything `ActionGateway.__init__` has signature `(env, resolution, max_steps, token)` and rejects the repository's `temporal_mode` argument. A targeted reproduction fails at unchanged `weird_captcha_gym/evaluation/codex_cli.py:33`. No production gateway code or global dependency was changed for this source-review run.
- `git diff --check`: passed during setup.
- Repeat full suite after adding the handoff option: 1,898 passed, 203 failed, 1 skipped, 45 errors, 4 warnings in 1,193.63 seconds. This run also encountered exhausted disk space in temporary-file setup and writes; it is not a clean test result. The original compatibility failure remains separate from this storage failure.

Regenerate the progress index and combined selected-100 matrix with:

```bash
python weird_captcha_gym/real_time_audits/selected_100_pending_490_2026-09-10/build_report.py
```

The default uses the original frozen source directory from the manifest. On another machine, pass `--source-root /path/to/source-at-6172cf4`. The source directory may be an archive of the recorded Git revision; no worktree is needed. The builder verifies cited source bytes against that revision's Git blobs before writing. If the checkout's cited source is still unchanged, `--source-root .` works from the repository root. The revision must be available in local Git history. The historical snapshot paths inside immutable reports/receipts are provenance, not portable launch defaults.

The report distinguishes pending/running reviews, failed processes, malformed reports, immutable first-pass labels/issues, explicit adjudications, and current labels/issues. In schema version 2, `cases[].label`, `cases[].issues`, and `selected_100_combined` use the corrected view; `first_pass_label`, `first_pass_issues`, and `counts.first_pass_labels` preserve the original view. Corrected report bodies are embedded in `adjudicated_report` only for the 14 adjudicated cases. It does not silently convert an unresolved or invalid review into a classification.
