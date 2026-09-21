# Historical 50: completed reviews and authorized retries

Updated: 2026-09-21T09:29:33.404134+00:00

All 25 authorized retries completed successfully. Together with the 25 completed original reviews, the audit now covers all 50 environments and 500 difficulty/interaction configurations.

## Results

| Scope | Games | Configurations | Yes | No | Unresolved |
|---|---:|---:|---:|---:|---:|
| Original completed reviews | 25 | 250 | 85 | 165 | 0 |
| Authorized retries | 25 | 250 | 44 | 206 | 0 |
| Combined | 50 | 500 | 129 | 371 | 0 |

Compared with the historical labels, 48 configurations across ten games disagree: 46 Yes → No and two No → Yes. These are raw source-review disagreements, not adjudicated changes to catalog labels.

The retries have no structural/reference/provenance flags. The original Rotating On-Screen Keyboard report still has ten configuration entries missing `environment_id` and `public_environment_name`; its game-level identity is correct. Those original flags remain visible, and its five Yes and five No judgments are included in the raw totals above. Excluding the flagged entries gives 124 Yes and 366 No across 490 configurations.

## Retry protocol and verification

Reviewer: `gpt-5.6-luna`, reasoning `max`; one fresh context per game and all ten configurations considered together. Prompt, definition, source snapshot, 2,700-second outer deadline, four-reviewer concurrency limit, and no automatic further retries are unchanged. Original game and configuration indices are retained. Dead Man’s Switch began alone to confirm provider activity; one queue awaited it while the other three queues started. Monitoring used one-hour foreground sleeps.

All 25 retry processes exited successfully. Every retry covers its ten assigned configurations and passed the existing structural and source-reference checks. All 2,231 source files still match the frozen Git revision `aa085c8caa6575cde1353272b94118b7903a62a3`. All 211 original audit artifacts, including failed attempts and logs, remain hash-identical. The existing launcher and grouped-audit tests passed: 39 tests.

The original failed Dead Man’s Switch artifact is preserved and excluded; its newly completed retry supplies the selected labels. Original completed reviews are not rerun or replaced. No raw report, historical result, definition, puzzle, or catalog label was edited.

## Disagreements with historical labels

| Environment | Difficulty | Interaction | Historical | Fresh | Configurations |
|---|---|---|---|---|---:|
| Clockwork Clutch Safe | L2 | Both | Yes | No | 2 |
| Polarized Palimpsest | L2 | Full | No | Yes | 1 |
| Polarized Palimpsest | L3–L5 | Simplified | Yes | No | 3 |
| Dead Man's Switch | L1 | Full | No | Yes | 1 |
| Elastic Membrane Sorter | L1–L2 | Both | Yes | No | 4 |
| Occlusion Shell Swindle | L1–L2 | Both | Yes | No | 4 |
| Parallel Grillmaster | L1–L5 | Both | Yes | No | 10 |
| Four-Tab Robot Handshake | L1 | Both | Yes | No | 2 |
| Slot-Reel Character Capture | L1–L5 | Both | Yes | No | 10 |
| First Change Memory | L1–L5 | Full | Yes | No | 5 |
| Wrong Number | L1–L3 | Both | Yes | No | 6 |

## All 50 environments

Each vector is ordered L1, L2, L3, L4, L5. Y = Yes; N = No. Links point to the selected raw report.

