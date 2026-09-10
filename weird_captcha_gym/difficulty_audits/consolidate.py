#!/usr/bin/env python3
"""Build derived audit indexes without modifying original reports or check records.

ASSESSMENTS is human-adjudicated content, not a verdict inferred from test counts.
All output files are derived indexes; run only after the underlying checks finish.
"""
import ast
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARTS = ("pilot_10_2026-09-09", "remaining_39_2026-09-10")
REVISE = {2, 3, 7, 8, 9, 10, 22, 24, 32, 35, 39, 42, 47}
PRIMARY_FULL_THIS_AUDIT = set(range(1, 11)) | {13, 18, 20, 22, 24, 29, 32, 35, 37, 39, 41, 42, 44, 47}
PRIMARY_FULL_PREVIOUS_AUDIT = {25, 26, 33, 45}
ASSESSMENTS = {
    1: "Retain L1. Visible recipe prefixes and prerequisite chains distinguish profiles, but repeating/composing named gestures does not by itself establish absolute upper levels.",
    2: "Revise gate-radius interpretation: acceptance uses fixed position/heading tolerances. Do not accept L2 to L4: free preview and a safe continuation at each current gate weaken the review's branching argument.",
    3: "Revise transport-difficulty claims to account for visible count calibration. Pump/leak/hold obligations remain; this is not a complete bypass. Original Full L4/L5 solver errors were separately resolved by scrolling to ATP.",
    4: "Retain L4. Flips change later drop paths, but drop operations commute for the final-state problem; do not credit order-dependent final states. Exact generated distance matters; extra budget is recovery.",
    5: "Retain L4. Active combat/state changes support a relative ladder. The Simplified WAIT dot is a source-reviewed instruction caveat, not an established usability failure. This new baseline is assigned, not one of the twenty approved anchors.",
    6: "Retain L3. Material legality, target geometry and thermal state are active. Scramble length is not established as minimum solving length; anchor action/tick quotas are not difficulty evidence.",
    7: "Revise profile/render claims: ramp_direction is inactive and scale stays capped through L4. At L5 sand overwrites the cup tile, removing its usual marker in the captured render. Cards are consumed: the fixed course is not a stateless problem.",
    8: "Revise upper-level justification: mostly independent requested edges do not establish L4/L5. Do not accept L3 to L2 from static geometry alone. Continuous versus stepped camera input has no demonstrated task-relevant information or endpoint loss here.",
    9: "Revise L1 tail-only wording: all four controls remain active. Body geometry ignores roll although numeric roll telemetry remains visible and grading uses it; do not call the roll state wholly hidden or the task impossible.",
    10: "Qualify/revise L2/L3 separation: same fork/opponent tactic, more clutter and looser L3 budget. Clutter can affect perception, so these are not proven identical or reversed levels; requested noise is not guaranteed after early exit.",
    11: "Provisionally retain the source review's baseline. L4/L5 share much of the dependency graph; longer entries and optional decoys need measurement. Browser-shipped answers are consistent with the static runtime, not a compliant UI shortcut.",
    12: "Provisionally retain the source review: sequential survival and overlapping allocation are active distinctions. Cross-environment absolute levels remain unmeasured.",
    13: "Retain the label only provisionally: no intermediate capture/crate progress is rendered although it affects allocation and the task text mentions meters. Private-state solver success does not establish screenshot-only fairness. Inactive early darter intervals are not hardness.",
    14: "Provisionally retain the source review. Generated minimum depth is relevant even when longer legal solutions are allowed; not grading an exact optimum is not a bypass and does not justify a new move quota.",
    15: "Provisionally retain the source review. Endpoint overlap is a seed-dependent hit-testing risk, not a reproduced failed world. Ten passing oracle profiles do not settle visual discriminability.",
    16: "Provisionally retain the source review, excluding static-versus-temporal ranking shortcuts. Displaced parcels are derived in balanced exchange; the brush minimum witnesses the input mode, not an extra reasoning objective.",
    17: "Provisionally retain the source review. Exact-depth twists are active; a constant recovery margin is not an independent increase. The weaker Full gesture instructions remain a source-reviewed usability risk.",
    18: "Retain L4 provisionally with incomplete high-level browser coverage. L5 seed 1 was already geometrically unreachable at the first delayed solver input, not at initial generation. Simplified grader acceptance exceeds the visible trim-button lattice.",
    19: "Provisionally retain the source review. The generation fallback can skip richness filters; no failing seed distribution was established here. Film duration and stored witness-arrow count do not establish required decision depth.",
    20: "Retain L3 provisionally. Alcove is inactive and higher geometry has mixed effects. L5 Simplified controller alignment remains unresolved; the same seed's Full pass does not resolve that missing control evidence.",
    21: "Provisionally retain the review's label, not a full interface sign-off. The reviewer identifies rectangular gateway clicks versus a smaller graded center region; this still needs a dedicated visible-edge reproduction. Orbit parameters are mode-limited.",
    22: "Revise any per-instance D3 reversal guarantee: all-forward runs are possible, and reversed width-one runs may add no decision. Extra RNG draws mean D2/D3 need not be identical for the same seed. Public fleet truth and shot-based score are not defects by themselves.",
    23: "Provisionally retain the source review's L4 driving baseline. Responsive traffic and physical replay matter; the review itself calls D5 high-L4, so do not present the full absolute L1-L5 mapping as established.",
    24: "Revise Full input/replay geometry: a real click accepted on visible tile r0c5 is rejected by the grader's ideal grid. Qualify hidden-age wording because stage styling remains. Original center-click passes do not erase this reproduced defect.",
    25: "Retain L4 Simplified provisionally. Posture/support changes are active. Direct camera dragging is also available in Simplified; record this surface overlap rather than claiming the mode-binding test proves all input exclusivity.",
    26: "Retain L4 provisionally. Branch count is derived and L5 mixes tighter/longer routing with easier transverse/landing margins; uniform adjacent ordering remains unproved.",
    27: "Provisionally retain the source review: height threshold and torque authority change the swing-up control problem. Different controls do not alone establish absolute difficulty bands.",
    28: "Provisionally retain the source review. inspection_complexity is inactive; an alternate route can avoid nominal fire-clearing counts. Do not impose a camera-view or fire-use quota to manufacture planning depth.",
    29: "Retain L4 provisionally. Original Full flick errors were caused by screen-versus-logical-pixel solver distances; all five separate scaled-distance diagnostics pass. Independent rounds and event minima are not planning depth; D1 hold has no positive minimum.",
    30: "Provisionally retain the source review of moving-tail identity matching and dependent reshuffles. No specific source defect was reported; this does not establish empirical L1-L5 calibration.",
    31: "Provisionally retain the source review of the state-dependent multi-pane route. L2/L3 and L4/L5 absolute boundaries remain unmeasured.",
    32: "Revise the preparation/return rationale: a carry-first route works without moving any helper crate in all tested worlds, including both baseline browser modes. stack_height is inactive; cargo_detour only swaps adjacent sides. Keep L4 recorded but unconfirmed.",
    33: "Retain L3 provisionally. Sustained correction is active, but a fixed number of handoffs/re-aims is not required. Do not add an arbitrary quota; D5 absolute placement remains unmeasured.",
    34: "Provisionally retain the source review's label, with source-reviewed issues still requiring follow-up: submitted program versus editor-event binding, decoration-only height variation, seed-invariant route and optional L1 routine reuse. Successful mode replays do not prove forged-program rejection.",
    35: "Revise interaction assistance and profile claims. Simplified enumerates legal connections/actions; Full does not. D5 decoy openings are inactive, realized elevation counts differ, and some generated worlds require no slides. The empty-position render cue is missing.",
    36: "Provisionally retain the source review of moving-target 3D interception. Ammunition/tick increases are allowances, not additional difficulty; absolute levels remain unmeasured.",
    37: "Retain L4 provisionally. The L4/L5 minimum-band difference is visually small, not a complete collapse. Both original L5 travel failures pass separately when only the solver's displayed-output polling latency is reduced.",
    38: "Provisionally retain L2 from the source review. Support-state changes are active; D3/D4 mixes structural changes rather than uniformly tightening every control, so per-seed monotonicity is not established.",
    39: "Revise inactive torsion-tolerance wording, not the goal into hidden exact angles. Coupled fitting remains state-dependent. Hidden-handle proxy access alone is not forbidden; all 30 checked construction targets pass and none starts solved.",
    40: "Provisionally retain the source review of state-changing exact cover. Full uses nearest-valid-origin snap assistance; L4/L5 is principally perceptual. View quotas are not required evidence that visual reasoning matters.",
    41: "Retain L4 provisionally. Reject public browser truth as an architecture defect. All five Simplified downstream paths pass only in separate DOM-assisted option diagnostics; primitive-input dropdown behavior remains unverified.",
    42: "Revise browser/Python layout agreement: restoring target_config fails D3 seed 1 in both modes because space-distribution gap calculations differ. Also qualify D4 rule-family coverage; all families are available but not guaranteed corrupted.",
    43: "Provisionally retain the source review. Reveal quota does not guarantee informative observations, but a lucky correct guess is not a code bypass. The effect of center-biased generation needs measurement, not a new evidence-use quota.",
    44: "Retain L4 and qualify the ladder, overriding the raw revision. Wrong stair selection is reversible: both modes pass after selecting the wrong end then correcting it. L5 may increase spatial/control difficulty without a new planning stage.",
    45: "Retain L4 provisionally with the prior source review. Arbitrary orbit events remain a binding concern; rejecting the tested opposite-mode transcript is narrower evidence. Four raw anchor-verifier paths are wrong and recorded as citation defects.",
    46: "Provisionally retain the source review. Some early decoy/cost parameters are unexposed padding, while later network/toll/training dependencies are active. Do not count unseen catalog items as screenshot decisions.",
    47: "Revise at-most wording versus exactly-required probes. The inference family changes are active, but generator decisiveness is certified within a family that the visible instructions do not name; privileged solving does not establish that information boundary.",
    48: "Provisionally retain the source review of observer-held state, handoffs and light interlocks. Structured higher profiles are not empirically equated to the approved L5 anchor.",
    49: "Provisionally retain the source review's L4. Capacity/fresh vats mainly govern recovery; graduations affect vision and metamer thresholds affect generation, not a guaranteed choice among explicit decoys. The review itself leaves D5 near high-L4.",
}


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def config_key(record):
    return record["case_index"], record["difficulty"], record["interaction"]


