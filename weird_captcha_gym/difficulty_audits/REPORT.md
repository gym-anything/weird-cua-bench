# Difficulty audit of the 49 selected new environments

The source audit is complete: all 49 fresh reviews cover all five difficulty profiles and both interaction modes, followed by primary adjudication and implementation checks. The primary decisions are **36 provisional keeps and 13 profile/claim revisions**, with **no accepted numerical relabels and no puzzle or label changes**. This is not a completed human or screenshot-only-agent calibration.

The [49-environment decision table](ASSESSMENTS.md) links every original review and the detailed primary assessments. [Machine-readable decisions](primary_assessments.json), [validation results](validation_summary.json), [report/provenance checks](all_49_report_checks.json), and the [evidence inventory](evidence_manifest.json) retain the distinction between review claims, observed results and missing evidence.

## What “keep” and “revise” mean

Keep means retain the existing configuration and label provisionally, with the listed qualifications. It does not certify every adjacent ordering, accept every reviewer argument, establish an absolute L5 profile, or approve release. In particular, Ballast Lantern still needs screenshot-only progress-allocation validation; Cloudpost Circuit and Concertina Courier retain incomplete browser coverage. Source-reviewed concerns in Consent Gauntlet, Lampwrights Program and Surveyors Toybox remain follow-up items, not reproduced browser defects in this audit.

Revise means the specified profile descriptions, difficulty justification or implementation need a separately authorized correction before their stated claims can be relied on. It does not mean automatically lower or raise the baseline. The thirteen are Apothecary Dead Reckoning, Cell Gatekeeper, Cloudstep Caddie, Facet Lantern, Lanternfin Dive, Pearl Lattice, Coordinates by Another Name, Crackglaze Crossing, Hearthlift Courier, Lantern Loft, Pocket Locksmith, Reflow Vitrine, and The Unlabeled Drawer.

Raw reviewers returned 37 keeps and 12 revisions. Primary review adds Cloudstep Caddie and Lanternfin Dive to revisions and changes Rising Causeway to a qualified keep. Neither proposed numerical change—Apothecary Dead Reckoning L2→L4 or Facet Lantern L3→L2—is accepted on the available evidence.

## Findings that materially change the interpretation

- **Crackglaze Crossing:** a real Full-mode click inside visible tile `r0c5` moves the player correctly, yet grading rejects that event because the replay uses ideal grid cells while input coordinates include transformed padding/gaps. This was reproduced separately after the ten original center/proxy solves passed. See [the primary reproduction](remaining_39_2026-09-10/primary_024.md) and [archived-attempt extracts](diagnostic_attempt_extracts.json).
- **Reflow Vitrine:** at D3 seed 1, restoring the exact target configuration fails in both modes. Browser and Python space-distribution gap calculations disagree; browser similarity is approximately 0.99106 while Python computes 1.0. This proves rejection of that valid target restoration, not that no alternative could pass. See [the layout comparison](remaining_39_2026-09-10/primary_042.md).
- **Hearthlift Courier:** the advertised preparation/return dependency is unnecessary in all 30 tested difficulty/seed/mode worlds. A player can carry immediately and traverse unmoved helper crates; both baseline browser modes pass this route. Do not defend the difficulty by adding arbitrary push/trip quotas. See [the counterexample](remaining_39_2026-09-10/primary_032.md).
- **Lantern Loft:** Simplified exposes computed legal connections/actions that Full players must infer. Generated elevation/decoy claims are also overstated; several tested initial worlds need no slide, and an invalid rendering call removes the intended empty-slot background cue. See [the source, search and render evidence](remaining_39_2026-09-10/primary_035.md).
- **Ballast Lantern:** capture/crate allocation affects success, but intermediate progress is not rendered, despite the task's meter wording. A private-state solver can allocate from hidden counters; its success does not establish that visible overlap/timing cues are sufficient. This is an unresolved information/fairness qualification, not proof of impossibility or an automatic instruction to add progress bars. See [the primary assessment](remaining_39_2026-09-10/primary_013.md).
- **Profile claims:** unused acceptance/ramp/torsion parameters, unenforced channel descriptions, optional probe budgets that are actually exact quotas, and construction witnesses presented as required solving work need correction or qualification. More clutter, tighter control and static visual geometry can affect difficulty; they do not have to add a new planning dependency to matter. See the [individual decisions](ASSESSMENTS.md).

The primary review also rejects several overstatements. Public browser truth is required by the static-play architecture and is not a compliant screenshot-only shortcut. Direct manipulation versus side-panel proxies is not automatically an interaction-equivalence defect. A larger optimal solution distance remains meaningful without grading an exact-optimum quota. Temporal tasks are not automatically harder than static spatial ones, and comparing a task with Candy Cascade does not establish a universal L4/L5 boundary. Rising Causeway already allows wrong stair selection to be corrected; both modes passed that recovery through existing controls.

## Implementation evidence and limits

