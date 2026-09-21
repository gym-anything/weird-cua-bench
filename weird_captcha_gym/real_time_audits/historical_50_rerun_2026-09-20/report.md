# Historical 50: fresh real-time audit results

Updated: 2026-09-21T06:13:07.513449+00:00

All 50 first attempts have finished. The audit remains incomplete: 25 game reviews completed and 25 failed because the reviewer reported a usage limit. No automatic retries were run.

Reviewer: `gpt-5.6-luna`, reasoning `max`; one fresh process per game, ten configurations per process, four sequential queues, a 2,700-second outer game deadline.

- Completed reviews: 250 configurations — 85 Yes, 165 No, 0 Unresolved.
- Structural flags: 10 configurations in Rotating On-Screen Keyboard.
- Completed configurations without structural flags: 240 — 80 Yes, 160 No.
- Failed attempts: 25 games / 250 configurations, excluded from label counts.
- Disagreements with historical labels: 21 configurations across six games — 20 Yes → No and one No → Yes.
- Historical labels, raw reports, failed-attempt artifacts, and the completed Forced-Perspective Moving Day review remain unchanged.

## Validation and failure records

All 2,231 archived source files still match their Git blobs at `aa085c8caa6575cde1353272b94118b7903a62a3`. Prompt, definition, manifest, source-snapshot, completed-report, receipt, and preserved historical-file hashes were checked. Completed reports cover their assigned configurations exactly. The existing source-review launcher and grouped-audit tests passed: 39 tests.

Rotating On-Screen Keyboard has the correct game-level identity, but all ten configuration entries omit `environment_id` and `public_environment_name`. Those original omissions remain flagged; the raw labels above include this report. Structural checks do not adjudicate the labels.

Dead Man’s Switch wrote a report before its process failed on the usage limit. That artifact is preserved but excluded from completed-review label counts. All 25 failed attempts and their error messages are indexed in [results.json](results.json). No failed attempt was converted into a completed review.

## Label disagreements

| Environment | Difficulty | Interaction | Historical | Fresh |
|---|---|---|---|---|
| Clockwork Clutch Safe | L2 | Full | Yes | No |
| Clockwork Clutch Safe | L2 | Simplified | Yes | No |
| Polarized Palimpsest | L2 | Full | No | Yes |
| Polarized Palimpsest | L3 | Simplified | Yes | No |
| Polarized Palimpsest | L4 | Simplified | Yes | No |
| Polarized Palimpsest | L5 | Simplified | Yes | No |
| Elastic Membrane Sorter | L1 | Full | Yes | No |
| Elastic Membrane Sorter | L1 | Simplified | Yes | No |
| Elastic Membrane Sorter | L2 | Full | Yes | No |
| Elastic Membrane Sorter | L2 | Simplified | Yes | No |
| Occlusion Shell Swindle | L1 | Full | Yes | No |
| Occlusion Shell Swindle | L1 | Simplified | Yes | No |
| Occlusion Shell Swindle | L2 | Full | Yes | No |
| Occlusion Shell Swindle | L2 | Simplified | Yes | No |
| Four-Tab Robot Handshake | L1 | Full | Yes | No |
| Four-Tab Robot Handshake | L1 | Simplified | Yes | No |
| First Change Memory | L1 | Full | Yes | No |
| First Change Memory | L2 | Full | Yes | No |
| First Change Memory | L3 | Full | Yes | No |
| First Change Memory | L4 | Full | Yes | No |
| First Change Memory | L5 | Full | Yes | No |

## All 50 games

Each vector is ordered L1, L2, L3, L4, L5. Y = Yes; N = No; — = no completed review. Report links retain the original first pass; failed rows link to the failure receipt.

