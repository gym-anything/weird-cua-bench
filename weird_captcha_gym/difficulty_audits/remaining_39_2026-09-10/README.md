# Difficulty audit: all 49 selected new environments

This continuation covers the 39 environments not included in the [ten-environment pilot](../pilot_10_2026-09-09/pilot_assessment.md). Together the two manifests define 49 environments and 490 difficulty/interaction configurations, without substitutions.

Fresh reviewers use GPT-5.6-Luna with max reasoning. Raw first-pass reports are immutable after completion. This is source review, not a computer-use benchmark evaluation or empirical calibration. No puzzle or difficulty-label changes are authorized by this run.

The frozen source revision and exact public-name selection are recorded in manifest.json. Launch receipts are recorded per case under provenance/. Process logs under outputs/ are ignored by the repository's existing rule. Monitoring used a foreground sleep 1800 / check / rearm loop in the active chat, not a detached monitor. Sequential execution queues kept at most three fresh reviewer processes active; no claim is made of uninterrupted observation while the chat was inactive.

Run a queued case with:

```bash
python weird_captcha_gym/difficulty_audits/remaining_39_2026-09-10/run_reviewer.py CASE_INDEX
```

Case indices 11-49 belong to this continuation; indices 1-10 retain their original pilot reports. The available concurrency limit was three reviewers plus the parent, despite the user's preference for six or eight. All 39 continuation reviews completed on their first attempts. The pilot's separate failed startup and successful fresh retry remain recorded.

Primary adjudication and the browser matrix are finished. See the [final report](../REPORT.md), [all 49 decisions](../ASSESSMENTS.md), and [validation summary](../validation_summary.json). Seven of the full set of 490 configurations still lack a successful browser/exported replay; this is a completed audit with reported missing evidence, not a claim that every implementation check passed. No puzzle or numerical label was changed.
