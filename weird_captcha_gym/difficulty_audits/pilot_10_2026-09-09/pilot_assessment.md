# Ten-environment pilot: expansion decision

Decision: proceed with the remaining 39 source reviews, retaining the ten pilot reviews for 49 total. The pilot is useful as a source-audit workflow with primary review; it is not reliable enough for automatic relabeling or for claims of measured difficulty.

All ten independent Luna/max reviewers completed. Each supplied ten difficulty/interaction profiles, four adjacent-level comparisons, five interaction-pair reviews, and at least three approved reference implementations. Their original reports remain unchanged in first_pass/. The mechanical checks are in report_checks.json; valid JSON and in-range citations alone do not establish semantic correctness.

## What supported expansion

The parent read the complete assigned generator, browser mechanic, relevant CSS, grader, verifier, solver and task/control specifications for all ten environments, plus the active implementations of Isometric Voxel Extraction Mine (L1), Cursor-Controlled Constellation Hunt (L2), Gyroscopic Tilt Board (L3), Blind Dice Courier (L4), and Exact-Change Candy Cascade (L5). Shared monolithic helpers were followed through their relevant dispatch paths, not claimed as entirely read.

Several reviewer findings have direct implementation support:

- Apothecary Dead Reckoning: the displayed gate_radius is not the acceptance tolerance; route matching uses fixed distance/angle tolerances. This does not establish the proposed L2-to-L4 relabel.
- Cell Gatekeeper: visible calibration controls directly adjust counts, while pump/leak/hold obligations still remain. This is an authored UI affordance, not an invalid solve or complete bypass.
- Cloudstep Caddie: ramp_direction is generated but does not affect ramp legality; board dimensions through L4 leave the tile-scale cap unchanged.
- Facet Lantern: upper profiles add mostly independent requested edges; current source does not establish their absolute L4/L5 placement merely by action count.
- Lanternfin Dive: L1 still exposes and accepts all four control channels despite the tail-only profile description.
- Pearl Lattice: L2/L3 share the fork construction and opponent policy; their active clutter changes coexist with a more generous L3 move ceiling. The noise generator also has an early-exit path, so requested noise is not guaranteed by source alone.

These support continuing the review process, not accepting every original recommendation.

## Corrections and limitations

- Some reports overstate decision dependence, credit anchor action/tick quotas, or treat static geometry as implying an unchanged decision state. In Cloudstep Caddie, for example, cards are consumed even though the course is fixed.
- The Facet Lantern report correctly identifies continuous versus 15-degree proxy rotation, but that fact alone does not prove a prohibited interaction mismatch. Selected endpoints persist across rotation; task-relevant reachability and information must be checked before demanding identical raw action spaces.
- A missing-path claim appears in the Clockbeat Catacomb source-coverage list (base_task.py); Apothecary lists the shared setup file under the wrong directory; Cloudstep has four wrong repository-prefix references; Cell has one reference ending two lines past EOF. Lanternfin lists a directory as a coverage record. These are preserved as report defects, not silently repaired in the originals.
- Five reports nest their verdict instead of using the requested top-level string; two use line strings instead of numeric range fields. The index can normalize these formats without altering first-pass evidence.
- The parent found omissions as well: Cloudstep Caddie L5 overwrites the cup tile with sand before rendering, removing the usual cup marker (confirmed in the captured render). Lanternfin body rendering does not use roll, even though roll is shown numerically and graded. Green scripted solves did not reveal these issues.
- No numerical baseline labels or puzzle sources have been changed. Source judgments remain provisional pending comparable screenshot-only agent and human measurements.

The continuation prompt adds explicit self-checks for paths, ranges and JSON shape, and clarifies the reasoning pitfalls above without supplying any assigned-task findings. It retains full-source and actual-anchor reading, both input modes, all five levels, and immutable original reports.

## Existing implementation evidence

- 300 generated configurations across seeds 1, 17 and 101 were regenerated deterministically. Identity-normalized Full/Simplified worlds match, and current defaults match current explicit baselines; historical pre-controls preservation is not established.
- All 100 pilot configurations have successful browser/server/direct-grader/exported-verifier wiring evidence. The original oracle matrix passed 98; two Cell Gatekeeper Full profiles required a separate scroll-aware harness diagnostic. The original two errors remain recorded.
- All 100 successful transcripts are rejected under the opposite interaction mode after rebinding only top-level identity/mode metadata, without rewriting their input events.
- Failure/fresh-challenge recovery is covered for both baseline modes in all ten environments: 18 existing failure helpers plus two separately recorded premature-submit diagnostics for Clockbeat Catacomb.
- Browser checks used isolated headless Chromium and local loopback servers. These private-state construction solvers are not screenshot-only agent evaluations, difficulty measurements, or human usability tests.
- The existing working-checkout test run finished with 1,775 passed, 171 failed, and two skipped. Focused checks found ActionGateway temporal_mode API incompatibility and missing hooks in a pre-existing ignored generated task directory. This is separate from the frozen 170-environment source audit and was not repaired in this audit.

The pilot's final primary findings are now in [primary_assessment.md](primary_assessment.md), with the complete [49-environment report](../REPORT.md) and [evidence index](../evidence_manifest.json). Correction to the failure/recovery wording above: twenty helper/control conditions completed, but only eighteen confirmed a fresh challenge; Lanternfin Dive's two records confirm rejected submissions without a new identity. Original records remain unchanged.
