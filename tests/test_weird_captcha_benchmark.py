from __future__ import annotations

import importlib.util
import json
import math
import os
import unittest

from gym_anything.registry import (
    get_tasks_for_environment,
    list_environments,
    resolve_benchmark_root,
)


class WeirdCaptchaBenchmarkTests(unittest.TestCase):
    def test_benchmark_package_resolves_by_name(self) -> None:
        root = resolve_benchmark_root("weird_captcha_gym")
        self.assertTrue((root / "environments").is_dir())
        self.assertTrue((root / "splits").is_dir())

    def test_all_75_current_envs_are_discoverable(self) -> None:
        envs = list_environments("weird_captcha_gym", split="all")
        self.assertEqual(len(envs), 75)
        self.assertIn("reverse_identity_gate_env", envs)
        self.assertIn("temporal_memory_first_change_env", envs)
        self.assertIn("motion_only_ghost_jigsaw_env", envs)
        self.assertIn("cursor_constellation_hunt_env", envs)
        self.assertIn("parallel_grillmaster_env", envs)
        self.assertIn("rotating_keyboard_env", envs)
        self.assertIn("slot_reel_capture_env", envs)
        self.assertIn("domino_autopsy_env", envs)
        self.assertIn("consequences_boss_env", envs)
        self.assertIn("popup_exorcist_env", envs)
        self.assertIn("funeral_ritual_env", envs)
        self.assertIn("slime_commute_env", envs)
        self.assertIn("wrong_number_env", envs)
        self.assertIn("bomb_manual_from_hell_env", envs)
        self.assertIn("dead_mans_switch_env", envs)
        self.assertIn("blind_dice_courier_env", envs)
        self.assertIn("input_lag_forklift_env", envs)
        self.assertIn("insider_trading_captcha_env", envs)
        self.assertIn("polyrhythm_customs_env", envs)
        self.assertIn("exact_change_candy_cascade_env", envs)
        self.assertIn("tiny_fps_customs_env", envs)
        self.assertIn("thirty_year_time_wheel_env", envs)
        self.assertIn("shadow_crime_lab_env", envs)
        self.assertIn("craftcha_alchemy_bench_env", envs)
        self.assertIn("occlusion_shell_swindle_env", envs)
        self.assertIn("ribbon_switchboard_env", envs)
        self.assertIn("magnetic_stripe_purgatory_env", envs)
        self.assertIn("trajectory_catcher_env", envs)
        self.assertIn("impossible_panorama_env", envs)
        self.assertIn("flat_pack_compliance_env", envs)
        self.assertIn("crash_deadline_hovercar_env", envs)
        self.assertIn("robot_art_critic_env", envs)
        self.assertIn("photograph_eats_the_room_env", envs)
        self.assertIn("clockwork_doppelganger_customs_env", envs)
        self.assertIn("recursive_dollhouse_smuggling_env", envs)
        self.assertIn("flat_prisoner_env", envs)
        self.assertIn("forced_perspective_moving_day_env", envs)
        self.assertIn("lidar_blacksite_env", envs)
        self.assertIn("tomographic_baggage_surgery_env", envs)
        self.assertIn("three_camera_claw_machine_env", envs)
        self.assertIn("zero_g_cable_autopsy_env", envs)
        self.assertIn("portal_freight_oversized_parcel_env", envs)
        self.assertIn("specular_lighthouse_relay_env", envs)
        self.assertIn("wind_tunnel_seed_courier_env", envs)
        self.assertIn("hologram_silhouette_foundry_env", envs)
        self.assertIn("orbital_docking_customs_env", envs)
        self.assertIn("gravity_room_freight_env", envs)
        self.assertIn("floodgate_archive_rescue_env", envs)
        self.assertIn("elastic_membrane_sorter_env", envs)
        self.assertIn("pheromone_dispatch_env", envs)
        self.assertIn("clockwork_clutch_safe_env", envs)
        self.assertIn("marionette_checkpoint_env", envs)

    def test_benchmark_manifest_matches_discovered_environment_folders(self) -> None:
        benchmark_root = resolve_benchmark_root("weird_captcha_gym")
        manifest = json.loads((benchmark_root / "benchmark_manifest.json").read_text(encoding="utf-8"))
        discovered = list_environments("weird_captcha_gym", split="all")
        self.assertEqual(manifest["environment_count"], len(discovered))
        self.assertEqual(set(manifest["environments"]), set(discovered))

    def test_initial_env_task_counts_are_discoverable(self) -> None:
        for env_name in list_environments("weird_captcha_gym", split="all"):
            tasks = get_tasks_for_environment(env_name, "weird_captcha_gym", split="all")
            self.assertEqual(len(tasks), 1, env_name)
            self.assertTrue(tasks[0].endswith("_seed_0001"), tasks[0])

    def test_all_environment_and_task_hook_scripts_are_executable(self) -> None:
        benchmark_root = resolve_benchmark_root("weird_captcha_gym")
        hooks = []
        for env_name in list_environments("weird_captcha_gym", split="all"):
            env_root = benchmark_root / "environments" / env_name
            hooks.extend(env_root.glob("scripts/*.sh"))
            hooks.extend(env_root.glob("tasks/*/*.sh"))
        self.assertEqual(len(hooks), 75 * 4)
        for hook in hooks:
            self.assertTrue(os.access(hook, os.X_OK), f"hook is not executable: {hook.relative_to(benchmark_root)}")

    def test_no_tasks_are_on_verified_surface_yet(self) -> None:
        envs = list_environments("weird_captcha_gym", split="verified")
        self.assertEqual(envs, [])

    def test_interaction_first_generators_are_deterministic_and_well_formed(self) -> None:
        benchmark_root = resolve_benchmark_root("weird_captcha_gym")
        setup_path = benchmark_root / "shared_scripts" / "setup_task.py"
        spec = importlib.util.spec_from_file_location("weird_captcha_setup_task_test", setup_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader if spec else None)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        mechanics = {
            "motion_only_ghost_jigsaw": (module.generate_motion_only_ghost_jigsaw, 9),
            "cursor_constellation_hunt": (module.generate_cursor_constellation_hunt, 138),
            "parallel_grillmaster": (module.generate_parallel_grillmaster, 6),
            "rotating_keyboard": (module.generate_rotating_keyboard, 5),
            "slot_reel_capture": (module.generate_slot_reel_capture, 5),
        }
        for mechanic, (generator, expected_size) in mechanics.items():
            task_path = benchmark_root / "environments" / f"{mechanic}_env" / "tasks" / f"{mechanic}_seed_0001" / "task.json"
            task = json.loads(task_path.read_text(encoding="utf-8"))
            public_a, truth_a = generator(task, f"fixed-{mechanic}")
            public_b, truth_b = generator(task, f"fixed-{mechanic}")
            public_c, truth_c = generator(task, f"other-{mechanic}")
            self.assertEqual(public_a, public_b, mechanic)
            self.assertEqual(truth_a, truth_b, mechanic)
            self.assertNotEqual(truth_a["challenge_id"], truth_c["challenge_id"], mechanic)
            self.assertEqual(public_a["mechanic_id"], mechanic)
            self.assertEqual(truth_a["mechanic_id"], mechanic)
            self.assertNotIn("seed", public_a)
            if mechanic == "motion_only_ghost_jigsaw":
                self.assertEqual(len(truth_a["expected_positions"]), expected_size)
            elif mechanic == "cursor_constellation_hunt":
                self.assertEqual(len(public_a["surface"]["stars"]), expected_size)
                self.assertGreater(truth_a["expected_click"]["radius"], 0)
            elif mechanic == "parallel_grillmaster":
                self.assertEqual(len(truth_a["targets"]), expected_size)
            elif mechanic == "rotating_keyboard":
                self.assertEqual(len(truth_a["target"]), expected_size)
            else:
                self.assertEqual(len(truth_a["sequence"]), expected_size)

    def test_interaction_second_generators_are_deterministic_and_well_formed(self) -> None:
        benchmark_root = resolve_benchmark_root("weird_captcha_gym")
        setup_path = benchmark_root / "shared_scripts" / "setup_task.py"
        spec = importlib.util.spec_from_file_location("weird_captcha_setup_task_second_test", setup_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader if spec else None)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        mechanics = {
            "domino_autopsy": module.generate_domino_autopsy,
            "consequences_boss": module.generate_consequences_boss,
            "popup_exorcist": module.generate_popup_exorcist,
            "funeral_ritual": module.generate_funeral_ritual,
            "slime_commute": module.generate_slime_commute,
        }
        for mechanic, generator in mechanics.items():
            task_path = benchmark_root / "environments" / f"{mechanic}_env" / "tasks" / f"{mechanic}_seed_0001" / "task.json"
            task = json.loads(task_path.read_text(encoding="utf-8"))
            public_a, truth_a = generator(task, f"fixed-{mechanic}")
            public_b, truth_b = generator(task, f"fixed-{mechanic}")
            public_c, truth_c = generator(task, f"other-{mechanic}")
            self.assertEqual(public_a, public_b, mechanic)
            self.assertEqual(truth_a, truth_b, mechanic)
            self.assertNotEqual(truth_a["challenge_id"], truth_c["challenge_id"], mechanic)
            self.assertEqual(public_a["mechanic_id"], mechanic)
            self.assertEqual(truth_a["mechanic_id"], mechanic)
            self.assertNotIn("seed", public_a)
        self.assertEqual(len(mechanics["domino_autopsy"](json.loads((benchmark_root / "environments/domino_autopsy_env/tasks/domino_autopsy_seed_0001/task.json").read_text()), "shape")[1]["target_slots"]), 3)
        consequences_public, consequences_truth = mechanics["consequences_boss"](json.loads((benchmark_root / "environments/consequences_boss_env/tasks/consequences_boss_seed_0001/task.json").read_text()), "shape")
        self.assertEqual(len(consequences_public["scenes"]), 5)
        self.assertEqual(set(consequences_truth["boss_order"]), set(consequences_truth["scene_ids"]))
        self.assertEqual(len(mechanics["popup_exorcist"](json.loads((benchmark_root / "environments/popup_exorcist_env/tasks/popup_exorcist_seed_0001/task.json").read_text()), "shape")[0]["popups"]), 7)
        self.assertEqual(len(mechanics["funeral_ritual"](json.loads((benchmark_root / "environments/funeral_ritual_env/tasks/funeral_ritual_seed_0001/task.json").read_text()), "shape")[0]["flowers"]), 4)
        self.assertEqual(len(mechanics["slime_commute"](json.loads((benchmark_root / "environments/slime_commute_env/tasks/slime_commute_seed_0001/task.json").read_text()), "shape")[0]["board"]["lanes"]), 6)

    def test_interaction_second_verifiers_accept_complete_outcomes(self) -> None:
        benchmark_root = resolve_benchmark_root("weird_captcha_gym")
        setup_spec = importlib.util.spec_from_file_location("weird_captcha_setup_task_verifier_test", benchmark_root / "shared_scripts/setup_task.py")
        helper_spec = importlib.util.spec_from_file_location("weird_captcha_verifier_helpers_test", benchmark_root / "shared_runtime/verifier_helpers.py")
        self.assertIsNotNone(setup_spec and setup_spec.loader)
        self.assertIsNotNone(helper_spec and helper_spec.loader)
        setup = importlib.util.module_from_spec(setup_spec)
        helpers = importlib.util.module_from_spec(helper_spec)
        setup_spec.loader.exec_module(setup)
        helper_spec.loader.exec_module(helpers)

        def generated(mechanic, generator):
            task = json.loads((benchmark_root / f"environments/{mechanic}_env/tasks/{mechanic}_seed_0001/task.json").read_text())
            return generator(task, f"verify-{mechanic}")

        _, domino = generated("domino_autopsy", setup.generate_domino_autopsy)
        domino_chain = domino["expected_body_ids"] + [domino["bell_body_id"]]
        domino_result = {
            "placements": {domino_id: dict(slot) for domino_id, slot in zip(domino["loose_ids"], domino["target_slots"])},
            "physics_engine": "matter-js@0.20.0",
            "bell_hit": True,
            "bell_peak_angle": domino["minimum_bell_swing_radians"] + 0.01,
            "run_completed": True,
            "collision_pairs": [[left, right] for left, right in zip(domino_chain, domino_chain[1:])],
        }
        verified_domino = helpers.verify_domino_autopsy({"result": domino_result, "ground_truth": domino})
        self.assertTrue(verified_domino["passed"])
        self.assertEqual(verified_domino["score"], 100)
        domino_result["collision_pairs"].pop()
        self.assertFalse(helpers.verify_domino_autopsy({"result": domino_result, "ground_truth": domino})["passed"])

        consequence_public, consequences = generated("consequences_boss", setup.generate_consequences_boss)
        choices = {scene_id: ("left" if index % 2 == 0 else "right", index % 4) for index, scene_id in enumerate(consequences["scene_ids"])}
        consequence_events = []
        def consequence_event(kind, **details):
            consequence_events.append({"sequence": len(consequence_events) + 1, "kind": kind, **details})
        for scene_id in consequences["scene_ids"]:
            socket, seal = choices[scene_id]
            consequence_event("place", scene_id=scene_id, socket=socket)
            consequence_event("seal", scene_id=scene_id, seal=seal)
            consequence_event("commit", scene_id=scene_id, socket=socket, seal=seal)
        consequence_event("storm", duration_ms=consequences["storm_ms"])
        for scene_id in consequences["boss_order"]:
            socket, seal = choices[scene_id]
            consequence_event("reconstruct", scene_id=scene_id, socket=socket, seal=seal)
        consequence_result = {"mechanic_id": "consequences_boss", "challenge_id": consequences["challenge_id"], "events": consequence_events}
        self.assertEqual(helpers.verify_consequences_boss({"result": consequence_result, "ground_truth": consequences, "public_state": consequence_public})["score"], 100)

        popup_public, popups = generated("popup_exorcist", setup.generate_popup_exorcist)
        parasite_spec = next(item for item in popup_public["popups"] if item["id"] == popups["parasite_id"])
        well = popups["containment"]
        end = [round(float(well["x"]) + float(well["w"]) / 2 - float(parasite_spec["w"]) / 2), round(float(well["y"]) + float(well["h"]) / 2 - float(parasite_spec["h"]) / 2)]
        popup_events = [
            {"sequence": 1, "kind": "focus", "window_id": popups["parasite_id"]},
            {"sequence": 2, "kind": "close", "window_id": popups["parasite_id"]},
            {"sequence": 3, "kind": "spawn", "parent_id": popups["parasite_id"], "echo_ids": popups["echo_ids"]},
            {"sequence": 4, "kind": "focus", "window_id": popups["echo_ids"][0]},
            {"sequence": 5, "kind": "drag", "window_id": popups["echo_ids"][0], "samples": [end]},
            {"sequence": 6, "kind": "contain", "window_id": popups["echo_ids"][0]},
            {"sequence": 7, "kind": "purge", "contained_id": popups["echo_ids"][0], "remaining_before": popups["popup_ids"] + popups["echo_ids"]},
        ]
        popup_result = {"mechanic_id": "popup_exorcist", "challenge_id": popups["challenge_id"], "events": popup_events}
        self.assertEqual(helpers.verify_popup_exorcist({"result": popup_result, "ground_truth": popups, "public_state": popup_public})["score"], 100)

        _, funeral = generated("funeral_ritual", setup.generate_funeral_ritual)
        funeral_result = {"events": funeral["required_events"], "brushed_cells": list(range(funeral["brush_threshold"])), "gathered_flower_ids": funeral["flower_ids"], "completed": True}
        self.assertEqual(helpers.verify_funeral_ritual({"result": funeral_result, "ground_truth": funeral})["score"], 100)

        slime_public, slime = generated("slime_commute", setup.generate_slime_commute)
        from benchmarks.weird_captcha_gym.tools.incubator_solvers.slime_commute import _plan
        plan = _plan(slime["board"])
        slime_result = {
            "mechanic_id": "slime_commute",
            "challenge_id": slime["challenge_id"],
            "actions": [{"sequence": index, "tick": tick, "key": key} for index, (tick, key) in enumerate(plan, start=1)],
            "final_tick": plan[-1][0],
            "completed": True,
            "reason": "home",
        }
        self.assertEqual(helpers.verify_slime_commute({"result": slime_result, "ground_truth": slime, "public_state": slime_public})["score"], 100)

    def test_incubator_batch_one_plugins_are_deterministic_private_and_identity_bound(self) -> None:
        benchmark_root = resolve_benchmark_root("weird_captcha_gym")
        setup_spec = importlib.util.spec_from_file_location(
            "weird_captcha_incubator_batch_one_setup_test",
            benchmark_root / "shared_scripts" / "setup_task.py",
        )
        self.assertIsNotNone(setup_spec and setup_spec.loader)
        setup = importlib.util.module_from_spec(setup_spec)
        setup_spec.loader.exec_module(setup)
        mechanics = (
            "wrong_number",
            "bomb_manual_from_hell",
            "dead_mans_switch",
            "blind_dice_courier",
            "input_lag_forklift",
        )
        for mechanic in mechanics:
            task_path = benchmark_root / f"environments/{mechanic}_env/tasks/{mechanic}_seed_0001/task.json"
            task = json.loads(task_path.read_text(encoding="utf-8"))
            public_a, truth_a = setup.generate_incubator_candidate(task, f"fixed-{mechanic}")
            public_b, truth_b = setup.generate_incubator_candidate(task, f"fixed-{mechanic}")
            public_c, truth_c = setup.generate_incubator_candidate(task, f"other-{mechanic}")
            self.assertEqual((public_a, truth_a), (public_b, truth_b), mechanic)
            self.assertNotEqual(truth_a["challenge_id"], truth_c["challenge_id"], mechanic)
            self.assertEqual(public_a["challenge_id"], truth_a["challenge_id"], mechanic)
            self.assertEqual(public_a["mechanic_id"], mechanic)
            self.assertEqual(truth_a["mechanic_id"], mechanic)
            self.assertNotIn("seed", public_a)
            self.assertNotIn("solution", public_a)
            self.assertNotIn("solution_path", public_a)
            self.assertEqual(public_a["asset_manifest"], "shared_runtime/assets/provenance/incubator_puzzles_v1.json")

            grader_path = benchmark_root / f"shared_runtime/server/incubator_graders/{mechanic}.py"
            grader_spec = importlib.util.spec_from_file_location(f"incubator_batch_one_grader_{mechanic}", grader_path)
            self.assertIsNotNone(grader_spec and grader_spec.loader)
            grader = importlib.util.module_from_spec(grader_spec)
            grader_spec.loader.exec_module(grader)
            stale = grader.grade({"mechanic_id": mechanic, "challenge_id": "stale"}, truth_a, public_a)
            self.assertFalse(stale.get("passed"), mechanic)

        wrong_task = json.loads((benchmark_root / "environments/wrong_number_env/tasks/wrong_number_seed_0001/task.json").read_text())
        positions = set()
        for index in range(64):
            _, truth = setup.generate_incubator_candidate(wrong_task, f"position-audit-{index}")
            positions.add(int(truth["target_slot"]))
        self.assertEqual(positions, set(range(7)))

    def test_pending_next_ten_v2_scale_variation_and_closed_shortcuts(self) -> None:
        benchmark_root = resolve_benchmark_root("weird_captcha_gym")
        setup_spec = importlib.util.spec_from_file_location(
            "weird_captcha_pending_next_ten_v2_setup_test",
            benchmark_root / "shared_scripts" / "setup_task.py",
        )
        self.assertIsNotNone(setup_spec and setup_spec.loader)
        setup = importlib.util.module_from_spec(setup_spec)
        setup_spec.loader.exec_module(setup)

        mechanics = (
            "bureaucratic_signature_trap",
            "temporal_memory_first_change",
            "polyrhythm_customs",
            "exact_change_candy_cascade",
            "tiny_fps_customs",
            "thirty_year_time_wheel",
        )

        def task_for(mechanic: str) -> dict:
            path = benchmark_root / f"environments/{mechanic}_env/tasks/{mechanic}_seed_0001/task.json"
            return json.loads(path.read_text(encoding="utf-8"))

        generated = {
            mechanic: [
                setup.generate_incubator_candidate(task_for(mechanic), f"pending-v2-audit-{index}-{mechanic}")
                for index in range(24)
            ]
            for mechanic in mechanics
        }

        signature_traces = set()
        for public, truth in generated["bureaucratic_signature_trap"]:
            self.assertEqual(len(public["form"]["layers"]), 4)
            self.assertEqual(public["form"], truth["form"])
            signature_traces.add(json.dumps(public["form"]["original_trace"], separators=(",", ":")))
        self.assertEqual(len(signature_traces), 24)

        memory_targets = set()
        for public, truth in generated["temporal_memory_first_change"]:
            timeline = public["timeline"]
            self.assertEqual(len(timeline["objects"]), 9)
            self.assertEqual(len(timeline["events"]), 5)
            self.assertNotIn("pulse_lead_ms", timeline)
            self.assertEqual(min(timeline["events"], key=lambda item: item["at_ms"])["object_id"], truth["target_object_id"])
            memory_targets.add(truth["target_object_id"])
        self.assertEqual(len(memory_targets), 24)

        for public, truth in generated["polyrhythm_customs"]:
            self.assertEqual(len(public["lanes"]), 4)
            self.assertTrue(18 <= len(public["score"]) <= 22)
            self.assertEqual(sum(note["kind"] == "hold" for note in truth["expected_notes"]), 2)
            self.assertEqual(len(truth["chords"]), 2)

        for public, truth in generated["exact_change_candy_cascade"]:
            self.assertEqual(public["move_budget"], 4)
            self.assertEqual(len(truth["solution_swaps"]), 4)
            self.assertGreaterEqual(max(truth["solution_wave_counts"]), 3)
            self.assertLessEqual(truth["solution_count_for_target"], 8)

        fps_maps = set()
        for public, truth in generated["tiny_fps_customs"]:
            fps_maps.add(tuple(public["map"]))
            self.assertEqual(len(public["wanted_posters"]), 4)
            self.assertEqual(len(truth["wanted_ids"]), 4)
            self.assertEqual(len(truth["protected_ids"]), 4)
        self.assertGreaterEqual(len(fps_maps), 22)

        for public, _truth in generated["thirty_year_time_wheel"]:
            self.assertNotIn("coast detent", public["rules"]["proof"].lower())
            self.assertNotIn("effective brake", public["rules"]["proof"].lower())

        def load_grader(mechanic: str):
            path = benchmark_root / f"shared_runtime/server/incubator_graders/{mechanic}.py"
            spec = importlib.util.spec_from_file_location(f"pending_v2_grader_{mechanic}", path)
            self.assertIsNotNone(spec and spec.loader)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

        signature_public, signature_truth = generated["bureaucratic_signature_trap"][0]
        form = signature_truth["form"]
        alignment = []
        for layer in form["layers"]:
            start = [float(layer["initial"]["x"]), float(layer["initial"]["y"])]
            end = [float(layer["target"]["x"]), float(layer["target"]["y"])]
            count = max(2, math.ceil(math.hypot(end[0] - start[0], end[1] - start[1]) / 24))
            samples = [
                [start[0] + (end[0] - start[0]) * index / count, start[1] + (end[1] - start[1]) * index / count]
                for index in range(1, count + 1)
            ]
            alignment.append({"kind": "sheet_drag", "sheet_id": layer["id"], "start": start, "samples": samples, "end": samples[-1]})

        def sequenced(events: list[dict]) -> list[dict]:
            return [{"sequence": index, **event} for index, event in enumerate(events, start=1)]

        aperture = form["aperture"]
        circle = [
            [
                aperture["x"] + aperture["radius"] * .62 * math.cos(index * math.tau / 80),
                aperture["y"] + aperture["radius"] * .62 * math.sin(index * math.tau / 80),
            ]
            for index in range(81)
        ]
        signature_grader = load_grader("bureaucratic_signature_trap")
        circle_payload = {
            "mechanic_id": "bureaucratic_signature_trap",
            "challenge_id": signature_truth["challenge_id"],
            "events": sequenced([*alignment, {"kind": "signature", "points": circle}, {"kind": "certify"}]),
        }
        self.assertFalse(signature_grader.grade(circle_payload, signature_truth, signature_public)["passed"])
        trace_payload = {
            **circle_payload,
            "events": sequenced([*alignment, {"kind": "signature", "points": form["original_trace"]}, {"kind": "certify"}]),
        }
        self.assertTrue(signature_grader.grade(trace_payload, signature_truth, signature_public)["passed"])

        memory_public, memory_truth = generated["temporal_memory_first_change"][0]
        timeline = memory_truth["timeline"]
        target_id = memory_truth["target_object_id"]
        target = next(item for item in timeline["objects"] if item["id"] == target_id)
        target_index = timeline["settle_order"].index(target_id)
        grid = timeline["settle_grid"]
        settled_point = [
            grid["x0"] + target_index % grid["columns"] * grid["dx"],
            grid["y0"] + target_index // grid["columns"] * grid["dy"],
        ]
        memory_grader = load_grader("temporal_memory_first_change")
        shortcut_events = sequenced([
            {"kind": "arm"},
            {"kind": "return_settled"},
            {"kind": "select", "selected_object_id": target_id, "point": settled_point},
        ])
        shortcut = {
            "mechanic_id": "temporal_memory_first_change",
            "challenge_id": memory_truth["challenge_id"],
            "selected_object_id": target_id,
            "events": shortcut_events,
        }
        self.assertFalse(memory_grader.grade(shortcut, memory_truth, memory_public)["passed"])

        first = timeline["events"][0]

        def moving_point(at_ms: float) -> list[float]:
            return [
                target["x0"] + math.sin(target["phase"] + at_ms * target["rate_x"]) * target["amp_x"],
                target["y0"] + math.cos(target["phase"] * .83 + at_ms * target["rate_y"]) * target["amp_y"],
            ]

        pre_ms = first["at_ms"] - 160
        change_a = first["at_ms"] + 120
        change_b = first["at_ms"] + 260
        witnessed = {
            **shortcut,
            "events": sequenced([
                {"kind": "arm"},
                {"kind": "observe", "mode": "review", "timeline_ms": pre_ms, "cursor": moving_point(pre_ms)},
                {"kind": "observe", "mode": "review", "timeline_ms": change_a, "cursor": moving_point(change_a)},
                {"kind": "observe", "mode": "review", "timeline_ms": change_b, "cursor": moving_point(change_b)},
                {"kind": "return_settled"},
                {"kind": "select", "selected_object_id": target_id, "point": settled_point},
            ]),
        }
        self.assertTrue(memory_grader.grade(witnessed, memory_truth, memory_public)["passed"])

    def test_incubator_batch_two_plugins_are_deterministic_private_and_identity_bound(self) -> None:
        benchmark_root = resolve_benchmark_root("weird_captcha_gym")
        setup_spec = importlib.util.spec_from_file_location(
            "weird_captcha_incubator_batch_two_setup_test",
            benchmark_root / "shared_scripts" / "setup_task.py",
        )
        self.assertIsNotNone(setup_spec and setup_spec.loader)
        setup = importlib.util.module_from_spec(setup_spec)
        setup_spec.loader.exec_module(setup)
        mechanics = (
            "insider_trading_captcha",
            "polyrhythm_customs",
            "exact_change_candy_cascade",
            "tiny_fps_customs",
            "thirty_year_time_wheel",
        )
        generated: dict[str, tuple[dict, dict]] = {}
        for mechanic in mechanics:
            task_path = benchmark_root / f"environments/{mechanic}_env/tasks/{mechanic}_seed_0001/task.json"
            task = json.loads(task_path.read_text(encoding="utf-8"))
            public_a, truth_a = setup.generate_incubator_candidate(task, f"fixed-{mechanic}")
            public_b, truth_b = setup.generate_incubator_candidate(task, f"fixed-{mechanic}")
            public_c, truth_c = setup.generate_incubator_candidate(task, f"other-{mechanic}")
            self.assertEqual((public_a, truth_a), (public_b, truth_b), mechanic)
            self.assertNotEqual(truth_a["challenge_id"], truth_c["challenge_id"], mechanic)
            self.assertEqual(public_a["challenge_id"], truth_a["challenge_id"], mechanic)
            self.assertEqual(public_a["mechanic_id"], mechanic)
            self.assertEqual(truth_a["mechanic_id"], mechanic)
            self.assertNotIn("seed", public_a)
            self.assertFalse(any("solution" in key or "solver" in key for key in public_a), mechanic)
            self.assertEqual(public_a["asset_manifest"], "shared_runtime/assets/provenance/incubator_puzzles_v1.json")

            grader_path = benchmark_root / f"shared_runtime/server/incubator_graders/{mechanic}.py"
            grader_spec = importlib.util.spec_from_file_location(f"incubator_batch_two_grader_{mechanic}", grader_path)
            self.assertIsNotNone(grader_spec and grader_spec.loader)
            grader = importlib.util.module_from_spec(grader_spec)
            grader_spec.loader.exec_module(grader)
            stale = grader.grade({"mechanic_id": mechanic, "challenge_id": "stale"}, truth_a, public_a)
            self.assertFalse(stale.get("passed"), mechanic)
            generated[mechanic] = (public_a, truth_a)

        _, candy_truth = generated["exact_change_candy_cascade"]
        self.assertEqual(len(candy_truth["solution_swaps"]), 4)
        self.assertGreaterEqual(max(candy_truth["solution_wave_counts"]), 3)
        self.assertLessEqual(candy_truth["solution_count_for_target"], 8)
        _, rhythm_truth = generated["polyrhythm_customs"]
        self.assertEqual(len(rhythm_truth["lanes"]), 4)
        self.assertEqual(len(rhythm_truth["chords"]), 2)
        self.assertEqual(sum(note["kind"] == "hold" and note["duration_ms"] > 0 for note in rhythm_truth["expected_notes"]), 2)
        self.assertGreaterEqual(len(rhythm_truth["expected_notes"]), 18)

        fps_task = json.loads((benchmark_root / "environments/tiny_fps_customs_env/tasks/tiny_fps_customs_seed_0001/task.json").read_text())
        fps_layouts = {
            setup.generate_incubator_candidate(fps_task, f"layout-audit-{index}")[0]["layout_variant"]
            for index in range(32)
        }
        self.assertEqual(fps_layouts, {"identity", "mirror_x", "mirror_y", "rotate_180"})
        fps_maps = {
            tuple(setup.generate_incubator_candidate(fps_task, f"maze-audit-{index}")[0]["map"])
            for index in range(32)
        }
        self.assertGreaterEqual(len(fps_maps), 28)

    def test_next_ten_v3_generators_have_meaningful_structural_variation_and_scale(self) -> None:
        benchmark_root = resolve_benchmark_root("weird_captcha_gym")
        setup_spec = importlib.util.spec_from_file_location(
            "weird_captcha_next_ten_v3_generator_audit",
            benchmark_root / "shared_scripts" / "setup_task.py",
        )
        self.assertIsNotNone(setup_spec and setup_spec.loader)
        setup = importlib.util.module_from_spec(setup_spec)
        setup_spec.loader.exec_module(setup)
        mechanics = (
            "impossible_panorama",
            "flat_pack_compliance",
            "crash_deadline_hovercar",
            "robot_art_critic",
            "wrong_number",
            "bomb_manual_from_hell",
            "dead_mans_switch",
            "blind_dice_courier",
            "input_lag_forklift",
            "insider_trading_captcha",
        )
        generated: dict[str, list[dict]] = {}
        examples: dict[str, tuple[dict, dict]] = {}
        for mechanic in mechanics:
            task_path = benchmark_root / f"environments/{mechanic}_env/tasks/{mechanic}_seed_0001/task.json"
            task = json.loads(task_path.read_text(encoding="utf-8"))
            challenge_ids: set[str] = set()
            contracts: set[str] = set()
            truths: list[dict] = []
            for index in range(80):
                public, truth = setup.generate_incubator_candidate(
                    task, f"next-ten-v3-generator-{mechanic}-{index}"
                )
                challenge_ids.add(str(truth["challenge_id"]))
                core = {
                    key: value
                    for key, value in truth.items()
                    if key not in {"seed", "challenge_id"}
                }
                contracts.add(json.dumps(core, sort_keys=True, separators=(",", ":")))
                self.assertEqual(public["challenge_id"], truth["challenge_id"])
                self.assertNotIn("seed", public)
                self.assertFalse(
                    any("solution" in key or "solver" in key for key in public),
                    mechanic,
                )
                if index == 0:
                    examples[mechanic] = (public, truth)
                truths.append(truth)
            self.assertEqual(len(challenge_ids), 80, mechanic)
            self.assertGreaterEqual(len(contracts), 40, mechanic)
            generated[mechanic] = truths

        for mechanic, (public, truth) in examples.items():
            grader_path = benchmark_root / f"shared_runtime/server/incubator_graders/{mechanic}.py"
            grader_spec = importlib.util.spec_from_file_location(
                f"next_ten_v3_task_binding_{mechanic}", grader_path
            )
            self.assertIsNotNone(grader_spec and grader_spec.loader)
            grader = importlib.util.module_from_spec(grader_spec)
            grader_spec.loader.exec_module(grader)
            mismatch = grader.grade(
                {
                    "mechanic_id": mechanic,
                    "task_id": "tampered-task",
                    "challenge_id": truth["challenge_id"],
                },
                truth,
                public,
            )
            self.assertFalse(mismatch.get("passed"), mechanic)
            self.assertIn("task", str(mismatch.get("feedback") or "").lower(), mechanic)

            forged_terminal_claim = grader.grade(
                {
                    "mechanic_id": mechanic,
                    "task_id": truth["task_id"],
                    "challenge_id": truth["challenge_id"],
                    "passed": True,
                    "score": 100,
                    "events": [],
                },
                truth,
                public,
            )
            self.assertFalse(
                forged_terminal_claim.get("passed"),
                f"{mechanic} trusted a client PASS without a replayable interaction transcript",
            )

        self.assertEqual(
            {int(truth["target_slot"]) for truth in generated["wrong_number"]},
            set(range(7)),
        )
        self.assertEqual(
            {int(truth["correct_wire_index"]) for truth in generated["bomb_manual_from_hell"]},
            set(range(9)),
        )
        forklift_truths = generated["input_lag_forklift"]
        self.assertEqual({int(truth["layout_index"]) for truth in forklift_truths}, set(range(12)))
        self.assertEqual(
            {str(truth["transform"]) for truth in forklift_truths},
            {"identity", "mirror_x", "mirror_y", "rotate_180"},
        )
        self.assertEqual(
            {str(truth["palette"]) for truth in forklift_truths},
            {"amber", "oxide", "mint", "cobalt"},
        )
        self.assertTrue(
            all(
                "max_pointer_jump" not in (truth.get("requirements") or {})
                for truth in generated["crash_deadline_hovercar"]
            ),
            "hovercar correctness must not depend on VNC pointer event density",
        )
        self.assertTrue(all(len(truth["objects"]) == 32 and truth["world"]["sector_columns"] == 8 and truth["world"]["sector_rows"] == 4 for truth in generated["impossible_panorama"]))
        self.assertTrue(all(len(truth["parts"]) == 7 and len(truth["joints"]) == 6 and len(truth["load_steps"]) == 36 for truth in generated["flat_pack_compliance"]))
        self.assertTrue(all(len(truth["targets"]) == 5 and len(truth["obstacles"]) == 6 for truth in generated["crash_deadline_hovercar"]))
        self.assertTrue(all(int(truth["target"]["expected_strokes"]) >= 10 and len(truth["class_vocabulary"]) == 8 for truth in generated["robot_art_critic"]))
        self.assertTrue(all(len(truth["lines"]) == 7 and int(truth["qualification"]["trial_ms"]) >= 4_800 and min(abs(int(line["drift_milli_steps_per_second"])) for line in truth["lines"]) >= 1_180 for truth in generated["wrong_number"]))
        self.assertTrue(all(len(truth["plates"]) == 5 and len(truth["wires"]) == 9 and all(len(plate["apertures"]) == 5 for plate in truth["plates"]) for truth in generated["bomb_manual_from_hell"]))
        self.assertTrue(all(len(truth["board"]["checkpoints"]) == 5 and int(truth["minimum_success_moves"]) >= 42 and int(truth["pressure_motion"]["minimum_hold_ms"]) >= 5_200 for truth in generated["dead_mans_switch"]))
        self.assertTrue(all(len(truth["board"]["gates"]) == 5 and len(truth["solution_path"]) >= 48 for truth in generated["blind_dice_courier"]))
        self.assertTrue(all(len(truth["initial_state"]["crates"]) == 2 and len(truth["solution"]) >= 22 for truth in generated["input_lag_forklift"]))
        self.assertTrue(
            all(
                len(truth["prices_cents"]) >= 34
                and int(truth["order_delay_ticks"]) >= 3
                and int(truth["causal_reference_profit_cents"]) >= 1_400
                and len(truth["causal_reference_ledger"]) >= 10
                and int(truth["target_profit_cents"]) >= 1_100
                and int(truth["causal_reference_profit_cents"])
                >= int(truth["target_profit_cents"])
                for truth in generated["insider_trading_captcha"]
            )
        )
        for truth in generated["insider_trading_captcha"]:
            prices = [int(value) for value in truth["prices_cents"]]
            deltas = [right - left for left, right in zip(prices, prices[1:])]
            nonzero_signs = [1 if value > 0 else -1 for value in deltas if value]
            self.assertGreaterEqual(
                sum(left != right for left, right in zip(nonzero_signs, nonzero_signs[1:])),
                3,
            )
            for lag in range(2, min(13, len(deltas) // 2)):
                near_repeats = sum(
                    abs(deltas[index] - deltas[index - lag]) <= 10
                    for index in range(lag, len(deltas))
                )
                self.assertLess(
                    near_repeats / (len(deltas) - lag),
                    0.45,
                    f"market tape retained a short near-period at lag {lag}",
                )

    def test_pending_next_ten_v3_are_structurally_varied_identity_bound_and_not_terminal_claims(self) -> None:
        benchmark_root = resolve_benchmark_root("weird_captcha_gym")
        setup_spec = importlib.util.spec_from_file_location(
            "weird_captcha_pending_next_ten_v3_setup_test",
            benchmark_root / "shared_scripts" / "setup_task.py",
        )
        self.assertIsNotNone(setup_spec and setup_spec.loader)
        setup = importlib.util.module_from_spec(setup_spec)
        setup_spec.loader.exec_module(setup)
        mechanics = (
            "forced_perspective_moving_day",
            "lidar_blacksite",
            "tomographic_baggage_surgery",
            "three_camera_claw_machine",
            "zero_g_cable_autopsy",
            "portal_freight_oversized_parcel",
            "code_to_diagram_captcha",
            "exit_vim_terminal_escape",
            "fake_desktop_automation_inversion",
            "impossible_ecology",
        )
        generated: dict[str, list[tuple[dict, dict]]] = {}
        cosmetic_fields = {
            "asset_manifest", "benchmark", "challenge_id", "generator", "palette",
            "prompt", "submit_label", "task_id",
        }
        for mechanic in mechanics:
            task_path = benchmark_root / f"environments/{mechanic}_env/tasks/{mechanic}_seed_0001/task.json"
            task = json.loads(task_path.read_text(encoding="utf-8"))
            examples: list[tuple[dict, dict]] = []
            structural_signatures: set[str] = set()
            for index in range(48):
                seed = f"pending-v3-variation-{index}"
                public, truth = setup.generate_incubator_candidate(task, seed)
                repeated = setup.generate_incubator_candidate(task, seed)
                self.assertEqual((public, truth), repeated, f"{mechanic} was not deterministic")
                structure = {key: value for key, value in public.items() if key not in cosmetic_fields}
                structural_signatures.add(json.dumps(structure, sort_keys=True))
                examples.append((public, truth))
            self.assertEqual(len(structural_signatures), 48, f"{mechanic} varied only cosmetically")
            generated[mechanic] = examples

            grader_path = benchmark_root / f"shared_runtime/server/incubator_graders/{mechanic}.py"
            grader_spec = importlib.util.spec_from_file_location(f"pending_v3_grader_{mechanic}", grader_path)
            self.assertIsNotNone(grader_spec and grader_spec.loader)
            grader = importlib.util.module_from_spec(grader_spec)
            grader_spec.loader.exec_module(grader)
            public, truth = examples[0]
            forged_terminal_claim = {
                "mechanic_id": mechanic,
                "challenge_id": truth["challenge_id"],
                "task_id": truth["task_id"],
                "events": [],
                "actions": [],
                "completed": True,
                "delivered": True,
                "captured": True,
                "armed": True,
            }
            self.assertFalse(
                grader.grade(forged_terminal_claim, truth, public).get("passed"),
                f"{mechanic} accepted an empty terminal-state claim",
            )
            forged_terminal_claim["task_id"] = "tampered-task"
            task_mismatch = grader.grade(forged_terminal_claim, truth, public)
            self.assertFalse(task_mismatch.get("passed"), mechanic)
            self.assertIn("task", str(task_mismatch.get("feedback") or "").lower(), mechanic)

        perspective = generated["forced_perspective_moving_day"]
        self.assertEqual({truth["mirror"] for _, truth in perspective}, {-1, 1})
        self.assertEqual(len({public["camera"]["yaw"] for public, _ in perspective}), 48)

        lidar = generated["lidar_blacksite"]
        self.assertEqual(
            len({tuple(tuple(point) for point in truth["solution"]["route_points"]) for _, truth in lidar}),
            8,
        )
        self.assertTrue(all(truth["solution"]["scan_route_indices"] == [0, 2, 4, 5] for _, truth in lidar))

        tomography = generated["tomographic_baggage_surgery"]
        self.assertEqual(len({tuple(truth["solver"]["target"]) for _, truth in tomography}), 48)
        self.assertTrue(all(len(public["solids"]) == 4 for public, _ in tomography))

        claw = generated["three_camera_claw_machine"]
        self.assertGreaterEqual(len({tuple(truth["solver"]["target"]) for _, truth in claw}), 14)
        self.assertTrue(all(sorted(camera["delay"] for camera in public["cameras"].values()) == [0, 2, 4] for public, _ in claw))

        cable = generated["zero_g_cable_autopsy"]
        self.assertEqual({public["rings"][0]["center"][1] for public, _ in cable}, {1.5, 1.75, 2.0})
        self.assertEqual({public["pegs"][0]["radius"] for public, _ in cable}, {0.68, 0.72, 0.76})
        self.assertEqual({1 if public["nodes"][4][2] > 0 else -1 for public, _ in cable}, {-1, 1})

        portals = generated["portal_freight_oversized_parcel"]
        self.assertEqual(
            {public["delivery"]["frame"]["wall_id"] for public, _ in portals},
            {"B-east", "B-west", "B-north", "B-south"},
        )
        self.assertEqual({public["parcel"]["initial_angle_deg"] for public, _ in portals}, {-20.0, 20.0})

        code = generated["code_to_diagram_captcha"]
        self.assertTrue(all(len(public["nodes"]) == 9 and len(public["probe_inputs"]) == 4 for public, _ in code))
        self.assertTrue(all(len(truth["expected_edges"]) == 10 for _, truth in code))
        self.assertTrue(all(sum(len(run["steps"]) for run in truth["expected_probe_runs"]) == 28 for _, truth in code))

        terminal = generated["exit_vim_terminal_escape"]
        self.assertGreaterEqual(len({tuple(public["layer_order"]) for public, _ in terminal}), 20)
        self.assertTrue(all(len(public["reference_buffers"]) == 3 and len(public["target_buffer"]) == 6 for public, _ in terminal))

        desktop = generated["fake_desktop_automation_inversion"]
        self.assertGreaterEqual(len({tuple(public["mapping_sequence"]) for public, _ in desktop}), 20)
        self.assertGreaterEqual(len({tuple(public["target_filenames"]) for public, _ in desktop}), 18)
        self.assertTrue(all(len(set(public["mapping_sequence"])) == 3 and len(public["target_filenames"]) == 2 for public, _ in desktop))

        ecology = generated["impossible_ecology"]
        for public, _ in ecology:
            dominant = {
                (
                    max(organism["responses"], key=lambda field: abs(organism["responses"][field])),
                    1 if organism["responses"][max(organism["responses"], key=lambda field: abs(organism["responses"][field]))] > 0 else -1,
                )
                for organism in public["organisms"]
            }
            self.assertEqual(len(dominant), 5)
            self.assertEqual(len(public["targets"]), 5)

    def test_interaction_vii_viii_are_seeded_replayable_and_resist_shortcuts(self) -> None:
        benchmark_root = resolve_benchmark_root("weird_captcha_gym")
        setup_spec = importlib.util.spec_from_file_location(
            "weird_captcha_interaction_vii_viii_setup_test",
            benchmark_root / "shared_scripts" / "setup_task.py",
        )
        self.assertIsNotNone(setup_spec and setup_spec.loader)
        setup = importlib.util.module_from_spec(setup_spec)
        setup_spec.loader.exec_module(setup)
        mechanics = (
            "specular_lighthouse_relay",
            "wind_tunnel_seed_courier",
            "hologram_silhouette_foundry",
            "orbital_docking_customs",
            "gravity_room_freight",
            "floodgate_archive_rescue",
            "elastic_membrane_sorter",
            "pheromone_dispatch",
            "clockwork_clutch_safe",
            "marionette_checkpoint",
        )
        examples: dict[str, tuple[dict, dict, object]] = {}
        for mechanic in mechanics:
            task_path = benchmark_root / f"environments/{mechanic}_env/tasks/{mechanic}_seed_0001/task.json"
            task = json.loads(task_path.read_text(encoding="utf-8"))
            contracts: set[str] = set()
            challenge_ids: set[str] = set()
            for seed_index in range(24):
                seed = f"interaction-vii-viii-variation-{mechanic}-{seed_index}"
                public, truth = setup.generate_incubator_candidate(task, seed)
                replay_public, replay_truth = setup.generate_incubator_candidate(task, seed)
                self.assertEqual((public, truth), (replay_public, replay_truth), mechanic)
                self.assertEqual(public["challenge_id"], truth["challenge_id"], mechanic)
                self.assertNotIn("seed", public, mechanic)
                challenge_ids.add(str(truth["challenge_id"]))
                contracts.add(json.dumps({
                    key: value for key, value in truth.items() if key not in {"seed", "challenge_id"}
                }, sort_keys=True, separators=(",", ":")))
                if seed_index == 0:
                    grader_path = benchmark_root / f"shared_runtime/server/incubator_graders/{mechanic}.py"
                    grader_spec = importlib.util.spec_from_file_location(
                        f"interaction_vii_viii_grader_{mechanic}", grader_path
                    )
                    self.assertIsNotNone(grader_spec and grader_spec.loader)
                    grader = importlib.util.module_from_spec(grader_spec)
                    grader_spec.loader.exec_module(grader)
                    examples[mechanic] = (public, truth, grader)
            self.assertEqual(len(challenge_ids), 24, mechanic)
            self.assertGreaterEqual(len(contracts), 8, mechanic)

        for mechanic, (public, truth, grader) in examples.items():
            forged = grader.grade({
                "mechanic_id": mechanic,
                "task_id": truth["task_id"],
                "challenge_id": truth["challenge_id"],
                "completed": True,
                "passed": True,
                "score": 100,
                "events": [],
            }, truth, public)
            self.assertFalse(
                forged.get("passed"),
                f"{mechanic} trusted a terminal claim without replayable interaction",
            )

        spec_public, spec_truth, spec_grader = examples["specular_lighthouse_relay"]
        first_round = spec_public["rounds"][0]
        initial_angles = [float(mirror["angle_deg"]) for mirror in first_round["mirrors"]]
        analytic_hit = spec_grader._trace_hit(first_round, initial_angles, 1)
        reflected_spoof = spec_grader.grade({
            "mechanic_id": "specular_lighthouse_relay",
            "task_id": spec_truth["task_id"],
            "challenge_id": spec_truth["challenge_id"],
            "events": [
                {"seq": 1, "type": "shutter", "round_id": first_round["id"], "tick": 0, "open": True},
                {"seq": 2, "type": "charge_sample", "round_id": first_round["id"], "tick": 1, "angles": initial_angles, "hit": not analytic_hit, "charge_after": 1},
            ],
            "completed": True,
        }, spec_truth, spec_public)
        self.assertFalse(reflected_spoof.get("passed"))
        self.assertIn("analytic", str(reflected_spoof.get("feedback") or ""))

        wind_public, wind_truth, wind_grader = examples["wind_tunnel_seed_courier"]
        thermal_prearm = wind_grader.grade({
            "mechanic_id": "wind_tunnel_seed_courier",
            "task_id": wind_truth["task_id"],
            "challenge_id": wind_truth["challenge_id"],
            "events": [
                {"seq": 1, "type": "launch", "tick": 0},
                {"seq": 2, "type": "fan_control", "tick": 0, "fan": 0, "power": 1},
            ],
            "completed": True,
        }, wind_truth, wind_public)
        self.assertFalse(thermal_prearm.get("passed"))
        self.assertTrue(str(thermal_prearm.get("feedback") or ""))

        pheromone_public, pheromone_truth, pheromone_grader = examples["pheromone_dispatch"]
        painted: dict[str, list[dict[str, float]]] = {}
        events: list[dict] = []
        for field_id, reference in pheromone_truth["reference_paths"].items():
            route: list[list[float]] = []
            for segment_index, (first, second) in enumerate(zip(reference, reference[1:])):
                if segment_index == 0:
                    route.append([float(first[0]), float(first[1])])
                for step in range(1, 13):
                    amount = step / 12
                    route.append([
                        float(first[0]) + (float(second[0]) - float(first[0])) * amount,
                        float(first[1]) + (float(second[1]) - float(first[1])) * amount,
                    ])
            points = [{"x": point[0], "y": point[1]} for point in route]
            painted[field_id] = points
            events.append({"seq": len(events) + 1, "type": "stroke_start", "tick": 0, "field_id": field_id, "mode": "route", "point": points[0]})
            events.extend({
                "seq": len(events) + 1, "type": "stroke_point", "tick": 0,
                "field_id": field_id, "mode": "route", "point": point,
            } for point in points[1:])
            events.append({"seq": len(events) + 1, "type": "stroke_end", "tick": 0, "field_id": field_id, "mode": "route", "samples": len(points)})
        events.append({"seq": len(events) + 1, "type": "dispatch", "tick": 0, "paths": painted})
        events.append({
            "seq": len(events) + 1, "type": "delivery", "tick": 650,
            "delivered": {field_id: 7 for field_id in painted},
            "last_refresh": {field_id: 0 for field_id in painted},
        })
        stale_field = pheromone_grader.grade({
            "mechanic_id": "pheromone_dispatch",
            "task_id": pheromone_truth["task_id"],
            "challenge_id": pheromone_truth["challenge_id"],
            "events": events,
            "completed": True,
        }, pheromone_truth, pheromone_public)
        self.assertFalse(stale_field.get("passed"))
        self.assertIn("delivery", str(stale_field.get("feedback") or ""))

        marionette_public, marionette_truth, marionette_grader = examples["marionette_checkpoint"]
        pose = marionette_truth["poses"][0]
        lengths = [float(value) for value in marionette_public["initial_lengths"]]
        marionette_events = [{
            "seq": 1, "type": "act_clear", "tick": 0, "pose_id": pose["id"],
            "lengths": list(lengths), "progress": int(pose["tracking_ticks"]),
        }]
        instant_pose = marionette_grader.grade({
            "mechanic_id": "marionette_checkpoint",
            "task_id": marionette_truth["task_id"],
            "challenge_id": marionette_truth["challenge_id"],
            "events": marionette_events,
            "completed": True,
        }, marionette_truth, marionette_public)
        self.assertFalse(instant_pose.get("passed"))
        self.assertIn("tracking", str(instant_pose.get("feedback") or ""))

        flood_public, flood_truth, flood_grader = examples["floodgate_archive_rescue"]
        initial_levels = [float(item["level"]) for item in flood_public["chambers"]]
        first_circuit = flood_public["circuits"][0]["between"]
        nonconserving = list(initial_levels)
        nonconserving[first_circuit[1]] += float(flood_public["pump_step"])
        fake_pump = flood_grader.grade({
            "mechanic_id": "floodgate_archive_rescue",
            "task_id": flood_truth["task_id"],
            "challenge_id": flood_truth["challenge_id"],
            "events": [{
                "seq": 1, "type": "pump", "circuit": 0, "direction": 1,
                "source": first_circuit[0], "destination": first_circuit[1],
                "before": initial_levels, "after": nonconserving,
                "total_after": sum(nonconserving),
            }],
            "completed": True,
        }, flood_truth, flood_public)
        self.assertFalse(fake_pump.get("passed"))
        self.assertIn("conservation", str(fake_pump.get("feedback") or ""))

        orbital_public, orbital_truth, _ = examples["orbital_docking_customs"]
        debris = orbital_public["debris"][0]
        ship = orbital_public["ship"]
        station = orbital_public["station"]
        self.assertAlmostEqual(float(debris["y"]), float(ship["y"]))
        self.assertGreater(float(debris["x"]), float(ship["x"]))
        self.assertLess(float(debris["x"]), float(station["x"]))
        transverse = sum(
            int(item.get("count", 0)) for item in orbital_truth["reference_plan"]
            if str(item.get("action", "")).startswith("strafe-")
        )
        self.assertGreaterEqual(transverse, 28)
        self.assertEqual(sum(int(item.get("ticks", 0)) for item in orbital_truth["reference_plan"] if item.get("action") == "coast"), 600)
        self.assertEqual(len(orbital_public["debris"]), 2)
        self.assertEqual(len(orbital_public["beacons"]), 2)

        self.assertEqual(len(examples["specular_lighthouse_relay"][0]["rounds"]), 4)
        self.assertTrue(all(item["required_charge_ticks"] >= 50 and item["receiver"]["amplitude"] > 0 for item in examples["specular_lighthouse_relay"][0]["rounds"]))
        self.assertEqual(len(examples["wind_tunnel_seed_courier"][0]["gates"]), 4)
        self.assertEqual(len(examples["wind_tunnel_seed_courier"][0]["pods"]), 2)
        self.assertTrue(all(len(item["slots"]) == 2 for item in examples["wind_tunnel_seed_courier"][0]["gates"]))
        self.assertEqual(len(examples["hologram_silhouette_foundry"][0]["objects"]), 6)
        self.assertEqual(examples["hologram_silhouette_foundry"][0]["grid_size"], 7)
        self.assertTrue(all(entry.count(":") >= 2 and "#" in entry for view in examples["hologram_silhouette_foundry"][0]["target_masks"].values() for entry in view))
        self.assertEqual(len(examples["gravity_room_freight"][0]["board"]["gates"]), 4)
        self.assertGreaterEqual(len(examples["gravity_room_freight"][1]["solution"]), 14)
        self.assertEqual(len(flood_public["chambers"]), 5)
        self.assertEqual(len(flood_public["capsules"]), 2)
        self.assertEqual(len(flood_public["circuits"]), 5)
        self.assertEqual(len(examples["elastic_membrane_sorter"][0]["rounds"]), 3)
        self.assertTrue(all(len(item["checkpoints"]) == 2 for item in examples["elastic_membrane_sorter"][0]["rounds"]))
        self.assertEqual(len(examples["pheromone_dispatch"][0]["fields"]), 2)
        self.assertEqual(examples["pheromone_dispatch"][0]["physics"]["delivery_required"], 7)
        self.assertEqual(len(examples["clockwork_clutch_safe"][1]["release_schedule"]), 4)
        self.assertEqual(examples["clockwork_clutch_safe"][0]["physics"]["load_numerator"], 4)
        self.assertEqual(len(examples["marionette_checkpoint"][0]["poses"]), 3)
        self.assertTrue(all(item["tracking_ticks"] >= 60 for item in examples["marionette_checkpoint"][0]["poses"]))

    def test_every_incubator_plugin_has_a_complete_identity_bound_surface(self) -> None:
        benchmark_root = resolve_benchmark_root("weird_captcha_gym")
        setup_spec = importlib.util.spec_from_file_location(
            "weird_captcha_all_incubator_plugins_setup_test",
            benchmark_root / "shared_scripts" / "setup_task.py",
        )
        self.assertIsNotNone(setup_spec and setup_spec.loader)
        setup = importlib.util.module_from_spec(setup_spec)
        setup_spec.loader.exec_module(setup)
        generator_root = benchmark_root / "shared_scripts" / "incubator_generators"
        mechanics = sorted(path.stem for path in generator_root.glob("*.py") if not path.name.startswith("_"))
        self.assertGreaterEqual(len(mechanics), 10)
        for mechanic in mechanics:
            env_root = benchmark_root / "environments" / f"{mechanic}_env"
            task_root = env_root / "tasks" / f"{mechanic}_seed_0001"
            task_path = task_root / "task.json"
            grader_path = benchmark_root / "shared_runtime" / "server" / "incubator_graders" / f"{mechanic}.py"
            frontend_root = benchmark_root / "shared_runtime" / "app" / "mechanics"
            solver_path = benchmark_root / "tools" / "incubator_solvers" / f"{mechanic}.py"
            split_path = benchmark_root / "splits" / f"{mechanic}_split.json"
            for required in (
                env_root / "env.json",
                task_path,
                task_root / "verifier.py",
                grader_path,
                frontend_root / f"{mechanic}.js",
                frontend_root / f"{mechanic}.css",
                solver_path,
                split_path,
            ):
                self.assertTrue(required.is_file(), f"{mechanic}: missing {required.relative_to(benchmark_root)}")

            task = json.loads(task_path.read_text(encoding="utf-8"))
            self.assertEqual(task["metadata"]["status"], "prototype_visual_candidate", mechanic)
            public_a, truth_a = setup.generate_incubator_candidate(task, f"surface-{mechanic}")
            public_b, truth_b = setup.generate_incubator_candidate(task, f"surface-{mechanic}")
            public_c, truth_c = setup.generate_incubator_candidate(task, f"surface-other-{mechanic}")
            self.assertEqual((public_a, truth_a), (public_b, truth_b), mechanic)
            self.assertNotEqual(truth_a["challenge_id"], truth_c["challenge_id"], mechanic)
            self.assertEqual(public_a["challenge_id"], truth_a["challenge_id"], mechanic)
            self.assertEqual(public_a["mechanic_id"], mechanic)
            self.assertEqual(truth_a["mechanic_id"], mechanic)
            self.assertNotIn("seed", public_a)
            asset_manifest = benchmark_root / str(public_a["asset_manifest"])
            self.assertTrue(asset_manifest.is_file(), f"{mechanic}: missing asset manifest")

            grader_spec = importlib.util.spec_from_file_location(f"all_incubator_grader_{mechanic}", grader_path)
            self.assertIsNotNone(grader_spec and grader_spec.loader)
            grader = importlib.util.module_from_spec(grader_spec)
            grader_spec.loader.exec_module(grader)
            stale = grader.grade({"mechanic_id": mechanic, "challenge_id": "stale"}, truth_a, public_a)
            self.assertFalse(stale.get("passed"), mechanic)


if __name__ == "__main__":
    unittest.main()