| Environment | Attempt status | Full | Simplified | Record |
|---|---|---|---|---|
| Blind Dice Courier | Completed | N N N N N | N N N N N | [Report](first_pass/001_blind_dice_courier_env.json) |
| Gyroscopic Tilt Board | Completed | Y Y Y Y Y | Y Y Y Y Y | [Report](first_pass/002_board_game_captcha_env.json) |
| Bomb Manual From Hell | Completed | N N N N N | N N N N N | [Report](first_pass/003_bomb_manual_from_hell_env.json) |
| Bureaucratic Signature Trap | Completed | N N N N N | N N N N N | [Report](first_pass/004_bureaucratic_signature_trap_env.json) |
| Clockwork Clutch Safe | Completed | N N Y Y Y | N N Y Y Y | [Report](first_pass/005_clockwork_clutch_safe_env.json) |
| Clockwork Doppelgänger Customs | Completed | N N N N N | N N N N N | [Report](first_pass/006_clockwork_doppelganger_customs_env.json) |
| Live Control-Flow Wiring Lab | Completed | N N N N N | N N N N N | [Report](first_pass/007_code_to_diagram_captcha_env.json) |
| Consequences Boss | Completed | N N N N N | N N N N N | [Report](first_pass/008_consequences_boss_env.json) |
| CRAFTCHA: Alchemy Bench | Completed | N N N N N | N N N N N | [Report](first_pass/009_craftcha_alchemy_bench_env.json) |
| Crash-Deadline Hovercar | Completed | Y Y Y Y Y | Y Y Y Y Y | [Report](first_pass/010_crash_deadline_hovercar_env.json) |
| Cursor-Controlled Constellation Hunt | Completed | N N N N N | N N N N N | [Report](first_pass/011_cursor_constellation_hunt_env.json) |
| Polarized Palimpsest | Completed | N Y Y Y Y | N N N N N | [Report](first_pass/012_cursor_lens_reveal_env.json) |
| Dead Man's Switch | Failed: usage limit | — — — — — | — — — — — | [Receipt](provenance/013_dead_mans_switch_env.json) |
| Elastic Membrane Sorter | Completed | N N Y Y Y | N N Y Y Y | [Report](first_pass/014_elastic_membrane_sorter_env.json) |
| The Flat Prisoner | Completed | Y Y Y Y Y | Y Y Y Y Y | [Report](first_pass/015_flat_prisoner_env.json) |
| Funeral With No Instructions | Completed | N N N N N | N N N N N | [Report](first_pass/016_funeral_ritual_env.json) |
| Hologram Silhouette Foundry | Failed: usage limit | — — — — — | — — — — — | [Receipt](provenance/017_hologram_silhouette_foundry_env.json) |
| Impossible Ecology | Completed | Y Y Y Y Y | Y Y Y Y Y | [Report](first_pass/018_impossible_ecology_env.json) |
| Impossible Panorama | Completed | Y Y Y Y Y | Y Y Y Y Y | [Report](first_pass/019_impossible_panorama_env.json) |
| Parallax / Inertial Jigsaw Alignment | Failed: usage limit | — — — — — | — — — — — | [Receipt](provenance/020_jigsaw_slider_alignment_env.json) |
| LIDAR Blacksite | Failed: usage limit | — — — — — | — — — — — | [Receipt](provenance/021_lidar_blacksite_env.json) |
| Magnetic-Stripe Purgatory | Completed | N N N N N | N N N N N | [Report](first_pass/022_magnetic_stripe_purgatory_env.json) |
| Five-System Verification Reactor | Failed: usage limit | — — — — — | — — — — — | [Receipt](provenance/023_microgame_gauntlet_env.json) |
| Isometric Voxel Extraction Mine | Failed: usage limit | — — — — — | — — — — — | [Receipt](provenance/024_minecraft_block_grid_env.json) |
| Motion-Only Ghost Jigsaw | Failed: usage limit | — — — — — | — — — — — | [Receipt](provenance/025_motion_only_ghost_jigsaw_env.json) |
| Occlusion Shell Swindle | Completed | N N Y Y Y | N N Y Y Y | [Report](first_pass/026_occlusion_shell_swindle_env.json) |
| Parallel Grillmaster | Failed: usage limit | — — — — — | — — — — — | [Receipt](provenance/027_parallel_grillmaster_env.json) |
| Photograph Eats the Room | Failed: usage limit | — — — — — | — — — — — | [Receipt](provenance/028_photograph_eats_the_room_env.json) |
| Polyrhythm Customs | Failed: usage limit | — — — — — | — — — — — | [Receipt](provenance/029_polyrhythm_customs_env.json) |
| Popup Exorcist | Completed | N N N N N | N N N N N | [Report](first_pass/030_popup_exorcist_env.json) |
| Recursive Dollhouse Smuggling | Failed: usage limit | — — — — — | — — — — — | [Receipt](provenance/031_recursive_dollhouse_smuggling_env.json) |
| Dual-Projection Sculpture Rig | Failed: usage limit | — — — — — | — — — — — | [Receipt](provenance/032_relation_prompt_grounding_env.json) |
| Reload Interruption | Failed: usage limit | — — — — — | — — — — — | [Receipt](provenance/033_reload_interruption_env.json) |
| Four-Tab Robot Handshake | Completed | N Y Y Y Y | N Y Y Y Y | [Report](first_pass/034_reverse_identity_gate_env.json) |
| Ribbon Switchboard | Failed: usage limit | — — — — — | — — — — — | [Receipt](provenance/035_ribbon_switchboard_env.json) |
| Rorschach / Subjective Prompt With A Fixed Rubric | Failed: usage limit | — — — — — | — — — — — | [Receipt](provenance/036_rorschach_fixed_rubric_env.json) |
| Rotate The Wrong Thing Upright | Failed: usage limit | — — — — — | — — — — — | [Receipt](provenance/037_rotate_wrong_thing_upright_env.json) |
| Rotating On-Screen Keyboard | Completed; missing identity fields | Y Y Y Y Y | N N N N N | [Report](first_pass/038_rotating_keyboard_env.json) |
| Shadow Crime Lab | Failed: usage limit | — — — — — | — — — — — | [Receipt](provenance/039_shadow_crime_lab_env.json) |
| Slot-Reel Character Capture | Failed: usage limit | — — — — — | — — — — — | [Receipt](provenance/040_slot_reel_capture_env.json) |
| Parallax Orchard | Failed: usage limit | — — — — — | — — — — — | [Receipt](provenance/041_surreal_apple_on_tree_grid_env.json) |
| First Change Memory | Completed | N N N N N | N N N N N | [Report](first_pass/042_temporal_memory_first_change_env.json) |
| Three-Camera Claw Machine | Failed: usage limit | — — — — — | — — — — — | [Receipt](provenance/043_three_camera_claw_machine_env.json) |
| Tiny FPS Customs | Failed: usage limit | — — — — — | — — — — — | [Receipt](provenance/044_tiny_fps_customs_env.json) |
| Tomographic Baggage Surgery | Failed: usage limit | — — — — — | — — — — — | [Receipt](provenance/045_tomographic_baggage_surgery_env.json) |
| Top-Face Dice Arithmetic | Completed | N N N N N | N N N N N | [Report](first_pass/046_top_face_dice_arithmetic_env.json) |
| Blind Corridor Oscilloscope | Failed: usage limit | — — — — — | — — — — — | [Receipt](provenance/047_trace_shape_without_walls_env.json) |
| Anamorphic Registration Press | Failed: usage limit | — — — — — | — — — — — | [Receipt](provenance/048_wonky_text_hostile_rendering_env.json) |
| Wrong Number | Failed: usage limit | — — — — — | — — — — — | [Receipt](provenance/049_wrong_number_env.json) |
| Zero-G Cable Autopsy | Completed | N N N N N | N N N N N | [Report](first_pass/050_zero_g_cable_autopsy_env.json) |

The next required work is a separately authorized retry of the 25 failed game reviews. This report does not apply adjudications or update catalog labels.
