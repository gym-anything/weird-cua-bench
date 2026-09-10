# Capability audit: 15 new environments

The combined catalog contains **170 environments: the previous 155 plus 15 new environments from PR #52**. No environment was removed, selected, promoted or changed by this audit.

## Distribution at the canonical baselines

| Core capability | Previous 155 | New 15 | Total 170 |
|---|---:|---:|---:|
| Visual understanding | 131 2D / 24 3D | 1 2D / 14 3D | 132 2D / 38 3D |
| Temporal understanding and memory | 82 | 6 | 88 |
| Reasoning and planning | 129 | 14 | 143 |
| Exploration and interface understanding | 56 | 6 | 62 |

For the last three rows, counts mean Yes. Capabilities overlap; the four rows do not sum to 170. All 170 require visual understanding, partitioned here into 2D and 3D. The previous 155 labels are preserved exactly; only the 15 new environments were audited in this pass. Temporal labels remain provisional until the separate configuration-wide temporal audit.

The previous 155 public names also remain those of the current annotated dashboard. PR #52 branches from an older base that lacks 33 of those display-name overrides; [the name comparison](prior_display_name_comparison.json) records this without renaming or duplicating environments. The 15 new names come from the pinned PR #52 dashboard catalog.

## The 15 new environments

| Public environment name | Baseline | Visual | Temporal | Reasoning and planning | Exploration and interface |
|---|---|---|---|---|---|
| Cloudpost Circuit | L4 / Full | 3D | Yes | Yes | Yes |
| Cloudstep Caddie | L4 / Simplified | 3D | No | Yes | No |
| Crater Walker | L4 / Simplified | 3D | No | Yes | Yes |
| Downsky Causeway | L4 / Full | 3D | Yes | Yes | No |
| Facet Lantern | L3 / Full | 3D | No | Yes | Yes |
| Hearthlift Courier | L4 / Full | 3D | No | Yes | Yes |
| Horizon Relay | L3 / Full | 2D | Yes | No | No |
| Lampwrights Program | L4 / Full | 3D | No | Yes | No |
| Lantern Loft | L4 / Full | 3D | No | Yes | No |
| Lanternfin Dive | L4 / Full | 3D | Yes | Yes | Yes |
| Lanternwing Roundup | L4 / Full | 3D | Yes | Yes | No |
| Pearl Lattice | L3 / Full | 3D | No | Yes | No |
| Polycube Parcel | L4 / Full | 3D | No | Yes | Yes |
| Rising Causeway | L4 / Full | 3D | Yes | Yes | No |
| Surveyors Toybox | L4 / Full | 3D | No | Yes | No |

The baseline column records the current configuration from controls.json; it is not a new difficulty judgment. [Full 170-environment list](combined_catalog.md) · [Machine-readable list](combined_catalog.json) · [Detailed new reviews](new_environment_reviews.json).

## Procedure and provenance

Each new environment received one independent, fresh GPT-5.6 Luna review at xhigh reasoning. The prompt and schema are the same as the prior 80-environment pass: only PR #50 → PR #52 and the pinned revision references changed. [Frozen prompt](prompt.md), [previous prompt](previous_prompt.md), [protocol](protocol.json).

Case 001 used a fresh collaboration subagent. The launcher then refused additional fresh threads, so cases 002–015 used fresh independent Codex CLI processes with the same model, effort and assignment wrapper. The CLI ignored user configuration and disabled app integrations. No old reviewer context was reused. All first-pass model/effort settings were checked; the active parent session performed primary review and adjudication, and is not claimed to be the first-pass model.

Surveyors Toybox required three fresh process attempts: the first exited before returning a review, the second encountered a local disk-space failure, and the third completed after free space became available again. Neither failed attempt produced an annotation; no returned first pass was rerun or replaced. [Retry history](provenance/retry_history.json) records the failures and preserved receipts. No user files were deleted.

All reviewers read the complete generator, browser implementation, relevant CSS, grader, verifier, solver, environment/task/control files and required guidelines. The primary read every review and checked supporting source, with additional complete-source review for disputed judgments; each primary file states the exact coverage. This is not an independent double annotation of every source file.

Source revision: `48e86f5950c056bfa0f2822fa430f9762c5fc29c` ([PR #52](https://github.com/gym-anything/weird-cua-bench/pull/52)). Previous annotation revision: `1e3ca0c258bfd02f9a232198bc93de30265f8adb`. All 2,859 snapshot source files were verified against Git blob hashes. Original first-pass JSON files are retained byte-for-byte in `first_pass/`; separate primary checks reference their SHA-256 hashes. [Source manifest](source_manifest.json) and [validation](validation.json).

## Primary baseline corrections

| Public environment name | First-pass → primary decision |
|---|---|
| Facet Lantern | Temporal understanding and memory: yes → no; Exploration and interface understanding: no → yes |
| Horizon Relay | Visual understanding: 3D → 2D; Reasoning and planning: yes → no |
| Lantern Loft | Temporal understanding and memory: yes → no |

These are adjudicated differences, not an inter-rater agreement statistic. Each correction's source evidence and explanation is stored in `primary_checks/`. Uncorrected first-pass evidence is preserved even when its interpretation was rejected; final labels and primary explanations take precedence.

## Configuration and creator comparisons

All five difficulty levels and both interaction modes were examined within each environment review. [The 150-row configuration matrix](new_15_configuration_matrix.json) expands the fifteen reviews plus their exceptions; it is **not 150 independent audits**. Low-difficulty camera-necessity boundaries in Crater Walker and Hearthlift Courier remain stated source-review limitations, not calibrated thresholds. There are no unresolved baseline labels.

[Creator comparison](creator_comparison.json) records only explicit labels in controls.json and task metadata. Missing creator labels remain missing rather than being converted into No: {'visual': 4, 'temporal': 8, 'reasoning_planning': 4, 'exploration_interface': 9}. There are 6 explicit creator-versus-final label differences. Creator metadata is comparison material, not evidence that a capability is required.

## Scope and limits

This is a source-based capability audit, not screenshot-only gameplay, human calibration, an agent success-rate experiment, a real-time audit or a difficulty audit. No browser/desktop session was controlled. No gameplay or browser smoke tests were run: no environment, browser runtime, dashboard, grader or quality-status code was changed. Annotation consistency, evidence bounds, source/prompt/review hashes, model settings, profile expansion and exact preservation of the previous 155 labels were checked.

Selection comes next, at the user's direction. Difficulty, dedicated temporal and real-time testing remain deferred.
