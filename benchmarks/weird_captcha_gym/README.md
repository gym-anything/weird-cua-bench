# Weird CUA Bench

A standalone, Gym-Anything-compatible benchmark for weird CAPTCHA-inspired visual puzzles for computer-use agents.

This package mirrors the CUA-World benchmark shape:

```text
benchmarks/weird_captcha_gym/
  environments/<mechanic_env>/env.json
  environments/<mechanic_env>/tasks/<task_id>/task.json
  splits/*.json
  registry/
```

Each environment is a puzzle-family environment. The action interface is common across all environments: screenshots plus mouse/keyboard actions. Individual tasks define puzzle setup, instructions, hidden generation metadata, and outcome verifiers; they do not define custom action subsets.

Current status: 75 environment folders, all 75 built/prototype designs. There are no remaining rejected, concept, or scaffold records in the live catalog. Forty-three mechanics that previously existed only as Incubator or Pack III–VI selections have been promoted, ten newly selected Interaction VII–VIII mechanics have complete runtime contracts, and the two historical infrastructure pilots were revived only through full interaction-first replacements. This is still a candidate corpus, not a benchmark-ready release.

- `reverse_identity_gate_env` and `moving_checkbox_evasive_button_env` preserve their rejected-pilot history in the design notes, but their live tasks are now the fully rebuilt Four-Tab Robot Handshake and Scroll-Cage Checkbox.
- The foundational visual, source-grounded, and first two interaction collections retain their original evidence directories (`apple_grid_v1`, `cursor_lens_v1`, `modifier_stack_v1`, `board_game_v1`, `source_mechanics_v1`, `interaction_first_five_v1`, and `interaction_second_five_v1`).
- Incubator batches one through five are now built. Batches one and two contain ten interaction-heavy designs; the historical batches three through five contribute thirteen more. Their browser/server/verifier summaries live under `evidence/incubator_batch_one_v1/` through `evidence/incubator_batch_five_v1/`.
- Interaction III and IV are five-mechanic built packs with evidence under `evidence/incubator_batch_six_v1/` and `evidence/incubator_batch_seven_v1/`.
- Interaction V is a five-mechanic built pack—photograph geometry, recorded ghosts, recursive scale, projection topology, and forced perspective—with evidence under `evidence/incubator_batch_eight_v1/`.
- Interaction VI is a five-mechanic built pack—LIDAR, tomography, three-camera teleoperation, deformable cable physics, and portal coordinate transforms—with evidence under `evidence/incubator_batch_nine_v1/`.
- Interaction VII and VIII add ten newly selected mechanics spanning reflected optics, thermally limited airflow, inverse 3D construction, orbital rendezvous, rotating support frames, lock hydraulics, deformable trajectories, decaying swarm control, live phase timing, and coupled kinematics. Their natural-difficulty v2 contracts, evidence, multiseed replay summary, and frozen-contract solution films live under `evidence/interaction_vii_viii_difficulty_v2/`; `interaction_vii_viii_v1/` is retained only as implementation history.
- Interaction IX revives the two rejected pilots as complete replacements: a four-surface physical scroll cage and an eight-relay handshake distributed across four real browser tabs. Canonical browser evidence, a 100-seed adversarial replay audit, and frozen-contract solution films live under `evidence/incubator_batch_revived_v1/`.
- The audited pending-review cohort has a binding repair audit, canonical screenshots, two fresh browser runs, and ten clean frozen-contract solution films under `evidence/pending_next_ten_v2/`. These films prove the scripted path only; the cohort is screened `looks_good`, with hands-on approval still pending.
- Solution-film coverage is now complete for all 75 built dossiers. The closing seven foundational films live under `evidence/foundational_seven_v1/solution_videos/`; the remaining fourteen modular films live under `evidence/remaining_modular_fourteen_v1/solution_videos/`. Both manifests preserve before/after contract hashes and require live-server, direct-grader, and exported-verifier agreement. Semantic Drag-Drop is the sole older pre-freeze walkthrough and is labeled accordingly in the dashboard.

All 75 built designs have local scripted browser, server-grade, and exported-verifier evidence. That does not imply human usability, benchmark validity, or model difficulty. Six mechanics preserve direct human feedback from this execution history; VNC human calibration is still pending for the other 69 designs, and no viewer-specific human-evidence claim is made. Automated AVF screenshots are evidence, not human feedback.

For mechanics that render spatial or physical worlds, the browser receives the geometry it must draw, hit-test, and collide with. It does not receive private solver routes or answer plans. The server independently replays submitted primitive actions against its own copy of the geometry, timing, collision, line-of-sight, and completion rules. Public render geometry is therefore an explicit screenshot/action-agent boundary, not a secrecy guarantee against an agent that can inspect page state or network responses.

Use `all` only as a development surface. The `verified` split remains intentionally empty until tasks pass the quality gate in `docs/benchmark-quality-gate-v0.md`, including real-runner, human, and agent evidence.

The complete interaction-first design history, human VNC findings, implementation corrections, validation status, and future-maintainer checklist are recorded in [`docs/interaction-puzzle-field-notes.md`](docs/interaction-puzzle-field-notes.md).

## Visual Dashboard

The benchmark includes a screenshot-first environment hub for browsing all 75 evidence-backed built designs. All thirty Pack III–VIII selections, all historical Incubator selections, and both rebuilt pilots are real, launchable environment records; the dashboard contains zero rejected, concept, or scaffold cards. Its Survey-free static export can open every built puzzle with one click and run the existing Python grader in a WebAssembly worker, requiring no checkout or localhost helper for ordinary exploration. The optional authenticated loopback companion preserves fresh authoritative generation, isolated VNC, persistent reviews, evaluations, and administrative controls on each collaborator's own computer. Static browser play is deliberately non-authoritative because its bundled challenge truth is inspectable.

[Open the hosted Weird CUA dashboard](https://gym-anything.github.io/weird-cua-bench/).

```bash
python benchmarks/weird_captcha_gym/dashboard/server.py --open --runner avf
```

The dashboard is available at <http://127.0.0.1:8767> and binds to localhost by default. See [`dashboard/README.md`](dashboard/README.md) for product surfaces, architecture, and verification commands; see [`dashboard/RESEARCH.md`](dashboard/RESEARCH.md) for the Prime Intellect and adjacent benchmark research that informed it.

Run the quality audit with:

```bash
python benchmarks/weird_captcha_gym/tools/audit_quality.py --strict
```

## Developer Answer Reveal

The normal benchmark URL must not expose answers. For manual inspection only, start the server with `WEIRD_CAPTCHA_CHEAT_PASSWORD=<password>` or write the password to `$WEIRD_CAPTCHA_STATE_DIR/cheat_password.txt`, then open `/?cheat=1`. Submitting the password reveals the current generated answer for the active mechanic.
