from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any


# The `temporal` values in ANNOTATIONS are the original environment-level
# classifications. They are intentionally preserved for reproducibility and
# are not the current difficulty-by-interaction classification. See the dated
# snapshot and the replacement definition linked below.
LEGACY_TEMPORAL_ANNOTATION_STATUS: dict[str, str] = {
    "status": "legacy_environment_level",
    "marked_old": "2026-08-13",
    "snapshot": "weird_captcha_gym/temporal_audits/legacy_environment_annotations_2026-08-13.json",
    "current_definition": "weird_captcha_gym/docs/controllability/temporal.md",
}


CAPABILITY_DEFINITIONS: tuple[dict[str, str], ...] = (
    {
        "id": "visual_understanding",
        "name": "Visual understanding",
        "description": "Understanding visible state and its 2D or 3D spatial relationships.",
    },
    {
        "id": "temporal_understanding_memory",
        "name": "Temporal understanding and memory",
        "description": "Understanding motion, duration, change across frames, or relevant state that is no longer visible.",
    },
    {
        "id": "reasoning_planning",
        "name": "Reasoning and planning",
        "description": "Inferring constraints and choosing actions whose consequences matter later.",
    },
    {
        "id": "exploration_interface_understanding",
        "name": "Exploration and interface understanding",
        "description": "Interacting to reveal relevant information or learn how the interface behaves before solving the task.",
    },
)


