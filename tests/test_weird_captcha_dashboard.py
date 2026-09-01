from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from unittest import mock

from weird_captcha_gym.dashboard.catalog import BENCHMARK_ROOT, REPO_ROOT, build_catalog
from weird_captcha_gym.dashboard.capability_annotations import (
    ANNOTATIONS,
    LEGACY_TEMPORAL_ANNOTATION_STATUS,
)
from weird_captcha_gym.dashboard.atlas import (
    AtlasCurationStore, COLLECTION_ROOT, artifact_page, build_atlas, instance_detail, instance_page,
    source_detail, specimen_detail,
)
from weird_captcha_gym.dashboard.server import (
    DashboardServer, EvaluationManager, SessionManager, paired_dashboard_url,
)
from weird_captcha_gym.dashboard.export_static import _validate_output_path, export_dashboard
from weird_captcha_gym.dashboard.reviews import EnvironmentReviewStore
from weird_captcha_gym.shared_runtime.server.legacy_browser_grader import grade as grade_legacy_browser_result
from weird_captcha_gym.shared_runtime.server import grillmaster_witness
from weird_captcha_gym.shared_runtime.server.weird_captcha_server import PuzzleServer
from weird_captcha_gym.shared_scripts.setup_task import generate_task_state, load_task
from run import launcher_args


PACK_III = {
    "shadow_crime_lab", "craftcha_alchemy_bench", "occlusion_shell_swindle",
    "ribbon_switchboard", "magnetic_stripe_purgatory",
}
PACK_IV = {
    "trajectory_catcher", "impossible_panorama", "flat_pack_compliance",
    "crash_deadline_hovercar", "robot_art_critic",
}
PACK_V = {
    "photograph_eats_the_room", "clockwork_doppelganger_customs",
    "recursive_dollhouse_smuggling", "flat_prisoner",
    "forced_perspective_moving_day",
}
PACK_VI = {
    "lidar_blacksite", "tomographic_baggage_surgery",
    "three_camera_claw_machine", "zero_g_cable_autopsy",
    "portal_freight_oversized_parcel",
}
PACK_VII = {
    "specular_lighthouse_relay", "wind_tunnel_seed_courier",
    "hologram_silhouette_foundry", "orbital_docking_customs",
    "gravity_room_freight",
}
PACK_VIII = {
    "floodgate_archive_rescue", "elastic_membrane_sorter",
    "pheromone_dispatch", "clockwork_clutch_safe",
    "marionette_checkpoint",
}
PENDING_NEXT_TEN_V2 = {
    "bureaucratic_signature_trap", "temporal_memory_first_change",
    "polyrhythm_customs", "exact_change_candy_cascade",
    "tiny_fps_customs", "thirty_year_time_wheel",
    "photograph_eats_the_room", "clockwork_doppelganger_customs",
    "recursive_dollhouse_smuggling", "flat_prisoner",
}
PENDING_NEXT_TEN_V3 = {
    "forced_perspective_moving_day", "lidar_blacksite",
    "tomographic_baggage_surgery", "three_camera_claw_machine",
    "zero_g_cable_autopsy", "portal_freight_oversized_parcel",
    "code_to_diagram_captcha", "exit_vim_terminal_escape",
    "fake_desktop_automation_inversion", "impossible_ecology",
}
FINAL_ELEVEN_V1 = {
    "shadow_crime_lab", "trajectory_catcher", "jigsaw_slider_alignment",
    "microgame_gauntlet", "minecraft_block_grid", "relation_prompt_grounding",
    "rorschach_fixed_rubric", "single_scene_split_boxes",
    "top_face_dice_arithmetic", "trace_shape_without_walls",
    "wizard_critter_capture",
}
FOUNDATIONAL_SEVEN_V1 = {
    "motion_only_ghost_jigsaw", "cursor_constellation_hunt",
    "parallel_grillmaster", "rotating_keyboard", "slot_reel_capture",
    "domino_autopsy", "funeral_ritual",
}
REMAINING_MODULAR_FOURTEEN_V1 = {
    "consequences_boss", "popup_exorcist", "slime_commute",
    "reload_interruption", "rotate_wrong_thing_upright",
    "wonky_text_hostile_rendering", "surreal_apple_on_tree_grid",
    "cursor_lens_reveal", "modifier_stack_image_grid",
    "board_game_captcha", "craftcha_alchemy_bench",
    "occlusion_shell_swindle", "ribbon_switchboard",
    "magnetic_stripe_purgatory",
}
SURVEY_CORPUS_AVAILABLE = (
    (COLLECTION_ROOT / "catalog.jsonl").is_file()
    and (COLLECTION_ROOT / "mechanic-index.jsonl").is_file()
    and (COLLECTION_ROOT / "sources").is_dir()
)
SURVEY_SKIP_REASON = "optional sibling research/collection survey corpus is not present"


