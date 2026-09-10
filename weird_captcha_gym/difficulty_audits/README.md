# Difficulty audits

The completed September 2026 source audit covers the 49 selected new environments, all five difficulty profiles and both interaction modes.

- [Final report](REPORT.md): findings, review provenance, validation counts and limitations.
- [Per-environment decisions](ASSESSMENTS.md): all 49 original reports and primary assessments.
- [Machine-readable decisions](primary_assessments.json) and [validation summary](validation_summary.json).
- [Report/provenance checks](all_49_report_checks.json), [source integrity](source_integrity_checks.json), and [evidence hashes](evidence_manifest.json).
- [Pilot expansion assessment](pilot_10_2026-09-09/pilot_assessment.md) and [pilot final assessment](pilot_10_2026-09-09/primary_assessment.md).

Raw `first_pass/` reports, per-attempt receipts and original browser check records are preserved. Separately named diagnostics do not replace failed runs. Screenshots and browser/reviewer process output remain ignored local evidence; no reviewer session logs are published here.

`consolidate.py` builds the derived decision/validation tables and evidence inventory from explicit primary judgments and completed check records. It requires the local frozen-source audit artifacts; it does not run models or browser tasks. The audit has not changed puzzles, labels or quality status, and is not empirical difficulty calibration.