| Environment | Selected attempt | Full | Simplified | Report flags |
|---|---|---|---|---|
| [Blind Dice Courier](../historical_50_rerun_2026-09-20/first_pass/001_blind_dice_courier_env.json) | Original | N N N N N | N N N N N | None |
| [Gyroscopic Tilt Board](../historical_50_rerun_2026-09-20/first_pass/002_board_game_captcha_env.json) | Original | Y Y Y Y Y | Y Y Y Y Y | None |
| [Bomb Manual From Hell](../historical_50_rerun_2026-09-20/first_pass/003_bomb_manual_from_hell_env.json) | Original | N N N N N | N N N N N | None |
| [Bureaucratic Signature Trap](../historical_50_rerun_2026-09-20/first_pass/004_bureaucratic_signature_trap_env.json) | Original | N N N N N | N N N N N | None |
| [Clockwork Clutch Safe](../historical_50_rerun_2026-09-20/first_pass/005_clockwork_clutch_safe_env.json) | Original | N N Y Y Y | N N Y Y Y | None |
| [Clockwork Doppelgänger Customs](../historical_50_rerun_2026-09-20/first_pass/006_clockwork_doppelganger_customs_env.json) | Original | N N N N N | N N N N N | None |
| [Live Control-Flow Wiring Lab](../historical_50_rerun_2026-09-20/first_pass/007_code_to_diagram_captcha_env.json) | Original | N N N N N | N N N N N | None |
| [Consequences Boss](../historical_50_rerun_2026-09-20/first_pass/008_consequences_boss_env.json) | Original | N N N N N | N N N N N | None |
| [CRAFTCHA: Alchemy Bench](../historical_50_rerun_2026-09-20/first_pass/009_craftcha_alchemy_bench_env.json) | Original | N N N N N | N N N N N | None |
| [Crash-Deadline Hovercar](../historical_50_rerun_2026-09-20/first_pass/010_crash_deadline_hovercar_env.json) | Original | Y Y Y Y Y | Y Y Y Y Y | None |
| [Cursor-Controlled Constellation Hunt](../historical_50_rerun_2026-09-20/first_pass/011_cursor_constellation_hunt_env.json) | Original | N N N N N | N N N N N | None |
| [Polarized Palimpsest](../historical_50_rerun_2026-09-20/first_pass/012_cursor_lens_reveal_env.json) | Original | N Y Y Y Y | N N N N N | None |
| [Dead Man's Switch](first_pass/013_dead_mans_switch_env.json) | Retry | Y Y Y Y Y | N N N N N | None |
| [Elastic Membrane Sorter](../historical_50_rerun_2026-09-20/first_pass/014_elastic_membrane_sorter_env.json) | Original | N N Y Y Y | N N Y Y Y | None |
| [The Flat Prisoner](../historical_50_rerun_2026-09-20/first_pass/015_flat_prisoner_env.json) | Original | Y Y Y Y Y | Y Y Y Y Y | None |
| [Funeral With No Instructions](../historical_50_rerun_2026-09-20/first_pass/016_funeral_ritual_env.json) | Original | N N N N N | N N N N N | None |
| [Hologram Silhouette Foundry](first_pass/017_hologram_silhouette_foundry_env.json) | Retry | N N N N N | N N N N N | None |
| [Impossible Ecology](../historical_50_rerun_2026-09-20/first_pass/018_impossible_ecology_env.json) | Original | Y Y Y Y Y | Y Y Y Y Y | None |
| [Impossible Panorama](../historical_50_rerun_2026-09-20/first_pass/019_impossible_panorama_env.json) | Original | Y Y Y Y Y | Y Y Y Y Y | None |
| [Parallax / Inertial Jigsaw Alignment](first_pass/020_jigsaw_slider_alignment_env.json) | Retry | N N N N N | N N N N N | None |
| [LIDAR Blacksite](first_pass/021_lidar_blacksite_env.json) | Retry | Y Y Y Y Y | Y Y Y Y Y | None |
| [Magnetic-Stripe Purgatory](../historical_50_rerun_2026-09-20/first_pass/022_magnetic_stripe_purgatory_env.json) | Original | N N N N N | N N N N N | None |
| [Five-System Verification Reactor](first_pass/023_microgame_gauntlet_env.json) | Retry | Y Y Y Y Y | Y Y Y Y Y | None |
| [Isometric Voxel Extraction Mine](first_pass/024_minecraft_block_grid_env.json) | Retry | N N N N N | N N N N N | None |
| [Motion-Only Ghost Jigsaw](first_pass/025_motion_only_ghost_jigsaw_env.json) | Retry | N N N N N | N N N N N | None |
| [Occlusion Shell Swindle](../historical_50_rerun_2026-09-20/first_pass/026_occlusion_shell_swindle_env.json) | Original | N N Y Y Y | N N Y Y Y | None |
| [Parallel Grillmaster](first_pass/027_parallel_grillmaster_env.json) | Retry | N N N N N | N N N N N | None |
| [Photograph Eats the Room](first_pass/028_photograph_eats_the_room_env.json) | Retry | Y Y Y Y Y | Y Y Y Y Y | None |
| [Polyrhythm Customs](first_pass/029_polyrhythm_customs_env.json) | Retry | N N N N N | N N N N N | None |
| [Popup Exorcist](../historical_50_rerun_2026-09-20/first_pass/030_popup_exorcist_env.json) | Original | N N N N N | N N N N N | None |
| [Recursive Dollhouse Smuggling](first_pass/031_recursive_dollhouse_smuggling_env.json) | Retry | N N N N N | N N N N N | None |
| [Dual-Projection Sculpture Rig](first_pass/032_relation_prompt_grounding_env.json) | Retry | N N N N N | N N N N N | None |
| [Reload Interruption](first_pass/033_reload_interruption_env.json) | Retry | Y Y Y Y Y | N N N N N | None |
| [Four-Tab Robot Handshake](../historical_50_rerun_2026-09-20/first_pass/034_reverse_identity_gate_env.json) | Original | N Y Y Y Y | N Y Y Y Y | None |
| [Ribbon Switchboard](first_pass/035_ribbon_switchboard_env.json) | Retry | N N N N N | N N N N N | None |
| [Rorschach / Subjective Prompt With A Fixed Rubric](first_pass/036_rorschach_fixed_rubric_env.json) | Retry | N N N N N | N N N N N | None |
| [Rotate The Wrong Thing Upright](first_pass/037_rotate_wrong_thing_upright_env.json) | Retry | N N N N N | N N N N N | None |
| [Rotating On-Screen Keyboard](../historical_50_rerun_2026-09-20/first_pass/038_rotating_keyboard_env.json) | Original | Y Y Y Y Y | N N N N N | 10 entries: missing identity fields |
| [Shadow Crime Lab](first_pass/039_shadow_crime_lab_env.json) | Retry | N N N N N | N N N N N | None |
| [Slot-Reel Character Capture](first_pass/040_slot_reel_capture_env.json) | Retry | N N N N N | N N N N N | None |
| [Parallax Orchard](first_pass/041_surreal_apple_on_tree_grid_env.json) | Retry | N N N N N | N N N N N | None |
| [First Change Memory](../historical_50_rerun_2026-09-20/first_pass/042_temporal_memory_first_change_env.json) | Original | N N N N N | N N N N N | None |
| [Three-Camera Claw Machine](first_pass/043_three_camera_claw_machine_env.json) | Retry | N N N N N | N N N N N | None |
| [Tiny FPS Customs](first_pass/044_tiny_fps_customs_env.json) | Retry | N N N N N | N N N N N | None |
| [Tomographic Baggage Surgery](first_pass/045_tomographic_baggage_surgery_env.json) | Retry | N N N N N | N N N N N | None |
| [Top-Face Dice Arithmetic](../historical_50_rerun_2026-09-20/first_pass/046_top_face_dice_arithmetic_env.json) | Original | N N N N N | N N N N N | None |
| [Blind Corridor Oscilloscope](first_pass/047_trace_shape_without_walls_env.json) | Retry | N N N N N | N N N N N | None |
| [Anamorphic Registration Press](first_pass/048_wonky_text_hostile_rendering_env.json) | Retry | N N N N N | N N N N N | None |
| [Wrong Number](first_pass/049_wrong_number_env.json) | Retry | N N N Y Y | N N N Y Y | None |
| [Zero-G Cable Autopsy](../historical_50_rerun_2026-09-20/first_pass/050_zero_g_cable_autopsy_env.json) | Original | N N N N N | N N N N N | None |

## Machine-readable records

- [results.json](results.json): the 25 retry attempts, raw judgments, hashes, and original-attempt references.
- [combined_results.json](combined_results.json): all 50 selected completed reviews, retained flags, and 48 historical-label disagreements.
- [preserved_parent_files.json](preserved_parent_files.json): hashes for all 211 preserved original artifacts.