class WeirdCaptchaDashboardTests(unittest.TestCase):
    def test_human_launcher_defaults_local_and_expands_hosted_shortcut(self) -> None:
        self.assertEqual(launcher_args([]), ["--open"])
        self.assertEqual(launcher_args(["--runner", "local"]), ["--open", "--runner", "local"])
        hosted = launcher_args(["--hosted", "--runner", "local"])
        self.assertEqual(hosted[:6], [
            "--companion",
            "--allow-origin",
            "https://gym-anything.github.io",
            "--dashboard-url",
            "https://gym-anything.github.io/weird-cua-bench/",
            "--open",
        ])
        self.assertEqual(hosted[6:], ["--runner", "local"])

    def test_companion_auto_pairing_uses_a_fragment_and_exact_allowed_origin(self) -> None:
        token = "automatic_pairing_token_with_enough_entropy"
        url = paired_dashboard_url(
            "https://gym-anything.github.io/weird-cua-bench/#/environments",
            token,
            {"https://gym-anything.github.io"},
        )
        self.assertEqual(url, f"https://gym-anything.github.io/weird-cua-bench/#pair={token}")
        with self.assertRaisesRegex(ValueError, "exactly match"):
            paired_dashboard_url(
                "https://hostile.example/weird-cua-bench/",
                token,
                {"https://gym-anything.github.io"},
            )
        with self.assertRaisesRegex(ValueError, "absolute"):
            paired_dashboard_url("/weird-cua-bench/", token, {"https://gym-anything.github.io"})


    @unittest.skipUnless(SURVEY_CORPUS_AVAILABLE, SURVEY_SKIP_REASON)
    def test_atlas_ingests_individual_specimens_sources_and_real_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = AtlasCurationStore(Path(temporary) / "curation.json")
            atlas = build_atlas(store)
        self.assertTrue(atlas["available"])
        self.assertEqual(atlas["stats"]["designs"], 44)
        self.assertEqual(atlas["stats"]["variants"], 250)
        self.assertEqual(atlas["stats"]["instances"], 1_043)
        self.assertEqual(atlas["stats"]["ground_truth_instances"], 983)
        self.assertEqual(atlas["stats"]["captured_examples"], 60)
        self.assertEqual(atlas["stats"]["catalog_records"], 1_411)
        self.assertEqual(atlas["stats"]["specimens"], 294)  # compatibility: designs + variants
        self.assertEqual(atlas["stats"]["sources"], 74)
        self.assertEqual(atlas["stats"]["files"], 19_168)
        self.assertEqual(atlas["stats"]["media"], 1_788)
        self.assertEqual(atlas["stats"]["visual_assets"], 12_710)
        self.assertEqual(atlas["stats"]["indexed_mechanics"], 44)
        specimen_types = Counter(specimen["specimen_type"] for specimen in atlas["specimens"])
        self.assertEqual(specimen_types["indexed_mechanic"], 44)
        self.assertEqual(specimen_types["verified_generator"], 28)
        self.assertEqual(specimen_types["extracted_game_screen"], 16)
        self.assertEqual(specimen_types["source_component"], 14)
        self.assertEqual(len(atlas["instance_sources"]), 3)
        self.assertEqual(len(atlas["instance_families"]), 52)

    @unittest.skipUnless(SURVEY_CORPUS_AVAILABLE, SURVEY_SKIP_REASON)
    def test_atlas_details_preserve_item_level_evidence_and_source_notes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = AtlasCurationStore(Path(temporary) / "curation.json")
            slot_machine = specimen_detail("neal-im-not-a-robot--level-40", store)
            self.assertEqual(slot_machine["title"], "Slot Machine")
            self.assertTrue(any("level-40" in artifact["path"] for artifact in slot_machine["artifacts"]))
            captured = specimen_detail("captcha-rpg--state-01", store)
            self.assertTrue(any("01-levelOneVerifyButton.png" in artifact["path"] for artifact in captured["artifacts"]))
            dossier = source_detail("captcha-rpg", store)
            self.assertIn("Captcha RPG", dossier["notes"])
            self.assertEqual(len(dossier["specimens"]), 50)
            images = artifact_page("nextgen-captchas-benchmark", kind="image", limit=12)
            self.assertEqual(len(images["artifacts"]), 12)
            self.assertTrue(images["has_more"])
            self.assertTrue(all(artifact["kind"] == "image" for artifact in images["artifacts"]))
            page = instance_page(source="nextgen-captchas-benchmark", family="3D_Viewpoint", limit=2, store=store)
            self.assertEqual(page["total"], 20)
            self.assertEqual(len(page["instances"]), 2)
            concrete = instance_detail(page["instances"][0]["id"], store)
            self.assertEqual(concrete["ground_truth_status"], "recorded")
            self.assertEqual(len(concrete["assets"]), 10)
            self.assertIn("answer", concrete["ground_truth"])
            virc = instance_page(source="visual-reasoning-captcha-vtt", limit=1, store=store)
            self.assertEqual(virc["total"], 60)
            self.assertEqual(virc["instances"][0]["ground_truth_status"], "unavailable")

    @unittest.skipUnless(SURVEY_CORPUS_AVAILABLE, SURVEY_SKIP_REASON)
    def test_atlas_curation_is_persistent_without_fabricating_an_environment(self) -> None:
        before = build_catalog()["stats"]["total"]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "atlas-curation.json"
            store = AtlasCurationStore(path)
            saved = store.update("neal-im-not-a-robot--level-40", {"decision": "maybe", "note": "Timing is the actual task."})
            self.assertEqual(saved["decision"], "maybe")
            promoted = store.update("neal-im-not-a-robot--level-40", {"decision": "maybe", "note": saved["note"], "promoted": True})
            self.assertEqual(promoted["decision"], "shortlisted")
            self.assertTrue(promoted["promoted"])
            reloaded = build_atlas(AtlasCurationStore(path))
            specimen = next(item for item in reloaded["specimens"] if item["id"] == "neal-im-not-a-robot--level-40")
            self.assertEqual(specimen["curation"]["note"], "Timing is the actual task.")
            self.assertTrue(specimen["curation"]["promoted"])
            self.assertEqual(reloaded["stats"]["promoted"], 1)
            concrete_id = instance_page(limit=1, store=store)["instances"][0]["id"]
            store.update(concrete_id, {"decision": "shortlisted", "note": "concrete seed"})
            self.assertEqual(instance_detail(concrete_id, store)["curation"]["note"], "concrete seed")
        self.assertEqual(build_catalog()["stats"]["total"], before)

    @unittest.skipIf(SURVEY_CORPUS_AVAILABLE, "full sibling survey corpus is present")
    def test_atlas_gracefully_reports_an_absent_optional_survey_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            atlas = build_atlas(AtlasCurationStore(Path(temporary) / "curation.json"))
        self.assertFalse(atlas["available"])
        self.assertEqual(atlas["stats"]["catalog_records"], 0)
        self.assertEqual(atlas["stats"]["files"], 0)



    def test_legacy_temporal_annotations_are_preserved_as_a_dated_snapshot(self) -> None:
        snapshot_path = REPO_ROOT / LEGACY_TEMPORAL_ANNOTATION_STATUS["snapshot"]
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        self.assertEqual(LEGACY_TEMPORAL_ANNOTATION_STATUS["status"], "legacy_environment_level")
        self.assertEqual(snapshot["status"], "legacy_environment_level")
        self.assertEqual(snapshot["marked_old"], LEGACY_TEMPORAL_ANNOTATION_STATUS["marked_old"])
        self.assertEqual(snapshot["annotation_count"], 75)
        preserved = {
            item["mechanic_id"]: item["temporal"]
            for item in snapshot["annotations"]
        }
        self.assertEqual(preserved, {
            mechanic_id: ANNOTATIONS[mechanic_id]["temporal"]
            for mechanic_id in preserved
        })
        self.assertNotIn("cockpit_preflight_checklist", preserved)

    def test_controlled_environment_cards_use_the_current_profile_label(self) -> None:
        controlled = [
            environment
            for environment in build_catalog()["environments"]
            if environment.get("difficulty_control")
        ]
        self.assertEqual(
            len(controlled),
            len(list((BENCHMARK_ROOT / "environments").glob("*_env/controls.json"))),
        )
        for environment in controlled:
            self.assertEqual(environment["difficulty_control"]["interactions"], ["simplified", "full"])
            self.assertIn(
                environment["difficulty_control"]["baseline_interaction"],
                environment["difficulty_control"]["interactions"],
            )
            current = [
                profile
                for profile in environment["difficulty_control"]["profiles"]
                if profile["current_implementation"]
            ]
            self.assertEqual(len(current), 1, environment["mechanic_id"])
            self.assertEqual(
                environment["difficulty"],
                current[0]["label"].replace("_", " "),
                environment["mechanic_id"],
            )

    def test_rorschach_annotation_matches_the_visible_passing_strategy(self) -> None:
        environment = next(
            item
            for item in build_catalog()["environments"]
            if item["mechanic_id"] == "rorschach_fixed_rubric"
        )
        annotation = environment["capability_annotation"]
        self.assertEqual(annotation["real_time"], "yes")
        self.assertFalse(annotation["temporal"])
        self.assertIn("archived response labels", annotation["interaction"])
        self.assertNotIn("observe every response film", annotation["interaction"])

    def test_all_thirty_selected_pack_three_through_eight_designs_are_promoted(self) -> None:
        selected = PACK_III | PACK_IV | PACK_V | PACK_VI | PACK_VII | PACK_VIII
        environments = {
            environment["mechanic_id"]: environment
            for environment in build_catalog()["environments"]
            if environment["mechanic_id"] in selected
        }
        self.assertEqual(set(environments), selected)
        self.assertEqual(Counter(environment["group"] for environment in environments.values()), {
            "Interaction III": 5,
            "Interaction IV": 5,
            "Interaction V": 5,
            "Interaction VI": 5,
            "Interaction VII": 5,
            "Interaction VIII": 5,
        })
        for mechanic, environment in environments.items():
            self.assertEqual(environment["stage"], "built", mechanic)
            self.assertTrue(environment["launchable"], mechanic)
            self.assertTrue(environment["tasks"], mechanic)
            self.assertTrue(environment["screenshots"], mechanic)
            self.assertTrue(environment["validation"]["ok"], mechanic)
            self.assertTrue(environment["source_anchors"], mechanic)
            self.assertEqual(environment["design_status"], "local_verification_pending_vnc_human_evidence", mechanic)

    def test_incubator_queue_has_been_promoted_to_real_environments(self) -> None:
        candidates = [environment for environment in build_catalog()["environments"] if environment["stage"] == "incubator"]
        self.assertEqual(candidates, [])
        expected = {
            "wrong_number",
            "bomb_manual_from_hell",
            "dead_mans_switch",
            "blind_dice_courier",
            "input_lag_forklift",
            "insider_trading_captcha",
            "polyrhythm_customs",
            "exact_change_candy_cascade",
            "tiny_fps_customs",
            "thirty_year_time_wheel",
        }
        promoted = [
            environment
            for environment in build_catalog()["environments"]
            if environment["mechanic_id"] in expected
        ]
        self.assertEqual(
            {environment["mechanic_id"] for environment in promoted},
            expected,
        )
        for environment in promoted:
            self.assertEqual(environment["group"], "Incubator")
            self.assertEqual(environment["stage"], "built")
            self.assertTrue(environment["launchable"])
            self.assertTrue(environment["tasks"])
            self.assertTrue(environment["screenshots"])
            self.assertTrue(environment["source_anchors"])

    def test_incubator_batch_one_is_launchable_but_still_pending_human_vnc_evidence(self) -> None:
        expected = {
            "wrong_number",
            "bomb_manual_from_hell",
            "dead_mans_switch",
            "blind_dice_courier",
            "input_lag_forklift",
        }
        environments = {
            environment["mechanic_id"]: environment
            for environment in build_catalog()["environments"]
            if environment["mechanic_id"] in expected
        }
        self.assertEqual(set(environments), expected)
        for mechanic, environment in environments.items():
            self.assertEqual(environment["stage"], "built", mechanic)
            self.assertTrue(environment["launchable"], mechanic)
            self.assertTrue(environment["screenshots"], mechanic)
            self.assertTrue(environment["validation"]["ok"], mechanic)
            self.assertEqual(environment["design_status"], "local_verification_pending_vnc_human_evidence")

    def test_incubator_batch_two_is_launchable_but_still_pending_human_vnc_evidence(self) -> None:
        expected = {
            "insider_trading_captcha",
            "polyrhythm_customs",
            "exact_change_candy_cascade",
            "tiny_fps_customs",
            "thirty_year_time_wheel",
        }
        environments = {
            environment["mechanic_id"]: environment
            for environment in build_catalog()["environments"]
            if environment["mechanic_id"] in expected
        }
        self.assertEqual(set(environments), expected)
        for mechanic, environment in environments.items():
            self.assertEqual(environment["stage"], "built", mechanic)
            self.assertTrue(environment["launchable"], mechanic)
            self.assertTrue(environment["screenshots"], mechanic)
            self.assertTrue(environment["validation"]["ok"], mechanic)
            self.assertEqual(environment["design_status"], "local_verification_pending_vnc_human_evidence")

    def test_historical_incubator_batch_three_is_launchable_with_evidence(self) -> None:
        expected = {
            "code_to_diagram_captcha",
            "exit_vim_terminal_escape",
            "fake_desktop_automation_inversion",
            "impossible_ecology",
            "jigsaw_slider_alignment",
        }
        environments = {
            environment["mechanic_id"]: environment
            for environment in build_catalog()["environments"]
            if environment["mechanic_id"] in expected
        }
        self.assertEqual(set(environments), expected)
        for mechanic, environment in environments.items():
            self.assertEqual(environment["stage"], "built", mechanic)
            self.assertTrue(environment["launchable"], mechanic)
            self.assertTrue(environment["screenshots"], mechanic)
            self.assertTrue(environment["validation"]["ok"], mechanic)
            self.assertEqual(environment["design_status"], "local_verification_pending_vnc_human_evidence")

    def test_historical_incubator_batch_four_is_launchable_with_evidence(self) -> None:
        expected = {
            "microgame_gauntlet",
            "minecraft_block_grid",
            "relation_prompt_grounding",
            "rorschach_fixed_rubric",
            "single_scene_split_boxes",
        }
        environments = {
            environment["mechanic_id"]: environment
            for environment in build_catalog()["environments"]
            if environment["mechanic_id"] in expected
        }
        self.assertEqual(set(environments), expected)
        for mechanic, environment in environments.items():
            self.assertEqual(environment["stage"], "built", mechanic)
            self.assertTrue(environment["launchable"], mechanic)
            self.assertTrue(environment["screenshots"], mechanic)
            self.assertTrue(environment["validation"]["ok"], mechanic)
            self.assertEqual(environment["design_status"], "local_verification_pending_vnc_human_evidence")

    def test_historical_incubator_batch_five_is_launchable_with_evidence(self) -> None:
        expected = {
            "top_face_dice_arithmetic",
            "trace_shape_without_walls",
            "wizard_critter_capture",
        }
        environments = {
            environment["mechanic_id"]: environment
            for environment in build_catalog()["environments"]
            if environment["mechanic_id"] in expected
        }
        self.assertEqual(set(environments), expected)
        for mechanic, environment in environments.items():
            self.assertEqual(environment["stage"], "built", mechanic)
            self.assertTrue(environment["launchable"], mechanic)
            self.assertTrue(environment["screenshots"], mechanic)
            self.assertTrue(environment["validation"]["ok"], mechanic)
            self.assertEqual(environment["design_status"], "local_verification_pending_vnc_human_evidence")

    def test_interaction_three_batch_six_is_launchable_with_evidence(self) -> None:
        expected = {
            "shadow_crime_lab",
            "craftcha_alchemy_bench",
            "occlusion_shell_swindle",
            "ribbon_switchboard",
            "magnetic_stripe_purgatory",
        }
        environments = {
            environment["mechanic_id"]: environment
            for environment in build_catalog()["environments"]
            if environment["mechanic_id"] in expected
        }
        self.assertEqual(set(environments), expected)
        for mechanic, environment in environments.items():
            self.assertEqual(environment["group"], "Interaction III", mechanic)
            self.assertEqual(environment["stage"], "built", mechanic)
            self.assertTrue(environment["launchable"], mechanic)
            self.assertTrue(environment["screenshots"], mechanic)
            self.assertTrue(environment["validation"]["ok"], mechanic)
            self.assertEqual(environment["design_status"], "local_verification_pending_vnc_human_evidence")

    def test_interaction_four_batch_seven_is_launchable_with_evidence(self) -> None:
        expected = {
            "trajectory_catcher",
            "impossible_panorama",
            "flat_pack_compliance",
            "crash_deadline_hovercar",
            "robot_art_critic",
        }
        environments = {
            environment["mechanic_id"]: environment
            for environment in build_catalog()["environments"]
            if environment["mechanic_id"] in expected
        }
        self.assertEqual(set(environments), expected)
        for mechanic, environment in environments.items():
            self.assertEqual(environment["group"], "Interaction IV", mechanic)
            self.assertEqual(environment["stage"], "built", mechanic)
            self.assertTrue(environment["launchable"], mechanic)
            self.assertTrue(environment["screenshots"], mechanic)
            self.assertTrue(environment["validation"]["ok"], mechanic)
            self.assertEqual(environment["design_status"], "local_verification_pending_vnc_human_evidence")

    def test_interaction_five_batch_eight_is_launchable_with_independent_evidence(self) -> None:
        environments = {
            environment["mechanic_id"]: environment
            for environment in build_catalog()["environments"]
            if environment["mechanic_id"] in PACK_V
        }
        self.assertEqual(set(environments), PACK_V)
        for mechanic, environment in environments.items():
            self.assertEqual(environment["group"], "Interaction V", mechanic)
            self.assertEqual(environment["stage"], "built", mechanic)
            self.assertTrue(environment["launchable"], mechanic)
            self.assertTrue(environment["screenshots"], mechanic)
            self.assertTrue(environment["validation"]["ok"], mechanic)
            self.assertEqual(environment["design_status"], "local_verification_pending_vnc_human_evidence")

        summary = json.loads((BENCHMARK_ROOT / "evidence/incubator_batch_eight_v1/summary.json").read_text(encoding="utf-8"))
        self.assertTrue(summary["ok"])
        self.assertEqual(set(summary["mechanics"]), PACK_V)
        self.assertEqual(sum(len(result["screenshots"]) for result in summary["mechanics"].values()), 46)
        for mechanic, result in summary["mechanics"].items():
            self.assertTrue(result["ok"], mechanic)
            self.assertTrue(result["server_grade"]["passed"], mechanic)
            self.assertTrue(result["direct_grade"]["passed"], mechanic)
            self.assertTrue(result["verifier"]["passed"], mechanic)


    def test_interaction_six_batch_nine_is_launchable_with_independent_evidence(self) -> None:
        environments = {
            environment["mechanic_id"]: environment
            for environment in build_catalog()["environments"]
            if environment["mechanic_id"] in PACK_VI
        }
        self.assertEqual(set(environments), PACK_VI)
        for mechanic, environment in environments.items():
            self.assertEqual(environment["group"], "Interaction VI", mechanic)
            self.assertEqual(environment["stage"], "built", mechanic)
            self.assertTrue(environment["launchable"], mechanic)
            self.assertTrue(environment["screenshots"], mechanic)
            self.assertTrue(environment["validation"]["ok"], mechanic)
            self.assertEqual(environment["design_status"], "local_verification_pending_vnc_human_evidence")

        summary = json.loads((BENCHMARK_ROOT / "evidence/incubator_batch_nine_v1/summary.json").read_text(encoding="utf-8"))
        self.assertTrue(summary["ok"])
        self.assertEqual(set(summary["mechanics"]), PACK_VI)
        self.assertEqual(sum(len(result["screenshots"]) for result in summary["mechanics"].values()), 47)
        for mechanic, result in summary["mechanics"].items():
            self.assertTrue(result["ok"], mechanic)
            self.assertTrue(result["server_grade"]["passed"], mechanic)
            self.assertTrue(result["direct_grade"]["passed"], mechanic)
            self.assertTrue(result["verifier"]["passed"], mechanic)
        clean_acceptance = {
            "lidar_blacksite": "collisions 0",
            "three_camera_claw_machine": "collisions 0",
            "tomographic_baggage_surgery": "damages 0",
            "portal_freight_oversized_parcel": "collisions 0",
            "zero_g_cable_autopsy": "alarms 0/0",
        }
        for mechanic, marker in clean_acceptance.items():
            self.assertIn(marker, summary["mechanics"][mechanic]["direct_grade"]["feedback"])

    def test_interaction_seven_and_eight_are_launchable_with_independent_evidence(self) -> None:
        expected = PACK_VII | PACK_VIII
        environments = {
            environment["mechanic_id"]: environment
            for environment in build_catalog()["environments"]
            if environment["mechanic_id"] in expected
        }
        self.assertEqual(set(environments), expected)
        self.assertEqual(Counter(environment["group"] for environment in environments.values()), {
            "Interaction VII": 5,
            "Interaction VIII": 5,
        })
        for mechanic, environment in environments.items():
            self.assertEqual(environment["stage"], "built", mechanic)
            self.assertTrue(environment["launchable"], mechanic)
            self.assertTrue(environment["screenshots"], mechanic)
            self.assertTrue(environment["validation"]["ok"], mechanic)
            self.assertEqual(environment["human_status"], "script-verified-pending-human", mechanic)
            self.assertEqual(environment["design_status"], "local_verification_pending_vnc_human_evidence", mechanic)

        summary = json.loads((BENCHMARK_ROOT / "evidence/interaction_vii_viii_difficulty_v2/summary.json").read_text(encoding="utf-8"))
        self.assertTrue(summary["ok"])
        self.assertEqual(set(summary["mechanics"]), expected)
        self.assertEqual(sum(len(result["screenshots"]) for result in summary["mechanics"].values()), 52)
        for mechanic, result in summary["mechanics"].items():
            self.assertTrue(result["ok"], mechanic)
            self.assertTrue(result["server_grade"]["passed"], mechanic)
            self.assertTrue(result["direct_grade"]["passed"], mechanic)
            self.assertTrue(result["verifier"]["passed"], mechanic)

        multiseed = json.loads((BENCHMARK_ROOT / "evidence/interaction_vii_viii_difficulty_v2/multiseed-summary.json").read_text(encoding="utf-8"))
        self.assertTrue(multiseed["ok"])
        self.assertEqual(multiseed["browser_solves"], 30)
        self.assertEqual(set(multiseed["mechanics"]), expected)
        for mechanic, result in multiseed["mechanics"].items():
            self.assertEqual(result, {
                "direct_grade_passes": 3,
                "server_grade_passes": 3,
                "task_verifier_passes": 3,
            }, mechanic)

        films = json.loads((BENCHMARK_ROOT / "evidence/interaction_vii_viii_difficulty_v2/solution_videos/manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(films["ok"])
        self.assertTrue(films["frozen_contract_verified"])
        self.assertFalse(films["task_implementations_modified"])
        self.assertEqual(set(films["videos"]), expected)
        for mechanic, recording in films["videos"].items():
            self.assertEqual((recording["media"]["width"], recording["media"]["height"]), (1280, 720), mechanic)
            self.assertEqual(recording["media"]["codec"], "h264", mechanic)
            self.assertTrue(recording["server_grade"]["passed"], mechanic)
            self.assertTrue(recording["direct_grade"]["passed"], mechanic)
            self.assertTrue(recording["verifier"]["passed"], mechanic)

    def test_next_ten_difficulty_v3_evidence_supersedes_historical_batch_frames(self) -> None:
        expected = {
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
        }
        environments = {
            environment["mechanic_id"]: environment
            for environment in build_catalog()["environments"]
            if environment["mechanic_id"] in expected
        }
        self.assertEqual(set(environments), expected)
        for mechanic, environment in environments.items():
            self.assertIn("/media/evidence/next_ten_difficulty_v3/", environment["cover"], mechanic)
            self.assertTrue(environment["screenshots"], mechanic)
            self.assertTrue(
                all(
                    "/media/evidence/next_ten_difficulty_v3/" in screenshot["url"]
                    for screenshot in environment["screenshots"]
                ),
                mechanic,
            )
            self.assertTrue(environment["validation"]["ok"], mechanic)

        summary = json.loads(
            (BENCHMARK_ROOT / "evidence/next_ten_difficulty_v3/summary.json").read_text(encoding="utf-8")
        )
        self.assertTrue(summary["ok"])
        self.assertEqual(set(summary["mechanics"]), expected)


    def test_eval_command_is_argument_safe_and_targets_weird_captcha(self) -> None:
        manager = EvaluationManager("avf")
        command, details = manager.build_command({
            "environment_id": "domino_autopsy_env",
            "task_id": "domino_autopsy_seed_0001",
            "agent": "Qwen3VLAgent",
            "model": "Qwen/Qwen3-VL-4B-Thinking",
            "steps": 80,
            "seed": 9,
            "experiment": "dashboard-smoke",
        })
        self.assertTrue(any("weird_captcha_gym" in argument for argument in command))
        self.assertNotIn("--benchmark", command)
        self.assertIn("domino_autopsy_seed_0001", command)
        self.assertNotIn("shell=True", command)
        self.assertEqual(details["steps"], 80)
        with self.assertRaises(ValueError):
            manager.build_command({
                "environment_id": "domino_autopsy_env",
                "agent": "Qwen3VLAgent; rm -rf /",
                "model": "qwen3-vl",
            })


    def test_legacy_browser_grader_is_exactly_equal_to_server_grading(self) -> None:
        methods = {
            "motion_only_ghost_jigsaw": "_grade_ghost_jigsaw_submission",
            "cursor_constellation_hunt": "_grade_constellation_submission",
            "parallel_grillmaster": "_grade_grillmaster_submission",
            "rotating_keyboard": "_grade_rotating_keyboard_submission",
            "slot_reel_capture": "_grade_slot_reel_submission",
            "domino_autopsy": "_grade_domino_submission",
            "funeral_ritual": "_grade_funeral_submission",
        }
        environments = {item["mechanic_id"]: item for item in build_catalog()["environments"]}
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary)
            server = object.__new__(PuzzleServer)
            server.state_dir = state_dir
            for mechanic_id, method_name in methods.items():
                environment = environments[mechanic_id]
                task_id = environment["tasks"][0]["id"]
                task = load_task(REPO_ROOT / environment["environment_path"] / "tasks" / task_id / "task.json")
                public_state, truth = generate_task_state(task, f"browser-grader-parity:{mechanic_id}")
                (state_dir / "public_state.json").write_text(json.dumps(public_state), encoding="utf-8")
                (state_dir / "ground_truth.json").write_text(json.dumps(truth), encoding="utf-8")
                server_grade = getattr(server, method_name)

                invalid = {"mechanic_id": mechanic_id, "challenge_id": truth["challenge_id"]}
                self.assertEqual(
                    grade_legacy_browser_result(invalid, truth, public_state),
                    server_grade(invalid),
                    f"invalid parity: {mechanic_id}",
                )

                if mechanic_id == "motion_only_ghost_jigsaw":
                    success = {"placements": truth["expected_positions"]}
                elif mechanic_id == "cursor_constellation_hunt":
                    success = {"click": {"x": truth["expected_click"]["x"], "y": truth["expected_click"]["y"]}}
                elif mechanic_id == "parallel_grillmaster":
                    success = {"durations_ms": {key: value["target_ms"] for key, value in truth["targets"].items()}}
                elif mechanic_id == "rotating_keyboard":
                    success = {"text": truth["target"]}
                elif mechanic_id == "slot_reel_capture":
                    actions = []
                    minimum_elapsed = 0.0
                    reels_by_id = {
                        str(reel["id"]): reel
                        for reel in public_state["reels"]
                    }
                    for sequence, (reel_id, target) in enumerate(
                        zip(truth["reel_ids"], truth["sequence"]),
                        start=1,
                    ):
                        reel = reels_by_id[str(reel_id)]
                        target_index = reel["tokens"].index(target)
                        cycle = (
                            target_index - int(reel["phase"])
                        ) % len(reel["tokens"])
                        elapsed_ms = (
                            cycle + 0.5
                        ) * int(reel["interval_ms"])
                        while elapsed_ms < minimum_elapsed:
                            cycle += len(reel["tokens"])
                            elapsed_ms = (
                                cycle + 0.5
                            ) * int(reel["interval_ms"])
                        minimum_elapsed = elapsed_ms
                        actions.append({
                            "sequence": sequence,
                            "reel_id": reel_id,
                            "elapsed_ms": elapsed_ms,
                            "client_elapsed_ms": elapsed_ms,
                            "server_task_time_ms": elapsed_ms,
                            "server_received_wall_ns": sequence,
                            "observed_token": target,
                            "entered_key": target,
                            "accepted": True,
                            "input_source": "physical_keyboard",
                            "event_surface": "keyboard_keydown",
                        })
                    witness_key = grillmaster_witness._generate_key(
                        truth["challenge_id"]
                    )
                    public_key = grillmaster_witness._public_key(
                        witness_key
                    )
                    truth["slot_reel_interaction_public_key"] = public_key
                    signed_witness = {
                        "version": 1,
                        "mechanic_id": "slot_reel_capture",
                        "task_id": truth["task_id"],
                        "challenge_id": truth["challenge_id"],
                        "interaction": "full",
                        "clock_source": "server_active_task_clock_v1",
                        "public_key": public_key,
                        "actions": actions,
                        "finalized_wall_ns": 1,
                    }
                    witness_size = (
                        int(witness_key["n_hex"], 16).bit_length() + 7
                    ) // 8
                    encoded_witness = grillmaster_witness._encoded_message(
                        signed_witness,
                        witness_size,
                    )
                    witness_signature = pow(
                        int.from_bytes(encoded_witness, "big"),
                        int(witness_key["d_hex"], 16),
                        int(witness_key["n_hex"], 16),
                    )
                    trusted_witness = {
                        **signed_witness,
                        "signature_hex": witness_signature.to_bytes(
                            witness_size,
                            "big",
                        ).hex(),
                    }
                    (state_dir / "ground_truth.json").write_text(
                        json.dumps(truth),
                        encoding="utf-8",
                    )
                    success = {
                        "captured_sequence": truth["sequence"],
                        "frozen_reel_ids": truth["reel_ids"],
                        "wrong_keys": 0,
                        "actions": actions,
                        "trusted_witness": trusted_witness,
                    }
                elif mechanic_id == "domino_autopsy":
                    placements = {
                        str(domino_id): dict(slot)
                        for domino_id, slot in zip(
                            truth["loose_ids"],
                            truth["target_slots"],
                        )
                    }
                    ordered = sorted(
                        [
                            *[
                                (str(item["id"]), float(item["x"]))
                                for item in truth["fixed_dominoes"]
                            ],
                            *[
                                (str(domino_id), float(placements[str(domino_id)]["x"]))
                                for domino_id in truth["loose_ids"]
                            ],
                        ],
                        key=lambda item: item[1],
                    )
                    bell = str(truth["bell_body_id"])
                    chain = [*[item[0] for item in ordered], bell]
                    success = {
                        "placements": placements,
                        "physics_engine": "matter-js@0.20.0",
                        "bell_hit": True,
                        "bell_peak_angle": 0.6,
                        "run_completed": True,
                        "collision_pairs": [[left, right] for left, right in zip(chain, chain[1:])],
                    }
                else:
                    success = {
                        "events": truth["required_events"],
                        "brushed_cells": list(range(int(truth["brush_threshold"]))),
                        "gathered_flower_ids": truth["flower_ids"],
                        "completed": True,
                    }
                success.update({"mechanic_id": mechanic_id, "challenge_id": truth["challenge_id"]})
                browser_grade = grade_legacy_browser_result(success, truth, public_state)
                self.assertEqual(browser_grade, server_grade(success), f"success parity: {mechanic_id}")
                self.assertTrue(browser_grade["passed"], mechanic_id)

    def test_rotating_keyboard_live_grade_enforces_the_selected_input_surface(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary)
            server = object.__new__(PuzzleServer)
            server.state_dir = state_dir
            sources = {
                "simplified": ("physical_keyboard", "onscreen_keys"),
                "full": ("onscreen_keys", "physical_keyboard"),
            }
            for interaction, (correct_source, wrong_source) in sources.items():
                condition = {
                    "difficulty": 1,
                    "interaction": interaction,
                    "real_time": "live",
                    "difficulty_parameters": {},
                }
                truth = {
                    "mechanic_id": "rotating_keyboard",
                    "target": "ABC",
                    "control_condition": condition,
                }
                public_state = {
                    "mechanic_id": "rotating_keyboard",
                    "control_condition": condition,
                }
                (state_dir / "ground_truth.json").write_text(
                    json.dumps(truth),
                    encoding="utf-8",
                )
                (state_dir / "public_state.json").write_text(
                    json.dumps(public_state),
                    encoding="utf-8",
                )

                accepted = server._grade_rotating_keyboard_submission(
                    {"text": "ABC", "input_source": correct_source}
                )
                rejected = server._grade_rotating_keyboard_submission(
                    {"text": "ABC", "input_source": wrong_source}
                )

                self.assertTrue(accepted["passed"], interaction)
                self.assertFalse(rejected["passed"], interaction)
                self.assertIn("wrong interaction input", rejected["feedback"])

    def test_browser_session_canceled_during_setup_cannot_boot_after_shutdown(self) -> None:
        manager = SessionManager("local")
        setup_started = threading.Event()
        release_setup = threading.Event()
        cancel_observed = threading.Event()
        remove_browser_state = manager._remove_browser_state

        def delayed_setup(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
            setup_started.set()
            self.assertTrue(release_setup.wait(timeout=5))
            return subprocess.CompletedProcess([], 0, "", "")

        def observed_remove(job_id: str) -> None:
            remove_browser_state(job_id)
            cancel_observed.set()

        with (
            mock.patch("weird_captcha_gym.dashboard.server.subprocess.run", side_effect=delayed_setup),
            mock.patch("weird_captcha_gym.dashboard.server.subprocess.Popen") as popen,
            mock.patch.object(manager, "_remove_browser_state", side_effect=observed_remove),
        ):
            session = manager.start_browser(
                "domino_autopsy_env",
                "domino_autopsy_seed_0001",
                seed=12,
                auto_open=False,
            )
            self.assertTrue(setup_started.wait(timeout=5))
            manager.cleanup()
            release_setup.set()
            self.assertTrue(cancel_observed.wait(timeout=5))
            self.assertEqual(manager.get(session["id"])["status"], "stopped")
            self.assertFalse(Path(session["state_dir"]).exists())
            popen.assert_not_called()

    def test_controlled_browser_session_uses_selected_difficulty_task(self) -> None:
        manager = SessionManager("local")
        setup_started = threading.Event()
        release_setup = threading.Event()

        def delayed_setup(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
            setup_started.set()
            self.assertTrue(release_setup.wait(timeout=5))
            return subprocess.CompletedProcess([], 0, "", "")

        with (
            mock.patch("weird_captcha_gym.dashboard.server.subprocess.run", side_effect=delayed_setup),
            mock.patch("weird_captcha_gym.dashboard.server.subprocess.Popen") as popen,
        ):
            session = manager.start_browser(
                "input_lag_forklift_env",
                "input_lag_forklift_seed_0001",
                difficulty=5,
                interaction="full",
                seed=91,
                auto_open=False,
            )
            self.assertTrue(setup_started.wait(timeout=5))
            self.assertEqual(session["task_id"], "input_lag_forklift_d5_full_seed_0001")
            self.assertEqual(session["difficulty"], 5)
            self.assertEqual(session["interaction"], "full")
            task = json.loads(Path(session["task_json"]).read_text(encoding="utf-8"))
            condition = task["metadata"]["control_condition"]
            self.assertEqual(condition["difficulty"], 5)
            self.assertEqual(condition["interaction"], "full")
            self.assertEqual(condition["difficulty_parameters"]["control_lag"], 2)
            manager.cleanup()
            release_setup.set()
            popen.assert_not_called()

    def test_companion_requires_pairing_key_and_exact_allowed_origin(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        token = "test-companion-token-with-enough-entropy"
        origin = "https://captcha.example.test"
        server = DashboardServer(
            ("127.0.0.1", 0),
            "avf",
            review_path=Path(temporary.name) / "reviews.json",
            companion_token=token,
            allowed_origins={origin},
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            health_request = urllib.request.Request(f"{base}/api/health", headers={"Origin": origin})
            with urllib.request.urlopen(health_request, timeout=3) as response:
                health = json.loads(response.read())
                self.assertTrue(health["auth_required"])
                self.assertEqual(response.headers["Access-Control-Allow-Origin"], origin)

            unpaired = urllib.request.Request(f"{base}/api/system", headers={"Origin": origin})
            with self.assertRaises(urllib.error.HTTPError) as unpaired_error:
                urllib.request.urlopen(unpaired, timeout=3)
            self.assertEqual(unpaired_error.exception.code, 401)
            self.assertEqual(unpaired_error.exception.headers["Access-Control-Allow-Origin"], origin)

            paired = urllib.request.Request(
                f"{base}/api/system",
                headers={"Origin": origin, "X-Captcha-Bench-Token": token},
            )
            with urllib.request.urlopen(paired, timeout=3) as response:
                system = json.loads(response.read())
                self.assertTrue(system["companion"])

            hostile = urllib.request.Request(
                f"{base}/api/system",
                headers={"Origin": "https://hostile.example", "X-Captcha-Bench-Token": token},
            )
            with self.assertRaises(urllib.error.HTTPError) as hostile_error:
                urllib.request.urlopen(hostile, timeout=3)
            self.assertEqual(hostile_error.exception.code, 403)

            preflight = urllib.request.Request(
                f"{base}/api/sessions",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type,x-captcha-bench-token",
                    "Access-Control-Request-Private-Network": "true",
                },
                method="OPTIONS",
            )
            with urllib.request.urlopen(preflight, timeout=3) as response:
                self.assertEqual(response.status, 204)
                self.assertEqual(response.headers["Access-Control-Allow-Private-Network"], "true")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