ANNOTATIONS: dict[str, dict[str, Any]] = {
    "cockpit_preflight_checklist": {
        "public_name": "Cockpit Preflight Checklist",
        "real_time": "no",
        "interaction": "Start on each range thumb or rotary indicator and move it through a direct pointer gesture, disclose treegrid branches, set circuit cells, and certify; simplified mode provides labelled step and cycle controls with the same linked effects.",
        "difficulty": "Calibration-chain length, sealed downstream targets, persistent readout availability, real parent-child disclosure, and circuit structure; the exact original panel configuration is assigned to L2.",
        "visual": "2D",
        "temporal": False,
        "reasoning_planning": True,
        "exploration_interface": True,
    },
    # Seed examples reviewed with the benchmark author.
    "board_game_captcha": {
        "public_name": "Gyroscopic Tilt Board",
        "real_time": "yes",
        "interaction": "Continuously drag an analog tilt control, then reset or certify the run.",
        "difficulty": "Board geometry, hazards, ordered lamps, physics parameters, and mirroring.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "cursor_constellation_hunt": {
        "public_name": "Cursor-Controlled Constellation Hunt",
        "real_time": "no",
        "interaction": "Move the cursor to reveal the field, then click the discovered position.",
        "difficulty": "Search area, noise stars, decoy regions, reveal radius, and target shape.",
        "visual": "2D",
        "temporal": False,
        "reasoning_planning": False,
        "exploration_interface": True,
    },
    "cursor_lens_reveal": {
        "public_name": "Polarized Palimpsest",
        "real_time": "yes",
        "interaction": "Scan with the cursor, change polarization, then hold and track moving echoes.",
        "difficulty": "Echo count, clutter, polarizations, motion paths, lens radius, and hold duration.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": False,
        "exploration_interface": True,
    },
    "exact_change_candy_cascade": {
        "public_name": "Exact-Change Candy Cascade",
        "real_time": "no",
        "interaction": "Click or drag adjacent swaps, reset the board, and submit the result.",
        "difficulty": "Board size, move budget, target score, candy types, cascades, and refill stream.",
        "visual": "2D",
        "temporal": False,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "flat_pack_compliance": {
        "public_name": "Flat-Pack Compliance Test",
        "real_time": "no",
        "interaction": "Drag and rotate parts, select sockets, lock joints, and run the load test.",
        "difficulty": "Part count, shapes, orientations, joint graph, load pattern, and tolerances.",
        "visual": "2D",
        "temporal": False,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "flat_prisoner": {
        "public_name": "The Flat Prisoner",
        "real_time": "yes",
        "interaction": "Manipulate the camera, freeze a view, then control the prisoner with held keys.",
        "difficulty": "Platform geometry, depth, camera solution, gaps, decoys, and movement physics.",
        "visual": "3D",
        "temporal": True,
        "reasoning_planning": True,
        "exploration_interface": True,
    },
    "input_lag_forklift": {
        "public_name": "Input-Lag Forklift",
        "real_time": "no",
        "interaction": "Use keyboard or direction buttons through a delayed command queue.",
        "difficulty": "Walls, crates, goals, transformed layouts, and input delay.",
        "visual": "2D",
        "temporal": False,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "insider_trading_captcha": {
        "public_name": "Insider Trading CAPTCHA",
        "real_time": "yes",
        "interaction": "Choose buy, hold, or sell during each live market tick.",
        "difficulty": "Tape length, tick rate, volatility, settlement delay, fees, position limit, and profit target.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "minecraft_block_grid": {
        "public_name": "Isometric Voxel Extraction Mine",
        "real_time": "no",
        "interaction": "Rotate viewpoints and click exposed voxel faces to mine them.",
        "difficulty": "Grid depth, targets, blockers, occlusion, hazards, durability, and viewpoints.",
        "visual": "3D",
        "temporal": False,
        "reasoning_planning": True,
        "exploration_interface": True,
    },
    "motion_only_ghost_jigsaw": {
        "public_name": "Motion-Only Ghost Jigsaw",
        "real_time": "observation_only",
        "interaction": "Drag nine animated pieces into fixed destination slots.",
        "difficulty": "Piece count, grid size, pattern, noise field, motion speed, and shuffle.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": False,
        "exploration_interface": False,
    },
    "rotate_wrong_thing_upright": {
        "public_name": "Rotate The Wrong Thing Upright",
        "real_time": "no",
        "interaction": "Switch among three views and drag three coupled axis controls.",
        "difficulty": "Initial angles, coupling values, required views, and tolerance.",
        "visual": "3D",
        "temporal": False,
        "reasoning_planning": True,
        "exploration_interface": True,
    },
    "rotating_keyboard": {
        "public_name": "Rotating On-Screen Keyboard",
        "real_time": "yes",
        "interaction": "Click keys on a keyboard rotating across three axes.",
        "difficulty": "Code length, keyboard size, rotation direction, and rotation speed.",
        "visual": "3D",
        "temporal": False,
        "reasoning_planning": False,
        "exploration_interface": False,
    },
    "slime_commute": {
        "public_name": "Slime Commute",
        "real_time": "yes",
        "interaction": "Use timed keyboard hops through moving traffic, rails, and water lanes.",
        "difficulty": "Lane count, entity count, speeds, support lengths, lives, start, and goal.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "specular_lighthouse_relay": {
        "public_name": "Specular Lighthouse Relay",
        "real_time": "yes",
        "interaction": "Adjust three mirrors and control the live tracking shutter.",
        "difficulty": "Mirror count, rounds, geometry, receiver motion, tolerance, charge duration, and miss decay.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "surreal_apple_on_tree_grid": {
        "public_name": "Parallax Orchard",
        "real_time": "no",
        "interaction": "Drag to orbit the orchard, then drag selected fruit into the basket.",
        "difficulty": "Fruit count, false contacts, depth separation, and required viewpoints.",
        "visual": "3D",
        "temporal": False,
        "reasoning_planning": False,
        "exploration_interface": True,
    },

    # Additional environments, reviewed one implementation at a time.
    "parallel_grillmaster": {
        "public_name": "Parallel Grillmaster",
        "real_time": "yes",
        "interaction": "Drag food from preparation to the grill, then to the tray during its ready interval.",
        "difficulty": "Food count, cooking durations, readiness tolerances, and concurrent cooking.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": False,
        "exploration_interface": False,
    },
    "slot_reel_capture": {
        "public_name": "Slot-Reel Character Capture",
        "real_time": "yes",
        "interaction": "Press the currently displayed letter or number while it is centered on the active reel.",
        "difficulty": "Reel count, symbol count, reel intervals, phases, and strike budget.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": False,
        "exploration_interface": False,
    },
    "domino_autopsy": {
        "public_name": "Domino Autopsy",
        "real_time": "no",
        "interaction": "Drag and rotate loose dominoes, run the physics simulation, and rewind when needed.",
        "difficulty": "Fixed and loose body count, gap geometry, initial angles, physics, and bell threshold.",
        "visual": "2D",
        "temporal": False,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "consequences_boss": {
        "public_name": "Consequences Boss",
        "real_time": "no",
        "interaction": "Drag each relic into a socket, rotate its seal, and reconstruct every covenant after occlusion.",
        "difficulty": "Scene count, socket choices, seal orientations, occlusion duration, and reconstruction order.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": False,
        "exploration_interface": False,
    },
    "popup_exorcist": {
        "public_name": "Popup Exorcist",
        "real_time": "no",
        "interaction": "Focus, close, and drag overlapping windows until an infected echo is contained.",
        "difficulty": "Popup count, overlap, stacking order, parasite identity, echo count, and containment position.",
        "visual": "2D",
        "temporal": False,
        "reasoning_planning": False,
        "exploration_interface": True,
    },
    "funeral_ritual": {
        "public_name": "Funeral With No Instructions",
        "real_time": "no",
        "interaction": "Inspect the grave, brush moss, light the candle, gather flowers, and drag the bouquet into place.",
        "difficulty": "Ritual stage count, moss coverage threshold, flower count, and affordance visibility.",
        "visual": "2D",
        "temporal": False,
        "reasoning_planning": True,
        "exploration_interface": True,
    },
    "semantic_drag_drop_absurdity": {
        "public_name": "Semantic Drag-Drop Absurdity",
        "real_time": "yes",
        "interaction": "Hold two probe tools over each specimen, observe the transient responses, then drag every specimen to its matching receiver.",
        "difficulty": "Specimen count, response dimensions, probe hold duration, response duration, receiver count, and spatial arrangement.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": True,
        "exploration_interface": True,
    },
    "reload_interruption": {
        "public_name": "Reload Interruption",
        "real_time": "yes",
        "interaction": "Watch a one-time gesture preview, drag the lever through the sequence, and hold the pointer on each moving overload spark.",
        "difficulty": "Sequence length, preview rate, interruption count, target paths, tracking tolerance, hold duration, and sampling continuity.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": False,
        "exploration_interface": False,
    },
    "bureaucratic_signature_trap": {
        "public_name": "Bureaucratic Signature Trap",
        "real_time": "no",
        "interaction": "Drag four sheet controls into registration, then reproduce the revealed signature in one continuous pointer stroke.",
        "difficulty": "Layer count, initial offsets, alignment tolerance, signature geometry, path tolerance, coverage, and sampling limits.",
        "visual": "2D",
        "temporal": False,
        "reasoning_planning": False,
        "exploration_interface": True,
    },
    "wonky_text_hostile_rendering": {
        "public_name": "Anamorphic Registration Press",
        "real_time": "no",
        "interaction": "Drag three optical wheels, lock each registered plate, then press the composite image.",
        "difficulty": "Plate count, initial and target angles, nonlinear warping, registration tolerance, and drag limits.",
        "visual": "2D",
        "temporal": False,
        "reasoning_planning": False,
        "exploration_interface": True,
    },
    "temporal_memory_first_change": {
        "public_name": "First Change Memory",
        "real_time": "no",
        "interaction": "Run the field once, scrub its recorded timeline, inspect moving objects through the cursor lens, then select the carrier after the field settles.",
        "difficulty": "Object count, trajectories, event timing, decoy changes, occluders, lens radius, and identity shuffle.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": False,
        "exploration_interface": True,
    },
    "modifier_stack_image_grid": {
        "public_name": "Kinetic Restoration Press",
        "real_time": "observation_only",
        "interaction": "Use the visible press-card inverse template to arrange and invert three modules, then drag the artifact continuously through the restoration rail.",
        "difficulty": "The preserved L3 configuration has three artifacts, three modules, one replay, four drag samples per module, and a timed three-gate rail. Controlled L4 and L5 hide the template and ready-state signal after the film.",
        "visual": "2D",
        "temporal": False,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "shadow_crime_lab": {
        "public_name": "Shadow Crime Lab",
        "real_time": "no",
        "interaction": "Drag the lamp through four probe zones, compare the resulting shadows, then drag an evidence tag onto the physically inconsistent shadow.",
        "difficulty": "Object geometry, light type, probe positions, forged response law, travel requirement, overlap, and tag location.",
        "visual": "3D",
        "temporal": False,
        "reasoning_planning": True,
        "exploration_interface": True,
    },
    "craftcha_alchemy_bench": {
        "public_name": "CRAFTCHA: Alchemy Bench",
        "real_time": "observation_only",
        "interaction": "Study a transient recipe, drag three materials through their required machines, assemble the terminal intermediates, and deliver the device.",
        "difficulty": "Branch count, transformations per branch, station sequence, inventory capacity, recipe duration, replay budget, and destructive errors.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "occlusion_shell_swindle": {
        "public_name": "Occlusion Shell Swindle",
        "real_time": "yes",
        "interaction": "Start each shuffle, track the marked carrier, hold the cursor over a timed peephole, then select the final carrier.",
        "difficulty": "Shell count, frame count, trajectories, occluders, transfer rounds, peephole interval, sample requirement, and round count.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": False,
        "exploration_interface": False,
    },
    "ribbon_switchboard": {
        "public_name": "Ribbon Switchboard",
        "real_time": "no",
        "interaction": "Inspect the weave by hovering, then press and hold the marked source while tracing its ribbon to the correct terminal.",
        "difficulty": "Ribbon count, curve geometry, crossing count, over-under order, reveal radius, trace tolerance, and sample requirements.",
        "visual": "2D",
        "temporal": False,
        "reasoning_planning": False,
        "exploration_interface": True,
    },
    "magnetic_stripe_purgatory": {
        "public_name": "Magnetic-Stripe Purgatory",
        "real_time": "yes",
        "interaction": "Match and insert three cards, then perform straight directional swipes whose durations satisfy three hidden reader windows.",
        "difficulty": "Card-reader assignment, swipe direction, timing windows, path tolerance, sample density, interference zones, and reader count.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": False,
        "exploration_interface": True,
    },
    "trajectory_catcher": {
        "public_name": "Trajectory Catcher",
        "real_time": "yes",
        "interaction": "Observe each moving projectile, then drag, rotate, resize, and arm a catcher while the projectile is occluded.",
        "difficulty": "Trajectory family, speed, occlusion duration, catcher geometry, placement tolerance, orientation tolerance, replay budget, and round count.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "impossible_panorama": {
        "public_name": "Impossible Panorama",
        "real_time": "yes",
        "interaction": "Pan a large world, adjust zoom and focal depth, center the moving target, then hold the shutter through its transient event.",
        "difficulty": "World size, object count, target motion, event period, zoom range, focal depth, reticle tolerance, hold duration, and sample continuity.",
        "visual": "3D",
        "temporal": True,
        "reasoning_planning": False,
        "exploration_interface": True,
    },
    "crash_deadline_hovercar": {
        "public_name": "Crash-Deadline Hovercar",
        "real_time": "yes",
        "interaction": "Drive continuously with held keys while using the pointer to track five moving inspection targets within their time windows.",
        "difficulty": "Road curvature, obstacles, vehicle physics, target paths, dwell durations, target windows, speed tradeoffs, and deadline.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "robot_art_critic": {
        "public_name": "Robot Art Critic",
        "real_time": "no",
        "interaction": "Draw a named object with continuous pointer strokes, then request recognition and optionally revise the drawing.",
        "difficulty": "Object class, pose, width, stroke budget, composition bounds, recognition threshold, class margin, and attempt budget.",
        "visual": "2D",
        "temporal": False,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "photograph_eats_the_room": {
        "public_name": "Photograph Eats the Room",
        "real_time": "yes",
        "interaction": "Navigate a perspective room with held movement, photograph visible geometry, transform each print, and develop it back into the room.",
        "difficulty": "Room geometry, capture locations, projection parameters, placement transforms, collision barriers, and required travel.",
        "visual": "3D",
        "temporal": False,
        "reasoning_planning": True,
        "exploration_interface": True,
    },
    "clockwork_doppelganger_customs": {
        "public_name": "Clockwork Doppelgänger Customs",
        "real_time": "yes",
        "interaction": "Record three timed pointer paths with embedded actions, set their phase offsets, and replay them concurrently.",
        "difficulty": "Path geometry, recording duration, conveyor speed, action timing, handoff windows, phase resolution, and loop duration.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": True,
        "exploration_interface": True,
    },
    "recursive_dollhouse_smuggling": {
        "public_name": "Recursive Dollhouse Smuggling",
        "real_time": "no",
        "interaction": "Drag a linked gate and parcel through three isometric views, two scale transitions, and the final bay.",
        "difficulty": "Projection matrices, room obstacles, object sizes, portal sizes, route geometry, collision clearance, and scale transitions.",
        "visual": "3D",
        "temporal": False,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "forced_perspective_moving_day": {
        "public_name": "Forced-Perspective Moving Day",
        "real_time": "yes",
        "interaction": "Pick objects by ray, change their depth while preserving apparent size, release them into the world, then navigate with held keys.",
        "difficulty": "Camera projection, object depths, scale bounds, placement zones, collision geometry, bridge clearance, and movement route.",
        "visual": "3D",
        "temporal": False,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "lidar_blacksite": {
        "public_name": "LIDAR Blacksite",
        "real_time": "yes",
        "interaction": "Navigate with held movement and turning controls, emit directional scan pulses, pick up the revealed beacon, and carry it to extraction.",
        "difficulty": "Facility layout, occluders, scan range, ray density, return lifetime, beacon location, movement geometry, and scan-station requirements.",
        "visual": "3D",
        "temporal": True,
        "reasoning_planning": True,
        "exploration_interface": True,
    },
    "tomographic_baggage_surgery": {
        "public_name": "Tomographic Baggage Surgery",
        "real_time": "no",
        "interaction": "Sweep and rotate slice planes, lock the case, move one probe through orthogonal views, capture the target, and withdraw it.",
        "difficulty": "Solid count, primitive geometry, target position, slice offsets, case rotations, probe radius, obstacle clearance, and observation requirements.",
        "visual": "3D",
        "temporal": True,
        "reasoning_planning": True,
        "exploration_interface": True,
    },
    "three_camera_claw_machine": {
        "public_name": "Three-Camera Claw Machine",
        "real_time": "no",
        "interaction": "Apply discrete three-axis acceleration, coast or brake one physics tick, operate the gripper, and monitor three delayed camera feeds.",
        "difficulty": "Target and chute positions, obstacle geometry, camera delays, acceleration, damping, speed limit, capture tolerance, and tick budget.",
        "visual": "3D",
        "temporal": True,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "zero_g_cable_autopsy": {
        "public_name": "Zero-G Cable Autopsy",
        "real_time": "no",
        "interaction": "Orbit the camera, attach two grippers to cable nodes, move each gripper along three axes, and settle the cable physics.",
        "difficulty": "Cable winding, node count, constraints, peg sizes, ring positions, contact hazards, movement step, and physics iterations.",
        "visual": "3D",
        "temporal": False,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "portal_freight_oversized_parcel": {
        "public_name": "Portal Freight: Oversized Parcel",
        "real_time": "no",
        "interaction": "Aim and place linked portals in two chambers, rotate the parcel, and push it through the apertures in fixed increments.",
        "difficulty": "Portal walls, placement rays, aperture size, parcel length and angle, receiver orientation, transform geometry, and push count.",
        "visual": "2D",
        "temporal": False,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "wind_tunnel_seed_courier": {
        "public_name": "Wind-Tunnel Seed Courier",
        "real_time": "yes",
        "interaction": "Launch two pods, switch four shared fans among lift, coast, and press during flight, and manage their heat.",
        "difficulty": "Pod responses, fan locations, spool rate, heat limits, gate motion, aperture size, gust phase, dock positions, and flight duration.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "hologram_silhouette_foundry": {
        "public_name": "Hologram Silhouette Foundry",
        "real_time": "no",
        "interaction": "Select six colored rods, translate them through a voxel grid, rotate their axes, and cast the resulting three projections.",
        "difficulty": "Grid size, rod positions, rod axes, color assignment, occlusion depth, projection ambiguity, and non-overlap constraints.",
        "visual": "3D",
        "temporal": False,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "orbital_docking_customs": {
        "public_name": "Orbital Docking Customs",
        "real_time": "no",
        "interaction": "Apply discrete RCS impulses and rotations, coast by fixed tick intervals, pass two scan beacons, and request a hard dock.",
        "difficulty": "Fuel, impulse size, coast interval, debris geometry, beacon route, ship velocity, station motion, port rotation, and docking tolerances.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "gravity_room_freight": {
        "public_name": "Gravity-Room Freight",
        "real_time": "no",
        "interaction": "Rotate the room clockwise or counterclockwise so two bodies slide together, then certify their final positions.",
        "difficulty": "Wall layout, body starting positions, ordered seals, two target cells, shared rotations, and solution length.",
        "visual": "2D",
        "temporal": False,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "floodgate_archive_rescue": {
        "public_name": "Floodgate Archive Rescue",
        "real_time": "no",
        "interaction": "Pump fixed water quantities among five vaults, toggle one lock, transfer eligible capsules, and certify both docks.",
        "difficulty": "Initial water levels, safe bands, circuit graph, equality tolerance, capsule positions, crossing order, and pump count.",
        "visual": "2D",
        "temporal": False,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "elastic_membrane_sorter": {
        "public_name": "Elastic Membrane Sorter",
        "real_time": "yes",
        "interaction": "Release each marble and continuously adjust four tension sliders while it rolls across the membrane.",
        "difficulty": "Marble courses, well assignment, post response, acceleration, drag, ring positions, capture radius, speed threshold, and time limit.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "pheromone_dispatch": {
        "public_name": "Pheromone Dispatch",
        "real_time": "yes",
        "interaction": "Select each color, trace its nest-to-cache-to-dock route, release both swarms, and retrace each route before it decays.",
        "difficulty": "Field count, cache positions, obstacle geometry, route length, ant count, swarm speed, decay interval, and delivery target.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "clockwork_clutch_safe": {
        "public_name": "Clockwork Clutch Safe",
        "real_time": "yes",
        "interaction": "Start or brake the drive, release or re-engage four clutches during rotation, and try the safe.",
        "difficulty": "Shaft count, initial phases, gear ratios, drive speed, load redistribution, phase tolerance, release order, and tick limit.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "marionette_checkpoint": {
        "public_name": "Marionette Checkpoint",
        "real_time": "yes",
        "interaction": "Continuously adjust four string sliders to keep four coupled limbs inside their moving rings across three acts.",
        "difficulty": "Act count, target trajectories, motion phases, coupling strength, slider precision, ring radius, tracking duration, and miss penalty.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "wrong_number": {
        "public_name": "Wrong Number",
        "real_time": "yes",
        "interaction": "Select among seven lines, tune phase and waveform shape, start a lock test, and keep correcting phase drift.",
        "difficulty": "Line count, phase resolution, shape range, distortion, drift rate, lock tolerance, test duration, and sampling requirement.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": False,
        "exploration_interface": True,
    },
    "bomb_manual_from_hell": {
        "public_name": "Bomb Manual From Hell",
        "real_time": "no",
        "interaction": "Select five transparent plates, drag rotate and flip each onto matching pins, select the exposed wire, and cut it.",
        "difficulty": "Plate count, wire count, initial poses, anchor layouts, aperture sets, rotation step, alignment tolerance, and decoy overlap.",
        "visual": "2D",
        "temporal": False,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "dead_mans_switch": {
        "public_name": "Dead Man's Switch",
        "real_time": "yes",
        "interaction": "Track and hold a moving pressure plate with the pointer while steering a vehicle with the keyboard.",
        "difficulty": "Grid size, wall layout, checkpoint count, route length, plate trajectory, hit area, hold duration, grace period, and sampling interval.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "blind_dice_courier": {
        "public_name": "Blind Dice Courier",
        "real_time": "no",
        "interaction": "Roll the die-crate through the warehouse with directional keys and optionally reset to its initial state.",
        "difficulty": "Grid geometry, route length, initial orientation, gate count, required top faces, scanner placement, and decoy paths.",
        "visual": "3D",
        "temporal": True,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "polyrhythm_customs": {
        "public_name": "Polyrhythm Customs",
        "real_time": "yes",
        "interaction": "Watch four lane previews then reproduce their combined taps holds and chords with four keys or buttons.",
        "difficulty": "Lane count, note count, preview speed, rhythm spacing, hold count, chord count, timing windows, and accuracy threshold.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": False,
        "exploration_interface": False,
    },
    "tiny_fps_customs": {
        "public_name": "Tiny FPS Customs",
        "real_time": "no",
        "interaction": "Move strafe and turn through a first person maze then aim and fire at selected creatures.",
        "difficulty": "Maze topology, route length, creature count, visual trait similarity, visibility, ammunition, movement step, and aiming precision.",
        "visual": "3D",
        "temporal": False,
        "reasoning_planning": True,
        "exploration_interface": True,
    },
    "thirty_year_time_wheel": {
        "public_name": "Thirty-Year Time Wheel",
        "real_time": "yes",
        "interaction": "Drag three concentric calendar rings through detents, brake release momentum, reset, and lock the resulting date.",
        "difficulty": "Date span, start and target dates, month lengths, leap years, ring offsets, drag distance, inertia speed, coast length, and brake timing.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "code_to_diagram_captcha": {
        "public_name": "Live Control-Flow Wiring Lab",
        "real_time": "observation_only",
        "interaction": "Run four probes one debugger step at a time then drag ten output cords to node inputs.",
        "difficulty": "Node count, branch count, probe count, trace length, arithmetic conditions, transient display duration, edge count, and graph layout.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": True,
        "exploration_interface": True,
    },
    "exit_vim_terminal_escape": {
        "public_name": "Modal Terminal Escape",
        "real_time": "no",
        "interaction": "Navigate four Vim buffers, replace six lines through modal key commands, write and quit, then type each terminal-layer escape.",
        "difficulty": "Field count, buffer count, value length, editor operations, layer count, layer order, command variety, and typing length.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "fake_desktop_automation_inversion": {
        "public_name": "Fake Desktop / Automation Inversion",
        "real_time": "no",
        "interaction": "Use a transformed remote cursor to close and move overlapping windows, drag two files in order, and arm the verifier.",
        "difficulty": "Window geometry, occlusion, z-order, pointer mappings, mapping order, file count, target order, drag distance, and workflow length.",
        "visual": "2D",
        "temporal": False,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "impossible_ecology": {
        "public_name": "Impossible Ecology",
        "real_time": "yes",
        "interaction": "Run a calibration film then select global fields and hold or move the pointer to shepherd five organisms simultaneously.",
        "difficulty": "Organism count, field count, hidden response matrix, sanctuary layout, obstacle geometry, damping, speed, capture tolerance, and tick budget.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": True,
        "exploration_interface": True,
    },
    "moving_checkbox_evasive_button": {
        "public_name": "Scroll-Cage Checkbox",
        "real_time": "yes",
        "interaction": "Scroll four shafts to align three portal pairs then move the cursor to repel the checkbox through the gates into its clamp and check it.",
        "difficulty": "Shaft count, portal count, offsets, alignment tolerance, route heights, field radius, acceleration, friction, speed, gate width, and clamp position.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "reverse_identity_gate": {
        "public_name": "Four-Tab Robot Handshake",
        "real_time": "yes",
        "interaction": "Deploy four browser tabs, follow the indicated tab, drive its receiver with the keyboard, and hold pointer contact during each of eight phase relays.",
        "difficulty": "Tab count, relay count, station order, phase positions, pulse speed, receiver speed, capture tolerance, hold duration, charge decay, and tick budget.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": False,
        "exploration_interface": False,
    },
    "jigsaw_slider_alignment": {
        "public_name": "Parallax / Inertial Jigsaw Alignment",
        "real_time": "no",
        "interaction": "Drag the fragment along a horizontal rail, drag a separate depth control, rotate the fragment with buttons, and hold the optical lock.",
        "difficulty": "Layer count, parallax rates, target depth, target position, initial displacement, initial rotation, alignment tolerances, release inertia, and hold duration.",
        "visual": "3D",
        "temporal": False,
        "reasoning_planning": False,
        "exploration_interface": True,
    },
    "microgame_gauntlet": {
        "public_name": "Five-System Verification Reactor",
        "real_time": "yes",
        "interaction": "Complete a shuffled set of five trials using held keys, simultaneous key chords, ordered clicks, inertial dial dragging, timed interception, and constrained dragging.",
        "difficulty": "Round order, pulse count, chord sequence, charge duration, dial target, inertia, packet speeds, gate positions, route geometry, corridor width, and shared fault budget.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "relation_prompt_grounding": {
        "public_name": "Dual-Projection Sculpture Rig",
        "real_time": "no",
        "interaction": "Drag five objects from a moving carousel, position them on a worktable, select each object, adjust its depth, run the force inspection, reset if needed, and certify.",
        "difficulty": "Object count, carousel speed, target projections, depth ordering, placement tolerance, settle vectors, settle duration, object overlap, and number of reconstruction cycles.",
        "visual": "3D",
        "temporal": True,
        "reasoning_planning": True,
        "exploration_interface": True,
    },
    "rorschach_fixed_rubric": {
        "public_name": "Rorschach / Subjective Prompt With A Fixed Rubric",
        "real_time": "yes",
        "interaction": "Select each specimen, apply two required tests through a sweep hold or pulse, read the archived response labels, then drag a stamp onto the matching specimen.",
        "difficulty": "Specimen count, tool pair, response signatures, response duration, visual similarity, fold distance, pressure duration, rubric conjunction, and stamp precision.",
        "visual": "2D",
        "temporal": False,
        "reasoning_planning": True,
        "exploration_interface": True,
    },
    "single_scene_split_boxes": {
        "public_name": "Live Shattered-Scene Synchronizer",
        "real_time": "observation_only",
        "interaction": "Swap nine animated shards by dragging, select and flip inverted shards, scrub each selected shard along a phase track, and hold scene sync.",
        "difficulty": "Grid size, tile permutation, inverted tile count, phase range, phase offsets, scene motion, visual similarity, seam continuity, and sync duration.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "top_face_dice_arithmetic": {
        "public_name": "Top-Face Dice Arithmetic",
        "real_time": "no",
        "interaction": "Select each of four dice, roll it through a rail with keyboard keys or direction buttons, optionally rotate the table view, and weigh the docked set.",
        "difficulty": "Die count, initial orientations, rail geometry, route length, housing occlusion, scanner placement, target sum, view transformation, and available final orientations.",
        "visual": "3D",
        "temporal": True,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
    "trace_shape_without_walls": {
        "public_name": "Blind Corridor Oscilloscope",
        "real_time": "yes",
        "interaction": "Move the pointer to emit local sonar, press and hold at the start, continuously trace the hidden corridor while compensating for crosswind, release at the exit, and rearm after a breach.",
        "difficulty": "Path length, curvature, branch count, sonar radius, fade duration, required map coverage, corridor width, drift amplitude, drift rate, checkpoint count, and trace precision.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": True,
        "exploration_interface": True,
    },
    "wizard_critter_capture": {
        "public_name": "Wizard Interception Observatory",
        "real_time": "yes",
        "interaction": "Use the marked familiar reference plate, place one lure, hold and release the freeze key, track the target, and launch a traveling net at a predicted interception point.",
        "difficulty": "Creature count, visual similarity, preview duration, target motion, occluder geometry, portal crossings, lure placement, freeze budget, projectile flight time, net count, and time limit.",
        "visual": "2D",
        "temporal": True,
        "reasoning_planning": True,
        "exploration_interface": False,
    },
}


# The source-reviewed configuration matrix is deliberately kept separate from
# the legacy environment-level annotation table above.  The latter is used by
# older dashboard consumers and must remain a stable compatibility surface.
CAPABILITY_AUDIT_PATH = (
    Path(__file__).resolve().parents[1]
    / "capability_audits"
    / "new_environments_2026-09-08.json"
)
_AUDIT_STATUS = "adjudicated_source_review"
_AUDIT_ROOT_REQUIRED_KEYS = {"schema_version", "source_revision", "status", "environments"}
_AUDIT_ROOT_METADATA_KEYS = {
    "initial_review_date",
    "adjudicated_at",
    "scope",
    "method",
    "temporal_scope",
    "historical_preservation",
}
_AUDIT_ENTRY_REQUIRED_KEYS = {
    "environment_id",
    "public_name",
    "baseline",
    "baseline_description",
    "labels",
    "rationale",
    "configuration_exceptions",
    "source_evidence",
    "limitations",
}
_AUDIT_ENTRY_METADATA_KEYS = {"first_pass_sha256", "review_scope"}
_AUDIT_CACHE: tuple[int, int, dict[str, Any]] | None = None
_LABEL_KEYS = ("visual", "temporal", "reasoning_planning", "exploration_interface")
_RATIONALE_METADATA_KEYS = {"configuration_review"}
_INTERACTION_MODES = ("full", "simplified")
_CAPABILITY_NAMES = {
    "temporal": "temporal understanding and memory",
    "reasoning_planning": "reasoning and planning",
    "exploration_interface": "exploration and interface understanding",
}


def _is_strict_int(value: Any) -> bool:
    return type(value) is int


def _require_nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"capability audit {field} must be a non-empty string")
    return value


def _validate_labels(labels: Any, field: str = "labels") -> dict[str, bool | str]:
    if not isinstance(labels, dict) or set(labels) != set(_LABEL_KEYS):
        raise ValueError(f"capability audit {field} must contain exactly {_LABEL_KEYS!r}")
    visual = labels["visual"]
    if visual not in {"2D", "3D"}:
        raise ValueError(f"capability audit {field}.visual must be '2D' or '3D'")
    output: dict[str, bool | str] = {"visual": visual}
    for key in _LABEL_KEYS[1:]:
        value = labels[key]
        if type(value) is not bool:
            raise ValueError(f"capability audit {field}.{key} must be boolean")
        output[key] = value
    return output


def _validate_exception(
    exception: Any,
    index: int,
    seen: dict[tuple[int, str, str], bool | str],
) -> dict[str, Any]:
    if not isinstance(exception, dict):
        raise ValueError(f"capability audit configuration exception {index} must be an object")
    expected = {
        "difficulties",
        "interaction_modes",
        "capability",
        "label",
        "reason",
        "source_evidence",
    }
    if set(exception) != expected:
        raise ValueError(
            f"capability audit configuration exception {index} has an invalid shape"
        )
    difficulties = exception["difficulties"]
    if (
        not isinstance(difficulties, list)
        or not difficulties
        or any(not _is_strict_int(level) or level not in range(1, 6) for level in difficulties)
        or len(set(difficulties)) != len(difficulties)
    ):
        raise ValueError(
            f"capability audit configuration exception {index}.difficulties is invalid"
        )
    interaction_modes = exception["interaction_modes"]
    if (
        not isinstance(interaction_modes, list)
        or not interaction_modes
        or any(mode not in _INTERACTION_MODES for mode in interaction_modes)
        or len(set(interaction_modes)) != len(interaction_modes)
    ):
        raise ValueError(
            f"capability audit configuration exception {index}.interaction_modes is invalid"
        )
    capability = exception["capability"]
    if capability not in _LABEL_KEYS:
        raise ValueError(
            f"capability audit configuration exception {index}.capability is invalid"
        )
    label = exception["label"]
    if capability == "visual":
        if label not in {"2D", "3D"}:
            raise ValueError(
                f"capability audit configuration exception {index}.visual label is invalid"
            )
    elif type(label) is not bool:
        raise ValueError(
            f"capability audit configuration exception {index}.{capability} label must be boolean"
        )
    _require_nonempty_string(exception["reason"], f"configuration_exceptions[{index}].reason")
    if not isinstance(exception["source_evidence"], list):
        raise ValueError(
            f"capability audit configuration exception {index}.source_evidence must be a list"
        )

    for difficulty in difficulties:
        for mode in interaction_modes:
            key = (difficulty, mode, capability)
            previous = seen.get(key)
            if previous is not None and previous != label:
                raise ValueError(
                    "capability audit contains conflicting configuration overrides "
                    f"for difficulty {difficulty}, interaction {mode}, capability {capability}"
                )
            seen[key] = label
    return deepcopy(exception)


def _validate_audit_payload(payload: Any) -> dict[str, Any]:
    if (
        not isinstance(payload, dict)
        or not _AUDIT_ROOT_REQUIRED_KEYS.issubset(payload)
        or set(payload) - _AUDIT_ROOT_REQUIRED_KEYS - _AUDIT_ROOT_METADATA_KEYS
    ):
        raise ValueError("capability audit root has an invalid schema")
    if payload["schema_version"] != 1:
        raise ValueError("capability audit schema_version must be 1")
    _require_nonempty_string(payload["source_revision"], "source_revision")
    if payload["status"] != _AUDIT_STATUS:
        raise ValueError(f"capability audit status must be {_AUDIT_STATUS!r}")
    for key in _AUDIT_ROOT_METADATA_KEYS & set(payload):
        _require_nonempty_string(payload[key], key)
    environments = payload["environments"]
    if not isinstance(environments, dict) or len(environments) != 80:
        raise ValueError("capability audit must contain exactly 80 environments")

    for mechanic_id, entry in environments.items():
        if not isinstance(mechanic_id, str) or not mechanic_id.strip():
            raise ValueError("capability audit environment keys must be non-empty strings")
        if (
            not isinstance(entry, dict)
            or not _AUDIT_ENTRY_REQUIRED_KEYS.issubset(entry)
            or set(entry) - _AUDIT_ENTRY_REQUIRED_KEYS - _AUDIT_ENTRY_METADATA_KEYS
        ):
            raise ValueError(f"capability audit entry {mechanic_id!r} has an invalid schema")
        if entry["environment_id"] != f"{mechanic_id}_env":
            raise ValueError(
                f"capability audit {mechanic_id!r} environment_id does not match its key"
            )
        _require_nonempty_string(entry["public_name"], f"{mechanic_id}.public_name")

        baseline = entry["baseline"]
        if (
            not isinstance(baseline, dict)
            or set(baseline) != {"difficulty", "interaction"}
            or not _is_strict_int(baseline["difficulty"])
            or baseline["difficulty"] not in range(1, 6)
            or baseline["interaction"] not in _INTERACTION_MODES
        ):
            raise ValueError(f"capability audit {mechanic_id!r} baseline is invalid")

        baseline_description = entry["baseline_description"]
        if (
            not isinstance(baseline_description, dict)
            or set(baseline_description) != {"interaction", "difficulty"}
        ):
            raise ValueError(
                f"capability audit {mechanic_id!r} baseline_description is invalid"
            )
        _require_nonempty_string(
            baseline_description["interaction"],
            f"{mechanic_id}.baseline_description.interaction",
        )
        _require_nonempty_string(
            baseline_description["difficulty"],
            f"{mechanic_id}.baseline_description.difficulty",
        )

        _validate_labels(entry["labels"], f"{mechanic_id}.labels")
        rationale = entry["rationale"]
        if (
            not isinstance(rationale, dict)
            or not set(_LABEL_KEYS).issubset(rationale)
            or set(rationale) - set(_LABEL_KEYS) - _RATIONALE_METADATA_KEYS
        ):
            raise ValueError(f"capability audit {mechanic_id!r} rationale is invalid")
        for key in set(_LABEL_KEYS) | (_RATIONALE_METADATA_KEYS & set(rationale)):
            _require_nonempty_string(rationale[key], f"{mechanic_id}.rationale.{key}")

        exceptions = entry["configuration_exceptions"]
        if not isinstance(exceptions, list):
            raise ValueError(
                f"capability audit {mechanic_id!r} configuration_exceptions must be a list"
            )
        seen: dict[tuple[int, str, str], bool | str] = {}
        for index, exception in enumerate(exceptions):
            _validate_exception(exception, index, seen)

        if not isinstance(entry["source_evidence"], list):
            raise ValueError(f"capability audit {mechanic_id!r} source_evidence must be a list")
        limitations = entry["limitations"]
        if not isinstance(limitations, list) or any(not isinstance(item, str) for item in limitations):
            raise ValueError(f"capability audit {mechanic_id!r} limitations must be strings")
        if "first_pass_sha256" in entry:
            _require_nonempty_string(entry["first_pass_sha256"], f"{mechanic_id}.first_pass_sha256")
        if "review_scope" in entry:
            _require_nonempty_string(entry["review_scope"], f"{mechanic_id}.review_scope")
    return deepcopy(payload)


def load_capability_audit(path: str | Path | None = None) -> dict[str, Any]:
    """Load and validate the source-reviewed configuration audit.

    Missing data is left to the builders to handle as a compatibility fallback;
    a present but malformed file always raises ``ValueError``.
    """
    audit_path = Path(path) if path is not None else CAPABILITY_AUDIT_PATH
    try:
        payload = json.loads(audit_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"capability audit is not valid JSON: {audit_path}") from exc
    return _validate_audit_payload(payload)


def _optional_capability_audit() -> dict[str, Any] | None:
    global _AUDIT_CACHE
    try:
        stat = CAPABILITY_AUDIT_PATH.stat()
    except FileNotFoundError:
        return None
    cache_key = (stat.st_mtime_ns, stat.st_size)
    if _AUDIT_CACHE is not None and _AUDIT_CACHE[:2] == cache_key:
        return _AUDIT_CACHE[2]
    try:
        payload = load_capability_audit()
    except FileNotFoundError:
        return None
    _AUDIT_CACHE = (*cache_key, payload)
    return payload


def _labels_for_entry(entry: dict[str, Any], difficulty: int, interaction: str) -> dict[str, bool | str]:
    labels = _validate_labels(entry["labels"])
    for exception in entry["configuration_exceptions"]:
        if difficulty in exception["difficulties"] and interaction in exception["interaction_modes"]:
            labels[exception["capability"]] = exception["label"]
    return labels


def capability_definitions() -> list[dict[str, str]]:
    return deepcopy(list(CAPABILITY_DEFINITIONS))


def build_capability_annotations() -> dict[str, dict[str, Any]]:
    annotations = deepcopy(ANNOTATIONS)
    audit = _optional_capability_audit()
    if audit is None:
        return annotations

    for mechanic_id, entry in audit["environments"].items():
        existing = annotations.get(mechanic_id)
        if existing is None:
            # Keep the legacy annotation contract for newly audited mechanics.  In
            # particular, real_time is intentionally unknown rather than inferred
            # from the new capability review.
            annotations[mechanic_id] = {
                "public_name": entry["public_name"],
                "real_time": None,
                "interaction": entry["baseline_description"]["interaction"],
                "difficulty": entry["baseline_description"]["difficulty"],
                **deepcopy(entry["labels"]),
            }
            continue

        # Existing annotations carry historical real-time and control descriptions;
        # only the audited public name and four core capability labels are replaced.
        existing["public_name"] = entry["public_name"]
        existing.update(deepcopy(entry["labels"]))
    return annotations


def build_capability_profiles() -> dict[str, dict[str, Any]]:
    """Build the difficulty-by-interaction capability profiles from the audit."""
    audit = _optional_capability_audit()
    if audit is None:
        return {}

    profiles: dict[str, dict[str, Any]] = {}
    for mechanic_id, entry in audit["environments"].items():
        profiles[mechanic_id] = {
            "source_revision": audit["source_revision"],
            "status": audit["status"],
            "baseline": deepcopy(entry["baseline"]),
            "configurations": {
                mode: {
                    str(difficulty): _labels_for_entry(entry, difficulty, mode)
                    for difficulty in range(1, 6)
                }
                for mode in _INTERACTION_MODES
            },
            "rationale": deepcopy(entry["rationale"]),
            "configuration_exceptions": deepcopy(entry["configuration_exceptions"]),
        }
    return profiles


def get_capability_labels(
    mechanic_id: str,
    difficulty: int,
    interaction: str,
) -> dict[str, bool | str] | None:
    """Return labels for one audited mechanic configuration, if available."""
    if not isinstance(mechanic_id, str) or not isinstance(interaction, str):
        return None
    if not _is_strict_int(difficulty) or difficulty not in range(1, 6):
        return None
    if interaction not in _INTERACTION_MODES:
        return None
    audit = _optional_capability_audit()
    if audit is None:
        return None
    entry = audit["environments"].get(mechanic_id)
    if entry is None:
        return None
    return _labels_for_entry(entry, difficulty, interaction)


def capability_names(labels: dict[str, bool | str]) -> list[str]:
    """Return enabled capability names in the dashboard's stable display order."""
    normalized = _validate_labels(labels)
    names = [f"visual understanding: {normalized['visual']}"]
    for key in _LABEL_KEYS[1:]:
        if normalized[key]:
            names.append(_CAPABILITY_NAMES[key])
    return names


__all__ = [
    "ANNOTATIONS",
    "CAPABILITY_DEFINITIONS",
    "LEGACY_TEMPORAL_ANNOTATION_STATUS",
    "build_capability_annotations",
    "build_capability_profiles",
    "capability_names",
    "capability_definitions",
    "get_capability_labels",
    "load_capability_audit",
]