| Check | Result | What it establishes |
|---|---:|---|
| Independent profile reviews | 490 | Ten profile/mode reviews per environment, plus 196 adjacent and 245 interaction-pair comparisons |
| Deterministic generation | 1,470/1,470 | Five levels × two modes × seeds 1, 17, 101, regenerated twice |
| Current default / explicit baseline comparisons | 147 | Current-source comparisons, not historical preservation |
| Full / Simplified generated-world comparisons | 735 | Detailed JSON differences retained; not proof of equal UI assistance |
| Original positive browser checks | 469/490 | Browser/server/direct-grader/exported-verifier wiring passed |
| Positive configurations with separate diagnostics included | 483/490 | 478 primitive-input wiring checks plus five Rayglass DOM-option-only checks |
| Opposite-mode replay rejection | 483/483 available passing exports | Input events untouched; only envelope identity rebound |
| Failure helper/control completions | 98/98 conditions | Not the same as verified terminal failure/recovery |
| Fresh challenge confirmed after failure | 92/98 conditions | Six lack this confirmation; see below |
| Frozen selected source files unchanged | 2,859/2,859 | Git blob and disk hashes match the original archive manifest |

The original 21 positive errors remain errors: 19 check errors and two 300-second outer deadlines. Fourteen additional configurations gain evidence only from separately named diagnostics: two Cell Gatekeeper scroll-aware runs, five Five-Second Rule screen-coordinate-corrected flick runs, two Letter Rapids lower-latency output-wait runs, and five Rayglass Vault native-option selections through DOM assistance. These change harness behavior, not puzzles, budgets or grading. They are not post-hoc model passes.

Seven configurations still lack a successful browser/exported replay: Cloudpost Circuit D4 and D5 in both modes, Concertina Courier D5 Simplified, and Reflow Vitrine D3 in both modes. Cloudpost's L5 seed-1 first target is already unreachable after the harness's initial 16–17 neutral ticks; an ideal tick-zero controller succeeds in all 15 tested worlds. That separates startup timing from initial-world solvability, without establishing screenshot-agent performance. Concertina's remaining controller alignment failure is unresolved. Reflow has the reproduced task defect above.

The recovery total corrects an earlier overstatement in the pilot expansion assessment. Lanternfin Dive's two helpers record rejected submissions but no confirmed fresh identity. Lampwrights Program's two helpers demonstrate blocked execution without submitting. Cloudpost Circuit's two helpers wait but do not assert a terminal failure or new challenge. Helper completion must not be reported as 98 verified failure/recovery cycles. [The validation summary](validation_summary.json) lists each missing condition.

All browser processes were isolated, headless, fresh-profile Chromium on loopback servers. No live user browser, desktop or profile was used. The existing solvers and diagnostics inspect task state/DOM and sometimes use construction witnesses: **none is a screenshot-only computer-use evaluation**. Render inspection was targeted, not manual visual QA of all 490 configurations. The visual-verification workflow helped expose the cup/empty-slot cues and confirm the geometry/layout defects; green oracles alone did not establish puzzle quality.

## Review quality, provenance and remaining gates

Every environment has a fresh Luna/max source review. Forty-seven CLI reviews have matching session model/effort metadata; the other two have native launcher acceptance receipts, not independent CLI metadata. The Cell Gatekeeper pilot retains one failed startup and its successful fresh second attempt. All 39 continuation reviews completed on their first attempts. All final report and prompt hashes match their receipts. Reviews had a 45-minute outer process deadline and no automatic outer retries; this was not a benchmark-evaluation provider protocol.

The parent read complete assigned core implementations for 24 environments during this difficulty audit, plus four already read completely in the prior frozen-source audit. The other 21 decisions rely on the independent full-source reviews with primary report adjudication and shared implementation checks. This is not a claim that the parent independently reread every line in all 49 environments. Shared monolithic helpers were followed through relevant dispatch paths. Source references refer to frozen revision `48e86f5950c056bfa0f2822fa430f9762c5fc29c`, not the older working checkout.

Mechanical coverage is complete, but original reports have documented defects: five pilot verdicts use a nested schema, and six reports have missing/mistyped paths or out-of-range citations. Originals were not rewritten; [the mechanical checker](all_49_report_checks.json) records the errata. Three original JSON reports also have extra EOF blank lines flagged by `git diff --check`; these are preserved to keep their receipt hashes intact, with all other staged files checked separately. In-range citations alone are not semantic validation. No separate committed pre-controls generator was found at any of the 49 paths, so historical baseline preservation is not established.

The requested working-checkout suite previously finished with **1,775 passed, 171 failed and two skipped**. Focused diagnosis found an `ActionGateway temporal_mode` API incompatibility and missing hooks in a pre-existing ignored generated task directory; not every failure was individually diagnosed. This was the 155-environment checkout, not a test run of the frozen 170-environment audit source. No full static-export smoke was run because puzzle/dashboard/runtime implementation files were unchanged. No quality status was promoted or audit requirement weakened.

The source-audit deliverable is finished. Puzzle fixes, comparable human and visible-UI-only agent runs, absolute level calibration, and the explicitly missing browser/recovery evidence remain separate work. Local screenshots/replays are ignored, not bundled into Git; the evidence manifest hashes them without exposing reviewer session logs.
