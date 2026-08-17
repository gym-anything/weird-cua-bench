# Pre-run solution audit: 1,500 configurations

Date: 2026-08-17

## Test

A configuration is pre-run when at least 50% of its generated instances admit a successful solution that, after preparation, starts the autonomous outcome phase and sends no more outcome-affecting actions until that phase ends.

Final submission or certification after the run is treated as administrative.

## Result

- Pre-run solution: **96 / 1500**
- No pre-run solution: **1404 / 1500**
- Pre-run solution while currently labelled real-time: **0**
- Reclassified from real-time by this audit: **20**

The live and paused rows have the same result because the test concerns the solution's action ordering, not the observation schedule.

## Configurations with a pre-run solution

| Environment | Difficulties | Interaction | Pre-run rate | Live + paused rows | Evidence |
|---|---|---|---:|---:|---|
| Clockwork Doppelgänger Customs | D1, D2, D3, D4, D5 | Simplified, Full | 100% | 20 | The solution records and phases every operator loop before CLOCKWORK RUN; the master cycle then completes without another task action. |
| Polarized Palimpsest | D1, D2 | Simplified | 100% | 4 | There is one echo. The solution scans and positions the coordinate lens, then CAPTURE ECHO performs the required tracking automatically without another task action. |
| Domino Autopsy | D1, D2, D3, D4, D5 | Simplified, Full | 100% | 20 | The solution places and levels every loose domino before DOMINO RUN; the chain and bell simulation then finish without another task action. |
| Flat-Pack Compliance Test | D1, D2, D3, D4, D5 | Simplified, Full | 100% | 20 | The solution positions, rotates, and joins every part before LOAD; the complete load sequence then finishes without another task action. |
| Dual-Projection Sculpture Rig | D1, D2, D3, D4, D5 | Simplified, Full | 100% | 20 | The solution places every object and sets every depth before SETTLE; the force-settle sequence then finishes without another task action. |
| Specular Lighthouse Relay | D1 | Simplified, Full | 100% | 4 | D1 has one round and one receiver whose entire motion stays inside the beam tolerance. One mirror setting before CHARGE completes the round without another task action. |
| Wind-Tunnel Seed Courier | D1, D2 | Simplified, Full | D1 100%; D2 98.3% | 8 | D1-D2 have one pod and admit a constant fan assignment made before LAUNCH; the complete flight then succeeds without another task action. |

## Reclassified real-time rows

| Environment | Interaction | Difficulties | Live + paused rows |
|---|---|---|---:|
| Dual-Projection Sculpture Rig | Full | D1, D2, D3, D4, D5 | 10 |
| Dual-Projection Sculpture Rig | Simplified | D1, D2, D3, D4, D5 | 10 |

## Reproduction

```bash
python weird_captcha_gym/real_time_audits/pre_run_solution_1500_2026-08-17/build_audit.py
```

The generated `results.json` contains all 1,500 rows.
