# Final adjudication of the 48 disagreements

I assign **5 Yes and 43 No** real-time labels to the 48 disputed configurations, using the [settled definition](../../docs/controllability/real-time.md) and the implementations at revision `aa085c8caa6575cde1353272b94118b7903a62a3`.

These are 48 difficulty × interaction configurations across 10 environments, not 48 environments. “Both” means Full and Simplified. The table contains only disputed configurations.

| Public environment name | Difficulty | Interaction | Final real-time label | Count | Decisive evidence |
|---|---|---|---|---:|---|
| Clockwork Clutch Safe | L2 | Both | No | 2 | Passing the last acceptable release band makes success irrecoverable; that deadline cannot supply a loss inside the definition’s salvageable set. |
| Polarized Palimpsest | L2 | Full | No | 1 | The complete motion envelope fits inside the lock radius around a fixed point. |
| Polarized Palimpsest | L3–L5 | Simplified | Yes | 3 | Initial capture checks the moving echo before automatic tracking starts; recent motion predicts which coordinate remains valid. |
| Dead Man's Switch | L1 | Full | No | 1 | A stationary center hold remains accepted throughout every allowed plate motion. |
| Elastic Membrane Sorter | L1–L2 | Both | No | 4 | Pre-set tensions solve at least two of three equally likely courses without correction after release. |
| Occlusion Shell Swindle | L1–L2 | Both | No | 4 | Static inspection placement suffices; the later stopped-shell choice is untimed. |
| Parallel Grillmaster | L1–L5 | Both | No | 10 | A missed serving window irreversibly fails the attempt; it does not provide recoverable action-value loss within the salvageable set. |
| Four-Tab Robot Handshake | L1 | Both | No | 2 | Prepared constant direction and contact automatically acquire, charge, and complete the single relay. |
| Slot-Reel Character Capture | L1–L4 | Both | No | 8 | A target becomes capturable immediately when an unseen token appears; recent frames cannot determine every delayed capture decision. |
| Slot-Reel Character Capture | L5 | Both | Yes | 2 | Visible travel precedes the capture band by at least 43.2 ms, supporting a 30-ms prediction horizon. |
| First Change Memory | L1–L5 | Full | No | 5 | The frozen review timeline preserves all required observation evidence. |
| Wrong Number | L1–L3 | Both | No | 6 | Pre-run tuning can remain within tolerance for the entire qualification trial. |
| **Total** | | | **5 Yes / 43 No** | **48** | |

## Seven reviewer verdicts I overturn

I agree with the fresh reviewer on 41 configurations and overturn seven:

- **Polarized Palimpsest, L2 Full: Yes → No.** The echo moves at most `sqrt(17² + 13²) ≈ 21.40` pixels from its fixed base, inside the 40-pixel lock radius. An off-center pointer slipping does not establish that prediction is necessary.
- **Dead Man's Switch, L1 Full: Yes → No.** The stationary center’s worst-case normalized elliptical distance is `(175/270)² + (115/310)² ≈ 0.5577 < 1`. Automatic pressure sampling permits the hold to remain fixed.
- **Polarized Palimpsest, L3–L5 Simplified: No → Yes.** Automation starts only after a successful capture-distance check. It completes one hold, not the five-echo task. I use a 200-ms delay and a 600-ms recent window: an echo that can be captured at delivery is already visible, and its recent motion supports acquisition. Treating the accepted automatic suffix as a pre-run solution omits the live acquisition decision.
- **Slot-Reel Character Capture, L5 Both: No → Yes.** L5’s 0.68 capture ratio leaves a visible lead-in of `0.16 × interval`, at least 43.2 ms. A 30-ms delay cannot turn an unseen next token into a capturable token. Recent visible displacement identifies motion; the trailing band edge can invalidate the action while future attempts remain possible. The reviewer’s 240-ms counterexample does not rule out this shorter witness.

## Records and validation

- [final_labels.json](final_labels.json) contains all 48 explicit configuration identities, historical/reviewer/final labels, detailed rationales, source evidence, and content hashes. It is the final-label overlay for this adjudication.
- [combined_results.json](../historical_50_retry_25_2026-09-21/combined_results.json) remains the unchanged raw 50-environment comparison. Original reports and receipts remain unchanged.
- [Regression checks](../../../tests/test_real_time_disagreement_adjudication.py) cover exact disagreement identity matching, source/report hashes, geometric bounds, fixed-input grader replays, review-only evidence, and L5 reel prediction/expiry.

Validation results:

- `python -m pytest tests/test_real_time_disagreement_adjudication.py -q`: **26 passed**.
- All 50 original report hashes and all 50 receipt hashes match the raw comparison.
- I started `python -m pytest tests -q`, then stopped it after failures in unchanged evaluation code. An isolated reproduction, `python -m pytest tests/test_codex_action_contract.py -x -q`, fails because `ActionGateway.__init__()` rejects the `temporal_mode` argument. The full suite did not complete; I made no evaluation-code changes.

Only these 48 configurations are adjudicated here. Forty-one historical labels change, all from Yes to No. Applying this overlay to the raw 500-configuration rerun changes its aggregate from 129 Yes / 371 No to 132 Yes / 368 No.
