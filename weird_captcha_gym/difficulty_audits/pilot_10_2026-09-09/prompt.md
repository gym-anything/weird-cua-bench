# Independent difficulty review: ten-environment pilot

Review only the assigned environment. This is an audit, not permission to modify a puzzle, assign capability labels, classify real time, or run a computer-use evaluation. Source-based assignments and automated implementation checks are not empirical human/agent calibration. No error quota applies: keeping every profile is an acceptable finding when supported.

The assignment supplies SOURCE_ROOT, CASE_INDEX, ENVIRONMENT_ID, PUBLIC_NAME, and OUTPUT_PATH. Use only the supplied immutable source for implementation evidence. Do not read previous audits, creator/auditor discussions, other reviewers' outputs, or the parent's judgments. Current controls necessarily expose current labels; this is independent review, not blindness to those labels. Do not delegate or spawn further agents. Write only OUTPUT_PATH using apply_patch; leave all source files untouched.

## Required reading

Read SOURCE_ROOT/AGENTS.md, the full controllability plan, and every guide under weird_captcha_gym/docs/controllability/. Read the complete task/environment specification, controls, generator, browser JavaScript and relevant CSS, grader, independent/exported verifier, and solver for the assigned environment, including shared helpers that determine behavior. Follow dispatches; do not judge from descriptions, keyword matches, parameter names, summaries, or private-state solvers alone. List the files actually read and distinguish complete from partial coverage.

Before making difficulty comparisons, read actual reference implementations, including their generator, visible UI, grader/verifier, solver and active baseline configuration. Use at least three approved reference environments, including one easier and one harder reference where the assigned baseline permits. Across your comparisons address both low and high ends of the ladder. The approved twenty-environment table in AGENTS.md is authoritative; historical additional labels in old reports are not new approved anchors. Useful references are Isometric Voxel Extraction Mine (minecraft_block_grid_env, L1), Cursor-Controlled Constellation Hunt (cursor_constellation_hunt_env, L2), Gyroscopic Tilt Board (board_game_captcha_env, L3), Blind Dice Courier (blind_dice_courier_env, L4), and Exact-Change Candy Cascade (exact_change_candy_cascade_env, L5). Choose additional approved examples when their decision or control requirements offer a closer comparison. Never substitute reading controls.json for reading an anchor's actual problem.

## Questions to decide

1. What does a screenshot-only solution actually require at the current baseline? Explain the visible information, decisions, dependent state, precision/control, recovery and success condition. Does the current level fit the approved reference tasks? State concrete similarities and differences rather than assigning the middle level by default.
2. Examine all five difficulty profiles and both interaction modes together. For each adjacent pair, identify active changes in the decision, perception, memory or control problem. Extra independent repetitions, ticks, steps, waiting, verifier-only minimum-action checks and inactive parameters do not themselves increase difficulty. More state-changing dependencies can matter; specify them. Larger parameter values do not automatically establish greater difficulty. L5 is the highest named profile, not the hardest imaginable configuration.
3. Does the assigned baseline preserve the original generated challenge and behavior at a fixed seed? Separate comparing current default versus current explicit baseline from comparing an actual historical pre-controls implementation. If historical evidence is unavailable, state that limitation; do not invent preservation evidence.
4. For each level, do Full and Simplified preserve world, visible information, goal, action effects, physics, timing, tolerances and success conditions, differing only in the input surface? Do browser handlers and grading reject the other mode's transcript? Identify any mode-specific difference that compromises the difficulty comparison.
5. Identify unsupported/unused parameters, indistinguishable adjacent levels, reversals, bypasses, or impossible/unfair profiles only when source evidence supports them. State exact code paths and whether the issue is proved by source, requires a runtime check, or remains uncertain. Passing solvers prove wiring, not difficulty. Preserve uncertainties rather than manufacturing confidence.

## Evidence and boundaries

Every substantive finding needs repository-relative file paths and valid line ranges. Quote or explain the active code and its causal effect on the visible task. For each proposed new level, compare against the actual approved reference implementations you read. You may conclude keep, relabel, revise_profiles, or insufficient_evidence, with a concrete explanation. Do not implement recommendations.

The parent performs the multi-seed generation and headless browser/grader/exported-verifier checks separately and adjudicates after reading your original report. Do not claim those checks ran in your review. Read-only source analysis is allowed; do not launch a browser or a benchmark evaluation. Never interact with a user's browser, desktop, foreground application, existing profile, or session. No code or task mutation is permitted.

## Return format

Write one JSON object to OUTPUT_PATH and finish with a short summary. Include:

- schema_version: 1; case_index; environment_id; public_name.
- current_baseline: difficulty and interaction as implemented.
- source_coverage: array of path and coverage (complete/partial), plus reason for any partial file.
- anchor_comparisons: array with public_name, approved_level, files_read, concrete comparison, and evidence.
- visible_baseline_solution: explanatory text.
- baseline_judgment: current_level, proposed_level (or null), decision, rationale, evidence, uncertainties.
- profiles: exactly ten records, difficulty 1..5 crossed with interaction simplified/full; active_parameters, visible_problem, success_condition, suspected_level (or null), rationale and evidence.
- adjacent_pairs: four records for 1->2, 2->3, 3->4, 4->5; include each mode's change, whether distinguished, ordering assessment and evidence.
- baseline_preservation: current_default_equivalence, historical_preservation, evidence, missing_evidence.
- interaction_equivalence: five records, one per level, covering world/information/effects/success and input/grading surface binding; status and evidence.
- findings: zero or more records with id, affected_configurations, category, severity, claim, causal_explanation, evidence, runtime_check_needed, recommended_action.
- verdict: keep/relabel/revise_profiles/insufficient_evidence; concise_summary; limitations; runtime_checks_performed (empty unless a specifically permitted read-only diagnostic is actually run).

Evidence records have path, start_line, end_line and explanation. Preserve the original report; do not rewrite it after parent feedback. This report is one environment review covering ten configurations, not ten independent reviews.