def status_counts(records):
    return dict(sorted(Counter(r["status"] for r in records).items()))


def main():
    assert set(ASSESSMENTS) == set(range(1, 50))
    integrity = read(ROOT / "source_integrity_checks.json")
    report_checks = read(ROOT / "all_49_report_checks.json")
    assert integrity["all_match"] and integrity["tracked_files_checked"] == 2859
    assert len(report_checks["rows"]) == 49
    rows, browser, generation, bindings, history = [], [], [], [], []
    for check in report_checks["rows"]:
        i = check["case_index"]
        report_path = ROOT / check["report"]
        report = read(report_path)
        assert sha(report_path) == check["sha256"]
        assert check["provenance"]["report_hash_matches_completed_receipt"]
        assert check["provenance"]["prompt_hash_matches_receipt"]
        baseline = report["current_baseline"]
        coverage = ("primary_complete_core_this_audit" if i in PRIMARY_FULL_THIS_AUDIT else
                    "primary_complete_core_previous_source_audit" if i in PRIMARY_FULL_PREVIOUS_AUDIT else
                    "independent_full_source_review_with_primary_report_adjudication")
        detail = ROOT / PARTS[1] / f"primary_{i:03d}.md"
        rows.append({
            "case_index": i, "environment_id": check["environment_id"], "public_name": check["public_name"],
            "current_baseline": {"difficulty": baseline["difficulty"], "interaction": baseline["interaction"]},
            "raw_verdict": check["raw_verdict_normalized_for_index_only"],
            "primary_disposition": "revise_profiles_or_claims" if i in REVISE else "keep_provisionally_with_qualifications",
            "primary_summary": ASSESSMENTS[i], "source_review_coverage": coverage,
            "numeric_relabel_accepted": False, "puzzle_or_label_changed": False,
            "raw_report": check["report"], "raw_report_sha256": check["sha256"],
            "detailed_assessment": str(detail.relative_to(ROOT)) if detail.exists() else
                (PARTS[0] + "/primary_assessment.md" if i <= 10 else None),
            "reference_issues": check["references"]["issues"],
        })
    for part in PARTS:
        generation.append(read(ROOT / part / "generation_checks.json"))
        bindings.extend(read(ROOT / part / "surface_binding_checks.json")["checks"])
        history.extend(read(ROOT / part / "historical_source_checks.json")["checks"])
        for p in sorted((ROOT / part / "browser_checks").glob("*.json")):
            record = read(p)
            record["record_path"] = str(p.relative_to(ROOT))
            record["separate_diagnostic"] = "_diagnostic" in p.stem
            record["dom_assisted_option_selection"] = "_rayglass_option_diagnostic" in p.stem
            browser.append(record)
    original = [r for r in browser if not r["separate_diagnostic"]]
    diagnostics = [r for r in browser if r["separate_diagnostic"]]
    solves = [r for r in original if r["check"] == "solve"]
    failures = [r for r in original if r["check"] == "failure"]
    assert len(solves) == 490 and len(failures) == 98
    assert len({config_key(r) for r in solves}) == 490
    assert len({config_key(r) for r in failures}) == 98
    successful = [r for r in browser if r["check"] == "solve" and r["status"] == "wiring_pass"]
    for record in successful:
        assert all(record[k]["passed"] is True for k in ("server_grade", "direct_grade", "exported_verifier"))
        assert record["headless"] and record["fresh_browser_profile"]
    positive_keys = {config_key(r) for r in successful}
    primitive_keys = {config_key(r) for r in successful if not r["dom_assisted_option_selection"]}
    missing_positive = [{k: r[k] for k in ("case_index", "public_name", "difficulty", "interaction", "status", "record_path")}
                        for r in solves if config_key(r) not in positive_keys]
    completed_failures = [r for r in browser if r["check"] == "failure" and r["status"] in
                          {"failure_helper_completed", "failure_control_completed"}]
    fresh_keys = {config_key(r) for r in completed_failures if r.get("fresh_challenge_after_failure") is True}
    not_fresh = [{k: r[k] for k in ("case_index", "public_name", "difficulty", "interaction", "record_path")}
                 for r in completed_failures if config_key(r) not in fresh_keys]
    all_profiles = [p for g in generation for p in g["profiles"]]
    assert len(all_profiles) == 1470 and all(p["deterministic"] for p in all_profiles)
    assert len(positive_keys) == 483 and len(primitive_keys) == 478
    assert len(missing_positive) == 7 and len(fresh_keys) == 92 and len(not_fresh) == 6
    assert len(bindings) == 490 and sum(b["status"] == "rejected" for b in bindings) == 483
    for b in bindings:
        if b["status"] == "rejected":
            assert b["own_mode_grade"]["passed"] is True
            assert b["opposite_mode_grade"]["passed"] is False
            assert b["events_unchanged"] is True
    source_tests = []
    for p in sorted(ROOT.rglob("*.py")):
        if "outputs" not in p.relative_to(ROOT).parts:
            ast.parse(p.read_text(), filename=str(p))
            source_tests.append(str(p.relative_to(ROOT)))
    summary = {
        "schema_version": 1, "source_revision": integrity["source_revision"],
        "scope": "Source audit and privileged wiring diagnostics; no human or screenshot-only agent calibration.",
        "reports": len(rows), "profile_reviews": 490, "adjacent_pair_reviews": 196, "interaction_pair_reviews": 245,
        "raw_dispositions": dict(Counter(r["raw_verdict"] for r in rows)),
        "primary_dispositions": dict(Counter(r["primary_disposition"] for r in rows)),
        "primary_complete_core_this_audit": len(PRIMARY_FULL_THIS_AUDIT),
        "primary_complete_core_previous_audit_additional": len(PRIMARY_FULL_PREVIOUS_AUDIT),
        "fresh_cli_reviewers_model_and_effort_verified": sum(r["provenance"].get("all_observed_model_effort_match") is True for r in report_checks["rows"]),
        "native_reviewers_launch_accepted_only": sum(r["provenance"].get("native_launch_accepted") is True for r in report_checks["rows"]),
        "original_reports_and_prompts_hash_match": True,
        "preserved_failed_reviewer_startups": 1,
        "generation": {"configurations": len(all_profiles), "seeds": [1, 17, 101], "all_deterministic": True,
                       "current_default_comparisons": sum(len(g["baseline_comparisons"]) for g in generation),
                       "interaction_world_comparisons": sum(len(g["interaction_comparisons"]) for g in generation),
                       "json_differences_are_not_equivalence_or_difficulty_proof": True},
        "original_positive_attempts": {"count": len(solves), "statuses": status_counts(solves)},
        "original_failure_attempts": {"count": len(failures), "statuses": status_counts(failures)},
        "separate_diagnostics": {"count": len(diagnostics), "statuses": status_counts(diagnostics),
                                 "records": [r["record_path"] for r in diagnostics]},
        "distinct_positive_configuration_coverage": {"total": len(positive_keys), "primitive_input_wiring": len(primitive_keys),
                                                      "additional_dom_option_wiring_only": len(positive_keys - primitive_keys),
                                                      "missing": missing_positive},
        "failure_checks": {"helper_or_control_completions": len(completed_failures), "fresh_challenge_confirmed": len(fresh_keys),
                           "fresh_challenge_not_confirmed": not_fresh,
                           "qualification": "Helper return is not proof of terminal failure or fresh recovery. Lanternfin has rejected submissions; Lampwrights has blocked execution; Cloudpost helper only waits."},
        "surface_binding": {"statuses": status_counts(bindings), "scope": "Own-mode passing transcripts, then only envelope identity rebound; unchanged input events. Not complete forged-transcript coverage."},
        "historical_pre_controls_preservation": {"environments_checked": len(history), "established": 0,
                                                "scope": "No separate committed predecessor at the generator paths; uncommitted creator versions not reconstructed."},
        "frozen_source_integrity": {"files": integrity["tracked_files_checked"], "all_match": integrity["all_match"]},
        "audit_python_syntax": {"all_parse": True, "files": source_tests},
        "git_diff_check": {"raw_report_eof_blank_line_warnings": [
            PARTS[1] + "/first_pass/025_crater_walker_env.json",
            PARTS[1] + "/first_pass/031_four_pane_pilgrimage_env.json",
            PARTS[1] + "/first_pass/045_surveyors_toybox_env.json"],
            "handling": "Preserve immutable raw reports and their receipt hashes; check all other staged files separately."},
        "working_checkout_pytest": {"command": "python -m pytest tests -q", "passed": 1775, "failed": 171, "skipped": 2,
                                   "scope": "Earlier full run in the current 155-environment working checkout, not a test run of the frozen 170-environment source.",
                                   "diagnosed_causes": ["ActionGateway temporal_mode API incompatibility", "Missing hooks in pre-existing ignored rotating_keyboard_seed_0001_tlive generated directory"],
                                   "all_171_individually_diagnosed": False},
        "puzzle_or_label_changes": False, "empirical_cua_runs": 0,
        "full_static_export_smoke": "Not run: audit-only files and harnesses changed, no dashboard/browser-runtime implementation changes.",
        "strict_quality_audit": "Not rerun: no puzzle quality/status metadata changed; no task promoted.",
    }
    write(ROOT / "primary_assessments.json", {"scope": summary["scope"], "definitions": {
        "keep_provisionally_with_qualifications": "Retain the current label/profile family with documented risks; not a calibrated ladder or release sign-off.",
        "revise_profiles_or_claims": "Revise specified active-profile descriptions, justification or implementation in a separately authorized pass; not an automatic numerical relabel."}, "rows": rows})
    write(ROOT / "validation_summary.json", summary)
    # Preserve compact causal evidence from browser attempts, never model session logs.
    extracts = []
    selected = [(PARTS[1], "024*crack_tile_edge_diagnostic"), (PARTS[1], "042*d3*"),
                (PARTS[0], "009*failure"), (PARTS[1], "018*failure"), (PARTS[1], "034*failure")]
    for part, pattern in selected:
        for directory in sorted((ROOT / part / "outputs/browser").glob(pattern)):
            path = directory / "state/attempts.jsonl"
            entry = {"run": str(directory.relative_to(ROOT)), "attempt_log_exists": path.exists(), "attempts": []}
            if path.exists():
                entry["attempt_log_sha256"] = sha(path)
                for line in path.read_text().splitlines():
                    a = json.loads(line)
                    extracted = {k: a[k] for k in ("server_grade", "completed", "final_state", "similarity", "submitted_at") if k in a}
                    if "024" in directory.name:
                        extracted["event_5"] = a["events"][4]
                    entry["attempts"].append(extracted)
            extracts.append(entry)
    write(ROOT / "diagnostic_attempt_extracts.json", {"scope": "Selected immutable browser-attempt fields; absence of a log is not proof of success or failure.", "runs": extracts})
    lines = ["# Per-environment primary decisions", "", "Generated by `consolidate.py` from its explicit primary assessments and immutable report/check records. See [the final report](REPORT.md) for scope and definitions.", "",
             "All numeric baselines remain unchanged. Keep is provisional, not an endorsement of calibrated L1–L5 or every reviewer claim. Revise covers the specified profile/implementation claims, not an automatic relabel.", "",
             "| Environment | Current baseline | Primary decision | Assessment and evidence |", "|---|---|---|---|"]
    for r in rows:
        label = "Revise" if r["case_index"] in REVISE else "Keep, qualified"
        detail = f" [Primary detail]({r['detailed_assessment']})." if r["detailed_assessment"] else ""
        lines.append(f"| [{r['public_name']}]({r['raw_report']}) | L{r['current_baseline']['difficulty']} / {r['current_baseline']['interaction'].title()} | {label} | {r['primary_summary']}{detail} |")
    (ROOT / "ASSESSMENTS.md").write_text("\n".join(lines) + "\n")
    # Hash durable files and local browser artifacts, excluding private reviewer logs.
    inventory = []
    for p in sorted(ROOT.rglob("*")):
        if not p.is_file() or p.name == "evidence_manifest.json" or "__pycache__" in p.parts:
            continue
        rel = p.relative_to(ROOT)
        parts = rel.parts
        local = "screenshots" in parts or "outputs" in parts
        if "outputs" in parts and (len(parts) < 3 or parts[2] != "browser"):
            continue
        inventory.append({"path": str(rel), "bytes": p.stat().st_size, "sha256": sha(p),
                          "availability": "local_ignored_browser_artifact" if local else "durable_audit_file"})
    write(ROOT / "evidence_manifest.json", {"scope": "Content hashes, not exported screenshots/replays. Private reviewer logs and session histories excluded. Rebuild after editing derived files.", "files": inventory})
    print(json.dumps({"primary": summary["primary_dispositions"], "original_solves": summary["original_positive_attempts"],
                      "positive_configs": len(positive_keys), "primitive_input_configs": len(primitive_keys),
                      "fresh_failure_recovery": len(fresh_keys), "inventory_files": len(inventory)}, indent=2))


if __name__ == "__main__":
    main()
