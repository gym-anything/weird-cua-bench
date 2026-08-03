from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import math
import subprocess
import types
from pathlib import Path

from benchmarks.weird_captcha_gym.shared_runtime.verifier_helpers import (
    verify_rotating_keyboard,
)


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "weird_captcha_gym"
CONTROLLED_ENVIRONMENTS = (
    "parallel_grillmaster_env",
    "blind_dice_courier_env",
    "bomb_manual_from_hell_env",
    "bureaucratic_signature_trap_env",
    "clockwork_clutch_safe_env",
    "clockwork_doppelganger_customs_env",
    "code_to_diagram_captcha_env",
    "craftcha_alchemy_bench_env",
    "dead_mans_switch_env",
    "domino_autopsy_env",
    "elastic_membrane_sorter_env",
    "exit_vim_terminal_escape_env",
    "marionette_checkpoint_env",
    "photograph_eats_the_room_env",
    "recursive_dollhouse_smuggling_env",
    "fake_desktop_automation_inversion_env",
    "funeral_ritual_env",
    "impossible_ecology_env",
    "impossible_panorama_env",
    "jigsaw_slider_alignment_env",
    "magnetic_stripe_purgatory_env",
    "consequences_boss_env",
    "crash_deadline_hovercar_env",
    "input_lag_forklift_env",
    "surreal_apple_on_tree_grid_env",
    "top_face_dice_arithmetic_env",
    "rotating_keyboard_env",
    "rotate_wrong_thing_upright_env",
    "insider_trading_captcha_env",
    "flat_prisoner_env",
    "forced_perspective_moving_day_env",
    "hologram_silhouette_foundry_env",
    "orbital_docking_customs_env",
    "portal_freight_oversized_parcel_env",
    "lidar_blacksite_env",
    "board_game_captcha_env",
    "flat_pack_compliance_env",
    "specular_lighthouse_relay_env",
    "wind_tunnel_seed_courier_env",
    "motion_only_ghost_jigsaw_env",
    "microgame_gauntlet_env",
    "modifier_stack_image_grid_env",
    "moving_checkbox_evasive_button_env",
    "occlusion_shell_swindle_env",
    "polyrhythm_customs_env",
    "ribbon_switchboard_env",
    "pheromone_dispatch_env",
    "popup_exorcist_env",
    "relation_prompt_grounding_env",
    "reload_interruption_env",
    "reverse_identity_gate_env",
    "robot_art_critic_env",
    "rorschach_fixed_rubric_env",
    "cursor_constellation_hunt_env",
    "cursor_lens_reveal_env",
    "exact_change_candy_cascade_env",
    "floodgate_archive_rescue_env",
    "gravity_room_freight_env",
    "minecraft_block_grid_env",
    "slime_commute_env",
    "slot_reel_capture_env",
    "semantic_drag_drop_absurdity_env",
    "shadow_crime_lab_env",
    "single_scene_split_boxes_env",
    "temporal_memory_first_change_env",
    "tomographic_baggage_surgery_env",
    "thirty_year_time_wheel_env",
    "three_camera_claw_machine_env",
    "tiny_fps_customs_env",
    "trace_shape_without_walls_env",
    "trajectory_catcher_env",
    "wonky_text_hostile_rendering_env",
    "wizard_critter_capture_env",
    "wrong_number_env",
    "zero_g_cable_autopsy_env",
)

APPROVED_BASELINE_LEVELS = {
    "parallel_grillmaster_env": 2,
    "blind_dice_courier_env": 4,
    "bomb_manual_from_hell_env": 4,
    "bureaucratic_signature_trap_env": 4,
    "clockwork_clutch_safe_env": 3,
    "clockwork_doppelganger_customs_env": 4,
    "code_to_diagram_captcha_env": 4,
    "craftcha_alchemy_bench_env": 4,
    "dead_mans_switch_env": 4,
    "domino_autopsy_env": 3,
    "elastic_membrane_sorter_env": 4,
    "exit_vim_terminal_escape_env": 4,
    "marionette_checkpoint_env": 4,
    "photograph_eats_the_room_env": 4,
    "recursive_dollhouse_smuggling_env": 4,
    "fake_desktop_automation_inversion_env": 3,
    "funeral_ritual_env": 3,
    "impossible_ecology_env": 4,
    "impossible_panorama_env": 4,
    "jigsaw_slider_alignment_env": 4,
    "magnetic_stripe_purgatory_env": 4,
    "consequences_boss_env": 1,
    "crash_deadline_hovercar_env": 4,
    "board_game_captcha_env": 3,
    "cursor_constellation_hunt_env": 2,
    "cursor_lens_reveal_env": 3,
    "exact_change_candy_cascade_env": 5,
    "floodgate_archive_rescue_env": 4,
    "gravity_room_freight_env": 4,
    "flat_pack_compliance_env": 4,
    "flat_prisoner_env": 4,
    "forced_perspective_moving_day_env": 4,
    "hologram_silhouette_foundry_env": 4,
    "orbital_docking_customs_env": 4,
    "portal_freight_oversized_parcel_env": 4,
    "input_lag_forklift_env": 4,
    "insider_trading_captcha_env": 2,
    "lidar_blacksite_env": 4,
    "minecraft_block_grid_env": 1,
    "motion_only_ghost_jigsaw_env": 4,
    "microgame_gauntlet_env": 4,
    "modifier_stack_image_grid_env": 3,
    "moving_checkbox_evasive_button_env": 4,
    "occlusion_shell_swindle_env": 2,
    "polyrhythm_customs_env": 4,
    "ribbon_switchboard_env": 4,
    "pheromone_dispatch_env": 4,
    "popup_exorcist_env": 2,
    "relation_prompt_grounding_env": 4,
    "reload_interruption_env": 4,
    "reverse_identity_gate_env": 4,
    "robot_art_critic_env": 4,
    "rorschach_fixed_rubric_env": 4,
    "rotate_wrong_thing_upright_env": 4,
    "rotating_keyboard_env": 4,
    "slime_commute_env": 4,
    "specular_lighthouse_relay_env": 3,
    "wind_tunnel_seed_courier_env": 4,
    "surreal_apple_on_tree_grid_env": 4,
    "top_face_dice_arithmetic_env": 5,
    "slot_reel_capture_env": 4,
    "semantic_drag_drop_absurdity_env": 3,
    "shadow_crime_lab_env": 4,
    "single_scene_split_boxes_env": 4,
    "temporal_memory_first_change_env": 4,
    "tomographic_baggage_surgery_env": 3,
    "thirty_year_time_wheel_env": 3,
    "three_camera_claw_machine_env": 4,
    "tiny_fps_customs_env": 4,
    "trace_shape_without_walls_env": 4,
    "trajectory_catcher_env": 4,
    "wonky_text_hostile_rendering_env": 3,
    "wizard_critter_capture_env": 4,
    "wrong_number_env": 4,
    "zero_g_cable_autopsy_env": 4,
}

DIFFICULTY_NAMES = {
    1: "very_easy",
    2: "easy",
    3: "medium",
    4: "hard",
    5: "very_hard",
}

# Historical task metadata is preserved verbatim even when the independent
# controllability audit assigns the implemented configuration to another
# level.
HISTORICAL_TASK_DIFFICULTY_OVERRIDES = {
    "parallel_grillmaster_env": "hard",
    "consequences_boss_env": "hard",
    "clockwork_doppelganger_customs_env": "extreme",
    "crash_deadline_hovercar_env": "extreme",
    "code_to_diagram_captcha_env": "extreme",
    "craftcha_alchemy_bench_env": "very_hard",
    "fake_desktop_automation_inversion_env": "extreme",
    "funeral_ritual_env": "hard",
    "impossible_ecology_env": "extreme",
    "forced_perspective_moving_day_env": "extreme",
    "hologram_silhouette_foundry_env": "extreme",
    "orbital_docking_customs_env": "extreme",
    "portal_freight_oversized_parcel_env": "extreme",
    "marionette_checkpoint_env": "extreme",
    "photograph_eats_the_room_env": "extreme",
    "recursive_dollhouse_smuggling_env": "extreme",
    "microgame_gauntlet_env": "extreme",
    "modifier_stack_image_grid_env": "hard",
    "moving_checkbox_evasive_button_env": "extreme",
    "occlusion_shell_swindle_env": "extreme",
    "ribbon_switchboard_env": "extreme",
    "relation_prompt_grounding_env": "extreme",
    "reload_interruption_env": "hard",
    "reverse_identity_gate_env": "extreme",
    "robot_art_critic_env": "extreme",
    "rorschach_fixed_rubric_env": "extreme",
    "semantic_drag_drop_absurdity_env": "hard",
    "tomographic_baggage_surgery_env": "extreme",
    "thirty_year_time_wheel_env": "hard",
    "three_camera_claw_machine_env": "extreme",
    "tiny_fps_customs_env": "very_hard",
    "trace_shape_without_walls_env": "extreme",
    "wonky_text_hostile_rendering_env": "hard",
    "zero_g_cable_autopsy_env": "extreme",
}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SETUP = load_module("controlled_setup_task", BENCHMARK / "shared_scripts" / "setup_task.py")
MATERIALIZER = load_module(
    "controlled_task_materializer", BENCHMARK / "tools" / "materialize_controlled_tasks.py"
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def controls_for(env_name: str) -> dict:
    return read_json(BENCHMARK / "environments" / env_name / "controls.json")


def base_task_for(env_name: str, mechanic: str) -> dict:
    return read_json(
        BENCHMARK
        / "environments"
        / env_name
        / "tasks"
        / f"{mechanic}_seed_0001"
        / "task.json"
    )


def task_for_level(env_name: str, level: int, interaction: str | None = None) -> dict:
    controls = controls_for(env_name)
    mechanic = controls["mechanic_id"]
    interaction = interaction or controls["baseline"]["interaction"]
    return MATERIALIZER.controlled_task(
        base_task_for(env_name, mechanic),
        mechanic_id=mechanic,
        level=level,
        interaction=interaction,
        profile=controls["difficulty"][str(level)],
        task_dir_name=f"{mechanic}_d{level}_{interaction}_seed_0001",
    )


def lidar_interaction_task(interaction: str) -> dict:
    return task_for_level("lidar_blacksite_env", 4, interaction)


def signature_interaction_task(interaction: str) -> dict:
    return task_for_level("bureaucratic_signature_trap_env", 4, interaction)


def blind_dice_interaction_task(interaction: str) -> dict:
    return task_for_level("blind_dice_courier_env", 4, interaction)


def generated_levels(env_name: str, seed: str = "controlled-profile-test"):
    return [SETUP.generate_task_state(task_for_level(env_name, level), seed) for level in range(1, 6)]


def without_control_identity(value: dict, *, extra: tuple[str, ...] = ()) -> dict:
    result = copy.deepcopy(value)
    for key in ("task_id", "challenge_id", "control_condition", *extra):
        result.pop(key, None)
    return result


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def test_control_files_have_one_baseline_and_five_profiles() -> None:
    control_files = {
        path.parent.name for path in (BENCHMARK / "environments").glob("*_env/controls.json")
    }
    assert set(CONTROLLED_ENVIRONMENTS) == control_files
    for env_name in CONTROLLED_ENVIRONMENTS:
        env_root = BENCHMARK / "environments" / env_name
        controls = controls_for(env_name)
        MATERIALIZER.validate_controls(controls, env_root)
        assert controls["baseline"]["difficulty"] in range(1, 6)
        assert controls["interaction"][controls["baseline"]["interaction"]]["implemented"] is True


def test_approved_baselines_match_control_files_and_original_tasks() -> None:
    assert set(APPROVED_BASELINE_LEVELS) == set(CONTROLLED_ENVIRONMENTS)
    for env_name, level in APPROVED_BASELINE_LEVELS.items():
        controls = controls_for(env_name)
        assert controls["baseline"]["difficulty"] == level
        task = base_task_for(env_name, controls["mechanic_id"])
        assert task["difficulty"] == HISTORICAL_TASK_DIFFICULTY_OVERRIDES.get(
            env_name,
            DIFFICULTY_NAMES[level],
        )


def test_materializer_writes_every_implemented_interaction_deterministically(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    for env_name in CONTROLLED_ENVIRONMENTS:
        env_root = BENCHMARK / "environments" / env_name
        MATERIALIZER.materialize_environment(env_root, first)
        MATERIALIZER.materialize_environment(env_root, second)
    first_tasks = sorted(first.glob("*_env/tasks/*/task.json"))
    second_tasks = sorted(second.glob("*_env/tasks/*/task.json"))
    expected_task_count = sum(
        5 * sum(bool(mode.get("implemented")) for mode in controls_for(env_name)["interaction"].values())
        for env_name in CONTROLLED_ENVIRONMENTS
    )
    assert len(first_tasks) == len(second_tasks) == expected_task_count
    for left, right in zip(first_tasks, second_tasks):
        assert left.relative_to(first) == right.relative_to(second)
        assert left.read_bytes() == right.read_bytes()
        task = read_json(left)
        condition = task["metadata"]["control_condition"]
        assert condition["difficulty"] in range(1, 6)
        assert condition["real_time"] == "live"
        assert isinstance(condition["difficulty_parameters"], dict)
        assert Path(task["hooks"]["pre_task"]).parent.name == left.parent.name
        profile = controls_for(left.parents[2].name)["difficulty"][str(condition["difficulty"])]
        if "natural_language" in profile:
            if (
                left.parents[2].name == "slot_reel_capture_env"
                and condition["interaction"] == "simplified"
            ):
                assert task["natural_language"].startswith("Click CAPTURE SYMBOL ")
            else:
                expected_instruction = (profile.get("natural_language_by_interaction") or {}).get(
                    condition["interaction"],
                    profile["natural_language"],
                )
                assert task["natural_language"] == expected_instruction


def test_original_tasks_match_their_independently_assigned_baselines() -> None:
    seed = "baseline-preservation"
    for env_name in CONTROLLED_ENVIRONMENTS:
        controls = controls_for(env_name)
        mechanic = controls["mechanic_id"]
        level = int(controls["baseline"]["difficulty"])
        original_public, original_truth = SETUP.generate_task_state(base_task_for(env_name, mechanic), seed)
        baseline_public, baseline_truth = SETUP.generate_task_state(task_for_level(env_name, level), seed)

        if mechanic == "rotating_keyboard":
            original_keyboard = original_public["keyboard"]
            baseline_keyboard = baseline_public["keyboard"]
            for key in ("target", "rows", "direction", "duration_ms"):
                assert baseline_keyboard[key] == original_keyboard[key]
            assert baseline_truth["target"] == original_truth["target"]
        elif mechanic == "input_lag_forklift":
            assert without_control_identity(baseline_public, extra=("queue_visibility",)) == without_control_identity(original_public)
            assert without_control_identity(baseline_truth, extra=("queue_visibility",)) == without_control_identity(original_truth)
        elif mechanic == "rotate_wrong_thing_upright":
            baseline_gimbal = copy.deepcopy(baseline_public["gimbal"])
            baseline_gimbal.pop("active_axes")
            baseline_gimbal.pop("target_needle_width")
            assert baseline_gimbal == original_public["gimbal"]
        elif mechanic == "insider_trading_captcha":
            assert without_control_identity(baseline_public, extra=("visible_chart_ticks",)) == without_control_identity(original_public)
            assert without_control_identity(baseline_truth, extra=("visible_chart_ticks",)) == without_control_identity(original_truth)
        elif mechanic in {
            "consequences_boss",
            "cursor_lens_reveal",
            "exact_change_candy_cascade",
            "minecraft_block_grid",
            "slime_commute",
        }:
            normalized_original = without_control_identity(original_public)
            normalized_baseline = without_control_identity(baseline_public)
            normalized_original["generator"]["name"] = normalized_baseline["generator"]["name"]
            if mechanic == "minecraft_block_grid":
                normalized_original["prompt"] = normalized_baseline["prompt"]
            assert normalized_baseline == normalized_original
            assert without_control_identity(baseline_truth) == without_control_identity(original_truth)
        else:
            assert without_control_identity(baseline_public) == without_control_identity(original_public)
            assert without_control_identity(baseline_truth) == without_control_identity(original_truth)


def _polyrhythm_payload(
    public: dict, truth: dict, interaction: str, *, shorten_holds: bool = False
) -> dict:
    source = "pointer_toggle" if interaction == "simplified" else "keyboard"
    events: list[dict] = []
    for note in truth["expected_notes"]:
        start = float(note["start_ms"])
        duration = 100.0 if shorten_holds and note["kind"] == "hold" else float(note["duration_ms"])
        events.extend((
            {"lane": str(note["lane"]), "type": "down", "t_ms": start, "source": source},
            {
                "lane": str(note["lane"]),
                "type": "up",
                "t_ms": start + duration,
                "source": source,
            },
        ))
    events.sort(key=lambda item: (float(item["t_ms"]), 0 if item["type"] == "up" else 1, str(item["lane"])))
    for sequence, event in enumerate(events):
        event["seq"] = sequence
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction_mode": interaction,
        "transcript": events,
    }


def test_polyrhythm_customs_controls_preserve_l4_and_bind_input_surfaces() -> None:
    env_name = "polyrhythm_customs_env"
    mechanic = "polyrhythm_customs"
    controls = controls_for(env_name)
    grader = load_module(
        "controlled_polyrhythm_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{mechanic}.py",
    )
    assert controls["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    assert controls["real_time"] == {
        "play_time_seconds": 120,
        "observation_window_ms": 1000,
        "frames_per_observation": 8,
    }
    assert base_task_for(env_name, mechanic)["natural_language"] == controls["difficulty"]["4"]["natural_language_by_interaction"]["full"]

    original = base_task_for(env_name, mechanic)
    for seed in ("polyrhythm-baseline-a", "polyrhythm-baseline-b"):
        original_public, original_truth = SETUP.generate_task_state(original, seed)
        baseline_public, baseline_truth = SETUP.generate_task_state(task_for_level(env_name, 4, "full"), seed)
        assert without_control_identity(baseline_public) == without_control_identity(original_public)
        assert without_control_identity(baseline_truth) == without_control_identity(original_truth)

    expected_lanes = [2, 3, 3, 4, 4]
    expected_holds = [1, 1, 2, 2, 3]
    expected_chords = [0, 1, 1, 2, 3]
    for level in range(1, 6):
        simplified_public, simplified_truth = SETUP.generate_task_state(
            task_for_level(env_name, level, "simplified"), f"polyrhythm-profile-{level}"
        )
        full_public, full_truth = SETUP.generate_task_state(
            task_for_level(env_name, level, "full"), f"polyrhythm-profile-{level}"
        )
        assert without_control_identity(simplified_public, extra=("prompt", "rules")) == without_control_identity(
            full_public, extra=("prompt", "rules")
        )
        assert without_control_identity(simplified_truth) == without_control_identity(full_truth)
        assert len(full_public["lanes"]) == expected_lanes[level - 1]
        assert sum(note["kind"] == "hold" for note in full_truth["expected_notes"]) == expected_holds[level - 1]
        assert len(full_truth["chords"]) == expected_chords[level - 1]
        if level == 1:
            assert len(full_truth["expected_notes"]) == 8
        if level == 5:
            assert len(full_truth["expected_notes"]) >= 23

        for interaction, public, truth in (
            ("simplified", simplified_public, simplified_truth),
            ("full", full_public, full_truth),
        ):
            payload = _polyrhythm_payload(public, truth, interaction)
            accepted = grader.grade(payload, truth, public)
            assert accepted["passed"] is True
            verifier = load_module(
                f"controlled_polyrhythm_verifier_{level}_{interaction}",
                BENCHMARK / "shared_runtime" / "verifier_helpers.py",
            )
            verification = verifier.verify_external_mechanic(
                {"result": payload, "ground_truth": truth, "public_state": public}, mechanic
            )
            assert verification["passed"] is True and verification["score"] == 100
            short_holds = _polyrhythm_payload(public, truth, interaction, shorten_holds=True)
            short_hold_grade = grader.grade(short_holds, truth, public)
            short_hold_verification = verifier.verify_external_mechanic(
                {"result": short_holds, "ground_truth": truth, "public_state": public}, mechanic
            )
            if level == 5:
                assert short_hold_grade["passed"] is False
                assert "holds 0/" in str(short_hold_grade["feedback"])
                assert short_hold_verification["passed"] is False and short_hold_verification["score"] == 0
            else:
                assert short_hold_grade["passed"] is True
                assert short_hold_verification["passed"] is True and short_hold_verification["score"] == 100
            if level == 4 and interaction == "full":
                original_public, original_truth = SETUP.generate_task_state(original, "polyrhythm-profile-4")
                original_short_holds = _polyrhythm_payload(
                    original_public, original_truth, "full", shorten_holds=True
                )
                assert grader.grade(original_short_holds, original_truth, original_public) == short_hold_grade
            wrong_mode = copy.deepcopy(payload)
            wrong_mode["interaction_mode"] = "full" if interaction == "simplified" else "simplified"
            assert grader.grade(wrong_mode, truth, public)["passed"] is False
            wrong_source = copy.deepcopy(payload)
            wrong_source["transcript"][0]["source"] = "keyboard" if interaction == "simplified" else "pointer_toggle"
            assert grader.grade(wrong_source, truth, public)["passed"] is False
            stale_identity = copy.deepcopy(payload)
            stale_identity["challenge_id"] = "stale-polyrhythm-challenge"
            assert grader.grade(stale_identity, truth, public)["passed"] is False


def _temporal_position(item: dict, elapsed_ms: float) -> list[float]:
    return [
        float(item["x0"]) + math.sin(float(item["phase"]) + elapsed_ms * float(item["rate_x"])) * float(item["amp_x"]),
        float(item["y0"]) + math.cos(float(item["phase"]) * .83 + elapsed_ms * float(item["rate_y"])) * float(item["amp_y"]),
    ]


def _temporal_payload(public: dict, truth: dict, interaction: str) -> dict:
    timeline = truth["timeline"]
    target_id = str(truth["target_object_id"])
    target = next(item for item in timeline["objects"] if item["id"] == target_id)
    first = timeline["events"][0]
    observation_source, selection_source = {
        "simplified": ("coordinate_controls", "settled_slot_button"),
        "full": ("canvas_pointer", "canvas_pointer"),
    }[interaction]
    events: list[dict] = []

    def push(kind: str, **details: object) -> None:
        events.append({"sequence": len(events) + 1, "kind": kind, **details})

    push("arm")
    pre_count = int(timeline["proof"]["minimum_pre_hits"])
    change_count = int(timeline["proof"]["minimum_change_hits"])
    first_at = int(first["at_ms"])
    for index in range(pre_count):
        at_ms = first_at - 300 + int(220 * index / max(1, pre_count - 1))
        push("observe", mode="review", timeline_ms=at_ms, cursor=_temporal_position(target, at_ms), input_source=observation_source)
    for index in range(change_count):
        at_ms = first_at + int(int(first["duration_ms"]) * (index + 1) / (change_count + 1))
        push("observe", mode="review", timeline_ms=at_ms, cursor=_temporal_position(target, at_ms), input_source=observation_source)
    target_index = timeline["settle_order"].index(target_id)
    grid = timeline["settle_grid"]
    point = [
        grid["x0"] + target_index % grid["columns"] * grid["dx"],
        grid["y0"] + target_index // grid["columns"] * grid["dy"],
    ]
    push("return_settled")
    push("select", selected_object_id=target_id, point=point, input_source=selection_source)
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction_mode": interaction,
        "selected_object_id": target_id,
        "events": events,
    }


def test_first_change_controls_preserve_l4_share_world_and_bind_input_surfaces() -> None:
    env_name = "temporal_memory_first_change_env"
    mechanic = "temporal_memory_first_change"
    controls = controls_for(env_name)
    grader = load_module(
        "controlled_first_change_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{mechanic}.py",
    )
    helpers = load_module(
        "controlled_first_change_verifier",
        BENCHMARK / "shared_runtime" / "verifier_helpers.py",
    )
    original = base_task_for(env_name, mechanic)
    historical = read_json(
        BENCHMARK / "environments" / env_name / "historical_l4_baseline_fixture.json"
    )
    assert controls["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    assert original["natural_language"] == controls["difficulty"]["4"]["natural_language_by_interaction"]["full"]
    assert historical["identity_fields_removed_for_controlled_comparison"] == [
        "task_id",
        "challenge_id",
        "control_condition",
    ]
    assert historical["source"]["generator_path"] == "benchmarks/weird_captcha_gym/shared_scripts/incubator_generators/temporal_memory_first_change.py"
    for historical_seed in historical["seeds"]:
        seed = historical_seed["seed"]
        original_public, original_truth = SETUP.generate_task_state(original, seed)
        baseline_public, baseline_truth = SETUP.generate_task_state(task_for_level(env_name, 4, "full"), seed)
        assert original_public["challenge_id"] == historical_seed["historical_challenge_id"]
        assert canonical_sha256(original_public) == historical_seed["historical_public_state_sha256"]
        assert canonical_sha256(original_truth) == historical_seed["historical_ground_truth_sha256"]
        assert canonical_sha256(without_control_identity(original_public)) == historical_seed["normalized_public_state_sha256"]
        assert canonical_sha256(without_control_identity(original_truth)) == historical_seed["normalized_ground_truth_sha256"]
        assert canonical_sha256(without_control_identity(baseline_public)) == historical_seed["normalized_public_state_sha256"]
        assert canonical_sha256(without_control_identity(baseline_truth)) == historical_seed["normalized_ground_truth_sha256"]
        timeline = baseline_public["timeline"]
        assert {
            "object_count": len(timeline["objects"]),
            "event_count": len(timeline["events"]),
            "first_change_ms": timeline["first_change_ms"],
            "first_change_duration_ms": timeline["events"][0]["duration_ms"],
            "lens_radius": timeline["lens_radius"],
            "occluders": timeline["occluders"],
            "proof": timeline["proof"],
            "settle_ms": timeline["settle_ms"],
            "target_object_id": baseline_truth["target_object_id"],
        } == historical_seed["contract"]
    for seed in ("first-change-baseline-a", "first-change-baseline-b"):
        original_public, original_truth = SETUP.generate_task_state(original, seed)
        baseline_public, baseline_truth = SETUP.generate_task_state(task_for_level(env_name, 4, "full"), seed)
        assert without_control_identity(baseline_public) == without_control_identity(original_public)
        assert without_control_identity(baseline_truth) == without_control_identity(original_truth)

    for level in range(1, 6):
        parameters = controls["difficulty"][str(level)]["parameters"]
        simplified_public, simplified_truth = SETUP.generate_task_state(task_for_level(env_name, level, "simplified"), f"first-change-profile-{level}")
        full_public, full_truth = SETUP.generate_task_state(task_for_level(env_name, level, "full"), f"first-change-profile-{level}")
        assert without_control_identity(simplified_public) == without_control_identity(full_public)
        assert without_control_identity(simplified_truth) == without_control_identity(full_truth)
        assert len(full_public["timeline"]["objects"]) == parameters["object_count"]
        assert len(full_public["timeline"]["events"]) == parameters["decoy_event_count"] + 1
        assert full_public["timeline"]["events"][0]["duration_ms"] == parameters["first_change_duration_ms"]
        assert full_public["timeline"]["lens_radius"] == parameters["lens_radius"]
        assert full_public["timeline"]["occluders"] == parameters["occluders"]
        assert full_public["timeline"]["proof"]["minimum_pre_hits"] == parameters["minimum_pre_hits"]
        assert full_public["timeline"]["proof"]["minimum_change_hits"] == parameters["minimum_change_hits"]
        for public, truth, interaction in (
            (simplified_public, simplified_truth, "simplified"),
            (full_public, full_truth, "full"),
        ):
            payload = _temporal_payload(public, truth, interaction)
            accepted = grader.grade(payload, truth, public)
            assert accepted["passed"] is True, accepted
            exported = {"result": payload, "public_state": public, "ground_truth": truth}
            assert helpers.verify_temporal_memory_first_change(exported)["passed"] is True
            wrong_mode = copy.deepcopy(payload)
            wrong_mode["interaction_mode"] = "full" if interaction == "simplified" else "simplified"
            rejected = grader.grade(wrong_mode, truth, public)
            assert rejected["passed"] is False
            wrong_source = copy.deepcopy(payload)
            observation = next(event for event in wrong_source["events"] if event["kind"] == "observe")
            observation["input_source"] = "canvas_pointer" if interaction == "simplified" else "coordinate_controls"
            rejected = grader.grade(wrong_source, truth, public)
            assert rejected["passed"] is False
            wrong_selection_surface = copy.deepcopy(payload)
            wrong_selection_surface["events"][-1]["input_source"] = "canvas_pointer" if interaction == "simplified" else "settled_slot_button"
            rejected = grader.grade(wrong_selection_surface, truth, public)
            assert rejected["passed"] is False
            stale = copy.deepcopy(payload)
            stale["challenge_id"] = "stale-first-change-challenge"
            rejected = grader.grade(stale, truth, public)
            assert rejected["passed"] is False
            malformed = copy.deepcopy(payload)
            malformed["events"] = [malformed["events"][0]]
            rejected = grader.grade(malformed, truth, public)
            assert rejected["passed"] is False


def test_robot_art_critic_controls_preserve_l4_and_bind_plot_and_pointer_surfaces() -> None:
    env_name = "robot_art_critic_env"
    mechanic = "robot_art_critic"
    controls = controls_for(env_name)
    grader = load_module(
        "controlled_robot_art_critic_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{mechanic}.py",
    )
    original = base_task_for(env_name, mechanic)
    assert controls["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    assert controls["real_time"] == {
        "play_time_seconds": 180,
        "observation_window_ms": 0,
        "frames_per_observation": 1,
    }
    assert original["natural_language"] == controls["difficulty"]["4"]["natural_language_by_interaction"]["full"]

    for seed in ("robot-art-baseline-a", "robot-art-baseline-b", "robot-art-baseline-c"):
        original_public, original_truth = SETUP.generate_task_state(original, seed)
        baseline_public, baseline_truth = SETUP.generate_task_state(task_for_level(env_name, 4, "full"), seed)
        assert original_public["challenge_id"] == baseline_public["challenge_id"]
        assert without_control_identity(original_public) == without_control_identity(baseline_public)
        assert without_control_identity(original_truth) == without_control_identity(baseline_truth)

    vocabulary_sizes = []
    pose_counts = []
    score_thresholds = []
    margin_thresholds = []
    for level in range(1, 6):
        parameters = controls["difficulty"][str(level)]["parameters"]
        full_public, full_truth = SETUP.generate_task_state(
            task_for_level(env_name, level, "full"), f"robot-art-profile-{level}"
        )
        simplified_public, simplified_truth = SETUP.generate_task_state(
            task_for_level(env_name, level, "simplified"), f"robot-art-profile-{level}"
        )
        assert full_public["control_condition"]["difficulty_parameters"] == parameters
        assert full_public["challenge_id"] == simplified_public["challenge_id"]
        assert without_control_identity(full_public, extra=("prompt", "rules")) == without_control_identity(
            simplified_public, extra=("prompt", "rules")
        )
        assert without_control_identity(full_truth) == without_control_identity(simplified_truth)
        assert full_public["target"]["class_name"] in parameters["class_vocabulary"]
        assert full_public["target"]["pose"]["name"] in parameters["pose_options"]
        assert full_public["target"]["style"]["name"] in parameters["style_options"]
        requirements = full_public["requirements"]
        assert requirements["stroke_budget"] == full_public["target"]["expected_strokes"] + parameters["stroke_budget_extra"]
        for key in (
            "maximum_attempts", "minimum_points_per_stroke", "minimum_stroke_ms",
            "maximum_sample_gap_px", "maximum_sample_interval_ms", "minimum_bbox_fraction_milli",
            "maximum_bbox_fraction_milli", "maximum_center_offset_milli", "acceptance_score_milli",
            "minimum_margin_milli",
        ):
            assert requirements[key] == parameters[key]
        vocabulary_sizes.append(len(full_truth["class_vocabulary"]))
        pose_counts.append(len(parameters["pose_options"]))
        score_thresholds.append(requirements["acceptance_score_milli"])
        margin_thresholds.append(requirements["minimum_margin_milli"])

        wrong_mode = {
            "mechanic_id": mechanic,
            "task_id": full_public["task_id"],
            "challenge_id": full_public["challenge_id"],
            "interaction_mode": "simplified",
            "events": [],
        }
        rejected = grader.grade(wrong_mode, full_truth, full_public)
        assert rejected["passed"] is False
        assert rejected["feedback"] == "robot-art drawing uses the wrong interaction input"
    assert vocabulary_sizes == [3, 5, 7, 8, 8]
    assert pose_counts == [1, 3, 3, 3, 5]
    assert score_thresholds == sorted(score_thresholds)
    assert margin_thresholds == sorted(margin_thresholds)

    renderer = (BENCHMARK / "shared_runtime" / "app" / "mechanics" / f"{mechanic}.js").read_text(encoding="utf-8")
    assert 'data-interaction="${clean(interaction)}"' in renderer
    assert 'id="finish-plot-stroke"' in renderer
    assert '"plot_clicks"' in renderer
    assert '"continuous_pointer"' in renderer


def _split_boxes_payload(public: dict, truth: dict, interaction: str, grader: types.ModuleType) -> dict:
    slots: list[str | None] = [None] * len(truth["tiles"])
    for tile in truth["tiles"]:
        slots[int(tile["initial_slot"])] = str(tile["id"])
    assert all(slots)
    slots = [str(tile_id) for tile_id in slots]
    columns = int(truth["scene"].get("columns") or 3)
    desired = {
        int(tile["source"]["row"]) * columns + int(tile["source"]["column"]): str(tile["id"])
        for tile in truth["tiles"]
    }
    rotations = {str(tile["id"]): int(tile["initial_rotation"]) for tile in truth["tiles"]}
    phases = {str(tile["id"]): int(tile["initial_phase"]) for tile in truth["tiles"]}
    events: list[dict] = []

    def record(event_type: str, **details: object) -> None:
        events.append({"sequence": len(events) + 1, "type": event_type, **details})

    source = {"simplified": "slot_button", "full": "tile_drag"}[interaction]
    for destination, tile_id in desired.items():
        if slots[destination] == tile_id:
            continue
        origin = slots.index(tile_id)
        displaced_id = slots[destination]
        record("swap", tile_id=tile_id, displaced_id=displaced_id, from_slot=origin, to_slot=destination, input_source=source)
        slots[origin], slots[destination] = slots[destination], slots[origin]
    for tile_id, rotation in list(rotations.items()):
        if rotation:
            rotations[tile_id] = 0
            record("rotate", tile_id=tile_id, rotation_after=0, input_source="rotation_button")
    for tile_id, phase in list(phases.items()):
        if phase:
            phases[tile_id] = 0
            record("phase", tile_id=tile_id, delta_ticks=-phase, phase_after=0, input_source="phase_track")
    sync_start = 100
    record("sync_start", scene_tick=sync_start)
    tile_by_id = {str(tile["id"]): tile for tile in truth["tiles"]}
    sample_count = int(truth["requirements"]["minimum_samples"])
    sample_ms = int(truth["requirements"]["sample_ms"])
    for sample_index in range(sample_count):
        elapsed = sample_index * sample_ms
        scene_tick = sync_start + elapsed
        errors = grader._errors(truth["scene"], slots, tile_by_id, rotations, phases, scene_tick)
        assert all(value == 0 for value in errors.values())
        record("sync_sample", elapsed_ms=elapsed, scene_tick=scene_tick, **errors, stable=True)
    record("sync_end", duration_ms=max(int(truth["requirements"]["hold_ms"]), (sample_count - 1) * sample_ms), sample_count=sample_count)
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "events": events,
        "final_slots": {tile_id: slot for slot, tile_id in enumerate(slots)},
        "final_rotations": rotations,
        "final_phases": phases,
        "completed": True,
    }


def test_split_boxes_controls_preserve_l4_and_bind_both_input_surfaces() -> None:
    env_name = "single_scene_split_boxes_env"
    controls = controls_for(env_name)
    grader = load_module("controlled_split_boxes_grader", BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "single_scene_split_boxes.py")
    original = base_task_for(env_name, "single_scene_split_boxes")
    historical_fixture = read_json(
        BENCHMARK / "environments" / env_name / "historical_l4_baseline_fixture.json"
    )
    assert controls["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    assert original["natural_language"] == controls["difficulty"]["4"]["natural_language"]
    assert historical_fixture["identity_fields_removed_for_comparison"] == [
        "task_id",
        "challenge_id",
        "control_condition",
    ]
    # This fixture was generated from the explicit pre-control revision named
    # in the fixture.  Compare both the uncontrolled path and controlled L4
    # against it; comparing those two current paths alone cannot detect a
    # shared regression in the generated task contract.
    for historical in historical_fixture["seeds"]:
        seed = historical["seed"]
        expected_public = historical["public_state"]
        expected_truth = historical["ground_truth"]
        original_public, original_truth = SETUP.generate_task_state(original, seed)
        baseline_public, baseline_truth = SETUP.generate_task_state(task_for_level(env_name, 4, "full"), seed)
        assert original_public["challenge_id"] == expected_public["challenge_id"]
        assert original_truth["challenge_id"] == expected_truth["challenge_id"]
        assert baseline_public["challenge_id"] == expected_public["challenge_id"]
        assert baseline_truth["challenge_id"] == expected_truth["challenge_id"]
        assert original_public["scene"]["rows"] == original_public["scene"]["columns"] == 3
        assert original_truth["scene"]["rows"] == original_truth["scene"]["columns"] == 3
        assert baseline_public["scene"]["rows"] == baseline_public["scene"]["columns"] == 3
        assert baseline_truth["scene"]["rows"] == baseline_truth["scene"]["columns"] == 3
        assert original_public == expected_public
        assert original_truth == expected_truth
        assert without_control_identity(original_public) == without_control_identity(expected_public)
        assert without_control_identity(original_truth) == without_control_identity(expected_truth)
        assert without_control_identity(baseline_public) == without_control_identity(expected_public)
        assert without_control_identity(baseline_truth) == without_control_identity(expected_truth)
        assert without_control_identity(baseline_public) == without_control_identity(original_public)
        assert without_control_identity(baseline_truth) == without_control_identity(original_truth)
    for level in range(1, 6):
        parameters = controls["difficulty"][str(level)]["parameters"]
        simplified_public, simplified_truth = SETUP.generate_task_state(task_for_level(env_name, level, "simplified"), f"split-boxes-{level}")
        full_public, full_truth = SETUP.generate_task_state(task_for_level(env_name, level, "full"), f"split-boxes-{level}")
        assert without_control_identity(simplified_public) == without_control_identity(full_public)
        assert without_control_identity(simplified_truth) == without_control_identity(full_truth)
        assert len(full_public["tiles"]) == parameters["rows"] * parameters["columns"]
        assert len(full_public["scene"]["decoys"]) == parameters["decoy_count"]
        for interaction, public, truth in (("simplified", simplified_public, simplified_truth), ("full", full_public, full_truth)):
            payload = _split_boxes_payload(public, truth, interaction, grader)
            accepted = grader.grade(payload, truth, public)
            assert accepted["passed"] is True, accepted
            wrong_source = copy.deepcopy(payload)
            next(event for event in wrong_source["events"] if event["type"] == "swap")["input_source"] = "tile_drag" if interaction == "simplified" else "slot_button"
            rejected = grader.grade(wrong_source, truth, public)
            assert rejected["passed"] is False
            assert "wrong interaction input" in rejected["feedback"]


def _reload_interruption_payload(public: dict, truth: dict, interaction: str, grader) -> dict:
    events: list[dict] = []

    def push(kind: str, **details: object) -> None:
        events.append({"sequence": len(events) + 1, "kind": kind, **details})

    interrupts = {
        int(spec["after_step"]): spec
        for spec in truth["interruptions"]
    }
    for index, direction in enumerate(truth["sequence"], start=1):
        push("gesture", index=index - 1, direction=direction, surface=interaction)
        spec = interrupts.get(index)
        if spec is None:
            continue
        sample_count = int(spec["min_samples"])
        duration = int(spec["hold_ms"])
        samples = []
        for sample_index in range(sample_count):
            elapsed = round(duration * sample_index / max(1, sample_count - 1))
            if interaction == "full":
                x, y = grader._spark(spec, elapsed)
                point = [x, y]
            else:
                point = [0, 0]
            samples.append({"elapsed_ms": elapsed, "point": point})
        push(
            "interrupt",
            interruption_id=spec["id"],
            surface=interaction,
            duration_ms=duration,
            samples=samples,
        )
    return {
        "mechanic_id": public["mechanic_id"],
        "challenge_id": public["challenge_id"],
        "interaction_mode": interaction,
        "events": events,
    }


def test_reload_interruption_profiles_preserve_l4_and_bind_both_input_surfaces() -> None:
    env_name = "reload_interruption_env"
    controls = controls_for(env_name)
    grader = load_module(
        "controlled_reload_interruption_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "reload_interruption.py",
    )
    helpers = load_module(
        "controlled_reload_interruption_verifier",
        BENCHMARK / "shared_runtime" / "verifier_helpers.py",
    )
    original = base_task_for(env_name, "reload_interruption")
    for seed in ("reload-baseline-a", "reload-baseline-b"):
        original_public, original_truth = SETUP.generate_task_state(original, seed)
        baseline_public, baseline_truth = SETUP.generate_task_state(
            task_for_level(env_name, 4, "full"), seed
        )
        assert without_control_identity(baseline_public) == without_control_identity(original_public)
        assert without_control_identity(baseline_truth) == without_control_identity(original_truth)

    for level in range(1, 6):
        parameters = controls["difficulty"][str(level)]["parameters"]
        simplified_public, simplified_truth = SETUP.generate_task_state(
            task_for_level(env_name, level, "simplified"), f"reload-profile-{level}"
        )
        full_public, full_truth = SETUP.generate_task_state(
            task_for_level(env_name, level, "full"), f"reload-profile-{level}"
        )
        assert without_control_identity(simplified_public) == without_control_identity(full_public)
        assert without_control_identity(simplified_truth) == without_control_identity(full_truth)
        assert len(simplified_public["sequence"]) == parameters["sequence_length"]
        assert [item["after_step"] for item in simplified_public["interruptions"]] == parameters["interruption_steps"]
        for public, truth, interaction in (
            (simplified_public, simplified_truth, "simplified"),
            (full_public, full_truth, "full"),
        ):
            payload = _reload_interruption_payload(public, truth, interaction, grader)
            assert grader.grade(payload, truth, public)["passed"] is True
            exported = {"result": payload, "public_state": public, "ground_truth": truth}
            assert helpers.verify_reload_interruption(exported)["passed"] is True
            wrong_surface = copy.deepcopy(payload)
            wrong_surface["interaction_mode"] = "full" if interaction == "simplified" else "simplified"
            assert grader.grade(wrong_surface, truth, public)["passed"] is False


def _wonky_delta(target: float, initial: float) -> float:
    return (target - initial + 180.0) % 360.0 - 180.0


def _wonky_payload(public: dict, truth: dict, interaction: str) -> dict:
    parameters = truth["control_condition"]["difficulty_parameters"]
    source = {"simplified": "proxy_step", "full": "wheel_drag"}[interaction]
    events: list[dict] = []

    def push(kind: str, **details: object) -> None:
        events.append({"sequence": len(events) + 1, "kind": kind, **details})

    for plate in truth["press"]["plates"]:
        remaining = _wonky_delta(float(plate["target"]), float(plate["initial"]))
        if interaction == "simplified":
            step = float(parameters["proxy_step_degrees"])
            coarse_step = float(parameters.get("proxy_coarse_step_degrees") or 0.0)
            for visible_step in sorted({step, coarse_step} - {0.0}, reverse=True):
                while abs(remaining) >= visible_step - 1e-8:
                    chunk = visible_step if remaining > 0 else -visible_step
                    push("wheel_drag", plate_id=plate["id"], delta=chunk, input_source=source)
                    remaining -= chunk
            assert abs(remaining) < 1e-8
        else:
            push("wheel_drag", plate_id=plate["id"], delta=remaining, input_source=source)
        push("lock", plate_id=plate["id"], locked=True)
    push("press")
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "events": events,
    }


def test_wonky_registration_profiles_preserve_l3_and_bind_both_input_surfaces() -> None:
    env_name = "wonky_text_hostile_rendering_env"
    mechanic = "wonky_text_hostile_rendering"
    controls = controls_for(env_name)
    grader = load_module(
        "controlled_wonky_registration_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{mechanic}.py",
    )
    verifier_helpers = load_module(
        "controlled_wonky_registration_verifier",
        BENCHMARK / "shared_runtime" / "verifier_helpers.py",
    )
    original = base_task_for(env_name, mechanic)
    assert original["natural_language"] == "Register all three color plates, lock them, then press."
    assert controls["baseline"] == {"difficulty": 3, "interaction": "full", "real_time": "live"}
    assert controls["difficulty"]["3"]["natural_language"] == original["natural_language"]

    for seed in ("wonky-baseline-a", "wonky-baseline-b", "wonky-baseline-c"):
        original_public, original_truth = SETUP.generate_task_state(original, seed)
        baseline_public, baseline_truth = SETUP.generate_task_state(task_for_level(env_name, 3, "full"), seed)
        assert original_public["challenge_id"] == baseline_public["challenge_id"]
        assert without_control_identity(baseline_public) == without_control_identity(original_public)
        assert without_control_identity(baseline_truth) == without_control_identity(original_truth)

    for level in range(1, 6):
        parameters = controls["difficulty"][str(level)]["parameters"]
        simplified_public, simplified_truth = SETUP.generate_task_state(task_for_level(env_name, level, "simplified"), f"wonky-d{level}")
        full_public, full_truth = SETUP.generate_task_state(task_for_level(env_name, level, "full"), f"wonky-d{level}")
        assert simplified_public["challenge_id"] == full_public["challenge_id"]
        assert without_control_identity(simplified_public) == without_control_identity(full_public)
        assert without_control_identity(simplified_truth) == without_control_identity(full_truth)
        assert len(full_public["press"]["plates"]) == int(parameters["plate_count"])
        assert len(full_public["press"]["token"]) == int(parameters["token_length"])
        assert full_public["press"]["tolerance"] == float(parameters["tolerance"])
        assert full_public["press"]["degrees_per_pixel"] == float(parameters["degrees_per_pixel"])
        assert all(
            int(plate["harmonic"]) in set(parameters["harmonic_values"])
            and float(parameters["warp_min"]) <= float(plate["warp"]) <= float(parameters["warp_max"])
            and abs(_wonky_delta(float(plate["target"]), float(plate["initial"]))) >= float(parameters["min_initial_delta_degrees"])
            for plate in full_public["press"]["plates"]
        )

        for interaction, public, truth in (("simplified", simplified_public, simplified_truth), ("full", full_public, full_truth)):
            payload = _wonky_payload(public, truth, interaction)
            accepted = grader.grade(payload, truth, public)
            assert accepted["passed"] is True
            verified = verifier_helpers.verify_wonky_text_hostile_rendering({"result": payload, "ground_truth": truth, "public_state": public})
            assert verified["passed"] is True
            wrong_surface = copy.deepcopy(payload)
            wheel_event = next(event for event in wrong_surface["events"] if event["kind"] == "wheel_drag")
            wheel_event["input_source"] = "wheel_drag" if interaction == "simplified" else "proxy_step"
            rejected = grader.grade(wrong_surface, truth, public)
            assert rejected["passed"] is False
            assert rejected["feedback"] == "plate rotation uses the wrong interaction input"

        failure_events = [
            {"sequence": index + 1, "kind": "lock", "plate_id": plate["id"], "locked": True}
            for index, plate in enumerate(full_truth["press"]["plates"])
        ]
        failure_events.append({"sequence": len(failure_events) + 1, "kind": "press"})
        failed = grader.grade({"mechanic_id": mechanic, "task_id": full_public["task_id"], "challenge_id": full_public["challenge_id"], "events": failure_events}, full_truth, full_public)
        assert failed["passed"] is False
        assert failed["feedback"].startswith("plate registration")

    boundary_seed = "wonky-event-limit-preservation"
    original_public, original_truth = SETUP.generate_task_state(original, boundary_seed)
    baseline_public, baseline_truth = SETUP.generate_task_state(task_for_level(env_name, 3, "full"), boundary_seed)

    def boundary_payload(public: dict, truth: dict, zero_releases: int) -> dict:
        events = [{"sequence": index + 1, "kind": "wheel_drag", "plate_id": truth["press"]["plates"][0]["id"], "delta": 0.0, "input_source": "wheel_drag"} for index in range(zero_releases)]
        for plate in truth["press"]["plates"]:
            events.append({"sequence": len(events) + 1, "kind": "wheel_drag", "plate_id": plate["id"], "delta": _wonky_delta(float(plate["target"]), float(plate["initial"])), "input_source": "wheel_drag"})
            events.append({"sequence": len(events) + 1, "kind": "lock", "plate_id": plate["id"], "locked": True})
        events.append({"sequence": len(events) + 1, "kind": "press"})
        return {"mechanic_id": mechanic, "task_id": public["task_id"], "challenge_id": public["challenge_id"], "events": events}

    for zero_releases, expected_passed in ((93, True), (94, False)):
        original_payload = boundary_payload(original_public, original_truth, zero_releases)
        baseline_payload = boundary_payload(baseline_public, baseline_truth, zero_releases)
        assert len(original_payload["events"]) == len(baseline_payload["events"]) == zero_releases + 7
        assert grader.grade(original_payload, original_truth, original_public)["passed"] is expected_passed
        assert grader.grade(baseline_payload, baseline_truth, baseline_public)["passed"] is expected_passed

    for public, truth in ((original_public, original_truth), (baseline_public, baseline_truth)):
        unlocked_payload = boundary_payload(public, truth, 0)
        unlocked_payload["events"].insert(2, {"kind": "lock", "plate_id": truth["press"]["plates"][0]["id"], "locked": False})
        for sequence, event in enumerate(unlocked_payload["events"], start=1):
            event["sequence"] = sequence
        rejected_unlock = grader.grade(unlocked_payload, truth, public)
        assert rejected_unlock["passed"] is False
        assert rejected_unlock["feedback"] == "plate lock is invalid"

    # The L3 simplified surface retains 5-degree precision but adds a visible
    # 10-degree coarse step.  Its largest possible three-plate replay is 58
    # events (18 rotations per plate, three locks, and the press), below the
    # preserved historical 100-event L3 limit.
    assert controls["difficulty"]["3"]["parameters"]["proxy_coarse_step_degrees"] == 10.0
    for index in range(16):
        simplified_public, simplified_truth = SETUP.generate_task_state(
            task_for_level(env_name, 3, "simplified"), f"wonky-l3-simplified-bound-{index}"
        )
        simplified_payload = _wonky_payload(simplified_public, simplified_truth, "simplified")
        assert len(simplified_payload["events"]) <= 58
        assert grader.grade(simplified_payload, simplified_truth, simplified_public)["passed"] is True

    renderer = (BENCHMARK / "shared_runtime" / "app" / "mechanics" / f"{mechanic}.js").read_text(encoding="utf-8")
    assert "WeirdCaptchaTime" not in renderer
    assert "requestAnimationFrame" not in renderer
    assert "EXPOSURE SWEEP" not in renderer


def test_scroll_cage_profiles_preserve_l4_and_bind_scroll_surfaces() -> None:
    env_name = "moving_checkbox_evasive_button_env"
    controls = controls_for(env_name)
    grader = load_module(
        "controlled_scroll_cage_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "moving_checkbox_evasive_button.py",
    )
    original_task = base_task_for(env_name, "moving_checkbox_evasive_button")
    assert original_task["natural_language"] == "Check the box."
    assert controls["difficulty"]["4"]["natural_language"] == "Check the box."
    for seed in ("scroll-cage-l4-preservation-a", "scroll-cage-l4-preservation-b"):
        original_public, original_truth = SETUP.generate_task_state(original_task, seed)
        baseline_public, baseline_truth = SETUP.generate_task_state(
            task_for_level(env_name, 4, "simplified"), seed
        )
        assert without_control_identity(baseline_public) == without_control_identity(original_public)
        assert without_control_identity(baseline_truth) == without_control_identity(original_truth)

    expected_sources = {"simplified": "shaft_button", "full": "shaft_wheel"}
    for level in range(1, 6):
        parameters = controls["difficulty"][str(level)]["parameters"]
        simplified_public, simplified_truth = SETUP.generate_task_state(
            task_for_level(env_name, level, "simplified"), f"scroll-cage-profile-{level}"
        )
        full_public, full_truth = SETUP.generate_task_state(
            task_for_level(env_name, level, "full"), f"scroll-cage-profile-{level}"
        )
        assert without_control_identity(simplified_public) == without_control_identity(full_public)
        assert without_control_identity(simplified_truth) == without_control_identity(full_truth)
        assert len(simplified_public["scene"]["shaft_lefts"]) == parameters["shaft_count"]
        assert len(simplified_public["scene"]["boundaries"]) == parameters["shaft_count"] - 1
        assert simplified_public["physics"]["cursor_radius"] == parameters["cursor_radius"]
        assert simplified_public["physics"]["friction_milli"] == parameters["friction_milli"]
        assert simplified_public["scene"]["clamp"]["capture_radius"] == parameters["capture_radius"]

        scene = simplified_truth["scene"]
        before = int(scene["initial_offsets"][0])
        delta = -int(scene["offset_step"]) if before > int(scene["offset_min"]) else int(scene["offset_step"])
        wrong_source = "shaft_wheel" if expected_sources["simplified"] == "shaft_button" else "shaft_button"
        payload = {
            "mechanic_id": "moving_checkbox_evasive_button",
            "task_id": simplified_truth["task_id"],
            "challenge_id": simplified_truth["challenge_id"],
            "events": [{
                "seq": sequence,
                "type": "scroll",
                "shaft": 0,
                "before": before,
                "delta": delta,
                "after": before + delta,
                "input_source": wrong_source,
            } for sequence in range(1, 4)],
            "completed": False,
        }
        rejected = grader.grade(payload, simplified_truth, simplified_public)
        assert "wrong interaction input" in rejected["feedback"]

    renderer = (BENCHMARK / "shared_runtime" / "app" / "mechanics" / "moving_checkbox_evasive_button.js").read_text(encoding="utf-8")
    styles = (BENCHMARK / "shared_runtime" / "app" / "mechanics" / "moving_checkbox_evasive_button.css").read_text(encoding="utf-8")
    assert 'data-shaft-count="${scene.shaft_lefts.length}"' in renderer
    assert '.scroll-cage[data-shaft-count="5"] .scroll-cage-console' in styles
    assert '.scroll-cage[data-shaft-count="5"] .scroll-cage-check' in styles


def test_impossible_ecology_visible_rules_match_each_generated_goal_count() -> None:
    env_name = "impossible_ecology_env"
    expected_completion_rules = {
        1: "A matching sanctuary locks an organism permanently. Stabilize both organisms.",
        2: "A matching sanctuary locks an organism permanently. Stabilize all three organisms.",
        3: "A matching sanctuary locks an organism permanently. Stabilize all four organisms.",
        4: "A matching sanctuary locks an organism permanently. Stabilize all five.",
        5: "A matching sanctuary locks an organism permanently. Stabilize all six organisms.",
    }
    for level, expected_rule in expected_completion_rules.items():
        for interaction in ("full", "simplified"):
            public, _truth = SETUP.generate_task_state(
                task_for_level(env_name, level, interaction),
                f"impossible-ecology-rule-{level}",
            )
            assert public["rules"][-1] == expected_rule

    original_public, _truth = SETUP.generate_task_state(
        base_task_for(env_name, "impossible_ecology"),
        "impossible-ecology-original-rule",
    )
    assert original_public["rules"][-1] == expected_completion_rules[4]


def test_impossible_ecology_coordinate_pad_preserves_manual_lure_action_effects() -> None:
    capture = load_module(
        "impossible_ecology_action_effect_capture",
        BENCHMARK / "tools" / "capture_impossible_ecology_interaction_equivalence.py",
    )
    snapshots: dict[str, list[list[dict]]] = {}
    for interaction, source in (("full", "arena_pointer"), ("simplified", "coordinate_pad")):
        public, truth = capture.SETUP.generate_task_state(
            capture.task_for(interaction),
            "impossible-ecology-action-equivalence-test",
        )
        payload, snapshots[interaction] = capture.canonical_trace(public, truth, source)
        accepted = capture.GRADER.grade(payload, truth, public)
        assert capture.accepted_partial_replay(accepted)
        wrong = copy.deepcopy(payload)
        next(event for event in wrong["events"] if event["kind"] == "pointer_down")["input_source"] = (
            "coordinate_pad" if source == "arena_pointer" else "arena_pointer"
        )
        assert "wrong interaction input" in capture.GRADER.grade(wrong, truth, public)["feedback"]

    assert snapshots["full"] == snapshots["simplified"]
    browser_source = (BENCHMARK / "shared_runtime" / "app" / "mechanics" / "impossible_ecology.js").read_text(encoding="utf-8")
    grader_source = (BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "impossible_ecology.py").read_text(encoding="utf-8")
    assert "coordinatePadPoint" in browser_source
    assert "proxyLure" not in browser_source
    assert '"coordinate_pad"' in grader_source
    assert "_proxy_lure" not in grader_source


def test_impossible_ecology_uses_the_shared_fhd_observation_surface() -> None:
    environment = read_json(BENCHMARK / "environments" / "impossible_ecology_env" / "env.json")
    assert environment["observation"][0]["resolution"] == [1920, 1080]


def funeral_payload(public: dict, truth: dict, interaction: str) -> dict:
    flower_ids = list(truth.get("flower_order") or truth.get("flower_ids") or [])
    required_events = list(truth["required_events"])
    return {
        "mechanic_id": "funeral_ritual",
        "challenge_id": public["challenge_id"],
        "interaction_mode": interaction,
        "events": required_events,
        "action_surfaces": [
            {"event": event, "surface": interaction}
            for event in required_events
        ],
        "brushed_cells": list(range(int(truth["brush_threshold"]))),
        "gathered_flower_ids": flower_ids,
        "flower_sources": {flower_id: interaction for flower_id in truth["flower_ids"]},
        "completed": True,
    }


def test_funeral_profiles_preserve_l3_and_bind_both_input_surfaces() -> None:
    env_name = "funeral_ritual_env"
    controls = controls_for(env_name)
    legacy = load_module(
        "controlled_funeral_legacy_grader",
        BENCHMARK / "shared_runtime" / "server" / "legacy_browser_grader.py",
    )
    helpers = load_module(
        "controlled_funeral_verifier",
        BENCHMARK / "shared_runtime" / "verifier_helpers.py",
    )
    original_task = base_task_for(env_name, "funeral_ritual")
    baseline = task_for_level(env_name, 3, "full")
    original_public, original_truth = SETUP.generate_task_state(original_task, "funeral-baseline")
    baseline_public, baseline_truth = SETUP.generate_task_state(baseline, "funeral-baseline")
    assert without_control_identity(baseline_public) == without_control_identity(original_public)
    assert without_control_identity(baseline_truth) == without_control_identity(original_truth)

    for level in range(1, 6):
        parameters = controls["difficulty"][str(level)]["parameters"]
        simplified_public, simplified_truth = SETUP.generate_task_state(
            task_for_level(env_name, level, "simplified"),
            f"funeral-profile-{level}",
        )
        full_public, full_truth = SETUP.generate_task_state(
            task_for_level(env_name, level, "full"),
            f"funeral-profile-{level}",
        )
        assert without_control_identity(simplified_public) == without_control_identity(full_public)
        assert without_control_identity(simplified_truth) == without_control_identity(full_truth)
        assert simplified_public["moss_cells"] == parameters["moss_cells"]
        assert simplified_public["brush_threshold"] == parameters["brush_threshold"]
        assert len(simplified_public["flowers"]) == parameters["flower_count"]
        if parameters["flower_order_mode"] == "none":
            assert "tribute_order" not in simplified_public
            assert "flower_order" not in simplified_truth
        else:
            assert len(simplified_public["tribute_order"]) == parameters["flower_count"]
            assert len(simplified_truth["flower_order"]) == parameters["flower_count"]

        for interaction, public, truth in (
            ("simplified", simplified_public, simplified_truth),
            ("full", full_public, full_truth),
        ):
            payload = funeral_payload(public, truth, interaction)
            assert legacy.grade(payload, truth, public)["passed"] is True
            assert helpers.verify_funeral_ritual({
                "result": payload,
                "ground_truth": truth,
                "public_state": public,
            })["passed"] is True
            wrong_surface = copy.deepcopy(payload)
            wrong_surface["interaction_mode"] = "full" if interaction == "simplified" else "simplified"
            wrong_surface["action_surfaces"] = [
                {"event": event["event"], "surface": wrong_surface["interaction_mode"]}
                for event in payload["action_surfaces"]
            ]
            wrong_surface["flower_sources"] = {
                flower_id: wrong_surface["interaction_mode"]
                for flower_id in truth["flower_ids"]
            }
            assert legacy.grade(wrong_surface, truth, public)["passed"] is False
            assert helpers.verify_funeral_ritual({
                "result": wrong_surface,
                "ground_truth": truth,
                "public_state": public,
            })["passed"] is False

            stale = copy.deepcopy(payload)
            stale["challenge_id"] = "stale-funeral-challenge"
            assert legacy.grade(stale, truth, public)["passed"] is False


def test_funeral_browser_exposes_only_the_selected_interaction_surface() -> None:
    source = (BENCHMARK / "shared_runtime" / "app" / "app.js").read_text(encoding="utf-8")
    styles = (BENCHMARK / "shared_runtime" / "app" / "styles.css").read_text(encoding="utf-8")
    assert 'data-interaction="${text(interaction)}"' in source
    assert 'if (interaction === "full") tombstone.addEventListener' in source
    assert 'data-proxy-action="inspect"' in source
    assert 'offerFuneralBouquet(state, "full")' in source
    assert 'offerFuneralBouquet(state, "simplified")' in source
    assert '.funeral-captcha[data-interaction="simplified"] .ritual-flower' in styles
    assert 'THE STONE REJECTS THIS TRIBUTE' in source
    assert 'if (funeralModel.state?.control_condition && (funeralModel.state?.tribute_order || []).length) submitFuneral(funeralModel.state);' in source


def test_hovercar_browser_binds_keyboard_only_for_full_interaction() -> None:
    source = (
        BENCHMARK
        / "shared_runtime"
        / "app"
        / "mechanics"
        / "crash_deadline_hovercar.js"
    ).read_text(encoding="utf-8")
    # The visible simplified surface may not retain a hidden keyboard path
    # that changes its running physics before the grader rejects the record.
    assert 'if (model?.interaction !== "full") return;' in source
    assert 'if (interaction === "full") { model.onKeyDown' in source
    assert 'window.addEventListener("keydown", model.onKeyDown)' in source


def test_implemented_interaction_pairs_share_generated_worlds_and_goals() -> None:
    seed = "interaction-pair-equivalence"
    paired = 0
    for env_name in CONTROLLED_ENVIRONMENTS:
        controls = controls_for(env_name)
        interactions = [
            name
            for name, mode in controls["interaction"].items()
            if mode.get("implemented")
        ]
        if len(interactions) < 2:
            continue
        paired += 1
        level = int(controls["baseline"]["difficulty"])
        first_public, first_truth = SETUP.generate_task_state(
            task_for_level(env_name, level, interactions[0]), seed
        )
        for interaction in interactions[1:]:
            public, truth = SETUP.generate_task_state(
                task_for_level(env_name, level, interaction), seed
            )
            first_normalized = without_control_identity(first_public)
            normalized = without_control_identity(public)
            if env_name in {
                "shadow_crime_lab_env",
                "slot_reel_capture_env",
                "ribbon_switchboard_env",
                "polyrhythm_customs_env",
                "tomographic_baggage_surgery_env",
            }:
                first_normalized.pop("prompt")
                normalized.pop("prompt")
            if env_name in {
                "robot_art_critic_env",
                "rotating_keyboard_env",
                "wizard_critter_capture_env",
            }:
                # The world and goal are identical, while the visible task
                # copy must name the selected direct or proxy input surface.
                for key in ("prompt", "rules"):
                    first_normalized.pop(key, None)
                    normalized.pop(key, None)
            assert normalized == first_normalized
            first_truth_normalized = without_control_identity(first_truth)
            truth_normalized = without_control_identity(truth)
            if env_name == "tomographic_baggage_surgery_env":
                # Mode-specific visible instructions travel in the truth bundle
                # too, but do not change the generated volume or goal.
                first_truth_normalized.pop("prompt")
                truth_normalized.pop("prompt")
            assert truth_normalized == first_truth_normalized
    assert paired >= 1


def _flood_events(public: dict, truth: dict, interaction: str) -> list[dict]:
    sources = {
        "simplified": {"pump": "circuit_button", "gate": "lock_button", "transfer": "transfer_button", "certify": "certify_button"},
        "full": {"pump": "water_drag", "gate": "lock_direct", "transfer": "capsule_drag", "certify": "certify_button"},
    }[interaction]
    levels = [float(chamber["level"]) for chamber in public["chambers"]]
    gates = [False] * len(public["gates"])
    capsules = copy.deepcopy(public["capsules"])
    precision = int(public.get("level_precision", 2))
    events: list[dict] = []
    for action in truth["reference_plan"]:
        kind = action["action"]
        if kind == "pump":
            circuit_index, direction = int(action["circuit"]), int(action["direction"])
            first, second = public["circuits"][circuit_index]["between"]
            source, destination = (first, second) if direction == 1 else (second, first)
            before = list(levels)
            levels[source] = round(levels[source] - float(public["pump_step"]), precision)
            levels[destination] = round(levels[destination] + float(public["pump_step"]), precision)
            details = {"circuit": circuit_index, "direction": direction, "source": source, "destination": destination, "before": before, "after": list(levels), "total_after": round(sum(levels), precision)}
        elif kind == "gate":
            gate = int(action["gate"])
            opening = not gates[gate]
            gates = [opening if index == gate else False for index in range(len(gates))]
            details = {"gate": gate, "open": opening, "levels": list(levels), "gates": list(gates)}
        elif kind == "transfer":
            gate = int(action["gate"])
            before_capsules = copy.deepcopy(capsules)
            moved: list[str] = []
            if abs(levels[gate] - levels[gate + 1]) <= float(public["equal_tolerance"]):
                for capsule in capsules:
                    if capsule["direction"] == 1 and capsule["chamber"] == gate:
                        capsule["chamber"] += 1
                        moved.append(capsule["id"])
                    elif capsule["direction"] == -1 and capsule["chamber"] == gate + 1:
                        capsule["chamber"] -= 1
                        moved.append(capsule["id"])
            details = {"gate": gate, "levels": list(levels), "before_capsules": before_capsules, "after_capsules": copy.deepcopy(capsules), "moved": moved}
        else:
            raise AssertionError(f"unknown flood reference action {kind!r}")
        events.append({"seq": len(events) + 1, "type": kind, "input_source": sources[kind], **details})
    events.append({"seq": len(events) + 1, "type": "certify", "input_source": sources["certify"], "levels": list(levels), "capsules": copy.deepcopy(capsules), "accepted": all(capsule["chamber"] == capsule["dock_chamber"] for capsule in capsules)})
    return events


def test_floodgate_profiles_and_both_input_surfaces_replay() -> None:
    grader = load_module(
        "controlled_floodgate_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "floodgate_archive_rescue.py",
    )
    for level in range(1, 6):
        parameters = controls_for("floodgate_archive_rescue_env")["difficulty"][str(level)]["parameters"]
        for interaction in ("simplified", "full"):
            public, truth = SETUP.generate_task_state(
                task_for_level("floodgate_archive_rescue_env", level, interaction),
                f"floodgate-profile-{level}-{interaction}",
            )
            assert len(public["chambers"]) == parameters["chamber_count"]
            assert len(public["gates"]) == parameters["chamber_count"] - 1
            assert [item["between"] for item in public["circuits"]] == parameters["circuits"]
            assert math.isclose(
                float(public["pump_step"]),
                parameters["pump_step_units"] / parameters["unit_divisor"],
            )
            assert math.isclose(
                float(public["equal_tolerance"]),
                float(parameters["equal_tolerance"]),
            )
            payload = {"mechanic_id": public["mechanic_id"], "task_id": public["task_id"], "challenge_id": public["challenge_id"], "events": _flood_events(public, truth, interaction), "completed": True}
            assert grader.grade(payload, truth, public)["passed"] is True
            wrong_surface = copy.deepcopy(payload)
            pump_event = next(event for event in wrong_surface["events"] if event["type"] == "pump")
            pump_event["input_source"] = "water_drag" if interaction == "simplified" else "circuit_button"
            rejected = grader.grade(wrong_surface, truth, public)
            assert rejected["passed"] is False
            assert rejected["feedback"] == "pump uses the wrong interaction input"


def test_floodgate_browser_binds_the_selected_direct_surface() -> None:
    source = (BENCHMARK / "shared_runtime" / "app" / "mechanics" / "_interaction_vii_viii.js").read_text(encoding="utf-8")
    assert 'pump(circuitIndex, direction, "water_drag")' in source
    assert 'toggleGate(Number(lock.dataset.physicalLock), "lock_direct")' in source
    assert 'transfer(gate, "capsule_drag")' in source


def test_floodgate_interaction_pair_has_distinct_challenge_identity() -> None:
    simplified_public, simplified_truth = SETUP.generate_task_state(
        task_for_level("floodgate_archive_rescue_env", 4, "simplified"),
        "floodgate-interaction-identity",
    )
    full_public, full_truth = SETUP.generate_task_state(
        task_for_level("floodgate_archive_rescue_env", 4, "full"),
        "floodgate-interaction-identity",
    )
    assert simplified_public["challenge_id"] != full_public["challenge_id"]
    assert without_control_identity(simplified_public) == without_control_identity(full_public)
    assert without_control_identity(simplified_truth) == without_control_identity(full_truth)


def _gravity_slide(board: dict, position: list[int], direction: int, collected: int) -> tuple[list[int], int]:
    vectors = ((1, 0), (0, 1), (-1, 0), (0, -1))
    dx, dy = vectors[direction % 4]
    walls = {tuple(point) for point in board["walls"]}
    x, y = position
    while (x + dx, y + dy) not in walls:
        x += dx
        y += dy
        if collected < len(board["gates"]) and [x, y] == board["gates"][collected]:
            collected += 1
    return [x, y], collected


def _gravity_events(public: dict, truth: dict, interaction: str) -> list[dict]:
    board = public["board"]
    cargo = list(board["cargo_start"])
    counter = list(board["counter_start"])
    orientation = int(public["initial_orientation"])
    collected = 0
    source = {"simplified": "rotation_button", "full": "gimbal_drag"}[interaction]
    events: list[dict] = []
    for action in truth["solution"]:
        before = {"cargo": list(cargo), "counter": list(counter), "orientation": orientation, "collected": collected}
        orientation = (orientation + (1 if action == "cw" else -1)) % 4
        cargo, collected = _gravity_slide(board, cargo, orientation, collected)
        counter, _ = _gravity_slide(board, counter, orientation, 0)
        events.append({
            "seq": len(events) + 1,
            "type": "rotate",
            "direction": action,
            "before": before,
            "after": {"cargo": list(cargo), "counter": list(counter), "orientation": orientation, "collected": collected},
            "input_source": source,
        })
    events.append({
        "seq": len(events) + 1,
        "type": "certify",
        "cargo": list(cargo),
        "counter": list(counter),
        "orientation": orientation,
        "collected": collected,
        "accepted": collected == len(board["gates"]) and cargo == board["cargo_target"] and counter == board["counter_target"],
        "input_source": "certify_button",
    })
    return events


def test_gravity_room_profiles_preserve_l4_and_bind_both_input_surfaces() -> None:
    env_name = "gravity_room_freight_env"
    controls = controls_for(env_name)
    grader = load_module(
        "controlled_gravity_room_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "gravity_room_freight.py",
    )
    for level in range(1, 6):
        parameters = controls["difficulty"][str(level)]["parameters"]
        for interaction in ("simplified", "full"):
            public, truth = SETUP.generate_task_state(
                task_for_level(env_name, level, interaction),
                f"gravity-room-profile-{level}-{interaction}",
            )
            assert public["board"]["size"] == parameters["grid_size"]
            assert len(public["board"]["gates"]) == parameters["gate_count"]
            assert parameters["min_solution_length"] <= len(truth["solution"]) <= parameters["max_solution_length"]
            payload = {
                "mechanic_id": public["mechanic_id"],
                "task_id": public["task_id"],
                "challenge_id": public["challenge_id"],
                "events": _gravity_events(public, truth, interaction),
                "completed": True,
            }
            assert grader.grade(payload, truth, public)["passed"] is True
            wrong_surface = copy.deepcopy(payload)
            first_rotation = next(event for event in wrong_surface["events"] if event["type"] == "rotate")
            first_rotation["input_source"] = "gimbal_drag" if interaction == "simplified" else "rotation_button"
            rejected = grader.grade(wrong_surface, truth, public)
            assert rejected["passed"] is False
            assert rejected["feedback"] == "room rotation uses the wrong interaction input"


def test_gravity_room_l4_preserves_the_world_and_repairs_the_task_contract() -> None:
    """Keep the historical L4 world while making its task text truthful."""
    env_name = "gravity_room_freight_env"
    original = base_task_for(env_name, "gravity_room_freight")
    l4 = task_for_level(env_name, 4, "simplified")
    environment = read_json(BENCHMARK / "environments" / env_name / "env.json")
    real_time = read_json(BENCHMARK / "real_time.json")["environments"]["gravity_room_freight"]
    controls = controls_for(env_name)

    expected_description = (
        "Rotate an entire chamber and route a physical freight capsule through four "
        "ordered airlocks while docking both the capsule and its isolated counterweight."
    )
    expected_instruction = (
        "Quarter-turn the room to clear all four numbered airlocks in order and dock "
        "both the capsule and the isolated counterweight."
    )
    assert original["description"] == expected_description
    assert original["natural_language"] == expected_instruction
    assert l4["description"] == original["description"]
    assert l4["natural_language"] == original["natural_language"]
    assert environment["description"] == original["description"]
    assert environment["observation"][0]["resolution"] == [1280, 720]
    assert real_time == {"play_time_seconds": 180, "observation_window_ms": 500, "frames_per_observation": 3}
    assert controls["real_time"] == real_time


def test_gravity_room_browser_binds_direct_gimbal_only_for_full_interaction() -> None:
    source = (BENCHMARK / "shared_runtime" / "app" / "mechanics" / "_interaction_vii_viii.js").read_text(encoding="utf-8")
    assert 'rotateRoom(button.dataset.gravity, "rotation_button")' in source
    assert 'rotateRoom(dx > 0 ? "cw" : "ccw", "gimbal_drag")' in source
    assert 'canvas.addEventListener("pointerdown"' in source
    assert 'helpers.beginAction?.("gravity_room_rotation")' in source
    assert "transition?.settle();" in source
    assert "time_mode" not in source


def test_paused_evaluator_settles_registered_actions_before_pausing() -> None:
    evaluator = (BENCHMARK / "tools" / "run_realtime_evaluation.py").read_text(encoding="utf-8")
    controller = (BENCHMARK / "shared_runtime" / "app" / "time_controller.js").read_text(encoding="utf-8")
    runtime = (BENCHMARK / "shared_runtime" / "app" / "app.js").read_text(encoding="utf-8")
    assert '_time_command(env, "settle-pause")' in evaluator
    assert 'kind === "settle_pause"' in controller
    assert "await pauseAfterActions(sequence);" in controller
    assert "beginAction: (label) => window.WeirdCaptchaTime?.beginAction?.(label)" in runtime


def test_floodgate_l4_evaluator_description_matches_the_preserved_world() -> None:
    expected_description = (
        "Equalize mass-conserving vault water levels, move two opposing capsules through "
        "four locks to their marked docks, and avoid flooding paper archives."
    )
    expected_instruction = (
        "Move both evidence capsules through all four locks to their opposite docks without "
        "raising any archive above its red flood line."
    )
    environment = read_json(BENCHMARK / "environments" / "floodgate_archive_rescue_env" / "env.json")
    original_task = read_json(
        BENCHMARK
        / "environments"
        / "floodgate_archive_rescue_env"
        / "tasks"
        / "floodgate_archive_rescue_seed_0001"
        / "task.json"
    )
    controls = controls_for("floodgate_archive_rescue_env")
    materialized_l4 = task_for_level("floodgate_archive_rescue_env", 4, "simplified")
    public, _truth = SETUP.generate_task_state(materialized_l4, "floodgate-description-contract")

    assert environment["description"] == expected_description
    assert original_task["description"] == expected_description
    assert original_task["natural_language"] == expected_instruction
    assert controls["difficulty"]["4"]["natural_language"] == expected_instruction
    assert materialized_l4["natural_language"] == expected_instruction
    assert len(public["capsules"]) == 2
    assert len(public["gates"]) == 4


def _hologram_events(public: dict, truth: dict, input_source: str) -> list[dict]:
    objects = copy.deepcopy(public["objects"])
    by_id = {item["id"]: item for item in objects}
    events: list[dict] = []
    for target in truth["solution_objects"]:
        current = by_id[target["id"]]
        for index, axis in enumerate("xyz"):
            delta = int(target["center"][index]) - int(current["center"][index])
            direction = 1 if delta > 0 else -1
            for _ in range(abs(delta)):
                before = copy.deepcopy(current)
                current["center"][index] += direction
                events.append({
                    "seq": len(events) + 1,
                    "type": "translate",
                    "object_id": current["id"],
                    "before": before,
                    "after": copy.deepcopy(current),
                    "axis": axis,
                    "delta": direction,
                    "input_source": input_source,
                })
        turns = ("xyz".index(target["axis"]) - "xyz".index(current["axis"])) % 3
        for _ in range(turns):
            before = copy.deepcopy(current)
            current["axis"] = "xyz"[("xyz".index(current["axis"]) + 1) % 3]
            events.append({
                "seq": len(events) + 1,
                "type": "rotate",
                "object_id": current["id"],
                "before": before,
                "after": copy.deepcopy(current),
                "input_source": input_source,
            })
    events.append({
        "seq": len(events) + 1,
        "type": "cast",
        "objects": objects,
        "masks": copy.deepcopy(public["target_masks"]),
        "valid": True,
        "exact": True,
    })
    return events


def test_hologram_foundry_profiles_preserve_l4_and_bind_both_input_surfaces() -> None:
    env_name = "hologram_silhouette_foundry_env"
    controls = controls_for(env_name)
    grader = load_module(
        "controlled_hologram_foundry_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "hologram_silhouette_foundry.py",
    )
    original = base_task_for(env_name, "hologram_silhouette_foundry")
    for seed in ("foundry-l4-preservation-a", "foundry-l4-preservation-b"):
        baseline = task_for_level(env_name, 4, "simplified")
        original_public, original_truth = SETUP.generate_task_state(original, seed)
        controlled_public, controlled_truth = SETUP.generate_task_state(baseline, seed)
        assert without_control_identity(controlled_public) == without_control_identity(original_public)
        assert without_control_identity(controlled_truth) == without_control_identity(original_truth)
    for level in range(1, 6):
        parameters = controls["difficulty"][str(level)]["parameters"]
        simplified_public, simplified_truth = SETUP.generate_task_state(
            task_for_level(env_name, level, "simplified"),
            f"hologram-profile-{level}",
        )
        full_public, full_truth = SETUP.generate_task_state(
            task_for_level(env_name, level, "full"),
            f"hologram-profile-{level}",
        )
        assert len(simplified_public["objects"]) == parameters["rod_count"]
        assert simplified_public["grid_size"] == parameters["grid_size"]
        assert without_control_identity(simplified_public) == without_control_identity(full_public)
        assert without_control_identity(simplified_truth) == without_control_identity(full_truth)
        for view in simplified_public["views"]:
            assert parameters["rod_count"] * 3 - len(simplified_public["target_masks"][view]) >= parameters["min_occluded_rays_per_view"]
        for interaction, source, public, truth in (
            ("simplified", "transform_button", simplified_public, simplified_truth),
            ("full", "gizmo_drag", full_public, full_truth),
        ):
            payload = {
                "mechanic_id": public["mechanic_id"],
                "task_id": public["task_id"],
                "challenge_id": public["challenge_id"],
                "events": _hologram_events(public, truth, source),
                "completed": True,
            }
            assert grader.grade(payload, truth, public)["passed"] is True
            wrong = copy.deepcopy(payload)
            transform = next(item for item in wrong["events"] if item["type"] in {"translate", "rotate"})
            transform["input_source"] = "gizmo_drag" if interaction == "simplified" else "transform_button"
            rejected = grader.grade(wrong, truth, public)
            assert rejected["passed"] is False
            assert rejected["feedback"] == "rod transform uses the wrong interaction input"
    source = (BENCHMARK / "shared_runtime" / "app" / "mechanics" / "_interaction_vii_viii.js").read_text(encoding="utf-8")
    assert 'const interaction = state.control_condition?.interaction || "simplified";' in source
    assert 'input_source:"transform_button"' in source
    assert 'input_source:"gizmo_drag"' in source


def test_orbital_docking_profiles_preserve_l4_and_bind_both_input_surfaces() -> None:
    env_name = "orbital_docking_customs_env"
    controls = controls_for(env_name)
    grader = load_module(
        "controlled_orbital_docking_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "orbital_docking_customs.py",
    )
    original = base_task_for(env_name, "orbital_docking_customs")
    l4 = task_for_level(env_name, 4, "simplified")
    for seed in ("orbital-l4-preservation-a", "orbital-l4-preservation-b"):
        original_public, original_truth = SETUP.generate_task_state(original, seed)
        controlled_public, controlled_truth = SETUP.generate_task_state(l4, seed)
        assert without_control_identity(controlled_public) == without_control_identity(original_public)
        assert without_control_identity(controlled_truth) == without_control_identity(original_truth)

    for level in range(1, 6):
        parameters = controls["difficulty"][str(level)]["parameters"]
        seed = f"orbital-profile-{level}"
        simplified_public, simplified_truth = SETUP.generate_task_state(
            task_for_level(env_name, level, "simplified"), seed
        )
        full_public, full_truth = SETUP.generate_task_state(
            task_for_level(env_name, level, "full"), seed
        )
        assert len(simplified_public["debris"]) == parameters["debris_count"]
        assert len(simplified_public["beacons"]) == parameters["beacon_count"]
        assert simplified_public["station"]["y_amplitude"] in parameters["station_y_amplitude_options"]
        assert simplified_public["station"]["y_rate"] in parameters["station_y_rate_options"]
        assert simplified_public["station"]["rotation_deg_per_tick"] in parameters["station_port_rate_options"]
        for key in ("fuel", "dock_distance", "dock_speed", "angle_tolerance_deg", "max_ticks"):
            assert simplified_public["physics"][key] == parameters[key]
        assert without_control_identity(simplified_public) == without_control_identity(full_public)
        assert without_control_identity(simplified_truth) == without_control_identity(full_truth)
        assert simplified_public["challenge_id"] != full_public["challenge_id"]

        before = copy.deepcopy(simplified_public["ship"])
        after = copy.deepcopy(before)
        after["vx"] += simplified_public["physics"]["impulse"]
        payload = {
            "mechanic_id": simplified_public["mechanic_id"],
            "task_id": simplified_public["task_id"],
            "challenge_id": simplified_public["challenge_id"],
            "events": [{
                "seq": 1,
                "type": "control",
                "action": "thrust",
                "before": before,
                "after": after,
                "fuel_after": simplified_public["physics"]["fuel"] - 1,
                "ticks_after": 0,
                "scans_after": [],
                "collision": None,
                "input_source": "rcs_button",
            }],
            "completed": False,
        }
        accepted_surface = grader.grade(payload, simplified_truth, simplified_public)
        assert accepted_surface["passed"] is False
        assert accepted_surface["feedback"] == "no hard-dock request"
        wrong_surface = copy.deepcopy(payload)
        wrong_surface["events"][0]["input_source"] = "rcs_keyboard"
        assert grader.grade(wrong_surface, simplified_truth, simplified_public)["feedback"] == "RCS control uses the wrong interaction input"

        full_before = copy.deepcopy(full_public["ship"])
        full_after = copy.deepcopy(full_before)
        full_after["vx"] += full_public["physics"]["impulse"]
        full_payload = copy.deepcopy(payload)
        full_payload["task_id"] = full_public["task_id"]
        full_payload["challenge_id"] = full_public["challenge_id"]
        full_payload["events"][0].update({
            "before": full_before,
            "after": full_after,
            "fuel_after": full_public["physics"]["fuel"] - 1,
            "input_source": "rcs_keyboard",
        })
        assert grader.grade(full_payload, full_truth, full_public)["feedback"] == "no hard-dock request"
        full_payload["events"][0]["input_source"] = "rcs_button"
        assert grader.grade(full_payload, full_truth, full_public)["feedback"] == "RCS control uses the wrong interaction input"

    source = (BENCHMARK / "shared_runtime" / "app" / "mechanics" / "_interaction_vii_viii.js").read_text(encoding="utf-8")
    assert 'input_source: inputSource' in source
    assert 'document.addEventListener("keydown", model.keyHandler)' in source
    assert 'requestDock("dock_keyboard")' in source
    assert '${model.scans.length}/${state.beacons.length}' in source
    assert "time_mode" not in source


def test_elastic_membrane_profiles_and_interaction_grader_are_bound() -> None:
    env_name = "elastic_membrane_sorter_env"
    controls = controls_for(env_name)
    grader = load_module(
        "controlled_elastic_membrane_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "elastic_membrane_sorter.py",
    )
    sources = {"simplified": "tension_slider", "full": "membrane_post_drag"}
    for level in range(1, 6):
        parameters = controls["difficulty"][str(level)]["parameters"]
        seed = f"elastic-membrane-profile-{level}"
        public, truth = SETUP.generate_task_state(
            task_for_level(env_name, level, "simplified"),
            seed,
        )
        assert len(public["rounds"]) == parameters["round_count"]
        assert all(
            len(round_data["checkpoints"]) == parameters["checkpoints_per_round"]
            for round_data in public["rounds"]
        )
        for key in ("slope_accel", "drag", "well_radius", "capture_speed", "checkpoint_radius", "max_ticks"):
            assert public["physics"][key] == parameters[key]
        for interaction, source in sources.items():
            mode_public, mode_truth = SETUP.generate_task_state(
                task_for_level(env_name, level, interaction),
                seed,
            )
            assert without_control_identity(mode_public) == without_control_identity(public)
            assert without_control_identity(mode_truth) == without_control_identity(truth)
            initial = mode_public["rounds"][0]["post_heights"]
            event = {
                "seq": 1,
                "type": "post",
                "round_id": mode_public["rounds"][0]["id"],
                "tick": 0,
                "post": 0,
                "before": initial[0],
                "after": max(0, min(1, round(initial[0] + .01, 2))),
                "input_source": source,
            }
            payload = {
                "mechanic_id": mode_public["mechanic_id"],
                "task_id": mode_public["task_id"],
                "challenge_id": mode_public["challenge_id"],
                "events": [event],
                "completed": False,
            }
            assert grader.grade(payload, mode_truth, mode_public)["passed"] is False
            wrong = copy.deepcopy(payload)
            wrong["events"][0]["input_source"] = sources[
                "full" if interaction == "simplified" else "simplified"
            ]
            rejected = grader.grade(wrong, mode_truth, mode_public)
            assert rejected["passed"] is False
            assert rejected["feedback"] == "tension change 1 uses the wrong interaction input"

            stale = copy.deepcopy(payload)
            stale["challenge_id"] = "stale-challenge"
            stale_decision = grader.grade(stale, mode_truth, mode_public)
            assert stale_decision["passed"] is False
            assert stale_decision["feedback"] == "stale task or challenge"

        full_public, full_truth = SETUP.generate_task_state(
            task_for_level(env_name, level, "full"),
            seed,
        )
        assert full_public["challenge_id"] != public["challenge_id"]
        assert full_truth["challenge_id"] != truth["challenge_id"]


def test_elastic_membrane_l4_preserves_the_uncontrolled_generator() -> None:
    env_name = "elastic_membrane_sorter_env"
    controls = controls_for(env_name)
    assert controls["baseline"] == {
        "difficulty": 4,
        "interaction": "simplified",
        "real_time": "live",
    }
    original_task = base_task_for(env_name, "elastic_membrane_sorter")
    controlled_task = task_for_level(env_name, 4, "simplified")
    for seed in (
        "elastic-membrane-baseline-a",
        "elastic-membrane-baseline-b",
        "elastic-membrane-baseline-c",
    ):
        original_public, original_truth = SETUP.generate_task_state(
            original_task,
            seed,
        )
        controlled_public, controlled_truth = SETUP.generate_task_state(
            controlled_task,
            seed,
        )
        assert without_control_identity(controlled_public) == without_control_identity(
            original_public
        )
        assert without_control_identity(controlled_truth) == without_control_identity(
            original_truth
        )


def test_lidar_interaction_pair_preserves_the_generated_world_and_goal() -> None:
    seed = "lidar-interaction-pair-equivalence"
    original_public, original_truth = SETUP.generate_task_state(
        base_task_for("lidar_blacksite_env", "lidar_blacksite"), seed
    )
    simplified_public, simplified_truth = SETUP.generate_task_state(
        lidar_interaction_task("simplified"), seed
    )
    full_public, full_truth = SETUP.generate_task_state(
        lidar_interaction_task("full"), seed
    )
    assert simplified_public["control_condition"]["interaction"] == "simplified"
    assert full_public["control_condition"]["interaction"] == "full"
    assert without_control_identity(simplified_public) == without_control_identity(full_public)
    assert without_control_identity(simplified_truth) == without_control_identity(full_truth)
    assert without_control_identity(simplified_public) == without_control_identity(original_public)
    assert without_control_identity(simplified_truth) == without_control_identity(original_truth)


def test_signature_interaction_pair_preserves_the_generated_world_and_goal() -> None:
    seed = "signature-interaction-pair-equivalence"
    original_public, original_truth = SETUP.generate_task_state(
        base_task_for("bureaucratic_signature_trap_env", "bureaucratic_signature_trap"), seed
    )
    simplified_public, simplified_truth = SETUP.generate_task_state(
        signature_interaction_task("simplified"), seed
    )
    full_public, full_truth = SETUP.generate_task_state(
        signature_interaction_task("full"), seed
    )
    assert simplified_public["control_condition"]["interaction"] == "simplified"
    assert full_public["control_condition"]["interaction"] == "full"
    assert without_control_identity(simplified_public) == without_control_identity(full_public)
    assert without_control_identity(simplified_truth) == without_control_identity(full_truth)
    assert without_control_identity(simplified_public) == without_control_identity(original_public)
    assert without_control_identity(simplified_truth) == without_control_identity(original_truth)


def _signature_events(truth: dict, interaction: str, input_source: str) -> list[dict]:
    events = []
    for layer in truth["form"]["layers"]:
        start = [float(layer["initial"]["x"]), float(layer["initial"]["y"])]
        end = [float(layer["target"]["x"]), float(layer["target"]["y"])]
        if interaction == "simplified":
            current = start
            axis_tolerance = float(truth["form"]["alignment_tolerance"]) / math.sqrt(2)
            for axis in (0, 1):
                step = 8.0 if end[axis] > current[axis] else -8.0
                step_count = math.ceil(max(0, abs(end[axis] - current[axis]) - axis_tolerance) / 8)
                for _ in range(step_count):
                    after = current.copy()
                    after[axis] += step
                    events.append({
                        "sequence": len(events) + 1,
                        "kind": "sheet_drag",
                        "sheet_id": layer["id"],
                        "input_source": input_source,
                        "start": current,
                        "samples": [after],
                        "end": after,
                    })
                    current = after
            continue
        distance = math.dist(start, end)
        step_count = max(1, math.ceil(distance / 40))
        samples = [
            [
                start[0] + (end[0] - start[0]) * index / step_count,
                start[1] + (end[1] - start[1]) * index / step_count,
            ]
            for index in range(1, step_count + 1)
        ]
        events.append({
            "sequence": len(events) + 1,
            "kind": "sheet_drag",
            "sheet_id": layer["id"],
            "input_source": input_source,
            "start": start,
            "samples": samples,
            "end": samples[-1],
        })
    events.append({
        "sequence": len(events) + 1,
        "kind": "signature",
        "input_source": "signature_canvas",
        "points": truth["form"]["original_trace"],
    })
    events.append({
        "sequence": len(events) + 1,
        "kind": "certify",
        "input_source": "certify_button",
    })
    return events


def test_signature_grader_enforces_both_interaction_surfaces() -> None:
    grader = load_module(
        "controlled_signature_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "bureaucratic_signature_trap.py",
    )
    sources = {"simplified": "sheet_nudge_button", "full": "fixed_registration_tab"}
    for interaction, expected_source in sources.items():
        public, truth = SETUP.generate_task_state(
            signature_interaction_task(interaction),
            f"signature-controlled-grader-{interaction}",
        )
        payload = {
            "mechanic_id": public["mechanic_id"],
            "task_id": public["task_id"],
            "challenge_id": public["challenge_id"],
            "events": _signature_events(truth, interaction, expected_source),
        }
        assert grader.grade(payload, truth, public)["passed"] is True
        wrong_source = sources["full" if interaction == "simplified" else "simplified"]
        wrong_payload = copy.deepcopy(payload)
        wrong_payload["events"][0]["input_source"] = wrong_source
        rejected = grader.grade(wrong_payload, truth, public)
        assert rejected["passed"] is False
        assert rejected["feedback"] == "sheet drag uses the wrong interaction input"


def test_blind_dice_interaction_pair_preserves_the_current_world_and_goal() -> None:
    seed = "blind-dice-interaction-pair-equivalence"
    original_public, original_truth = SETUP.generate_task_state(
        base_task_for("blind_dice_courier_env", "blind_dice_courier"), seed
    )
    simplified_public, simplified_truth = SETUP.generate_task_state(
        blind_dice_interaction_task("simplified"), seed
    )
    full_public, full_truth = SETUP.generate_task_state(
        blind_dice_interaction_task("full"), seed
    )
    assert simplified_public["control_condition"]["interaction"] == "simplified"
    assert full_public["control_condition"]["interaction"] == "full"
    assert simplified_public["challenge_id"] == full_public["challenge_id"]
    assert without_control_identity(simplified_public) == without_control_identity(full_public)
    assert without_control_identity(simplified_truth) == without_control_identity(full_truth)
    assert without_control_identity(full_public) == without_control_identity(original_public)
    assert without_control_identity(full_truth) == without_control_identity(original_truth)

    for seed_index in range(4):
        for level in range(1, 6):
            paired_seed = f"blind-dice-all-interaction-pairs-{seed_index:02d}"
            level_simplified_public, level_simplified_truth = SETUP.generate_task_state(
                task_for_level("blind_dice_courier_env", level, "simplified"), paired_seed
            )
            level_full_public, level_full_truth = SETUP.generate_task_state(
                task_for_level("blind_dice_courier_env", level, "full"), paired_seed
            )
            assert level_simplified_public["challenge_id"] == level_full_public["challenge_id"]
            assert without_control_identity(level_simplified_public) == without_control_identity(level_full_public)
            assert without_control_identity(level_simplified_truth) == without_control_identity(level_full_truth)


def test_blind_dice_profiles_match_geometry_visibility_and_gate_contracts() -> None:
    controls = controls_for("blind_dice_courier_env")
    for level, (public, truth) in enumerate(generated_levels("blind_dice_courier_env"), start=1):
        parameters = controls["difficulty"][str(level)]["parameters"]
        board = public["board"]
        assert board == truth["board"]
        assert board["columns"] == parameters["columns"]
        assert board["rows"] == parameters["rows"]
        assert [gate["x"] for gate in board["gates"]] == parameters["barrier_columns"]
        assert len(board["gates"]) == len(parameters["barrier_columns"])
        assert len(board["scanners"]) == len(parameters["scanner_gate_indices"])
        assert parameters["minimum_solution_rolls"] <= len(truth["solution_path"]) <= parameters["maximum_solution_rolls"]
        assert public["prompt"] == controls["difficulty"][str(level)]["natural_language"]
        assert public["control_condition"]["difficulty_parameters"] == parameters
        for gate in board["gates"]:
            assert 1 <= gate["required_top"] <= 6
            assert ("required_east" in gate) == (parameters["gate_face_requirements"] == 2)
            if "required_east" in gate:
                assert 1 <= gate["required_east"] <= 6
                assert gate["required_east"] not in {gate["required_top"], 7 - gate["required_top"]}
        for scanner_index, gate_index in enumerate(parameters["scanner_gate_indices"]):
            gate = board["gates"][gate_index]
            scanner = board["scanners"][scanner_index]
            expected_y = max(
                1,
                min(
                    board["rows"] - 2,
                    gate["y"] + (parameters["scanner_offset"] if gate_index % 2 == 0 else -parameters["scanner_offset"]),
                ),
            )
            assert scanner == {
                "id": f"scanner-{scanner_index + 1}",
                "x": gate["x"] - 1,
                "y": expected_y,
            }


def test_blind_dice_profiles_preserve_the_baseline_and_order_the_actual_problem_across_seeds() -> None:
    for seed_index in range(12):
        seed = f"blind-dice-profile-order-{seed_index:02d}"
        original_public, original_truth = SETUP.generate_task_state(
            base_task_for("blind_dice_courier_env", "blind_dice_courier"),
            seed,
        )
        levels = [
            SETUP.generate_task_state(task_for_level("blind_dice_courier_env", level), seed)
            for level in range(1, 6)
        ]
        baseline_public, baseline_truth = levels[3]
        assert without_control_identity(baseline_public) == without_control_identity(original_public)
        assert without_control_identity(baseline_truth) == without_control_identity(original_truth)

        boards = [public["board"] for public, _truth in levels]
        paths = [truth["solution_path"] for _public, truth in levels]
        assert [len(board["gates"]) for board in boards] == [1, 2, 3, 5, 6]
        assert [len(board["scanners"]) for board in boards] == [0, 0, 3, 4, 2]
        assert [
            public["control_condition"]["difficulty_parameters"]["orientation_visibility"]
            for public, _truth in levels
        ] == ["always", "always", "initial_and_scanners", "initial_and_scanners", "initial_and_scanners"]
        assert [sum("required_east" in gate for gate in board["gates"]) for board in boards] == [0, 0, 0, 0, 6]
        assert all(left < right for left, right in zip(map(len, paths), map(len, paths[1:])))


def _blind_dice_payload(grader, public: dict, truth: dict, input_source: str) -> dict:
    position = (int(truth["board"]["start"]["x"]), int(truth["board"]["start"]["y"]))
    orientation = dict(truth["initial_orientation"])
    gates = {
        (int(item["x"]), int(item["y"])): item
        for item in truth["board"]["gates"]
    }
    deltas = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
    crossings = []
    actions = []
    for direction in truth["solution_path"]:
        before = position
        dx, dy = deltas[direction]
        position = (before[0] + dx, before[1] + dy)
        orientation = grader._roll(orientation, direction)
        gate = gates.get(position)
        if gate is not None and gate["id"] not in crossings:
            crossings.append(gate["id"])
        actions.append({
            "seq": len(actions) + 1,
            "t_ms": len(actions) * 55,
            "type": "move",
            "direction": direction,
            "input_source": input_source,
            "from": {"x": before[0], "y": before[1]},
            "to": {"x": position[0], "y": position[1]},
            "accepted": True,
            "gate_id": gate["id"] if gate is not None else None,
            "orientation_after": dict(orientation),
        })
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "completed": True,
        "actions": actions,
        "path": list(truth["solution_path"]),
        "gate_crossings": crossings,
        "reset_count": 0,
        "final_position": {"x": position[0], "y": position[1]},
        "final_orientation": orientation,
    }


def test_blind_dice_grader_accepts_each_mode_and_rejects_cross_mode_transcripts() -> None:
    grader = load_module(
        "controlled_blind_dice_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "blind_dice_courier.py",
    )
    for level in range(1, 6):
        for interaction, source, wrong_source in (
            ("simplified", "direction_buttons", "keyboard"),
            ("full", "keyboard", "direction_buttons"),
        ):
            public, truth = SETUP.generate_task_state(
                task_for_level("blind_dice_courier_env", level, interaction),
                f"blind-dice-grader-d{level}-{interaction}",
            )
            payload = _blind_dice_payload(grader, public, truth, source)
            assert grader.grade(payload, truth, public)["passed"] is True
            forged = copy.deepcopy(payload)
            forged["actions"][0]["input_source"] = wrong_source
            rejected = grader.grade(forged, truth, public)
            assert rejected["passed"] is False
            assert rejected["feedback"] == "roll uses the wrong interaction input"


def test_blind_dice_dual_face_gate_rejects_a_top_only_match() -> None:
    generator = load_module(
        "controlled_blind_dice_generator",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "blind_dice_courier.py",
    )
    grader = load_module(
        "controlled_blind_dice_dual_gate_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "blind_dice_courier.py",
    )
    public, truth = SETUP.generate_task_state(
        task_for_level("blind_dice_courier_env", 5, "full"),
        "blind-dice-dual-face-rejection",
    )
    board = truth["board"]
    gate = board["gates"][0]
    start = (int(board["start"]["x"]), int(board["start"]["y"]))
    target = (int(gate["x"]), int(gate["y"]))
    open_cells = {(int(cell["x"]), int(cell["y"])) for cell in board["open_cells"]}
    top_only_path = None
    alternate_gate = None
    for east in range(1, 7):
        if east == gate["required_east"]:
            continue
        candidate_gate = {**gate, "required_east": east}
        try:
            candidate_path = generator._solve_course(
                truth["initial_orientation"],
                start,
                target,
                open_cells,
                [candidate_gate],
            )
        except ValueError:
            continue
        top_only_path = candidate_path
        alternate_gate = candidate_gate
        break
    assert top_only_path is not None and alternate_gate is not None

    position = start
    orientation = dict(truth["initial_orientation"])
    actions = []
    for direction in top_only_path:
        before = position
        dx, dy = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}[direction]
        position = (before[0] + dx, before[1] + dy)
        orientation = grader._roll(orientation, direction)
        encountered = gate if position == target else None
        actions.append({
            "seq": len(actions) + 1,
            "t_ms": len(actions) * 55,
            "type": "move",
            "direction": direction,
            "input_source": "keyboard",
            "from": {"x": before[0], "y": before[1]},
            "to": {"x": position[0], "y": position[1]},
            "accepted": True,
            "gate_id": encountered["id"] if encountered else None,
            "orientation_after": dict(orientation),
        })
    assert orientation["top"] == gate["required_top"]
    assert orientation["east"] == alternate_gate["required_east"] != gate["required_east"]
    forged = {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "completed": True,
        "actions": actions,
    }
    decision = grader.grade(forged, truth, public)
    assert decision["passed"] is False
    assert decision["feedback"] == "reported gate or wall collision does not match replay"


def test_lidar_grader_enforces_every_selected_interaction_surface() -> None:
    grader = load_module(
        "controlled_lidar_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "lidar_blacksite.py",
    )
    cases = (
        ("simplified", "keyboard", "movement"),
        ("full", "control_buttons", "movement"),
        ("simplified", "viewport_scan", "scanner"),
        ("full", "scan_button", "scanner"),
        ("simplified", "scene_beacon", "pickup"),
        ("full", "pickup_button", "pickup"),
        ("simplified", "physical_gate", "extraction"),
        ("full", "verify_button", "extraction"),
    )
    for interaction, source, action in cases:
        public, truth = SETUP.generate_task_state(
            lidar_interaction_task(interaction),
            f"lidar-wrong-{action}-{interaction}",
        )
        if action == "movement":
            event = {
                "sequence": 1,
                "kind": "key_down",
                "tick": 0,
                "elapsed_ms": 0,
                "control": "forward",
                "input_source": source,
            }
        elif action == "scanner":
            event = {
                "sequence": 1,
                "kind": "scan",
                "tick": 0,
                "elapsed_ms": 0,
                "aim_millirad": 0,
                "visible_returns": [],
                "input_source": source,
            }
        else:
            event = {
                "sequence": 1,
                "kind": "pickup" if action == "pickup" else "submit",
                "tick": 0,
                "elapsed_ms": 0,
                "input_source": source,
            }
        result = grader.grade(
            {
                "mechanic_id": public["mechanic_id"],
                "task_id": public["task_id"],
                "challenge_id": public["challenge_id"],
                "events": [event],
            },
            truth,
            public,
        )
        assert result["passed"] is False
        assert f"wrong {action} input" in result["feedback"]


def test_lidar_profiles_match_topology_sensing_persistence_and_precision_contracts() -> None:
    controls = controls_for("lidar_blacksite_env")
    expected_turn_counts = ({2}, {3}, {4}, {5, 6}, {7})
    expected_branch_counts = (0, 0, 0, 0, 3)
    for level, (public, truth) in enumerate(generated_levels("lidar_blacksite_env"), start=1):
        parameters = controls["difficulty"][str(level)]["parameters"]
        route = truth["solution"]["route_points"]
        controls_state = public["controls"]
        requirements = public["requirements"]
        assert len(route) - 2 in expected_turn_counts[level - 1]
        assert len(truth["solution"]["branch_routes"]) == expected_branch_counts[level - 1]
        assert len(public["occluders"]) == parameters["occluder_count"]
        for key in (
            "scan_range",
            "scan_rays",
            "scan_half_angle_deg",
            "point_lifetime_ticks",
            "pickup_range",
            "exit_radius",
        ):
            assert controls_state[key] == parameters[key]
        for key in (
            "minimum_scan_count",
            "minimum_scan_stations",
            "station_distance",
            "minimum_target_scan_displacement",
            "minimum_travel_distance",
            "minimum_key_transitions",
        ):
            assert requirements[key] == parameters[key]
        assert len(truth["solution"]["scan_route_indices"]) == parameters["minimum_scan_count"]
        assert truth["control_condition"]["difficulty_parameters"]["layout_profile"] == parameters["layout_profile"]


def test_lidar_profiles_preserve_the_baseline_and_order_the_actual_problem_across_seeds() -> None:
    descending_control_keys = (
        "scan_range",
        "scan_rays",
        "scan_half_angle_deg",
        "point_lifetime_ticks",
        "pickup_range",
        "exit_radius",
    )
    for seed_index in range(12):
        seed = f"lidar-profile-order-{seed_index:02d}"
        original_public, original_truth = SETUP.generate_task_state(
            base_task_for("lidar_blacksite_env", "lidar_blacksite"),
            seed,
        )
        levels = [
            SETUP.generate_task_state(task_for_level("lidar_blacksite_env", level), seed)
            for level in range(1, 6)
        ]
        baseline_public, baseline_truth = levels[3]
        assert without_control_identity(baseline_public) == without_control_identity(original_public)
        assert without_control_identity(baseline_truth) == without_control_identity(original_truth)

        route_lengths = []
        turn_counts = []
        for public, truth in levels:
            route = truth["solution"]["route_points"]
            route_lengths.append(sum(math.dist(first, second) for first, second in zip(route, route[1:])))
            turn_counts.append(len(route) - 2)
            assert public["walls"] == truth["walls"]
            assert public["occluders"] == truth["occluders"]
            assert public["objects"] == truth["objects"]
            assert public["controls"] == truth["controls"]
            assert public["requirements"] == truth["requirements"]
        assert all(left <= right for left, right in zip(route_lengths, route_lengths[1:]))
        assert all(left < right for left, right in zip(turn_counts, turn_counts[1:]))
        assert [len(public["occluders"]) for public, _truth in levels] == [0, 1, 1, 2, 4]
        assert [len(truth["solution"]["branch_routes"]) for _public, truth in levels] == [0, 0, 0, 0, 3]
        for key in descending_control_keys:
            values = [public["controls"][key] for public, _truth in levels]
            assert all(left > right for left, right in zip(values, values[1:])), key


def test_lidar_interaction_modes_share_every_difficulty_world_across_seeds() -> None:
    for seed_index in range(4):
        seed = f"lidar-all-interaction-pairs-{seed_index:02d}"
        for level in range(1, 6):
            simplified_public, simplified_truth = SETUP.generate_task_state(
                task_for_level("lidar_blacksite_env", level, "simplified"),
                seed,
            )
            full_public, full_truth = SETUP.generate_task_state(
                task_for_level("lidar_blacksite_env", level, "full"),
                seed,
            )
            assert without_control_identity(simplified_public) == without_control_identity(full_public)
            assert without_control_identity(simplified_truth) == without_control_identity(full_truth)


def test_lidar_grader_replays_every_difficulty_and_interaction_condition() -> None:
    grader = load_module(
        "controlled_lidar_profile_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "lidar_blacksite.py",
    )
    seed = "lidar-controlled-grader-replay"
    for level in range(1, 6):
        for interaction in ("simplified", "full"):
            public, truth = SETUP.generate_task_state(
                task_for_level("lidar_blacksite_env", level, interaction),
                seed,
            )
            world = truth["world"]
            walls = truth["walls"]
            occluders = truth["occluders"]
            objects = truth["objects"]
            controls = truth["controls"]
            requirements = truth["requirements"]
            player = grader._initial_player(truth["initial_player"])
            events = []
            key_transitions = 0
            scan_count = 0
            stations: list[tuple[float, float]] = []
            target_seen = False
            carrying = False

            def record(kind: str, **details) -> None:
                tick = int(player["tick"])
                events.append({
                    "sequence": len(events) + 1,
                    "kind": kind,
                    "tick": tick,
                    "elapsed_ms": tick * int(controls["tick_ms"]),
                    **details,
                })

            def transition(control: str, down: bool) -> None:
                nonlocal key_transitions
                source = "control_buttons" if interaction == "simplified" else "keyboard"
                record("key_down" if down else "key_up", control=control, input_source=source)
                player["keys"][control] = down
                key_transitions += 1

            def hold(control: str, ticks: int) -> None:
                transition(control, True)
                grader._advance(
                    player,
                    int(player["tick"]) + ticks,
                    int(requirements["maximum_event_gap_ticks"]),
                    controls,
                    world,
                    walls,
                    occluders,
                )
                transition(control, False)

            def turn_to(point: list[float]) -> None:
                desired = math.atan2(
                    float(point[1]) - float(player["y"]),
                    float(point[0]) - float(player["x"]),
                )
                difference = grader._normalize_angle(desired - float(player["heading"]))
                if abs(difference) < 0.0005:
                    return
                if interaction == "full":
                    remaining = round(difference * 1000)
                    while remaining:
                        delta = int(math.copysign(min(600, abs(remaining)), remaining))
                        record("look", delta_millirad=delta, input_source="viewport_drag")
                        player["heading"] = grader._normalize_angle(float(player["heading"]) + delta / 1000)
                        remaining -= delta
                    return
                radians_per_tick = math.radians(float(controls["turn_speed_deg"])) * float(controls["tick_ms"]) / 1000
                ticks = max(1, round(abs(difference) / radians_per_tick))
                hold("turn_right" if difference > 0 else "turn_left", ticks)

            def move_to(point: list[float]) -> None:
                turn_to(point)
                remaining = math.dist(
                    (float(player["x"]), float(player["y"])),
                    (float(point[0]), float(point[1])),
                )
                distance_per_tick = float(controls["move_speed"]) * float(controls["tick_ms"]) / 1000
                ticks = max(1, round(remaining / distance_per_tick))
                first = max(1, ticks // 2)
                hold("forward", first)
                if ticks - first:
                    hold("forward", ticks - first)

            def scan() -> None:
                nonlocal scan_count, target_seen
                hits = grader._scan_hits(player, 0, controls, walls, occluders, objects)
                visible_returns = [
                    {
                        "ray_index": int(hit["ray_index"]),
                        "id": str(hit["id"]),
                        "kind": str(hit["kind"]),
                        "distance": round(float(hit["distance"]), 6),
                        "x": round(float(hit["x"]), 6),
                        "y": round(float(hit["y"]), 6),
                    }
                    for hit in hits
                ]
                source = "scan_button" if interaction == "simplified" else "viewport_scan"
                record("scan", aim_millirad=0, visible_returns=visible_returns, input_source=source)
                scan_count += 1
                origin = (float(player["x"]), float(player["y"]))
                if not stations or all(
                    math.dist(origin, station) >= float(requirements["station_distance"])
                    for station in stations
                ):
                    stations.append(origin)
                target_seen = target_seen or any(hit["kind"] == "beacon" for hit in hits)

            route = truth["solution"]["route_points"]
            scan_indices = set(truth["solution"]["scan_route_indices"])
            beacon_index = int(truth["solution"]["beacon_route_index"])
            for index, waypoint in enumerate(route):
                if index:
                    move_to(waypoint)
                if index in scan_indices:
                    if index < len(route) - 1:
                        turn_to(route[index + 1])
                    scan()
                if index == beacon_index:
                    assert target_seen
                    pickup_source = "pickup_button" if interaction == "simplified" else "scene_beacon"
                    record("pickup", input_source=pickup_source)
                    carrying = True

            assert carrying
            submit_source = "verify_button" if interaction == "simplified" else "physical_gate"
            record("submit", input_source=submit_source)
            payload = {
                "mechanic_id": public["mechanic_id"],
                "task_id": public["task_id"],
                "challenge_id": public["challenge_id"],
                "events": events,
                "scan_count": scan_count,
                "scan_station_count": len(stations),
                "key_transition_count": key_transitions,
                "collision_count": int(player["collisions"]),
                "carrying": True,
                "abandoned": False,
                "accepted": True,
                "completed": True,
            }
            decision = grader.grade(payload, truth, public)
            assert decision["passed"] is True, (level, interaction, decision["feedback"])


def test_forklift_profiles_match_board_route_and_delay_contracts() -> None:
    generated = generated_levels("input_lag_forklift_env")
    controls = controls_for("input_lag_forklift_env")
    for level, (public, truth) in enumerate(generated, start=1):
        parameters = controls["difficulty"][str(level)]["parameters"]
        assert public["warehouse"]["width"] == parameters["board_width"]
        assert public["warehouse"]["height"] == parameters["board_height"]
        assert len(public["warehouse"]["crates"]) == parameters["crate_count"]
        assert parameters["solution_length_min"] <= len(truth["solution"]) <= parameters["solution_length_max"]
        assert public["control_lag"] == parameters["control_lag"]
        assert truth["solution_issued_commands"][-parameters["control_lag"]:] == ["FLUSH"] * parameters["control_lag"]
        assert public["prompt"] == controls["difficulty"][str(level)]["natural_language"]
        if parameters["control_lag"] == 1:
            assert public["rules"]["flush"] == "EXECUTE QUEUE runs the pending direction without adding another."
        else:
            assert f"queued {parameters['control_lag']} inputs earlier" in public["rules"]["direction"]
            assert public["rules"]["flush"] == "EXECUTE QUEUE runs the oldest queued direction without adding another."


def test_orchard_profiles_match_visual_and_drag_contracts() -> None:
    generated = generated_levels("surreal_apple_on_tree_grid_env")
    controls = controls_for("surreal_apple_on_tree_grid_env")
    for level, (public, truth) in enumerate(generated, start=1):
        parameters = controls["difficulty"][str(level)]["parameters"]
        by_id = {apple["id"]: apple for apple in public["apples"]}
        detached_gaps = [
            abs(branch["points"][-1][2] - by_id[branch["fruit_id"]]["position"][2])
            for branch in public["branches"]
            if branch["fruit_id"] not in truth["attached_ids"]
        ]
        assert len(public["apples"]) == parameters["fruit_count"]
        assert len(truth["attached_ids"]) == parameters["attached_count"]
        assert all(parameters["depth_gap_min"] <= gap <= parameters["depth_gap_max"] for gap in detached_gaps)
        assert public["view_limit_deg"] == parameters["view_limit_deg"]
        assert all(parameters["fruit_radius_min"] <= apple["radius"] <= parameters["fruit_radius_max"] for apple in public["apples"])
        assert public["basket"]["width"] == parameters["basket_width"]
        assert public["basket"]["height"] == parameters["basket_height"]


def test_rotating_keyboard_profiles_match_motion_contracts() -> None:
    generated = generated_levels("rotating_keyboard_env")
    controls = controls_for("rotating_keyboard_env")
    for level, (public, truth) in enumerate(generated, start=1):
        parameters = controls["difficulty"][str(level)]["parameters"]
        instructions = controls["difficulty"][str(level)]["natural_language_by_interaction"]
        simplified_task = task_for_level("rotating_keyboard_env", level, "simplified")
        full_task = task_for_level("rotating_keyboard_env", level, "full")
        assert simplified_task["natural_language"] == instructions["simplified"]
        assert full_task["natural_language"] == instructions["full"]
        simplified_public, simplified_truth = SETUP.generate_task_state(
            simplified_task,
            f"rotating-pair-{level}",
        )
        full_public, full_truth = SETUP.generate_task_state(
            full_task,
            f"rotating-pair-{level}",
        )
        normalized_simplified = without_control_identity(simplified_public)
        normalized_full = without_control_identity(full_public)
        normalized_simplified.pop("prompt")
        normalized_full.pop("prompt")
        assert normalized_simplified == normalized_full
        assert without_control_identity(simplified_truth) == without_control_identity(full_truth)
        keyboard = public["keyboard"]
        assert sum(len(row) for row in keyboard["rows"]) == parameters["key_count"]
        assert len(truth["target"]) == parameters["code_length"]
        assert keyboard["motion_profile"] == parameters["motion_profile"]
        assert keyboard["spin_after_characters"] == parameters["spin_after_characters"]
        if "duration_ms_values" in parameters:
            assert keyboard["duration_ms"] in parameters["duration_ms_values"]
        else:
            assert parameters["duration_ms_min"] <= keyboard["duration_ms"] <= parameters["duration_ms_max"]


def test_rotating_keyboard_final_verifier_enforces_both_input_surfaces() -> None:
    sources = {
        "simplified": ("physical_keyboard", "onscreen_keys"),
        "full": ("onscreen_keys", "physical_keyboard"),
    }
    for interaction, (correct_source, wrong_source) in sources.items():
        public, truth = SETUP.generate_task_state(
            task_for_level("rotating_keyboard_env", 1, interaction),
            f"rotating-verifier-{interaction}",
        )
        accepted = verify_rotating_keyboard({
            "public_state": public,
            "ground_truth": truth,
            "result": {
                "text": truth["target"],
                "input_source": correct_source,
            },
        })
        rejected = verify_rotating_keyboard({
            "public_state": public,
            "ground_truth": truth,
            "result": {
                "text": truth["target"],
                "input_source": wrong_source,
            },
        })
        assert accepted["passed"] is True
        assert rejected["passed"] is False


def test_slot_reel_profiles_match_temporal_precision_and_recovery_contracts() -> None:
    generated = generated_levels("slot_reel_capture_env")
    controls = controls_for("slot_reel_capture_env")
    assert SETUP.SLOT_SYMBOLS == ("◆", "●", "✦", "♢", "▰", "✶")
    assert controls["difficulty"]["4"]["parameters"]["token_count"] == 7
    for level, (public, truth) in enumerate(generated, start=1):
        parameters = controls["difficulty"][str(level)]["parameters"]
        assert len(public["reels"]) == parameters["reel_count"]
        assert len(truth["sequence"]) == parameters["reel_count"]
        assert len(truth["reel_ids"]) == parameters["reel_count"]
        assert all(len(reel["tokens"]) == parameters["token_count"] for reel in public["reels"])
        assert all(reel["interval_ms"] in parameters["interval_ms_values"] for reel in public["reels"])
        assert public["max_strikes"] == truth["max_strikes"] == parameters["max_strikes"]
        assert truth.get("capture_window_ratio", 1.0) == parameters["capture_window_ratio"]
        assert public.get("capture_window_ratio", 1.0) == parameters["capture_window_ratio"]


def test_slot_reel_l5_visible_capture_lines_match_the_graded_window() -> None:
    app_source = (
        BENCHMARK / "shared_runtime" / "app" / "app.js"
    ).read_text(encoding="utf-8")
    style_source = (
        BENCHMARK / "shared_runtime" / "app" / "styles.css"
    ).read_text(encoding="utf-8")
    assert "Math.abs(cyclePosition - 0.5) <= captureWindowRatio / 2" in app_source
    assert "captureWindowRatio)) * 46}px" in app_source
    assert "calc(50% - var(--slot-capture-half-span))" in style_source
    assert "calc(50% + var(--slot-capture-half-span))" in style_source


def _slot_reel_passing_actions(
    public: dict,
    truth: dict,
    interaction: str,
) -> list[dict]:
    source = {
        "simplified": "capture_button",
        "full": "physical_keyboard",
    }[interaction]
    surface = {
        "simplified": "capture_button_click",
        "full": "keyboard_keydown",
    }[interaction]
    reels_by_id = {str(reel["id"]): reel for reel in public["reels"]}
    minimum_elapsed = 0.0
    actions = []
    for sequence, (reel_id, target) in enumerate(
        zip(truth["reel_ids"], truth["sequence"]),
        start=1,
    ):
        reel = reels_by_id[str(reel_id)]
        target_index = reel["tokens"].index(target)
        cycle = (target_index - int(reel["phase"])) % len(reel["tokens"])
        elapsed_ms = (cycle + 0.5) * int(reel["interval_ms"])
        while elapsed_ms < minimum_elapsed:
            cycle += len(reel["tokens"])
            elapsed_ms = (cycle + 0.5) * int(reel["interval_ms"])
        minimum_elapsed = elapsed_ms
        actions.append(
            {
                "sequence": sequence,
                "reel_id": reel_id,
                "elapsed_ms": elapsed_ms,
                "client_elapsed_ms": elapsed_ms,
                "server_task_time_ms": elapsed_ms,
                "server_received_wall_ns": sequence,
                "observed_token": target,
                "entered_key": target if interaction == "full" else None,
                "accepted": True,
                "input_source": source,
                "event_surface": surface,
            }
        )
    return actions


def _signed_slot_witness(
    truth: dict,
    actions: list[dict],
    interaction: str,
    key: dict | None = None,
) -> tuple[dict, dict, dict]:
    witness_module = load_module(
        "controlled_slot_reel_crypto",
        BENCHMARK
        / "shared_runtime"
        / "server"
        / "grillmaster_witness.py",
    )
    key = key or witness_module._generate_key(
        truth["challenge_id"]
    )
    public_key = witness_module._public_key(key)
    bound_truth = copy.deepcopy(truth)
    bound_truth["slot_reel_interaction_public_key"] = public_key
    signed = {
        "version": 1,
        "mechanic_id": "slot_reel_capture",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "interaction": interaction,
        "clock_source": "server_active_task_clock_v1",
        "public_key": public_key,
        "actions": copy.deepcopy(actions),
        "finalized_wall_ns": 1,
    }
    modulus = int(key["n_hex"], 16)
    private = int(key["d_hex"], 16)
    size = (modulus.bit_length() + 7) // 8
    encoded = witness_module._encoded_message(
        signed,
        size,
    )
    signature = pow(int.from_bytes(encoded, "big"), private, modulus)
    witness = {
        **signed,
        "signature_hex": signature.to_bytes(size, "big").hex(),
    }
    return bound_truth, witness, key


def test_slot_reel_verifier_binds_each_interaction_source_and_challenge() -> None:
    helpers = load_module(
        "controlled_slot_reel_verifier",
        BENCHMARK / "shared_runtime" / "verifier_helpers.py",
    )
    for interaction, source in (("simplified", "capture_button"), ("full", "physical_keyboard")):
        public, truth = SETUP.generate_task_state(
            task_for_level("slot_reel_capture_env", 4, interaction),
            f"slot-reel-{interaction}-verifier",
        )
        actions = _slot_reel_passing_actions(public, truth, interaction)
        truth, witness, key = _signed_slot_witness(
            truth,
            actions,
            interaction,
        )
        result = {
            "mechanic_id": "slot_reel_capture",
            "challenge_id": truth["challenge_id"],
            "captured_sequence": truth["sequence"],
            "frozen_reel_ids": truth["reel_ids"],
            "wrong_keys": 0,
            "actions": actions,
            "trusted_witness": witness,
        }
        exported = {"result": result, "ground_truth": truth, "public_state": public}
        assert helpers.verify_slot_reel_capture(exported)["passed"] is True

        wrong_source = copy.deepcopy(exported)
        wrong_actions = copy.deepcopy(actions)
        wrong_actions[0]["input_source"] = (
            "physical_keyboard" if source == "capture_button" else "capture_button"
        )
        (
            wrong_source["ground_truth"],
            wrong_source["result"]["trusted_witness"],
            _key,
        ) = _signed_slot_witness(
            truth,
            wrong_actions,
            interaction,
            key,
        )
        assert helpers.verify_slot_reel_capture(wrong_source)["passed"] is False

        stale = copy.deepcopy(exported)
        stale["result"]["challenge_id"] = "stale-challenge"
        assert helpers.verify_slot_reel_capture(stale)["passed"] is False

        missing_timing = copy.deepcopy(exported)
        missing_actions = copy.deepcopy(actions)
        missing_actions[0].pop("elapsed_ms")
        (
            missing_timing["ground_truth"],
            missing_timing["result"]["trusted_witness"],
            _key,
        ) = _signed_slot_witness(
            truth,
            missing_actions,
            interaction,
            key,
        )
        missing_decision = helpers.verify_slot_reel_capture(missing_timing)
        assert missing_decision["passed"] is False
        assert missing_decision["feedback"] == "slot-reel action is missing timing evidence"

        fabricated = copy.deepcopy(exported)
        first_reel = public["reels"][0]
        decoy_index = next(
            index
            for index, token in enumerate(first_reel["tokens"])
            if token != truth["sequence"][0]
        )
        cycle = (decoy_index - int(first_reel["phase"])) % len(first_reel["tokens"])
        fabricated_actions = copy.deepcopy(actions)
        fabricated_actions[0]["elapsed_ms"] = (
            cycle + 0.5
        ) * int(first_reel["interval_ms"])
        fabricated_actions[0]["client_elapsed_ms"] = fabricated_actions[0][
            "elapsed_ms"
        ]
        fabricated_actions[0]["server_task_time_ms"] = fabricated_actions[0][
            "elapsed_ms"
        ]
        (
            fabricated["ground_truth"],
            fabricated["result"]["trusted_witness"],
            _key,
        ) = _signed_slot_witness(
            truth,
            fabricated_actions,
            interaction,
            key,
        )
        fabricated_decision = helpers.verify_slot_reel_capture(fabricated)
        assert fabricated_decision["passed"] is False
        assert (
            fabricated_decision["feedback"]
            == "slot-reel observed symbol disagrees with task-time replay"
        )


def test_slot_reel_prompts_name_each_modes_actual_action_at_every_level() -> None:
    for level in range(1, 6):
        full = task_for_level("slot_reel_capture_env", level, "full")
        simplified = task_for_level(
            "slot_reel_capture_env",
            level,
            "simplified",
        )
        assert full["natural_language"].startswith("Type each letter or number ")
        assert simplified["natural_language"].startswith("Click CAPTURE SYMBOL ")


def test_gimbal_profiles_match_axis_coupling_and_precision_contracts() -> None:
    generated = generated_levels("rotate_wrong_thing_upright_env")
    controls = controls_for("rotate_wrong_thing_upright_env")
    for level, (public, _truth) in enumerate(generated, start=1):
        parameters = controls["difficulty"][str(level)]["parameters"]
        gimbal = public["gimbal"]
        assert gimbal["active_axes"] == parameters["active_axes"]
        assert len(gimbal["views"]) == parameters["view_count"]
        assert gimbal["coupling"] == parameters["coupling"]
        assert gimbal["tolerance"] == parameters["tolerance"]
        assert gimbal["degrees_per_pixel"] == parameters["degrees_per_pixel"]
        assert gimbal["target_needle_width"] == parameters["target_needle_width"]
        for axis, angle in gimbal["initial"].items():
            if axis in parameters["active_axes"]:
                assert parameters["initial_angle_min"] <= abs(angle) <= parameters["initial_angle_max"]
            else:
                assert angle == 0


def test_market_profiles_match_time_state_and_price_contracts() -> None:
    generated = generated_levels("insider_trading_captcha_env")
    controls = controls_for("insider_trading_captcha_env")
    grader = load_module(
        "controlled_market_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "insider_trading_captcha.py",
    )
    for level, (public, truth) in enumerate(generated, start=1):
        parameters = controls["difficulty"][str(level)]["parameters"]
        assert parameters["tick_count_min"] <= public["tick_count"] <= parameters["tick_count_max"]
        assert public["order_delay_ticks"] == parameters["order_delay_ticks"]
        assert public["max_position"] == parameters["max_position"]
        assert public["target_profit_cents"] >= parameters["target_profit_floor_cents"]
        assert len(truth["causal_reference_ledger"]) >= parameters["reference_settlements_min"]
        assert public["prompt"] == controls["difficulty"][str(level)]["natural_language"]
        if "tick_ms_values" in parameters:
            assert public["tick_ms"] in parameters["tick_ms_values"]
        else:
            assert parameters["tick_ms_min"] <= public["tick_ms"] <= parameters["tick_ms_max"]
        interaction = truth["control_condition"]["interaction"]
        input_source = "keyboard_hotkeys" if interaction == "simplified" else "order_buttons"
        orders = [
            {"tick": index, "side": side, "input_source": input_source}
            for index, side in enumerate(truth["solver_actions"])
        ]
        payload = {
            "mechanic_id": public["mechanic_id"],
            "task_id": public["task_id"],
            "challenge_id": public["challenge_id"],
            "orders": orders,
            "settlement_ledger": truth["solver_ledger"],
            "final": {"cash_cents": truth["max_profit_cents"] + truth["initial_cash_cents"], "position": 0},
        }
        assert grader.grade(payload, truth, public)["passed"] is True


def test_flat_prisoner_profiles_match_camera_decoy_and_traversal_contracts() -> None:
    controls = controls_for("flat_prisoner_env")
    for level, (public, truth) in enumerate(generated_levels("flat_prisoner_env"), start=1):
        parameters = controls["difficulty"][str(level)]["parameters"]
        assert len(public["platforms"]) == 5 + parameters["decoy_count"]
        assert math.isclose(public["initial_camera"]["pitch_deg"] - truth["solution"]["camera"]["pitch_deg"], parameters["pitch_offset_deg"])
        assert math.isclose(public["initial_camera"]["distance"] - truth["solution"]["camera"]["distance"], parameters["distance_offset"])
        assert public["controls"]["orbit_step_deg"] == parameters["orbit_step_deg"]
        assert public["controls"]["pan_step"] == parameters["pan_step"]
        assert public["physics"]["move_speed"] == parameters["move_speed"]
        assert public["physics"]["exit_radius"] == parameters["exit_radius"]
        assert public["requirements"]["minimum_camera_events"] == parameters["minimum_camera_events"]
        assert public["requirements"]["minimum_traversal_ticks"] == parameters["minimum_traversal_ticks"]


def test_forced_perspective_profiles_change_projective_placement_and_bind_input_surface() -> None:
    controls = controls_for("forced_perspective_moving_day_env")
    profiles = list(generated_levels("forced_perspective_moving_day_env"))
    gap_lengths = []
    slot_sizes = []
    for level, (public, truth) in enumerate(profiles, start=1):
        parameters = controls["difficulty"][str(level)]["parameters"]
        assert public["control_condition"]["difficulty"] == level
        assert public["camera"]["focal"] in parameters["focal_choices"]
        assert parameters["yaw_abs_min"] <= abs(public["camera"]["yaw"]) <= parameters["yaw_abs_max"]
        assert public["world"]["gap"] == parameters["gap"]
        assert public["slot"]["size"] == parameters["slot_size"]
        assert public["slot"]["max_scale"] == parameters["slot_max_scale"]
        assert public["bridge_zone"]["min_scale"] == parameters["bridge_min_scale"]
        assert public["world"]["door"]["half_gap"] == parameters["door_half_gap"]
        assert public["depth_controls"]["step"] == parameters["depth_step"]
        assert truth["control_condition"] == public["control_condition"]
        gap_lengths.append(public["world"]["gap"][1] - public["world"]["gap"][0])
        slot_sizes.append(public["slot"]["size"][0] * public["slot"]["size"][1])
    assert gap_lengths == sorted(gap_lengths)
    assert slot_sizes == sorted(slot_sizes, reverse=True)

    # The rendered slot must use the same active dimensions as browser and
    # replay readiness.  A fixed L4 outline would make four profiles lie about
    # their visible acceptance geometry.
    renderer = (
        BENCHMARK / "shared_runtime" / "app" / "mechanics" / "forced_perspective_moving_day.js"
    ).read_text(encoding="utf-8")
    assert "slotHalfX = slot.size[0] / 2" in renderer
    assert "slotHalfZ = slot.size[1] / 2" in renderer
    assert "slot.center[0] - .8" not in renderer

    environment = read_json(BENCHMARK / "environments" / "forced_perspective_moving_day_env" / "env.json")
    assert environment["observation"][0]["resolution"] == [1280, 720]

    grader = load_module(
        "controlled_forced_perspective_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "forced_perspective_moving_day.py",
    )
    for interaction, wrong_source in (("simplified", "direct_canvas_drag"), ("full", "ray_click")):
        public, truth = SETUP.generate_task_state(
            task_for_level("forced_perspective_moving_day_env", 4, interaction),
            f"forced-perspective-interaction-{interaction}",
        )
        result = grader.grade({
            "mechanic_id": public["mechanic_id"],
            "task_id": public["task_id"],
            "challenge_id": public["challenge_id"],
            "events": [{"sequence": 1, "kind": "pick", "input_source": wrong_source}],
        }, truth, public)
        assert result["passed"] is False
        assert result["feedback"] == "pickup uses the wrong interaction input"


def test_photograph_room_profiles_change_rewrites_and_bind_the_selected_surface() -> None:
    controls = controls_for("photograph_eats_the_room_env")
    profiles = list(generated_levels("photograph_eats_the_room_env"))
    source_counts = []
    void_widths = []
    capture_ranges = []
    bridge_half_widths = []
    for level, (public, truth) in enumerate(profiles, start=1):
        parameters = controls["difficulty"][str(level)]["parameters"]
        assert public["control_condition"]["difficulty"] == level
        assert public["control_condition"] == truth["control_condition"]
        assert len(public["sources"]) == parameters["stage_count"]
        assert len(public["sockets"]) == parameters["stage_count"]
        assert public["controls"]["plane_rotation_step_deg"] == parameters["plane_rotation_step_deg"]
        assert math.isclose(public["controls"]["plane_scale_step"], parameters["plane_scale_step"])
        assert math.isclose(public["qualification"]["capture_range"], parameters["capture_range"])
        assert math.isclose(public["qualification"]["bridge_half_width"], parameters["bridge_half_width"])
        assert all(math.isclose(socket["tolerance"], parameters["socket_tolerance"]) for socket in public["sockets"])
        source_counts.append(len(public["sources"]))
        void_widths.append(public["room"]["void"]["x2"] - public["room"]["void"]["x1"])
        capture_ranges.append(public["qualification"]["capture_range"])
        bridge_half_widths.append(public["qualification"]["bridge_half_width"])
    assert source_counts == [1, 2, 2, 2, 2]
    assert void_widths == sorted(void_widths)
    assert capture_ranges == sorted(capture_ranges, reverse=True)
    assert bridge_half_widths == [0.7, 0.62, 0.55, 0.48, 0.4]

    grader = load_module(
        "controlled_photograph_room_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "photograph_eats_the_room.py",
    )
    for interaction, wrong_surface in (("simplified", "full"), ("full", "simplified")):
        public, truth = SETUP.generate_task_state(
            task_for_level("photograph_eats_the_room_env", 4, interaction),
            f"photograph-room-interaction-{interaction}",
        )
        result = grader.grade({
            "mechanic_id": public["mechanic_id"],
            "task_id": public["task_id"],
            "challenge_id": public["challenge_id"],
            "events": [{
                "seq": 1,
                "t_ms": 0,
                "type": "challenge_start",
                "input_surface": wrong_surface,
                "camera": public["initial_camera"],
            }],
            "final_state": {},
        }, truth, public)
        assert result["passed"] is False
        assert result["feedback"] == "room event 1 uses the wrong interaction input"

    for public, _truth in profiles:
        bridge_half_width = float(public["qualification"]["bridge_half_width"])
        void = public["room"]["void"]
        bridge = {
            "operation": "add_walkway",
            "center": dict(public["sockets"][0]["center"]),
            "angle_deg": 0,
            "length": float(public["sockets"][0]["minimum_length"]),
        }
        accepted_before = {
            "x": float(void["x1"]) - 0.15,
            "y": float(public["room"]["lane_y"]) + bridge_half_width - 0.01,
        }
        accepted = grader._collision_move(
            dict(accepted_before), 0.4, 0.0, public["room"], [bridge], public["qualification"]
        )
        assert accepted["x"] > accepted_before["x"]
        blocked_before = {
            "x": float(void["x1"]) - 0.15,
            "y": float(public["room"]["lane_y"]) + bridge_half_width + 0.01,
        }
        blocked = grader._collision_move(
            dict(blocked_before), 0.4, 0.0, public["room"], [bridge], public["qualification"]
        )
        assert blocked == blocked_before

    renderer = (
        BENCHMARK / "shared_runtime" / "app" / "mechanics" / "photograph_eats_the_room.js"
    ).read_text(encoding="utf-8")
    styles = (
        BENCHMARK / "shared_runtime" / "app" / "mechanics" / "photograph_eats_the_room.css"
    ).read_text(encoding="utf-8")
    assert 'const interaction=state.control_condition?.interaction||"simplified"' in renderer
    assert 'supportsHistoricalKeys=interaction==="simplified"' in renderer
    assert '"WASD MOVE · ← → TURN · C CAPTURE"' in renderer
    assert "function scenePointerDown" in renderer
    assert "input_surface:model?.interaction" in renderer
    assert "width = Number(model.state.qualification.bridge_half_width)" in renderer
    assert "width = .48" not in renderer
    assert '.photo-room[data-interaction="full"] .photo-nav' in styles


def test_board_game_profiles_match_lamp_obstacle_and_physics_contracts() -> None:
    controls = controls_for("board_game_captcha_env")
    for level, (public, truth) in enumerate(generated_levels("board_game_captcha_env"), start=1):
        parameters = controls["difficulty"][str(level)]["parameters"]
        assert len(public["switches"]) == parameters["lamp_count"]
        assert len(public["walls"]) == parameters["wall_count"]
        assert len(public["hazards"]) == parameters["hazard_count"]
        assert all(item["radius"] == parameters["lamp_radius"] for item in public["switches"])
        assert public["goal"]["radius"] == parameters["goal_radius"]
        for key in ("tick_ms", "acceleration", "friction", "maximum_speed", "bounce", "ball_radius"):
            assert public["physics"][key] == parameters[key]
        assert len(truth["solver_switch_waypoint_indices"]) == parameters["lamp_count"]


def test_board_game_grader_enforces_the_selected_interaction_mode() -> None:
    grader = load_module(
        "controlled_board_game_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "board_game_captcha.py",
    )
    for interaction, wrong_source in (("simplified", "analog_drag"), ("full", "compass_button")):
        public, truth = SETUP.generate_task_state(
            task_for_level("board_game_captcha_env", 3, interaction),
            f"board-interaction-{interaction}",
        )
        payload = {
            "mechanic_id": public["mechanic_id"],
            "task_id": public["task_id"],
            "challenge_id": public["challenge_id"],
            "events": [{
                "sequence": 1,
                "kind": "tilt_change",
                "t_ms": 0,
                "from": [0, 0],
                "to": [1, 0],
                "input_source": wrong_source,
            }],
        }
        result = grader.grade(payload, truth, public)
        assert result["passed"] is False
        assert result["feedback"] == "event 1 uses the wrong interaction input"

    public, truth = SETUP.generate_task_state(
        task_for_level("board_game_captcha_env", 3, "simplified"),
        "board-interaction-non-compass",
    )
    payload = {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "events": [{
            "sequence": 1,
            "kind": "tilt_change",
            "t_ms": 0,
            "from": [0, 0],
            "to": [0.5, 0],
            "input_source": "compass_button",
        }],
    }
    result = grader.grade(payload, truth, public)
    assert result["passed"] is False
    assert result["feedback"] == "event 1 reports a non-compass simplified tilt"


def test_constellation_grader_enforces_the_selected_interaction_mode() -> None:
    grader = load_module(
        "controlled_constellation_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "cursor_constellation_hunt.py",
    )
    for interaction, source, wrong_source in (
        ("simplified", "coordinate_controls", "canvas_pointer"),
        ("full", "canvas_pointer", "coordinate_controls"),
    ):
        public, truth = SETUP.generate_task_state(
            task_for_level("cursor_constellation_hunt_env", 2, interaction),
            f"constellation-interaction-{interaction}",
        )
        expected = truth["expected_click"]
        payload = {
            "mechanic_id": public["mechanic_id"],
            "task_id": public["task_id"],
            "challenge_id": public["challenge_id"],
            "input_source": source,
            "click": {"x": expected["x"], "y": expected["y"]},
        }
        assert grader.grade(payload, truth, public)["passed"] is True
        payload["input_source"] = wrong_source
        result = grader.grade(payload, truth, public)
        assert result["passed"] is False
        assert result["feedback"] == "constellation submission uses the wrong interaction input"


def test_flat_pack_profiles_match_part_socket_and_load_contracts() -> None:
    controls = controls_for("flat_pack_compliance_env")
    for level, (public, truth) in enumerate(generated_levels("flat_pack_compliance_env"), start=1):
        parameters = controls["difficulty"][str(level)]["parameters"]
        assert [item["id"] for item in public["parts"]] == parameters["part_ids"]
        assert len(public["joints"]) == len(parameters["part_ids"]) - 1
        assert len(public["load_steps"]) == parameters["load_step_count"]
        assert public["requirements"]["pose_tolerance"] == parameters["pose_tolerance"]
        assert public["requirements"]["angle_tolerance"] == parameters["angle_tolerance"]
        assert public["requirements"]["strain_limit"] == parameters["strain_limit"]
        assert set(public["compliance_model"]["joint_factors"]) == set(truth["expected_joint_ids"])
        compliance = public["compliance_model"]
        peak_sensor_strain = max(
            (
                abs(step["force_x"]) * compliance["force_x_scale"]
                + abs(step["force_y"]) * compliance["force_y_scale"]
            ) * max(compliance["joint_factors"].values())
            for step in public["load_steps"]
        )
        assert peak_sensor_strain <= public["requirements"]["strain_limit"]


def test_specular_profiles_match_mirror_round_motion_and_tracking_contracts() -> None:
    controls = controls_for("specular_lighthouse_relay_env")
    for level, (public, truth) in enumerate(generated_levels("specular_lighthouse_relay_env"), start=1):
        parameters = controls["difficulty"][str(level)]["parameters"]
        assert len(public["rounds"]) == parameters["round_count"]
        assert public["round_count"] == parameters["round_count"]
        assert truth["angle_tolerance_deg"] == parameters["angle_tolerance_deg"]
        for round_data in public["rounds"]:
            assert len(round_data["mirrors"]) == parameters["mirror_count"]
            assert all(item["length"] == parameters["mirror_length"] for item in round_data["mirrors"])
            assert round_data["receiver"]["radius"] == parameters["receiver_radius"]
            assert round_data["receiver"]["amplitude"] in parameters["receiver_amplitudes"]
            assert round_data["receiver"]["angular_rate"] in parameters["receiver_angular_rates"]
            assert round_data["angle_step_deg"] == parameters["angle_step_deg"]
            assert round_data["tolerance_px"] == parameters["tolerance_px"]
            assert round_data["required_charge_ticks"] == parameters["required_charge_ticks"]
            assert round_data["miss_decay_ticks"] == parameters["miss_decay_ticks"]


def test_ghost_jigsaw_profiles_match_grid_size_and_motion_contracts() -> None:
    controls = controls_for("motion_only_ghost_jigsaw_env")
    for level, (public, truth) in enumerate(generated_levels("motion_only_ghost_jigsaw_env"), start=1):
        parameters = controls["difficulty"][str(level)]["parameters"]
        visual = public["visual"]
        assert len(public["pieces"]) == parameters["piece_count"]
        assert len(truth["expected_positions"]) == parameters["piece_count"]
        assert visual["rows"] == parameters["rows"]
        assert visual["columns"] == parameters["columns"]
        assert visual["frame_count"] == parameters["frame_count"]
        assert visual["fps"] == parameters["fps"]
        assert visual["frame_step"] == parameters["frame_step"]
        assert visual["scroll_speed"] in parameters["scroll_speeds"]


def test_constellation_profiles_match_search_field_contracts() -> None:
    controls = controls_for("cursor_constellation_hunt_env")
    for level, (public, truth) in enumerate(generated_levels("cursor_constellation_hunt_env"), start=1):
        parameters = controls["difficulty"][str(level)]["parameters"]
        surface = public["surface"]
        expected = truth["expected_click"]
        assert len(surface["decoys"]) == parameters["decoy_count"]
        assert sum(bool(star["noise"]) for star in surface["stars"]) == parameters["noise_star_count"]
        assert surface["reveal_radius"] == parameters["reveal_radius"]
        assert surface["decoy_radius"] == parameters["decoy_radius"]
        assert surface["decoy_strength"] == parameters["decoy_strength"]
        assert expected["radius"] == parameters["accepted_radius"]


def test_palimpsest_profiles_match_motion_scan_and_hold_contracts() -> None:
    controls = controls_for("cursor_lens_reveal_env")
    for level, (public, truth) in enumerate(generated_levels("cursor_lens_reveal_env"), start=1):
        parameters = controls["difficulty"][str(level)]["parameters"]
        assert len(public["nodes"]) == parameters["echo_count"]
        assert len(public["clutter"]) == parameters["clutter_count"]
        assert public["lens_radius"] == parameters["lens_radius"]
        for key in ("lock_radius", "minimum_hold_ms", "minimum_track_samples", "minimum_probe_samples", "minimum_probe_cells", "minimum_tuning_changes"):
            assert truth["requirements"][key] == parameters[key]
        for node in public["nodes"]:
            motion = node["motion"]
            assert parameters["motion_radius_x_min"] <= motion["radius_x"] <= parameters["motion_radius_x_max"]
            assert parameters["motion_radius_y_min"] <= motion["radius_y"] <= parameters["motion_radius_y_max"]
            assert parameters["motion_period_ms_min"] <= motion["period_ms"] <= parameters["motion_period_ms_max"]


def _consequences_payload(
    public: dict,
    truth: dict,
    interaction: str,
    *,
    force_repeated_state: bool = False,
) -> dict:
    parameters = (
        (truth.get("control_condition") or {}).get(
            "difficulty_parameters"
        )
        or {
            "socket_options": ["left", "right"],
            "seal_positions": 4,
            "minimum_distinct_states": 1,
        }
    )
    sockets = list(parameters["socket_options"])
    seal_positions = int(parameters["seal_positions"])
    minimum_distinct = int(parameters["minimum_distinct_states"])
    states = [(socket, seal) for socket in sockets for seal in range(seal_positions)]
    commitments = {
        scene_id: states[0 if force_repeated_state or index >= minimum_distinct else index]
        for index, scene_id in enumerate(truth["scene_ids"])
    }
    place_source = "socket_button" if interaction == "simplified" else "relic_drag"
    seal_source = "seal_button" if interaction == "simplified" else "seal_drag"
    events: list[dict] = []
    elapsed_ms = 0

    def append(kind: str, **values: object) -> None:
        nonlocal elapsed_ms
        events.append(
            {
                "sequence": len(events) + 1,
                "kind": kind,
                "elapsed_ms": elapsed_ms,
                **values,
            }
        )
        elapsed_ms += 10

    for order_index, scene_id in enumerate(truth["scene_ids"]):
        socket, seal = commitments[scene_id]
        append(
            "place",
            phase="commit",
            scene_id=scene_id,
            socket=socket,
            input_source=place_source,
        )
        append(
            "seal",
            phase="commit",
            scene_id=scene_id,
            seal=seal,
            input_source=seal_source,
        )
        append(
            "commit",
            scene_id=scene_id,
            socket=socket,
            seal=seal,
            order_index=order_index,
            place_input_source=place_source,
            seal_input_source=seal_source,
        )
    append("storm")
    elapsed_ms += int(truth["storm_ms"])
    append("judgment")
    for order_index, scene_id in enumerate(truth["boss_order"]):
        socket, seal = commitments[scene_id]
        append(
            "place",
            phase="reconstruct",
            scene_id=scene_id,
            socket=socket,
            input_source=place_source,
        )
        append(
            "seal",
            phase="reconstruct",
            scene_id=scene_id,
            seal=seal,
            input_source=seal_source,
        )
        append(
            "reconstruct",
            scene_id=scene_id,
            socket=socket,
            seal=seal,
            order_index=order_index,
            place_input_source=place_source,
            seal_input_source=seal_source,
        )
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "events": events,
    }


def test_consequences_profiles_change_the_actual_memory_contract() -> None:
    controls = controls_for("consequences_boss_env")
    for level, (public, truth) in enumerate(
        generated_levels("consequences_boss_env", "consequences-profile-contract"),
        start=1,
    ):
        parameters = controls["difficulty"][str(level)]["parameters"]
        assert len(public["scenes"]) == parameters["scene_count"]
        assert len(truth["scene_ids"]) == parameters["scene_count"]
        assert [scene["id"] for scene in public["scenes"]] == truth["scene_ids"]
        assert sorted(public["boss_order"]) == sorted(truth["scene_ids"])
        assert public["boss_order"] == truth["boss_order"]
        if parameters["shuffle_judgment"] is False:
            assert truth["boss_order"] == truth["scene_ids"]
        assert all(
            len(scene["socket_glyphs"]) == len(parameters["socket_options"])
            and 0 <= scene["initial_seal"] < parameters["seal_positions"]
            for scene in public["scenes"]
        )
        state_count = len(parameters["socket_options"]) * parameters["seal_positions"]
        assert 1 <= parameters["minimum_distinct_states"] <= min(
            parameters["scene_count"], state_count
        )

    assert controls["baseline"]["difficulty"] == 1
    assert controls["difficulty"]["1"]["parameters"] == {
        "scene_count": 5,
        "socket_options": ["left", "right"],
        "seal_positions": 4,
        "minimum_distinct_states": 1,
        "shuffle_judgment": True,
    }
    assert controls["difficulty"]["2"]["parameters"]["minimum_distinct_states"] == 2
    assert controls["difficulty"]["3"]["parameters"]["minimum_distinct_states"] == 3
    assert controls["difficulty"]["4"]["parameters"]["minimum_distinct_states"] == 6
    assert controls["difficulty"]["5"]["parameters"]["minimum_distinct_states"] == 8


def test_consequences_level_one_preserves_original_identity_and_world_across_seeds() -> None:
    original_task = json.loads(
        (
            BENCHMARK
            / "environments"
            / "consequences_boss_env"
            / "tasks"
            / "consequences_boss_seed_0001"
            / "task.json"
        ).read_text(encoding="utf-8")
    )
    baseline_task = task_for_level("consequences_boss_env", 1, "full")
    for seed in (
        "consequences-baseline-test-a",
        "consequences-baseline-test-b",
        "consequences-baseline-test-c",
    ):
        original_public, original_truth = SETUP.generate_task_state(
            original_task,
            seed,
        )
        baseline_public, baseline_truth = SETUP.generate_task_state(
            baseline_task,
            seed,
        )
        assert baseline_public["challenge_id"] == original_public["challenge_id"]
        assert baseline_public["generator"] == original_public["generator"]
        assert without_control_identity(baseline_public) == without_control_identity(
            original_public
        )
        assert without_control_identity(baseline_truth) == without_control_identity(
            original_truth
        )


def test_consequences_grader_accepts_each_mode_and_rejects_cross_mode_transcripts() -> None:
    grader = load_module(
        "controlled_consequences_grader",
        BENCHMARK
        / "shared_runtime"
        / "server"
        / "incubator_graders"
        / "consequences_boss.py",
    )
    for level in range(1, 6):
        for interaction in ("simplified", "full"):
            public, truth = SETUP.generate_task_state(
                task_for_level("consequences_boss_env", level, interaction),
                f"consequences-grader-{level}",
            )
            payload = _consequences_payload(public, truth, interaction)
            assert grader.grade(payload, truth, public)["passed"] is True
            wrong_interaction = "full" if interaction == "simplified" else "simplified"
            cross_mode = _consequences_payload(public, truth, wrong_interaction)
            rejected = grader.grade(cross_mode, truth, public)
            assert rejected["passed"] is False
            assert "wrong interaction input" in rejected["feedback"]


def test_consequences_grader_replays_storm_elapsed_time_instead_of_declared_duration() -> None:
    grader = load_module(
        "controlled_consequences_storm_grader",
        BENCHMARK
        / "shared_runtime"
        / "server"
        / "incubator_graders"
        / "consequences_boss.py",
    )
    public, truth = SETUP.generate_task_state(
        task_for_level("consequences_boss_env", 2, "full"),
        "consequences-storm-timing",
    )
    payload = _consequences_payload(public, truth, "full")
    assert grader.grade(payload, truth, public)["passed"] is True

    forged = copy.deepcopy(payload)
    storm = next(event for event in forged["events"] if event["kind"] == "storm")
    storm["duration_ms"] = int(truth["storm_ms"]) * 100
    judgment = next(event for event in forged["events"] if event["kind"] == "judgment")
    delta = int(judgment["elapsed_ms"]) - int(storm["elapsed_ms"])
    shift = delta - int(truth["storm_ms"]) + 1
    for event in forged["events"][forged["events"].index(judgment) :]:
        event["elapsed_ms"] -= shift
    rejected = grader.grade(forged, truth, public)
    assert rejected["passed"] is False
    assert "storm elapsed" in rejected["feedback"]


def test_consequences_memory_profiles_reject_repeated_state_shortcut() -> None:
    grader = load_module(
        "controlled_consequences_distinct_grader",
        BENCHMARK
        / "shared_runtime"
        / "server"
        / "incubator_graders"
        / "consequences_boss.py",
    )
    for level, required in ((2, 2), (3, 3), (4, 6), (5, 8)):
        public, truth = SETUP.generate_task_state(
            task_for_level("consequences_boss_env", level, "full"),
            f"consequences-repeated-state-d{level}",
        )
        repeated = _consequences_payload(
            public,
            truth,
            "full",
            force_repeated_state=True,
        )
        rejected = grader.grade(repeated, truth, public)
        assert rejected["passed"] is False
        assert f"distinct states 1/{required}" in rejected["feedback"]

    tutorial_public, tutorial_truth = SETUP.generate_task_state(
        task_for_level("consequences_boss_env", 1, "full"),
        "consequences-repeated-state-tutorial",
    )
    tutorial_repeated = _consequences_payload(
        tutorial_public,
        tutorial_truth,
        "full",
        force_repeated_state=True,
    )
    assert grader.grade(
        tutorial_repeated,
        tutorial_truth,
        tutorial_public,
    )["passed"] is True

    raw_task = json.loads(
        (
            BENCHMARK
            / "environments"
            / "consequences_boss_env"
            / "tasks"
            / "consequences_boss_seed_0001"
            / "task.json"
        ).read_text(encoding="utf-8")
    )
    raw_public, raw_truth = SETUP.generate_task_state(
        raw_task,
        "consequences-raw-repeated-state",
    )
    raw_repeated = _consequences_payload(
        raw_public,
        raw_truth,
        "full",
        force_repeated_state=True,
    )
    raw_decision = grader.grade(
        raw_repeated,
        raw_truth,
        raw_public,
    )
    assert raw_decision["passed"] is True


def test_candy_profiles_match_route_cascade_blocker_and_preview_contracts() -> None:
    controls = controls_for("exact_change_candy_cascade_env")
    for level, (public, truth) in enumerate(generated_levels("exact_change_candy_cascade_env"), start=1):
        parameters = controls["difficulty"][str(level)]["parameters"]
        assert public["move_budget"] == parameters["move_budget"]
        assert len(truth["solution_swaps"]) == parameters["move_budget"]
        assert max(truth["solution_wave_counts"]) >= parameters["minimum_max_wave"]
        assert max(truth["solution_wave_counts"]) <= parameters["maximum_max_wave"]
        assert sum(truth["solution_wave_counts"]) >= parameters["minimum_total_waves"]
        assert sum(truth["solution_wave_counts"]) <= parameters["maximum_total_waves"]
        assert len(truth["forbidden_positions"]) == parameters["forbidden_count"]
        assert public["refill_preview_count"] == parameters["refill_preview_count"]
        assert truth["solution_count_for_target"] <= parameters["maximum_solution_count"]


def test_voxel_profiles_match_extraction_risk_and_durability_contracts() -> None:
    controls = controls_for("minecraft_block_grid_env")
    for level, (public, truth) in enumerate(generated_levels("minecraft_block_grid_env"), start=1):
        parameters = controls["difficulty"][str(level)]["parameters"]
        materials = [voxel["material"] for voxel in public["voxels"]]
        required_strikes = parameters["target_count"] * (3 if parameters["sealed_targets"] else 2)
        assert public["target_count"] == parameters["target_count"]
        assert len(truth["solution_steps"]) == required_strikes
        assert materials.count("lava") == parameters["lava_count"]
        assert materials.count("support") == parameters["support_count"]
        assert sum(voxel["role"] == "screen" for voxel in public["voxels"]) == parameters["screen_count"]
        assert public["starting_durability"] == required_strikes + parameters["durability_margin"]
        if parameters["sealed_targets"]:
            assert public["extraction_prerequisites"] == truth["extraction_prerequisites"]
            assert len(public["extraction_prerequisites"]) == parameters["target_count"]
            assert all(len(required_ids) == 2 for required_ids in public["extraction_prerequisites"].values())
        else:
            assert "extraction_prerequisites" not in public
            assert "extraction_prerequisites" not in truth


def test_sealed_voxel_cannot_be_extracted_before_its_marked_stones() -> None:
    grader = load_module(
        "controlled_voxel_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "minecraft_block_grid.py",
    )
    public, truth = generated_levels("minecraft_block_grid_env", "voxel-seal-replay")[1]
    voxels = {str(voxel["id"]): dict(voxel) for voxel in truth["voxels"]}
    target_ids = set(truth["extraction_prerequisites"])
    visible_target = None
    for orientation in range(4):
        for face in grader._faces(voxels, orientation):
            if str(face["voxel_id"]) not in target_ids:
                continue
            x = sum(point[0] for point in face["points"]) / len(face["points"])
            y = sum(point[1] for point in face["points"]) / len(face["points"])
            hit = grader._raycast(voxels, orientation, x, y)
            if hit and hit["voxel_id"] == str(face["voxel_id"]):
                visible_target = (orientation, x, y, hit)
                break
        if visible_target:
            break
    assert visible_target is not None

    orientation, x, y, hit = visible_target
    events = []
    current_orientation = int(truth["starting_orientation"])
    while current_orientation != orientation:
        before = current_orientation
        current_orientation = (current_orientation + 1) % 4
        events.append({
            "sequence": len(events) + 1,
            "action": "rotate",
            "delta": 1,
            "orientation_before": before,
            "orientation_after": current_orientation,
            "input_source": "rotation_buttons",
        })
    durability = int(truth["starting_durability"]) - 1
    events.append({
        "sequence": len(events) + 1,
        "action": "mine",
        "orientation": orientation,
        "x": x,
        "y": y,
        "voxel_id": hit["voxel_id"],
        "face": hit["face"],
        "outcome": "diamond_sealed",
        "durability_after": durability,
        "inventory_after": [],
        "input_source": "canvas_click",
    })
    payload = {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "events": events,
        "final_state": {
            "orientation": orientation,
            "durability": durability,
            "inventory": [],
            "collapsed": False,
            "remaining_voxel_ids": sorted(voxels),
        },
        "completed": True,
    }
    result = grader.grade(payload, truth, public)
    assert result["passed"] is False
    assert result["feedback"].startswith("diamonds 0/")

    forged = copy.deepcopy(payload)
    forged["events"][-1]["outcome"] = "diamond_extracted"
    assert "material replay" in grader.grade(forged, truth, public)["feedback"]


def test_slime_profiles_match_lane_motion_and_control_contracts() -> None:
    controls = controls_for("slime_commute_env")
    for level, (public, truth) in enumerate(generated_levels("slime_commute_env"), start=1):
        parameters = controls["difficulty"][str(level)]["parameters"]
        board = public["board"]
        assert [lane["row"] for lane in board["lanes"]] == parameters["lane_rows"]
        assert board["hop_cooldown_ticks"] == parameters["hop_cooldown_ticks"]
        assert board["max_deaths"] == parameters["max_deaths"]
        assert truth["board"] == board


def test_controlled_forklift_grader_replays_every_delay_level() -> None:
    grader = load_module(
        "controlled_forklift_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "input_lag_forklift.py",
    )
    for public, truth in generated_levels("input_lag_forklift_env", "forklift-grader-levels"):
        player, crates, walls, goals = grader._initial(truth)
        lag = int(truth["control_lag"])
        interaction = truth["control_condition"]["interaction"]
        input_source = "control_buttons" if interaction == "simplified" else "keyboard"
        pending: list[str] = []
        events = []

        def pending_snapshot():
            return (pending[0] if pending else None) if lag == 1 else list(pending)

        for issued in truth["solution_issued_commands"]:
            before = grader._snapshot(player, crates)
            pending_before = pending_snapshot()
            executed = None
            if issued == "FLUSH":
                event_type = "flush"
                if pending:
                    executed = pending.pop(0)
                    player, crates, outcome = grader._move(player, crates, walls, executed)
                else:
                    outcome = "flushed_empty"
            else:
                event_type = "direction"
                if len(pending) < lag:
                    outcome = "queued"
                else:
                    executed = pending.pop(0)
                    player, crates, outcome = grader._move(player, crates, walls, executed)
                pending.append(issued)
            events.append({
                "sequence": len(events) + 1,
                "type": event_type,
                "issued": issued,
                "pending_before": pending_before,
                "executed": executed,
                "outcome": outcome,
                "before": before,
                "after": grader._snapshot(player, crates),
                "pending_after": pending_snapshot(),
                "input_source": input_source,
            })
        payload = {
            "mechanic_id": public["mechanic_id"],
            "task_id": public["task_id"],
            "challenge_id": public["challenge_id"],
            "issued_commands": events,
            "final_state": grader._snapshot(player, crates),
            "pending_command": pending_snapshot(),
            "collisions": sum(event["outcome"].startswith("collision_") for event in events),
            "reset_count": 0,
            "calibration_history": [],
            "completed": not pending and set(crates) == set(goals),
        }
        assert grader.grade(payload, truth, public)["passed"] is True


def test_controlled_orchard_grader_accepts_each_target_count() -> None:
    grader = load_module(
        "controlled_orchard_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "surreal_apple_on_tree_grid.py",
    )
    seed = "orchard-grader-levels"
    for level in range(1, 6):
        for interaction in ("simplified", "full"):
            public, truth = SETUP.generate_task_state(
                task_for_level("surreal_apple_on_tree_grid_env", level, interaction), seed
            )
            events = []

            def record(kind: str, **details) -> None:
                events.append({"sequence": len(events) + 1, "kind": kind, **details})

            limit = float(public["view_limit_deg"])
            angles = [0.0]
            if interaction == "full":
                start = [480.0, 260.0]
                record("orbit_start", point=start, angle_before=0.0, input_source="canvas_drag")
                xs = [360, 240, 120, 0, 120, 240, 360, 480, 600, 720, 840, 960]
                xs.extend(950 if index % 2 == 0 else 960 for index in range(8))
                for x in xs:
                    angle = max(-limit, min(limit, (x - start[0]) * 0.24))
                    record("orbit_move", point=[float(x), 260.0], angle_after=round(angle, 2), input_source="canvas_drag")
                    angles.append(round(angle, 2))
                record("orbit_end", point=[float(xs[-1]), 260.0], angle=angles[-1], input_source="canvas_drag")
            else:
                targets = [6.0] * math.ceil(limit / 6) + [-6.0] * math.ceil(2 * limit / 6)
                for delta in targets:
                    before = angles[-1]
                    after = round(max(-limit, min(limit, before + delta)), 2)
                    record("orbit_step", angle_before=before, angle_after=after, input_source="orbit_buttons")
                    angles.append(after)

            apple_by_id = {apple["id"]: apple for apple in truth["apples"]}
            basket = truth["basket"]
            destination = [basket["x"] + basket["width"] / 2, basket["y"] + basket["height"] / 2]
            for apple_id in truth["attached_ids"]:
                center = list(grader._project(apple_by_id[apple_id]["position"], angles[-1]))
                if interaction == "simplified":
                    record("pluck_select", apple_id=apple_id, point=center, angle=angles[-1], input_source="fruit_basket_clicks")
                    record("basket_click", apple_id=apple_id, point=destination, accepted=True, input_source="fruit_basket_clicks")
                else:
                    record("pluck_start", apple_id=apple_id, point=center, angle=angles[-1], input_source="fruit_drag")
                    for index in range(1, 5):
                        fraction = index / 5
                        point = [
                            center[0] + (destination[0] - center[0]) * fraction,
                            center[1] + (destination[1] - center[1]) * fraction,
                        ]
                        record("pluck_move", apple_id=apple_id, point=point, elapsed_ms=index * 20, input_source="fruit_drag")
                    record("pluck_end", apple_id=apple_id, point=destination, duration_ms=100, in_basket=True, accepted=True, input_source="fruit_drag")
            record("seal")
            travel = round(sum(abs(right - left) for left, right in zip(angles, angles[1:])), 2)
            span = round(max(angles) - min(angles), 2)
            sectors = {grader._sector(angle) for angle in angles}
            payload = {
                "mechanic_id": public["mechanic_id"],
                "task_id": public["task_id"],
                "challenge_id": public["challenge_id"],
                "events": events,
                "final_angle_deg": angles[-1],
                "orbit_samples": len(angles) - 1,
                "orbit_span_deg": span,
                "orbit_travel_deg": travel,
                "view_sector_count": len(sectors),
                "plucked_ids": sorted(truth["attached_ids"]),
                "invalid_plucks": 0,
                "reset_count": 0,
                "seal_count": 1,
                "completed": True,
            }
            assert grader.grade(payload, truth, public)["passed"] is True


def solve_linear(matrix: list[list[float]], right: list[float]) -> list[float]:
    size = len(matrix)
    work = [row[:] + [right[index]] for index, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(work[row][column]))
        work[column], work[pivot] = work[pivot], work[column]
        scale = work[column][column]
        work[column] = [value / scale for value in work[column]]
        for row in range(size):
            if row == column:
                continue
            amount = work[row][column]
            work[row] = [work[row][index] - amount * work[column][index] for index in range(size + 1)]
    return [work[index][size] for index in range(size)]


def test_controlled_gimbal_grader_accepts_each_axis_and_coupling_profile() -> None:
    grader = load_module(
        "controlled_gimbal_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "rotate_wrong_thing_upright.py",
    )
    for public, truth in generated_levels("rotate_wrong_thing_upright_env", "gimbal-grader-levels"):
        contract = truth["gimbal"]
        axes = contract["active_axes"]
        coupling = contract["coupling"]
        effects = {
            "outer": {"outer": 1.0, "middle": 0.0, "inner": float(coupling["outer_to_inner"])},
            "middle": {"outer": float(coupling["middle_to_outer"]), "middle": 1.0, "inner": 0.0},
            "inner": {"outer": 0.0, "middle": float(coupling["inner_to_middle"]), "inner": 1.0},
        }
        matrix = [[effects[input_axis][output_axis] for input_axis in axes] for output_axis in axes]
        deltas = solve_linear(matrix, [-float(contract["initial"][axis]) for axis in axes])
        events = []
        for view in contract["views"]:
            events.append({"sequence": len(events) + 1, "kind": "view", "view": view})
        maximum = float(contract["max_drag_delta"])
        for axis, delta in zip(axes, deltas):
            remaining = delta
            while abs(remaining) > 1e-8:
                chunk = math.copysign(min(abs(remaining), maximum * 0.9), remaining)
                interaction = truth["control_condition"]["interaction"]
                input_source = "axis_controls" if interaction == "simplified" else "gimbal_ring_drag"
                events.append({"sequence": len(events) + 1, "kind": "drag", "axis": axis, "delta": chunk, "input_source": input_source})
                remaining -= chunk
        payload = {
            "mechanic_id": public["mechanic_id"],
            "challenge_id": public["challenge_id"],
            "events": events,
        }
        assert grader.grade(payload, truth, public)["passed"] is True


def test_every_controlled_generator_is_deterministic_and_binds_the_condition() -> None:
    for env_name in CONTROLLED_ENVIRONMENTS:
        challenge_ids = set()
        for level in range(1, 6):
            task = task_for_level(env_name, level)
            first = SETUP.generate_task_state(task, "controlled-determinism")
            second = SETUP.generate_task_state(task, "controlled-determinism")
            assert first == second
            challenge_ids.add(first[0]["challenge_id"])
            for state in first:
                assert state["control_condition"] == task["metadata"]["control_condition"]
        assert len(challenge_ids) == 5


def _time_wheel_payload(grader, public: dict, truth: dict, interaction: str) -> dict:
    current = copy.deepcopy(public["initial_date"])
    source = "proxy_step" if interaction == "simplified" else "wheel_drag"
    events: list[dict] = []

    def append(kind: str, **details) -> None:
        events.append({"sequence": len(events) + 1, "type": kind, **details, "date_after": copy.deepcopy(current)})

    for action in truth["direct_recovery_route"]:
        component = str(action["component"])
        steps = int(action["steps"])
        append("drag_start", component=component, input_source=source)
        direction = 1 if steps > 0 else -1
        for _ in range(abs(steps)):
            current = grader._step(
                current,
                component,
                direction,
                int(public["year_range"]["minimum"]),
                int(public["year_range"]["maximum"]),
            )
            append("detent", source="drag", component=component, direction=direction, input_source=source)
        append("drag_end", component=component, drag_detents=abs(steps), input_source=source)
    append("lock")
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction_mode": interaction,
        "events": events,
        "final_date": current,
        "completed": current == public["target_date"],
    }


def test_thirty_year_time_wheel_profiles_preserve_l3_and_bind_both_input_surfaces() -> None:
    env_name = "thirty_year_time_wheel_env"
    mechanic = "thirty_year_time_wheel"
    controls = controls_for(env_name)
    grader = load_module(
        "controlled_thirty_year_time_wheel_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{mechanic}.py",
    )
    original = base_task_for(env_name, mechanic)
    assert controls["baseline"] == {"difficulty": 3, "interaction": "full", "real_time": "live"}
    assert controls["real_time"] == {
        "play_time_seconds": 120,
        "observation_window_ms": 600,
        "frames_per_observation": 5,
    }

    for seed in ("time-wheel-baseline-a", "time-wheel-baseline-b", "time-wheel-baseline-c"):
        original_public, original_truth = SETUP.generate_task_state(original, seed)
        baseline_public, baseline_truth = SETUP.generate_task_state(task_for_level(env_name, 3, "full"), seed)
        assert without_control_identity(baseline_public) == without_control_identity(original_public)
        assert without_control_identity(baseline_truth) == without_control_identity(original_truth)

    expected_sources = {"simplified": "proxy_step", "full": "wheel_drag"}
    for level in range(1, 6):
        parameters = controls["difficulty"][str(level)]["parameters"]
        simplified_public, simplified_truth = SETUP.generate_task_state(
            task_for_level(env_name, level, "simplified"), f"time-wheel-profile-{level}"
        )
        full_public, full_truth = SETUP.generate_task_state(
            task_for_level(env_name, level, "full"), f"time-wheel-profile-{level}"
        )
        assert without_control_identity(simplified_public) == without_control_identity(full_public)
        assert without_control_identity(simplified_truth) == without_control_identity(full_truth)
        assert full_public["year_range"] == {
            "minimum": parameters["year_min"],
            "maximum": parameters["year_max"],
        }
        expected_required = parameters["required_components"]
        assert full_public.get("required_components", ["month", "year", "day"]) == expected_required
        assert full_truth.get("required_components", ["month", "year", "day"]) == expected_required
        if level == 3:
            assert "target_presentation" not in full_public
        else:
            assert full_public["target_presentation"] == parameters["target_presentation"]

        for interaction, public, truth in (
            ("simplified", simplified_public, simplified_truth),
            ("full", full_public, full_truth),
        ):
            payload = _time_wheel_payload(grader, public, truth, interaction)
            assert grader.grade(payload, truth, public)["passed"] is True
            wrong_mode = copy.deepcopy(payload)
            wrong_mode["interaction_mode"] = "full" if interaction == "simplified" else "simplified"
            assert grader.grade(wrong_mode, truth, public)["passed"] is False
            wrong_source = copy.deepcopy(payload)
            next(event for event in wrong_source["events"] if event["type"] == "detent")["input_source"] = (
                "wheel_drag" if interaction == "simplified" else "proxy_step"
            )
            assert grader.grade(wrong_source, truth, public)["passed"] is False

    renderer = (
        BENCHMARK / "shared_runtime" / "app" / "mechanics" / f"{mechanic}.js"
    ).read_text(encoding="utf-8")
    assert 'data-time-proxy-component' in renderer
    assert 'if (interactionMode() !== "full"' in renderer
    assert 'input_source: "proxy_step"' in renderer


def _wrong_number_payload(public: dict, truth: dict, interaction: str, grader) -> dict:
    source = {"simplified": "step_proxy", "full": "tuning_slider"}[interaction]
    qualification = truth["qualification"]
    target = next(line for line in truth["lines"] if line["id"] == truth["target_line_id"])
    phase = int(truth["solution_phase_step"])
    skew = int(truth["solution_skew_step"])
    events: list[dict] = []

    def push(event_type: str, timestamp: int, **details: object) -> dict:
        event = {"seq": len(events) + 1, "t_ms": timestamp, "type": event_type, **details}
        events.append(event)
        return event

    push("line_select", 0, line_id=target["id"])
    push("tune", 1, control="phase", value=phase, input_source=source)
    push("tune", 2, control="skew", value=skew, input_source=source)
    trial_start = push("trial_start", 10, line_id=target["id"], phase=phase, skew=skew)
    start_t = 10
    locked_samples = 0
    lock_history: list[bool] = []
    sample_count = 0
    sample_times = list(range(0, int(qualification["trial_ms"]) + 1, int(qualification["sample_ms"])))
    if sample_times[-1] != int(qualification["trial_ms"]):
        sample_times.append(int(qualification["trial_ms"]))
    for elapsed in sample_times:
        target_phase = (
            -float(target["phase_offset_steps"])
            - float(target["drift_milli_steps_per_second"]) * elapsed / 1_000_000
        ) % int(qualification["phase_steps"])
        desired_phase = int(math.floor(target_phase + .5)) % int(qualification["phase_steps"])
        if desired_phase != phase:
            push("tune", start_t + elapsed - 1, control="phase", value=desired_phase, input_source=source)
            phase = desired_phase
        residual, locked = grader._alignment(target, phase, skew, elapsed, qualification)
        push(
            "trial_sample",
            start_t + elapsed,
            line_id=target["id"],
            elapsed_ms=elapsed,
            phase=phase,
            skew=skew,
            locked=locked,
            residual_milli=round(residual * 1000),
        )
        sample_count += 1
        locked_samples += int(locked)
        lock_history.append(locked)
        lock_history = lock_history[-int(qualification["final_window_samples"]):]
    passed_local = (
        locked_samples >= int(qualification["minimum_lock_samples"])
        and sum(lock_history) >= int(qualification["minimum_final_lock_samples"])
    )
    push(
        "trial_end",
        start_t + sample_times[-1] + 1,
        line_id=target["id"],
        passed_local=passed_local,
        sample_count=sample_count,
        locked_sample_count=locked_samples,
        final_window_locked_samples=sum(lock_history),
    )
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction_mode": interaction,
        "events": events,
        "completed": True,
        "selected_line_id": target["id"],
        "final_phase": phase,
        "final_skew": skew,
        "successful_trial_start_seq": trial_start["seq"],
        "trial_count": 1,
    }


def test_wrong_number_profiles_preserve_l4_and_bind_both_tuning_surfaces() -> None:
    env_name = "wrong_number_env"
    mechanic = "wrong_number"
    controls = controls_for(env_name)
    grader = load_module(
        "controlled_wrong_number_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{mechanic}.py",
    )
    original = base_task_for(env_name, mechanic)
    assert controls["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    assert original["natural_language"] == controls["difficulty"]["4"]["natural_language"]

    for seed in ("wrong-number-baseline-a", "wrong-number-baseline-b"):
        original_public, original_truth = SETUP.generate_task_state(original, seed)
        baseline_public, baseline_truth = SETUP.generate_task_state(task_for_level(env_name, 4, "full"), seed)
        assert without_control_identity(baseline_public) == without_control_identity(original_public)
        assert without_control_identity(baseline_truth) == without_control_identity(original_truth)

    line_counts: list[int] = []
    phase_steps: list[int] = []
    trial_lengths: list[int] = []
    for level in range(1, 6):
        parameters = controls["difficulty"][str(level)]["parameters"]
        simplified_public, simplified_truth = SETUP.generate_task_state(
            task_for_level(env_name, level, "simplified"), f"wrong-number-d{level}"
        )
        full_public, full_truth = SETUP.generate_task_state(
            task_for_level(env_name, level, "full"), f"wrong-number-d{level}"
        )
        assert without_control_identity(simplified_public) == without_control_identity(full_public)
        assert without_control_identity(simplified_truth) == without_control_identity(full_truth)
        assert len(full_public["lines"]) == parameters["line_count"]
        assert full_public["qualification"]["phase_steps"] == parameters["phase_steps"]
        assert full_public["qualification"]["skew_min"] == parameters["skew_min"]
        assert full_public["qualification"]["skew_max"] == parameters["skew_max"]
        assert full_public["qualification"]["trial_ms"] == parameters["trial_ms"]
        assert all(
            int(line["drift_milli_steps_per_second"]) in parameters["drift_milli_values"]
            for line in full_public["lines"]
        )
        assert all(
            int(parameters["impostor_distortion_min_milli"]) <= int(line["distortion_milli"]) <= int(parameters["impostor_distortion_max_milli"])
            for line in full_public["lines"]
            if line["id"] != full_truth["target_line_id"]
        )
        line_counts.append(len(full_public["lines"]))
        phase_steps.append(int(full_public["qualification"]["phase_steps"]))
        trial_lengths.append(int(full_public["qualification"]["trial_ms"]))

        for interaction, public, truth in (
            ("simplified", simplified_public, simplified_truth),
            ("full", full_public, full_truth),
        ):
            payload = _wrong_number_payload(public, truth, interaction, grader)
            assert grader.grade(payload, truth, public)["passed"] is True
            wrong_mode = copy.deepcopy(payload)
            wrong_mode["interaction_mode"] = "full" if interaction == "simplified" else "simplified"
            assert grader.grade(wrong_mode, truth, public)["passed"] is False
            wrong_source = copy.deepcopy(payload)
            first_tune = next(event for event in wrong_source["events"] if event["type"] == "tune")
            first_tune["input_source"] = "tuning_slider" if interaction == "simplified" else "step_proxy"
            assert grader.grade(wrong_source, truth, public)["passed"] is False
            stale = copy.deepcopy(payload)
            stale["challenge_id"] = "stale-switchboard"
            assert grader.grade(stale, truth, public)["passed"] is False

    assert line_counts == sorted(line_counts)
    assert phase_steps == sorted(phase_steps)
    assert trial_lengths == sorted(trial_lengths)


def _top_face_dice_payload(public: dict, truth: dict, interaction: str, grader) -> dict:
    sources = {
        "simplified": {"select": "die_clamp", "roll": "roll_pad"},
        "full": {"select": "rail_drag_select", "roll": "direct_rail_drag"},
    }[interaction]
    dice = {
        item["id"]: {
            "position": dict(item["start"]),
            "orientation": copy.deepcopy(item["initial_orientation"]),
            "accepted_rolls": 0,
            "docked": False,
            "initial_reveal": True,
            "scanner_cells": {tuple(cell.values()) for cell in item["scanner_cells"]},
        }
        for item in truth["dice"]
    }
    events: list[dict] = []
    selected = truth["initial_selected_die_id"]
    for plan in truth["solution_plans"]:
        die_id = plan["die_id"]
        events.append({
            "seq": len(events) + 1,
            "t_ms": len(events),
            "type": "select",
            "die_id": die_id,
            "selected_before": selected,
            "selected_after": die_id,
            "input_source": sources["select"],
        })
        selected = die_id
        die = dice[die_id]
        for world_direction in plan["world_directions"]:
            before = dict(die["position"])
            dx, dy = grader.DIRECTIONS[world_direction]
            candidate = {"x": before["x"] + dx, "y": before["y"] + dy}
            die["position"] = candidate
            die["orientation"] = grader._roll(die["orientation"], world_direction)
            die["accepted_rolls"] += 1
            die["initial_reveal"] = False
            die["docked"] = candidate == truth["dice"][list(dice).index(die_id)]["dock"]
            top_visible = (
                public.get("orientation_visibility", "initial_and_scanners") == "always"
                or tuple(candidate.values()) in die["scanner_cells"]
                or die["docked"]
            )
            events.append({
                "seq": len(events) + 1,
                "t_ms": len(events),
                "type": "roll",
                "die_id": die_id,
                "input_direction": world_direction,
                "world_direction": world_direction,
                "view": 0,
                "from": before,
                "to": dict(candidate),
                "accepted": True,
                "orientation_after": copy.deepcopy(die["orientation"]),
                "accepted_rolls_after": die["accepted_rolls"],
                "docked": die["docked"],
                "top_visible": top_visible,
                "input_source": sources["roll"],
            })
    events.append({"seq": len(events) + 1, "t_ms": len(events), "type": "settle_start", "sample_count": 7})
    for sample_index, deflection in enumerate([26, -16, 10, -6, 3, -1, 0], start=1):
        events.append({"seq": len(events) + 1, "t_ms": len(events), "type": "settle_sample", "sample_index": sample_index, "deflection": deflection})
    top_sum = sum(int(die["orientation"]["top"]) for die in dice.values())
    events.append({"seq": len(events) + 1, "t_ms": len(events), "type": "settle_complete", "balanced": True, "top_sum": top_sum})
    final_dice = [{
        "die_id": item["id"],
        "position": dict(dice[item["id"]]["position"]),
        "orientation": copy.deepcopy(dice[item["id"]]["orientation"]),
        "accepted_rolls": dice[item["id"]]["accepted_rolls"],
        "docked": dice[item["id"]]["docked"],
        "top_visible": (
            public.get("orientation_visibility", "initial_and_scanners") == "always"
            or tuple(dice[item["id"]]["position"].values()) in dice[item["id"]]["scanner_cells"]
            or dice[item["id"]]["docked"]
        ),
    } for item in truth["dice"]]
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "events": events,
        "final_state": {
            "view": 0,
            "selected_die_id": selected,
            "view_rotations": 0,
            "reset_count": 0,
            "dice": final_dice,
            "top_sum": top_sum,
            "settled": True,
            "settle_samples": [26, -16, 10, -6, 3, -1, 0],
        },
    }


def test_top_face_dice_profiles_preserve_l5_and_bind_both_input_surfaces() -> None:
    env_name = "top_face_dice_arithmetic_env"
    controls = controls_for(env_name)
    grader = load_module(
        "controlled_top_face_dice_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "top_face_dice_arithmetic.py",
    )
    helpers = load_module(
        "controlled_top_face_dice_verifier",
        BENCHMARK / "shared_runtime" / "verifier_helpers.py",
    )
    original = base_task_for(env_name, "top_face_dice_arithmetic")
    baseline = task_for_level(env_name, 5, "simplified")
    for seed in ("top-face-l5-preservation-a", "top-face-l5-preservation-b"):
        original_public, original_truth = SETUP.generate_task_state(original, seed)
        baseline_public, baseline_truth = SETUP.generate_task_state(baseline, seed)
        assert without_control_identity(baseline_public) == without_control_identity(original_public)
        assert without_control_identity(baseline_truth) == without_control_identity(original_truth)

    profile_dice_counts: list[int] = []
    visibility: list[str] = []
    for level in range(1, 6):
        parameters = controls["difficulty"][str(level)]["parameters"]
        seed = f"top-face-profile-{level}"
        simplified_public, simplified_truth = SETUP.generate_task_state(task_for_level(env_name, level, "simplified"), seed)
        full_public, full_truth = SETUP.generate_task_state(task_for_level(env_name, level, "full"), seed)
        assert without_control_identity(simplified_public) == without_control_identity(full_public)
        assert without_control_identity(simplified_truth) == without_control_identity(full_truth)
        assert len(simplified_public["dice"]) == parameters["dice_count"]
        effective_visibility = simplified_public.get("orientation_visibility", "initial_and_scanners")
        assert effective_visibility == parameters["orientation_visibility"]
        profile_dice_counts.append(len(simplified_public["dice"]))
        visibility.append(effective_visibility)
        for interaction, public, truth in (("simplified", simplified_public, simplified_truth), ("full", full_public, full_truth)):
            payload = _top_face_dice_payload(public, truth, interaction, grader)
            assert grader.grade(payload, truth, public)["passed"] is True
            verifier_payload = {
                "result": payload,
                "ground_truth": truth,
                "public_state": public,
            }
            assert helpers.verify_external_mechanic(verifier_payload, "top_face_dice_arithmetic")["passed"] is True
            forged = copy.deepcopy(payload)
            first_roll = next(event for event in forged["events"] if event["type"] == "roll")
            first_roll["input_source"] = "direct_rail_drag" if interaction == "simplified" else "roll_pad"
            assert grader.grade(forged, truth, public)["feedback"] == "die roll uses the wrong interaction input"
            verifier_payload["result"] = forged
            assert helpers.verify_external_mechanic(verifier_payload, "top_face_dice_arithmetic") == {
                "passed": False,
                "score": 0,
                "feedback": "die roll uses the wrong interaction input",
            }
            stale = copy.deepcopy(payload)
            stale["challenge_id"] = "stale-top-face-challenge"
            assert grader.grade(stale, truth, public)["feedback"] == "stale challenge"
            verifier_payload["result"] = stale
            assert helpers.verify_external_mechanic(verifier_payload, "top_face_dice_arithmetic") == {
                "passed": False,
                "score": 0,
                "feedback": "stale challenge",
            }

    assert profile_dice_counts == [1, 2, 3, 3, 4]
    assert visibility == ["always", "always", "always", "initial_and_scanners", "initial_and_scanners"]
    browser = (BENCHMARK / "shared_runtime" / "app" / "mechanics" / "top_face_dice_arithmetic.js").read_text(encoding="utf-8")
    styles = (BENCHMARK / "shared_runtime" / "app" / "mechanics" / "top_face_dice_arithmetic.css").read_text(encoding="utf-8")
    assert 'data-interaction="${helpers.text(interaction)}"' in browser
    assert 'rollSelected(direction, "direct_rail_drag")' in browser
    assert 'model.interaction !== "simplified"' in browser
    assert 'repeat(var(--foundry-dice), 1fr)' in styles


def test_top_face_dice_controlled_exhaustion_constructs_a_valid_lot(monkeypatch) -> None:
    env_name = "top_face_dice_arithmetic_env"
    controls = controls_for(env_name)
    generator = load_module(
        "controlled_top_face_dice_generator_exhaustion",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "top_face_dice_arithmetic.py",
    )
    grader = load_module(
        "controlled_top_face_dice_grader_exhaustion",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "top_face_dice_arithmetic.py",
    )

    class ExhaustedLotRng:
        def shuffle(self, _items) -> None:
            return None

        def randint(self, lower: int, _upper: int) -> int:
            return lower

        def choice(self, options):
            values = tuple(options)
            if values == generator.ROUTE_PLANS:
                return generator.ROUTE_PLANS[5]
            return values[0]

    monkeypatch.setattr(generator.random, "Random", lambda _seed: ExhaustedLotRng())
    monkeypatch.setattr(generator, "_initial_orientation", lambda _rng: dict(generator.CANONICAL))

    task = SETUP.task_with_control_condition(task_for_level(env_name, 4, "simplified"))
    full_task = SETUP.task_with_control_condition(task_for_level(env_name, 4, "full"))
    parameters = controls["difficulty"]["4"]["parameters"]
    forced_candidate = generator._candidate_lot(
        [dict(generator.CANONICAL)] * 3,
        (generator.ROUTE_PLANS[5],) * 3,
    )
    assert not generator._matches_profile(
        forced_candidate,
        parameters["minimum_target_sum"],
        parameters["maximum_target_sum"],
        parameters["dice_count"],
    )

    public, truth = generator.generate(task, "top-face-forced-exhaustion")
    full_public, full_truth = generator.generate(full_task, "top-face-forced-exhaustion")
    final_tops = [plan["final_top"] for plan in truth["solution_plans"]]
    assert parameters["minimum_target_sum"] <= public["target_sum"] <= parameters["maximum_target_sum"]
    assert public["target_sum"] == sum(final_tops)
    assert len(set(final_tops)) >= 3
    assert public["target_sum"] != 18
    assert without_control_identity(public) == without_control_identity(full_public)
    assert without_control_identity(truth) == without_control_identity(full_truth)
    payload = _top_face_dice_payload(public, truth, "simplified", grader)
    assert grader.grade(payload, truth, public)["passed"] is True
    full_payload = _top_face_dice_payload(full_public, full_truth, "full", grader)
    assert grader.grade(full_payload, full_truth, full_public)["passed"] is True


def test_top_face_dice_l5_matches_head_generator_including_exhaustion(monkeypatch) -> None:
    env_name = "top_face_dice_arithmetic_env"
    controls = controls_for(env_name)
    historical_source = subprocess.run(
        [
            "git",
            "show",
            "HEAD:benchmarks/weird_captcha_gym/shared_scripts/incubator_generators/top_face_dice_arithmetic.py",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    historical = types.ModuleType("head_top_face_dice_generator")
    exec(compile(historical_source, "HEAD:top_face_dice_arithmetic.py", "exec"), historical.__dict__)
    current = load_module(
        "controlled_top_face_dice_generator_head_comparison",
        BENCHMARK / "shared_scripts" / "incubator_generators" / "top_face_dice_arithmetic.py",
    )
    grader = load_module(
        "controlled_top_face_dice_grader_head_comparison",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "top_face_dice_arithmetic.py",
    )
    historical_task = json.loads(
        subprocess.run(
            [
                "git",
                "show",
                "HEAD:benchmarks/weird_captcha_gym/environments/top_face_dice_arithmetic_env/tasks/top_face_dice_arithmetic_seed_0001/task.json",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    controlled_task = copy.deepcopy(historical_task)
    controlled_task["_control_condition"] = {
        "difficulty": 5,
        "interaction": "simplified",
        "real_time": "live",
        "difficulty_parameters": copy.deepcopy(controls["difficulty"]["5"]["parameters"]),
    }
    materialized_l5_task = SETUP.task_with_control_condition(task_for_level(env_name, 5, "simplified"))

    def without_condition(value: dict) -> dict:
        result = copy.deepcopy(value)
        result.pop("control_condition", None)
        return result

    def without_materialized_identity(value: dict) -> dict:
        result = without_condition(value)
        result.pop("task_id", None)
        result.pop("challenge_id", None)
        return result

    for seed in ("top-face-baseline-a", "top-face-baseline-b"):
        historical_public, historical_truth = historical.generate(historical_task, seed)
        uncontrolled_public, uncontrolled_truth = current.generate(historical_task, seed)
        controlled_public, controlled_truth = current.generate(controlled_task, seed)
        materialized_public, materialized_truth = current.generate(materialized_l5_task, seed)
        assert uncontrolled_public == historical_public
        assert uncontrolled_truth == historical_truth
        assert without_condition(controlled_public) == historical_public
        assert without_condition(controlled_truth) == historical_truth
        assert without_materialized_identity(materialized_public) == without_materialized_identity(historical_public)
        assert without_materialized_identity(materialized_truth) == without_materialized_identity(historical_truth)
        assert "orientation_visibility" not in controlled_public

    class ExhaustedLotRng:
        def shuffle(self, _items) -> None:
            return None

        def randint(self, lower: int, _upper: int) -> int:
            return lower

        def choice(self, options):
            values = tuple(options)
            if values == current.ROUTE_PLANS:
                return current.ROUTE_PLANS[5]
            return values[0]

    monkeypatch.setattr(historical.random, "Random", lambda _seed: ExhaustedLotRng())
    monkeypatch.setattr(current.random, "Random", lambda _seed: ExhaustedLotRng())
    monkeypatch.setattr(historical, "_initial_orientation", lambda _rng: dict(historical.CANONICAL))
    monkeypatch.setattr(current, "_initial_orientation", lambda _rng: dict(current.CANONICAL))
    historical_public, historical_truth = historical.generate(historical_task, "top-face-l5-head-exhaustion")
    uncontrolled_public, uncontrolled_truth = current.generate(historical_task, "top-face-l5-head-exhaustion")
    controlled_public, controlled_truth = current.generate(controlled_task, "top-face-l5-head-exhaustion")
    materialized_public, materialized_truth = current.generate(materialized_l5_task, "top-face-l5-head-exhaustion")
    assert uncontrolled_public == historical_public
    assert uncontrolled_truth == historical_truth
    assert without_condition(controlled_public) == historical_public
    assert without_condition(controlled_truth) == historical_truth
    assert without_materialized_identity(materialized_public) == without_materialized_identity(historical_public)
    assert without_materialized_identity(materialized_truth) == without_materialized_identity(historical_truth)
    assert controlled_public["target_sum"] == 24
    assert "orientation_visibility" not in controlled_public
    payload = _top_face_dice_payload(controlled_public, controlled_truth, "simplified", grader)
    assert grader.grade(payload, controlled_truth, controlled_public)["passed"] is True


def _grillmaster_payload(
    public: dict,
    truth: dict,
    source: str,
    *,
    start_times: dict[str, float] | None = None,
) -> dict:
    targets = truth["targets"]
    starts = start_times or {
        food_id: index * 20.0
        for index, food_id in enumerate(targets)
    }
    actions = []
    for food_id in targets:
        actions.append({
            "sequence": len(actions) + 1,
            "kind": "start",
            "food_id": food_id,
            "input_source": source,
            "t_ms": starts[food_id],
        })
    serves = sorted(
        (
            starts[food_id] + float(target["target_ms"]),
            food_id,
        )
        for food_id, target in targets.items()
    )
    for timestamp, food_id in serves:
        actions.append({
            "sequence": len(actions) + 1,
            "kind": "serve",
            "food_id": food_id,
            "input_source": source,
            "t_ms": timestamp,
        })
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "durations_ms": {
            food_id: target["target_ms"]
            for food_id, target in targets.items()
        },
        "actions": actions,
    }


def _server_attested_grillmaster_payload(
    public: dict,
    truth: dict,
    source: str,
    *,
    start_times: dict[str, float] | None = None,
) -> dict:
    witness_module = load_module(
        f"grillmaster_witness_fixture_{public['challenge_id']}",
        BENCHMARK / "shared_runtime" / "server" / "grillmaster_witness.py",
    )
    client_claim = _grillmaster_payload(
        public,
        truth,
        source,
        start_times=start_times,
    )
    surface = {
        "food_drag": "html_drag_drop",
        "grill_proxy_controls": "selection_plus_proxy_button",
    }[source]
    witnessed_route = {
        "food_drag": "full_drop",
        "grill_proxy_controls": "simplified_proxy",
    }[source]
    actions = [
        {
            "sequence": action["sequence"],
            "kind": action["kind"],
            "food_id": action["food_id"],
            "input_source": action["input_source"],
            "event_surface": surface,
            "witnessed_route": witnessed_route,
            "task_time_ms": action["t_ms"],
            "server_received_wall_ns": 1_000_000 + action["sequence"],
            "gesture_created_wall_ns": 500_000 + action["sequence"],
            "gesture_evidence_sha256": f"gesture-{action['sequence']}",
            "action_evidence_sha256": f"action-{action['sequence']}",
        }
        for action in client_claim["actions"]
    ]
    key = witness_module._generate_key(public["challenge_id"])
    public_key = witness_module._public_key(key)
    truth[witness_module.PUBLIC_KEY_FIELD] = public_key
    interaction = (
        (truth.get("control_condition") or {}).get("interaction")
        or "full"
    )
    witness = {
        "version": 1,
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction": interaction,
        "clock_source": "server_active_task_clock_v1",
        "public_key": public_key,
        "actions": actions,
        "finalized_wall_ns": 2_000_000,
    }
    modulus = int(key["n_hex"], 16)
    private = int(key["d_hex"], 16)
    size = (modulus.bit_length() + 7) // 8
    encoded = witness_module._encoded_message(witness, size)
    signature = pow(int.from_bytes(encoded, "big"), private, modulus)
    witness["signature_hex"] = signature.to_bytes(size, "big").hex()
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "trusted_witness": witness,
    }


def test_grillmaster_profiles_change_concurrency_and_response_precision() -> None:
    controls = controls_for("parallel_grillmaster_env")
    levels = generated_levels("parallel_grillmaster_env", "grillmaster-profile-contracts")
    assert [len(public["foods"]) for public, _truth in levels] == [3, 6, 6, 6, 8]
    assert [
        public["control_condition"]["difficulty_parameters"]["parallel_start_count"]
        for public, _truth in levels
    ] == [1, 1, 3, 6, 8]
    assert [
        public["control_condition"]["difficulty_parameters"]["parallel_start_window_ms"]
        for public, _truth in levels
    ] == [None, None, 2600, 3000, 3200]
    for level, (public, truth) in enumerate(levels, start=1):
        parameters = controls["difficulty"][str(level)]["parameters"]
        assert {
            target["target_ms"]
            for target in truth["targets"].values()
        } == set(parameters["target_times_ms"])
        assert {
            target["tolerance_ms"]
            for target in truth["targets"].values()
        } <= set(parameters["tolerance_ms_values"])
        assert public["prompt"] == controls["difficulty"][str(level)]["natural_language"]


def test_grillmaster_modes_share_every_generated_world_and_challenge() -> None:
    for seed_index in range(4):
        seed = f"grillmaster-interaction-pair-{seed_index}"
        for level in range(1, 6):
            simplified_public, simplified_truth = SETUP.generate_task_state(
                task_for_level("parallel_grillmaster_env", level, "simplified"),
                seed,
            )
            full_public, full_truth = SETUP.generate_task_state(
                task_for_level("parallel_grillmaster_env", level, "full"),
                seed,
            )
            assert simplified_public["challenge_id"] == full_public["challenge_id"]
            assert without_control_identity(simplified_public) == without_control_identity(full_public)
            assert without_control_identity(simplified_truth) == without_control_identity(full_truth)


def test_grillmaster_grader_requires_server_attestation_for_every_condition() -> None:
    grader = load_module(
        "controlled_grillmaster_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "parallel_grillmaster.py",
    )
    helpers = load_module(
        "controlled_grillmaster_verifier",
        BENCHMARK / "shared_runtime" / "verifier_helpers.py",
    )
    sources = {
        "simplified": "grill_proxy_controls",
        "full": "food_drag",
    }
    for level in range(1, 6):
        for interaction, source in sources.items():
            public, truth = SETUP.generate_task_state(
                task_for_level("parallel_grillmaster_env", level, interaction),
                f"grillmaster-grade-d{level}-{interaction}",
            )
            synthetic = _grillmaster_payload(public, truth, source)
            rejected_synthetic = grader.grade(synthetic, truth, public)
            assert rejected_synthetic == {
                "graded": True,
                "passed": False,
                "feedback": "server-witnessed grill actions are missing",
            }
            payload = _server_attested_grillmaster_payload(
                public,
                truth,
                source,
            )
            accepted = grader.grade(payload, truth, public)
            assert accepted["passed"] is True, accepted
            accepted_verifier = helpers.verify_external_mechanic(
                {
                    "result": payload,
                    "ground_truth": truth,
                    "public_state": public,
                },
                "parallel_grillmaster",
            )
            assert accepted_verifier["passed"] is True, accepted_verifier
            forged = copy.deepcopy(payload)
            forged["trusted_witness"]["actions"][0]["input_source"] = sources[
                "full" if interaction == "simplified" else "simplified"
            ]
            rejected = grader.grade(forged, truth, public)
            assert rejected["passed"] is False
            assert rejected["feedback"] == "server witness signature is invalid"
            rejected_verifier = helpers.verify_external_mechanic(
                {
                    "result": forged,
                    "ground_truth": truth,
                    "public_state": public,
                },
                "parallel_grillmaster",
            )
            assert rejected_verifier == {
                "passed": False,
                "score": 0,
                "feedback": "server witness signature is invalid",
            }


def test_grillmaster_concurrent_start_rule_is_enforced() -> None:
    grader = load_module(
        "controlled_grillmaster_parallel_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "parallel_grillmaster.py",
    )
    public, truth = SETUP.generate_task_state(
        task_for_level("parallel_grillmaster_env", 3, "full"),
        "grillmaster-concurrent-start-rejection",
    )
    food_ids = list(truth["targets"])
    start_times = {
        food_id: timestamp
        for food_id, timestamp in zip(food_ids, (0, 2701, 2702, 2703, 2704, 2705))
    }
    payload = _server_attested_grillmaster_payload(
        public,
        truth,
        "food_drag",
        start_times=start_times,
    )
    decision = grader.grade(payload, truth, public)
    assert decision["passed"] is False
    assert "first 3 start spread 2702ms/2600ms" in decision["feedback"]


def test_grillmaster_server_witness_derives_interaction_from_endpoint_route(
    tmp_path: Path,
    monkeypatch,
) -> None:
    witness = load_module(
        "grillmaster_server_witness_routes",
        BENCHMARK / "shared_runtime" / "server" / "grillmaster_witness.py",
    )
    public, truth = SETUP.generate_task_state(
        task_for_level("parallel_grillmaster_env", 2, "full"),
        "grillmaster-server-route-witness",
    )
    (tmp_path / "ground_truth.json").write_text(
        json.dumps(truth),
        encoding="utf-8",
    )
    monkeypatch.setenv("WEIRD_CAPTCHA_TIME_MODE", "paused")
    monkeypatch.setenv("WEIRD_CAPTCHA_START_PAUSED", "1")
    food_id = next(iter(truth["targets"]))
    gesture_payload = {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "food_id": food_id,
        "is_trusted": True,
        "gesture_kind": "drag",
        "event_evidence": {
            "start_point": [100, 100],
        },
    }
    rejected, status = witness.begin_gesture(
        tmp_path,
        gesture_payload,
        truth,
        "simplified_selection",
    )
    assert status == 400
    assert rejected["error"] == "gesture surface does not match interaction"

    accepted, status = witness.begin_gesture(
        tmp_path,
        gesture_payload,
        truth,
        "full_drag_begin",
    )
    assert status == 200
    updated_truth = json.loads(
        (tmp_path / "ground_truth.json").read_text(encoding="utf-8")
    )
    action_payload = {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "food_id": food_id,
        "kind": "start",
        "destination": "grill",
        "gesture_token": accepted["gesture_token"],
        "input_source": "grill_proxy_controls",
        "event_evidence": {
            "drop_zone": "grill",
            "start_point": [100, 100],
            "end_point": [500, 300],
        },
    }
    recorded, status = witness.record_action(
        tmp_path,
        action_payload,
        updated_truth,
        "full_drop",
    )
    assert status == 200
    assert recorded["witness_action"]["input_source"] == "food_drag"
    assert recorded["witness_action"]["event_surface"] == "html_drag_drop"
    assert recorded["witness_action"]["witnessed_route"] == "full_drop"


def test_grillmaster_original_signed_result_uses_strict_exported_verifier() -> None:
    grader = load_module(
        "original_signed_grillmaster_grader",
        BENCHMARK
        / "shared_runtime"
        / "server"
        / "incubator_graders"
        / "parallel_grillmaster.py",
    )
    helpers = load_module(
        "original_signed_grillmaster_verifier",
        BENCHMARK / "shared_runtime" / "verifier_helpers.py",
    )
    task = base_task_for("parallel_grillmaster_env", "parallel_grillmaster")
    public, truth = SETUP.generate_task_state(
        task,
        "grillmaster-original-signed-verifier",
    )
    payload = _server_attested_grillmaster_payload(
        public,
        truth,
        "food_drag",
    )

    decision = grader.grade(payload, truth, public)
    assert decision["passed"] is True, decision
    verified = helpers.verify_parallel_grillmaster(
        {
            "result": payload,
            "ground_truth": truth,
            "public_state": public,
        }
    )
    assert verified == {
        "passed": True,
        "score": 100,
        "feedback": "server-attested; foods 6/6; sequential starts allowed",
    }


def _code_to_diagram_payload(public: dict, truth: dict, input_source: str) -> dict:
    wires = [dict(edge) for edge in truth["expected_edges"]]
    events = [
        {
            "sequence": index,
            "action": "connect",
            "from_port": wire["from_port"],
            "label": wire["label"],
            "to_node": wire["to_node"],
            "input_source": input_source,
        }
        for index, wire in enumerate(wires, start=1)
    ]
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "probe_runs": copy.deepcopy(truth["expected_probe_runs"]),
        "wire_events": events,
        "final_wires": wires,
    }


def test_code_to_diagram_profiles_change_the_active_controller_problem() -> None:
    controls = controls_for("code_to_diagram_captcha_env")
    levels = generated_levels("code_to_diagram_captcha_env", "code-to-diagram-profile-contracts")
    assert [len(public["nodes"]) for public, _truth in levels] == [6, 7, 8, 9, 11]
    assert [len(public["probe_inputs"]) for public, _truth in levels] == [2, 2, 4, 4, 8]
    assert [public["expected_edge_count"] for public, _truth in levels] == [6, 7, 9, 10, 13]
    assert [public.get("transient_erase_ms", 720) for public, _truth in levels] == [1400, 1100, 900, 720, 500]
    for level, (public, truth) in enumerate(levels, start=1):
        parameters = controls["difficulty"][str(level)]["parameters"]
        assert public["control_condition"]["difficulty_parameters"] == parameters
        assert truth["control_condition"]["difficulty_parameters"] == parameters
        assert {len(run["steps"]) for run in truth["expected_probe_runs"]} == {
            parameters["trace_step_count"]
        }
        assert len(truth["expected_edges"]) == parameters["edge_count"]


def test_code_to_diagram_level_four_preserves_the_original_controller_across_seeds() -> None:
    original_task = base_task_for("code_to_diagram_captcha_env", "code_to_diagram_captcha")
    baseline_task = task_for_level("code_to_diagram_captcha_env", 4, "full")
    for seed in ("code-to-diagram-baseline-a", "code-to-diagram-baseline-b", "code-to-diagram-baseline-c"):
        original_public, original_truth = SETUP.generate_task_state(original_task, seed)
        baseline_public, baseline_truth = SETUP.generate_task_state(baseline_task, seed)
        assert baseline_public["challenge_id"] == original_public["challenge_id"]
        assert without_control_identity(baseline_public) == without_control_identity(original_public)
        assert without_control_identity(baseline_truth) == without_control_identity(original_truth)


def test_code_to_diagram_interaction_pairs_share_the_controller_and_grader_binds_the_surface() -> None:
    grader = load_module(
        "controlled_code_to_diagram_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "code_to_diagram_captcha.py",
    )
    sources = {"simplified": "port_click_pair", "full": "port_drag"}
    for level in range(1, 6):
        simplified_public, simplified_truth = SETUP.generate_task_state(
            task_for_level("code_to_diagram_captcha_env", level, "simplified"),
            f"code-to-diagram-pair-d{level}",
        )
        full_public, full_truth = SETUP.generate_task_state(
            task_for_level("code_to_diagram_captcha_env", level, "full"),
            f"code-to-diagram-pair-d{level}",
        )
        assert simplified_public["challenge_id"] == full_public["challenge_id"]
        assert without_control_identity(simplified_public) == without_control_identity(full_public)
        assert without_control_identity(simplified_truth) == without_control_identity(full_truth)
        for interaction, public, truth in (
            ("simplified", simplified_public, simplified_truth),
            ("full", full_public, full_truth),
        ):
            accepted = grader.grade(_code_to_diagram_payload(public, truth, sources[interaction]), truth, public)
            assert accepted["passed"] is True, accepted
            wrong = "full" if interaction == "simplified" else "simplified"
            rejected = grader.grade(_code_to_diagram_payload(public, truth, sources[wrong]), truth, public)
            assert rejected["passed"] is False
            assert "wrong interaction input" in rejected["feedback"]


def _clockwork_payload(grader, public: dict, truth: dict, input_source: str) -> dict:
    controls = truth["controls"]
    qualification = truth["qualification"]
    roles = truth["roles"]
    nominal = truth["solution"]["nominal_action_times"]
    events: list[dict] = []
    sequence = 0

    def push(timestamp: int, **event: object) -> None:
        nonlocal sequence
        sequence += 1
        events.append({"seq": sequence, "t_ms": timestamp, **event})

    def position_at(knots: list[tuple[int, dict]], local: int) -> dict:
        for (before_time, before), (after_time, after) in zip(knots, knots[1:]):
            if before_time <= local <= after_time:
                span = after_time - before_time
                amount = 0 if span == 0 else (local - before_time) / span
                return {
                    "x": before["x"] + (after["x"] - before["x"]) * amount,
                    "y": before["y"] + (after["y"] - before["y"]) * amount,
                }
        return dict(knots[-1][1])

    push(0, type="challenge_start")
    recordings: list[dict] = []
    clock = 0
    for slot, (role, action_times) in enumerate(zip(roles, nominal)):
        start = clock
        guide = role["guide"]
        required = role["required_actions"]
        duration = int(controls["record_duration_ms"])
        knots = [(0, guide[0])]
        for index, action in enumerate(required):
            knots.append((int(action_times[action]), guide[index]))
        knots.append((duration, guide[-1]))
        knots = sorted(knots, key=lambda item: item[0])
        action_times_by_kind = {int(action_times[action]): (index, action) for index, action in enumerate(required)}
        # The browser records every visible station action as part of the path, even
        # when it falls between its regular pointer samples.  Preserve those knots
        # while omitting nearby regular samples so the transcript still satisfies
        # the grader's minimum 30 ms sample spacing.
        anchor_times = {0, duration, *action_times_by_kind}
        sample_times = set(anchor_times)
        for local in range(0, duration + 1, int(controls["sample_interval_ms"])):
            if all(abs(local - anchor) >= 30 for anchor in anchor_times):
                sample_times.add(local)
        sample_times = sorted(sample_times)
        push(start, type="record_start", slot=slot, pointer=position_at(knots, 0))
        samples = []
        action_items = []
        for local in sample_times:
            position = position_at(knots, local)
            samples.append({"local_t_ms": local, "position": (position["x"], position["y"])})
            push(start + local, type="record_sample", slot=slot, local_t_ms=local, position=position)
            if local in action_times_by_kind:
                index, action = action_times_by_kind[local]
                action_position = dict(guide[index])
                action_items.append({"local_t_ms": local, "position": (action_position["x"], action_position["y"]), "action": action})
                push(start + local, type="record_action", slot=slot, local_t_ms=local, position=action_position, action=action, input_source=input_source)
        travel = sum(
            math.hypot(after["position"][0] - before["position"][0], after["position"][1] - before["position"][1])
            for before, after in zip(samples, samples[1:])
        )
        recordings.append({"samples": samples, "actions": action_items, "duration_ms": duration, "travel": round(travel + 1e-12, 2)})
        push(start + duration, type="record_end", slot=slot, local_t_ms=duration, accepted=True)
        clock += duration + 50
    phases = list(truth["solution"]["phases_ms"])
    for slot, phase in enumerate(phases):
        push(clock, type="phase_edit", slot=slot, from_ms=0, to_ms=phase)
        clock += 1
    cycle_start = clock + 5
    push(cycle_start, type="cycle_start", phases_ms=phases)
    for local in range(0, int(controls["loop_duration_ms"]), int(controls["cycle_sample_interval_ms"])):
        passport = grader._simulate(recordings, phases, local, truth["stations"], truth["conveyor"], qualification)
        push(cycle_start + local, type="cycle_sample", cycle_t_ms=local, passport=passport)
    outcome = grader._simulate(recordings, phases, int(controls["loop_duration_ms"]), truth["stations"], truth["conveyor"], qualification)
    push(cycle_start + int(controls["loop_duration_ms"]), type="cycle_end", client_delivered=outcome["delivered"], passport=outcome)
    push(cycle_start + int(controls["loop_duration_ms"]) + 1, type="verify", claimed_delivered=outcome["delivered"])
    summaries = [
        {
            "slot": slot,
            "samples": len(recording["samples"]),
            "actions": [action["action"] for action in recording["actions"]],
            "duration_ms": recording["duration_ms"],
            "travel": recording["travel"],
        }
        for slot, recording in enumerate(recordings)
    ]
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "events": events,
        "final_state": {
            "recordings": summaries,
            "revisions": [1] * len(roles),
            "phases_ms": phases,
            "record_failures": 0,
            "phase_edits": len(roles),
            "cycle_attempts": 1,
            "successful_cycles": 1,
            "rewind_count": 0,
            "last_outcome": outcome,
        },
    }


def test_clockwork_customs_profiles_change_coupled_control_and_bind_input_surface() -> None:
    controls = controls_for("clockwork_doppelganger_customs_env")
    grader = load_module(
        "controlled_clockwork_customs_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "clockwork_doppelganger_customs.py",
    )
    expected_sources = {"simplified": "proxy_control", "full": "direct_station"}
    expected_role_counts = [1, 2, 3, 3, 3]
    expected_phase_steps = [100, 75, 100, 50, 25]
    for level, (expected_roles, expected_step) in enumerate(zip(expected_role_counts, expected_phase_steps), start=1):
        for interaction, expected_source in expected_sources.items():
            public, truth = SETUP.generate_task_state(
                task_for_level("clockwork_doppelganger_customs_env", level, interaction),
                f"clockwork-controls-d{level}",
            )
            parameters = controls["difficulty"][str(level)]["parameters"]
            assert len(public["roles"]) == len(truth["roles"]) == expected_roles
            assert public["controls"]["phase_step_ms"] == expected_step
            assert public["controls"]["record_duration_ms"] == parameters["record_duration_ms"]
            assert public["controls"]["loop_duration_ms"] in parameters["loop_duration_ms_values"]
            assert public["conveyor"]["track_y"] in parameters["track_y_values"]
            assert public["conveyor"]["catch_time_ms"] in parameters["catch_time_ms_values"]
            assert public["conveyor"]["speed_px_per_ms"] in parameters["speed_px_per_ms_values"]
            assert truth["solution"]["handoff_gap_ms"] == parameters["handoff_gap_ms"]
            assert public["qualification"] == {
                key: parameters[key] for key in public["qualification"]
            }
            assert public["control_condition"]["interaction"] == interaction
            accepted = grader.grade(_clockwork_payload(grader, public, truth, expected_source), truth, public)
            assert accepted["passed"] is True, accepted
            wrong_source = expected_sources["full" if interaction == "simplified" else "simplified"]
            rejected = grader.grade(_clockwork_payload(grader, public, truth, wrong_source), truth, public)
            assert rejected["passed"] is False
            assert rejected["feedback"] == "customs action uses the wrong interaction input"

    public, truth = SETUP.generate_task_state(
        task_for_level("clockwork_doppelganger_customs_env", 4, "simplified"),
        "clockwork-contract-binding",
    )
    payload = _clockwork_payload(grader, public, truth, "proxy_control")
    bad_profiles = {
        "loop_duration_ms_values": [9999],
        "track_y_values": [-1],
        "catch_time_ms_values": [-1],
        "speed_px_per_ms_values": [-1.0],
        "handoff_gap_ms": -1,
    }
    for key, value in bad_profiles.items():
        changed_public = copy.deepcopy(public)
        changed_truth = copy.deepcopy(truth)
        changed_public["control_condition"]["difficulty_parameters"][key] = value
        changed_truth["control_condition"]["difficulty_parameters"][key] = value
        rejected = grader.grade(payload, changed_truth, changed_public)
        assert rejected["passed"] is False
        assert rejected["feedback"] == "customs difficulty condition differs from generated contract"


def _fake_desktop_simplified_payload(public: dict, truth: dict) -> dict:
    """One clean selected-file proxy transcript for the preserved L3 world."""

    events: list[dict] = []

    def event(kind: str, **values) -> None:
        events.append({"sequence": len(events) + 1, "kind": kind, **values})

    mappings = truth["mapping_sequence"]
    event("proxy", action="close_interceptor", input_source="automation_panel")
    event("proxy", action="move_vault", input_source="automation_panel")
    event("proxy", action="select_file", file_id=truth["target_file_ids"][0], input_source="automation_panel")
    event("proxy", action="transfer_selected", input_source="automation_panel")
    event("boundary", from_=0, to=1, reason="keyfile_1_loaded", mapping=mappings[1], input_source="automation_panel")
    # Python cannot use `from` as a keyword, but the replay expects that exact
    # browser field name.
    events[-1]["from"] = events[-1].pop("from_")
    event("proxy", action="move_verifier", input_source="automation_panel")
    event("proxy", action="select_file", file_id=truth["target_file_ids"][1], input_source="automation_panel")
    event("proxy", action="transfer_selected", input_source="automation_panel")
    event("boundary", from_=1, to=2, reason="keyfile_2_loaded", mapping=mappings[2], input_source="automation_panel")
    events[-1]["from"] = events[-1].pop("from_")
    event("proxy", action="arm_manual_control", input_source="automation_panel")

    windows = {item["id"]: dict(item) for item in truth["initial_windows"]}
    windows["interceptor"]["closed"] = True
    width, height = truth["desktop"]["width"], truth["desktop"]["height"]
    windows["vault"]["x"] = max(0, min(width - windows["vault"]["width"], windows["vault"]["x"] + 70))
    windows["vault"]["y"] = max(0, min(height - windows["vault"]["height"], windows["vault"]["y"] - 20))
    windows["vault"]["z"] = 5
    windows["verifier"]["x"] = max(0, min(width - windows["verifier"]["width"], windows["verifier"]["x"] - 55))
    windows["verifier"]["y"] = max(0, min(height - windows["verifier"]["height"], windows["verifier"]["y"] + 28))
    windows["verifier"]["z"] = 6
    window_state = [
        {key: window[key] for key in ("id", "x", "y", "z", "closed")}
        for window in sorted(windows.values(), key=lambda item: item["id"])
    ]
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction": "simplified",
        "events": events,
        "window_state": window_state,
        "boundary_index": 2,
        "active_mapping": mappings[2],
        "loaded_file_ids": truth["target_file_ids"],
        "armed": True,
        "move_count": 2,
        "closed_count": 1,
        "z_order_changes": 2,
        "file_drag_moves": 2,
        "moved_window_ids": ["vault", "verifier"],
        "reset_count": 0,
    }


def test_fake_desktop_profiles_preserve_l3_and_bind_proxy_transcripts() -> None:
    controls = controls_for("fake_desktop_automation_inversion_env")
    grader = load_module(
        "controlled_fake_desktop_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "fake_desktop_automation_inversion.py",
    )
    original_task = base_task_for("fake_desktop_automation_inversion_env", "fake_desktop_automation_inversion")
    baseline_task = task_for_level("fake_desktop_automation_inversion_env", 3, "full")
    for seed in ("fake-desktop-baseline-a", "fake-desktop-baseline-b", "fake-desktop-baseline-c"):
        original_public, original_truth = SETUP.generate_task_state(original_task, seed)
        baseline_public, baseline_truth = SETUP.generate_task_state(baseline_task, seed)
        assert baseline_public["challenge_id"] == original_public["challenge_id"]
        assert without_control_identity(baseline_public) == without_control_identity(original_public)
        assert without_control_identity(baseline_truth) == without_control_identity(original_truth)

    expected_profiles = {
        1: (1, 3, 2, []),
        2: (2, 3, 3, []),
        3: (2, 4, 3, ["vault", "verifier"]),
        4: (3, 5, 4, ["vault", "verifier"]),
        5: (4, 6, 5, ["vault", "verifier"]),
    }
    for level, expected in expected_profiles.items():
        public, truth = SETUP.generate_task_state(
            task_for_level("fake_desktop_automation_inversion_env", level, "full"),
            f"fake-desktop-d{level}",
        )
        assert (
            len(public["target_filenames"]),
            len(public["files"]),
            len(public["mapping_sequence"]),
            public["required_moved_window_ids"],
        ) == expected
        assert public["control_condition"]["difficulty_parameters"] == controls["difficulty"][str(level)]["parameters"]
        simplified_public, simplified_truth = SETUP.generate_task_state(
            task_for_level("fake_desktop_automation_inversion_env", level, "simplified"),
            f"fake-desktop-d{level}",
        )
        assert public["challenge_id"] == simplified_public["challenge_id"]
        assert without_control_identity(public) == without_control_identity(simplified_public)
        assert without_control_identity(truth) == without_control_identity(simplified_truth)

    for index in range(100):
        public, _truth = SETUP.generate_task_state(
            task_for_level("fake_desktop_automation_inversion_env", 5, "full"),
            f"fake-desktop-l5-final-remap-{index}",
        )
        mappings = public["mapping_sequence"]
        assert len(set(mappings[:4])) == 4
        assert mappings[-1] != mappings[-2]

    public, truth = SETUP.generate_task_state(
        task_for_level("fake_desktop_automation_inversion_env", 3, "simplified"),
        "fake-desktop-interaction-binding",
    )
    payload = _fake_desktop_simplified_payload(public, truth)
    accepted = grader.grade(payload, truth, public)
    assert accepted["passed"] is True, accepted

    wrong_mode = copy.deepcopy(payload)
    wrong_mode["interaction"] = "full"
    rejected = grader.grade(wrong_mode, truth, public)
    assert rejected["passed"] is False
    assert rejected["feedback"] == "transcript belongs to the other interaction mode"

    full_public, full_truth = SETUP.generate_task_state(
        task_for_level("fake_desktop_automation_inversion_env", 3, "full"),
        "fake-desktop-interaction-binding",
    )
    assert full_public["challenge_id"] == public["challenge_id"]
    rejected = grader.grade(payload, full_truth, full_public)
    assert rejected["passed"] is False
    assert rejected["feedback"] == "task identity mismatch"
    cross_mode = copy.deepcopy(payload)
    cross_mode["task_id"] = full_public["task_id"]
    rejected = grader.grade(cross_mode, full_truth, full_public)
    assert rejected["passed"] is False
    assert rejected["feedback"] == "transcript belongs to the other interaction mode"

    wrong_source = copy.deepcopy(payload)
    wrong_source["events"][0]["input_source"] = "remote_pointer"
    rejected = grader.grade(wrong_source, truth, public)
    assert rejected["passed"] is False
    assert rejected["feedback"] == "proxy action used the wrong input source"

    wrong_selection = copy.deepcopy(payload)
    decoy = next(file_item["id"] for file_item in truth["files"] if file_item["id"] not in truth["target_file_ids"])
    first_selection = next(event for event in wrong_selection["events"] if event.get("action") == "select_file")
    first_selection["file_id"] = decoy
    rejected = grader.grade(wrong_selection, truth, public)
    assert rejected["passed"] is False
    assert rejected["feedback"] == "selected keyfile is not the requested keyfile"


def _modifier_stack_payload(public: dict, truth: dict, interaction: str) -> dict:
    """Build one L1 trace with a complete, timing-sensitive rail hold."""

    assert interaction in {"full", "simplified"}
    artifact = truth["artifacts"][0]
    requirements = truth["requirements"]
    source = "direct_canvas" if interaction == "full" else "proxy_controls"
    events: list[dict] = [{
        "sequence": 1,
        "kind": "playback_complete",
        "t_ms": 4_500,
        "artifact_id": artifact["id"],
        "duration_ms": artifact["playback_ms"],
    }]
    timestamp = 4_510
    rack_by_token = {item["token_id"]: item for item in artifact["rack_rects"]}
    for slot, token in zip(truth["slots"], reversed(artifact["stack"])):
        if interaction == "simplified":
            events.append({
                "sequence": len(events) + 1,
                "kind": "proxy_place",
                "t_ms": timestamp,
                "input_source": source,
                "token_id": token["id"],
                "slot_index": slot["index"],
            })
            timestamp += 10
        else:
            rack = rack_by_token[token["id"]]
            start = [rack["x"] + rack["width"] / 2, rack["y"] + rack["height"] / 2]
            end = [slot["x"] + slot["width"] / 2, slot["y"] + slot["height"] / 2]
            events.append({"sequence": len(events) + 1, "kind": "chip_down", "t_ms": timestamp, "input_source": source, "token_id": token["id"], "point": start})
            for move in range(1, requirements["minimum_chip_moves"] + 1):
                amount = move / requirements["minimum_chip_moves"]
                timestamp += 10
                events.append({"sequence": len(events) + 1, "kind": "chip_move", "t_ms": timestamp, "input_source": source, "token_id": token["id"], "point": [start[0] + (end[0] - start[0]) * amount, start[1] + (end[1] - start[1]) * amount], "elapsed_ms": move * 20})
            timestamp += 10
            events.append({"sequence": len(events) + 1, "kind": "chip_up", "t_ms": timestamp, "input_source": source, "token_id": token["id"], "point": end, "duration_ms": requirements["minimum_chip_drag_ms"], "slot_index": slot["index"], "accepted": True})
            timestamp += 10
        events.append({
            "sequence": len(events) + 1,
            "kind": "invert",
            "t_ms": timestamp,
            "input_source": source,
            "token_id": token["id"],
            "before": False,
            "after": True,
        })
        timestamp += 10
    rail = truth["rail"]
    start_time = timestamp
    events.append({"sequence": len(events) + 1, "kind": "rail_start", "t_ms": timestamp, "input_source": source, "point": rail["start"]})
    for sample in range(1, requirements["minimum_rail_samples"] + 1):
        timestamp += 10
        amount = sample / requirements["minimum_rail_samples"]
        events.append({"sequence": len(events) + 1, "kind": "rail_sample", "t_ms": timestamp, "input_source": source, "point": [rail["start"][0] + (rail["end"][0] - rail["start"][0]) * amount, rail["start"][1]], "elapsed_ms": sample * 20})
    timestamp = max(timestamp + 10, start_time + requirements["minimum_rail_ms"])
    events.append({"sequence": len(events) + 1, "kind": "rail_end", "t_ms": timestamp, "input_source": source, "point": rail["end"], "duration_ms": requirements["minimum_rail_ms"], "accepted": True})
    events.append({"sequence": len(events) + 1, "kind": "seal", "t_ms": timestamp + 10, "input_source": source})
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction_mode": interaction,
        "events": events,
        "completed_ids": [artifact["id"]],
        "replay_count": 0,
        "reset_count": 0,
        "rail_samples": requirements["minimum_rail_samples"],
        "seal_count": 1,
        "completed": True,
    }


def _resequenced(events: list[dict]) -> list[dict]:
    return [{**event, "sequence": index} for index, event in enumerate(events, start=1)]


def _rail_event(payload: dict, kind: str) -> dict:
    return next(event for event in payload["events"] if event["kind"] == kind)


def test_modifier_stack_controls_preserve_l3_and_bind_equivalent_rail_input() -> None:
    env_name = "modifier_stack_image_grid_env"
    mechanic = "modifier_stack_image_grid"
    controls = controls_for(env_name)
    assert controls["baseline"] == {"difficulty": 3, "interaction": "full", "real_time": "live"}
    original = base_task_for(env_name, mechanic)
    baseline = task_for_level(env_name, 3, "full")
    for seed in ("modifier-stack-baseline-a", "modifier-stack-baseline-b", "modifier-stack-baseline-c"):
        raw_public, raw_truth = SETUP.generate_task_state(original, seed)
        baseline_public, baseline_truth = SETUP.generate_task_state(baseline, seed)
        assert raw_public["challenge_id"] == baseline_public["challenge_id"]
        assert without_control_identity(raw_public) == without_control_identity(baseline_public)
        assert without_control_identity(raw_truth) == without_control_identity(baseline_truth)

    expected_shapes = {
        1: (1, 2, 1),
        2: (2, 2, 2),
        3: (3, 3, 3),
        4: (3, 3, 3),
        5: (3, 4, 4),
    }
    for level, (artifact_count, modifier_count, gate_count) in expected_shapes.items():
        full_public, full_truth = SETUP.generate_task_state(
            task_for_level(env_name, level, "full"), f"modifier-stack-pair-{level}"
        )
        simplified_public, simplified_truth = SETUP.generate_task_state(
            task_for_level(env_name, level, "simplified"), f"modifier-stack-pair-{level}"
        )
        assert len(full_public["artifacts"]) == artifact_count
        assert all(len(artifact["stack"]) == modifier_count for artifact in full_public["artifacts"])
        assert len(full_public["slots"]) == modifier_count
        assert len(full_public["rail"]["gate_x"]) == gate_count
        assert full_public["control_condition"]["difficulty_parameters"] == controls["difficulty"][str(level)]["parameters"]
        assert full_public["challenge_id"] == simplified_public["challenge_id"]
        assert without_control_identity(full_public) == without_control_identity(simplified_public)
        assert without_control_identity(full_truth) == without_control_identity(simplified_truth)
    assert controls["difficulty"]["3"]["parameters"]["show_inverse_template"] is True
    assert controls["difficulty"]["3"]["parameters"]["show_arrangement_oracle"] is True
    assert controls["difficulty"]["4"]["parameters"]["show_inverse_template"] is False
    assert controls["difficulty"]["4"]["parameters"]["show_arrangement_oracle"] is False

    grader = load_module(
        "controlled_modifier_stack_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "modifier_stack_image_grid.py",
    )
    for interaction in ("full", "simplified"):
        public, truth = SETUP.generate_task_state(
            task_for_level(env_name, 1, interaction), f"modifier-stack-rail-binding-{interaction}"
        )
        payload = _modifier_stack_payload(public, truth, interaction)
        accepted = grader.grade(payload, truth, public)
        assert accepted["passed"] is True, accepted
        assert accepted["feedback"].endswith(f"rail samples {truth['requirements']['minimum_rail_samples']}; inverse press terminal=True")

        wrong_mode = copy.deepcopy(payload)
        wrong_mode["interaction_mode"] = "simplified" if interaction == "full" else "full"
        rejected = grader.grade(wrong_mode, truth, public)
        assert rejected["passed"] is False
        assert rejected["feedback"] == "restoration transcript belongs to the other interaction mode"
        wrong_source = copy.deepcopy(payload)
        wrong_source["events"][1]["input_source"] = "proxy_controls" if interaction == "full" else "direct_canvas"
        rejected = grader.grade(wrong_source, truth, public)
        assert rejected["passed"] is False
        assert rejected["feedback"] == "event 2 uses the wrong interaction input"

        too_few = copy.deepcopy(payload)
        sample_positions = [index for index, event in enumerate(too_few["events"]) if event["kind"] == "rail_sample"]
        del too_few["events"][sample_positions[-1]]
        _rail_event(too_few, "rail_end")["accepted"] = False
        too_few["events"] = _resequenced(too_few["events"])
        too_few["rail_samples"] -= 1
        rejected = grader.grade(too_few, truth, public)
        assert rejected["passed"] is False
        assert "incomplete restoration rail" in rejected["feedback"]

        too_short = copy.deepcopy(payload)
        short_end = _rail_event(too_short, "rail_end")
        short_end["duration_ms"] = truth["requirements"]["minimum_rail_ms"] - 1
        short_end["accepted"] = False
        rejected = grader.grade(too_short, truth, public)
        assert rejected["passed"] is False
        assert "incomplete restoration rail" in rejected["feedback"]

        skips_gate = copy.deepcopy(payload)
        first_gate = truth["rail"]["gate_x"][0]
        samples = [event for event in skips_gate["events"] if event["kind"] == "rail_sample"]
        for index, event in enumerate(samples, start=1):
            event["point"] = [truth["rail"]["start"][0] + (first_gate - truth["rail"]["start"][0]) * index / (len(samples) * 2), truth["rail"]["start"][1]]
        _rail_event(skips_gate, "rail_end")["accepted"] = False
        rejected = grader.grade(skips_gate, truth, public)
        assert rejected["passed"] is False
        assert "incomplete restoration rail" in rejected["feedback"]

        oversized_step = copy.deepcopy(payload)
        _rail_event(oversized_step, "rail_sample")["point"][0] = truth["rail"]["start"][0] + truth["requirements"]["maximum_rail_step"] + 1
        rejected = grader.grade(oversized_step, truth, public)
        assert rejected["passed"] is False
        assert "breaks the continuous restoration rail" in rejected["feedback"]

        off_rail = copy.deepcopy(payload)
        _rail_event(off_rail, "rail_sample")["point"][1] = truth["rail"]["start"][1] + truth["rail"]["half_height"] + 1
        rejected = grader.grade(off_rail, truth, public)
        assert rejected["passed"] is False
        assert "breaks the continuous restoration rail" in rejected["feedback"]


def test_modifier_stack_gate_instruction_pluralization_covers_every_profile() -> None:
    """Keep the displayed rail instruction grammatical without changing L3 text."""

    source = (
        BENCHMARK / "shared_runtime" / "app" / "mechanics" / "modifier_stack_image_grid.js"
    ).read_text(encoding="utf-8")
    assert 'function gatePhrase(count) { return count === 1 ? "the one gate" : count === 2 ? "both gates" : `all ${gateWords(count)} gates`; }' in source
    assert "railGatePhrase = gatePhrase(gates)" in source
    assert "all one gates" not in source

    expected_phrases = {
        1: "the one gate",
        2: "both gates",
        3: "all three gates",
        4: "all three gates",
        5: "all four gates",
    }
    for level, expected_phrase in expected_phrases.items():
        public, _truth = SETUP.generate_task_state(
            task_for_level("modifier_stack_image_grid_env", level, "full"),
            f"modifier-stack-instruction-{level}",
        )
        gate_count = len(public["rail"]["gate_x"])
        assert {1: "the one gate", 2: "both gates"}.get(
            gate_count, f"all {['zero', 'one', 'two', 'three', 'four'][gate_count]} gates"
        ) == expected_phrase


def _reverse_identity_gate_payload(public: dict, truth: dict, interaction: str) -> dict:
    """Build a replayable ordinary-input ledger for source-binding checks."""

    events: list[dict] = []

    def record(kind: str, **details) -> None:
        events.append({"seq": len(events) + 1, "type": kind, **details})

    stations = [int(station["id"]) for station in truth["stations"]]
    for station in stations:
        record("deploy", station=station, deployed_count=station + 1)

    physics = truth["physics"]
    key_source = "keyboard" if interaction == "full" else "direction_button"
    contact_source = "pointer_hold" if interaction == "full" else "contact_toggle"
    for stage_index, stage in enumerate(truth["stages"]):
        station = int(stage["station"])
        direction = 1 if int(stage["pulse_speed_deg_per_tick"]) > 0 else -1
        record(
            "key",
            stage=stage_index,
            station=station,
            before=0,
            after=direction,
            input_source=key_source,
        )
        record(
            "contact",
            stage=stage_index,
            station=station,
            before=False,
            after=True,
            input_source=contact_source,
        )
        pulse = int(stage["pulse_start_deg"])
        receiver = int(stage["receiver_initial_deg"])
        charge = 0
        tick = 0
        while charge < int(physics["hold_ticks"]):
            tick += 1
            pulse = (pulse + int(stage["pulse_speed_deg_per_tick"])) % 360
            receiver = (receiver + direction * int(physics["receiver_control_deg_per_tick"])) % 360
            phase_error = abs((receiver - pulse + 180) % 360 - 180)
            locked = phase_error <= int(physics["capture_tolerance_deg"])
            if locked:
                receiver = pulse
                phase_error = 0
                charge += 1
            else:
                charge = max(0, charge - int(physics["charge_decay_per_tick"]))
            record(
                "tick",
                stage=stage_index,
                station=station,
                tick=tick,
                state={
                    "pulse_deg": pulse,
                    "receiver_deg": receiver,
                    "error_deg": phase_error,
                    "charge": charge,
                    "locked": locked,
                    "direction": direction,
                    "contact": True,
                },
            )
        record(
            "relay",
            stage=stage_index,
            station=station,
            tick=tick,
            charge=charge,
            next_station=(
                truth["stages"][stage_index + 1]["station"]
                if stage_index + 1 < len(truth["stages"])
                else None
            ),
        )
    record("verify", completed_stages=len(truth["stages"]), deployed=stations)
    return {
        "mechanic_id": "reverse_identity_gate",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "events": events,
        "completed": True,
    }


def test_reverse_identity_gate_controls_preserve_the_historical_full_reference_and_pair_simplified() -> None:
    env_name = "reverse_identity_gate_env"
    controls = controls_for(env_name)
    grader = load_module(
        "controlled_reverse_identity_gate_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "reverse_identity_gate.py",
    )
    original_task = base_task_for(env_name, "reverse_identity_gate")
    assert controls["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    assert original_task["natural_language"] == controls["difficulty"]["4"]["natural_language"]

    for seed in ("reverse-identity-l4-preservation-a", "reverse-identity-l4-preservation-b"):
        original_public, original_truth = SETUP.generate_task_state(original_task, seed)
        reference_public, reference_truth = SETUP.generate_task_state(
            task_for_level(env_name, 4), seed
        )
        assert reference_public["control_condition"]["interaction"] == "full"
        assert reference_truth["control_condition"]["interaction"] == "full"
        assert without_control_identity(reference_public) == without_control_identity(original_public)
        assert without_control_identity(reference_truth) == without_control_identity(original_truth)
        simplified_public, simplified_truth = SETUP.generate_task_state(
            task_for_level(env_name, 4, "simplified"), seed
        )
        assert simplified_public["control_condition"]["interaction"] == "simplified"
        assert simplified_truth["control_condition"]["interaction"] == "simplified"
        assert without_control_identity(simplified_public) == without_control_identity(original_public)
        assert without_control_identity(simplified_truth) == without_control_identity(original_truth)

    for level in range(1, 6):
        parameters = controls["difficulty"][str(level)]["parameters"]
        simplified_public, simplified_truth = SETUP.generate_task_state(
            task_for_level(env_name, level, "simplified"), f"reverse-identity-profile-{level}"
        )
        full_public, full_truth = SETUP.generate_task_state(
            task_for_level(env_name, level, "full"), f"reverse-identity-profile-{level}"
        )
        assert without_control_identity(simplified_public) == without_control_identity(full_public)
        assert without_control_identity(simplified_truth) == without_control_identity(full_truth)
        assert len(full_public["stations"]) == parameters["station_count"]
        assert len(full_public["stages"]) == sum(parameters["station_relays"])
        assert full_public["physics"] == {
            "tick_ms": parameters["tick_ms"],
            "receiver_control_deg_per_tick": parameters["receiver_control_deg_per_tick"],
            "capture_tolerance_deg": parameters["capture_tolerance_deg"],
            "hold_ticks": parameters["hold_ticks"],
            "charge_decay_per_tick": parameters["charge_decay_per_tick"],
            "maximum_ticks_per_stage": parameters["maximum_ticks_per_stage"],
        }
        for interaction, public, truth in (
            ("simplified", simplified_public, simplified_truth),
            ("full", full_public, full_truth),
        ):
            payload = _reverse_identity_gate_payload(public, truth, interaction)
            accepted = grader.grade(payload, truth, public)
            assert accepted["passed"] is True, accepted
            wrong_source = copy.deepcopy(payload)
            source_event = next(event for event in wrong_source["events"] if event["type"] == "key")
            source_event["input_source"] = "keyboard" if interaction == "simplified" else "direction_button"
            rejected = grader.grade(wrong_source, truth, public)
            assert rejected["passed"] is False
            assert rejected["feedback"] == "receiver drive uses the wrong interaction input"
            wrong_contact = copy.deepcopy(payload)
            contact_event = next(event for event in wrong_contact["events"] if event["type"] == "contact")
            contact_event["input_source"] = "pointer_hold" if interaction == "simplified" else "contact_toggle"
            rejected = grader.grade(wrong_contact, truth, public)
            assert rejected["passed"] is False
            assert rejected["feedback"] == "phase contact uses the wrong interaction input"

    renderer = (
        BENCHMARK / "shared_runtime" / "app" / "mechanics" / "reverse_identity_gate.js"
    ).read_text(encoding="utf-8")
    assert 'data-interaction="${esc(bridge.interaction)}"' in renderer
    assert 'state.control_condition?.interaction || "full"' in renderer
    assert '"direction_button"' in renderer
    assert '"pointer_hold"' in renderer


def _semantic_probe_payload(public: dict, truth: dict, interaction: str) -> dict:
    probe_source = {"simplified": "proxy_probe", "full": "direct_probe_drag"}[interaction]
    placement_source = {"simplified": "proxy_pair_click", "full": "direct_specimen_drag"}[interaction]
    probes = []
    for object_id in truth["expected_assignments"]:
        for channel in ("thermal", "polarity"):
            probes.append({
                "sequence": len(probes) + 1,
                "object_id": object_id,
                "probe": channel,
                "hold_ms": public["probe_hold_ms"],
                "input_source": probe_source,
            })
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction_mode": interaction,
        "placements": truth["expected_assignments"],
        "placement_sources": {
            object_id: placement_source
            for object_id in truth["expected_assignments"]
        },
        "probes": probes,
    }


def test_semantic_drag_drop_controls_preserve_l3_and_bind_probe_and_route_surfaces() -> None:
    env_name = "semantic_drag_drop_absurdity_env"
    mechanic = "semantic_drag_drop_absurdity"
    controls = controls_for(env_name)
    grader = load_module(
        "controlled_semantic_drag_drop_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{mechanic}.py",
    )
    assert controls["baseline"] == {"difficulty": 3, "interaction": "full", "real_time": "live"}
    assert controls["real_time"] == {
        "play_time_seconds": 150,
        "observation_window_ms": 800,
        "frames_per_observation": 6,
    }

    original = base_task_for(env_name, mechanic)
    for seed in ("semantic-baseline-a", "semantic-baseline-b", "semantic-baseline-c"):
        original_public, original_truth = SETUP.generate_task_state(original, seed)
        baseline_public, baseline_truth = SETUP.generate_task_state(
            task_for_level(env_name, 3, "full"), seed
        )
        assert original_public["challenge_id"] == baseline_public["challenge_id"]
        assert without_control_identity(original_public) == without_control_identity(baseline_public)
        assert without_control_identity(original_truth) == without_control_identity(baseline_truth)

    expected_counts = {1: 2, 2: 3, 3: 4, 4: 5, 5: 6}
    for level, count in expected_counts.items():
        full_public, full_truth = SETUP.generate_task_state(
            task_for_level(env_name, level, "full"), f"semantic-profile-{level}"
        )
        simplified_public, simplified_truth = SETUP.generate_task_state(
            task_for_level(env_name, level, "simplified"), f"semantic-profile-{level}"
        )
        assert len(full_public["objects"]) == len(full_public["receivers"]) == count
        assert len({(item["runtime_signature"]["thermal"], item["runtime_signature"]["polarity"]) for item in full_public["objects"]}) == count
        assert full_public["control_condition"]["difficulty_parameters"] == controls["difficulty"][str(level)]["parameters"]
        assert full_public["challenge_id"] == simplified_public["challenge_id"]
        assert without_control_identity(full_public) == without_control_identity(simplified_public)
        assert without_control_identity(full_truth) == without_control_identity(simplified_truth)

        for interaction, public, truth in (
            ("full", full_public, full_truth),
            ("simplified", simplified_public, simplified_truth),
        ):
            payload = _semantic_probe_payload(public, truth, interaction)
            accepted = grader.grade(payload, truth, public)
            assert accepted["passed"] is True, accepted

            wrong_mode = copy.deepcopy(payload)
            wrong_mode["interaction_mode"] = "simplified" if interaction == "full" else "full"
            rejected = grader.grade(wrong_mode, truth, public)
            assert rejected["passed"] is False
            assert rejected["feedback"] == "causal routing transcript uses the wrong interaction mode"

            wrong_probe_source = copy.deepcopy(payload)
            wrong_probe_source["probes"][0]["input_source"] = "proxy_probe" if interaction == "full" else "direct_probe_drag"
            rejected = grader.grade(wrong_probe_source, truth, public)
            assert rejected["passed"] is False
            assert rejected["feedback"] == "material probe uses the wrong interaction input"

            missing_probe = copy.deepcopy(payload)
            missing_probe["probes"].pop()
            rejected = grader.grade(missing_probe, truth, public)
            assert rejected["passed"] is False

    renderer = (
        BENCHMARK / "shared_runtime" / "app" / "mechanics" / f"{mechanic}.js"
    ).read_text(encoding="utf-8")
    assert 'state.control_condition?.interaction || "full"' in renderer
    assert 'data-interaction="${esc(interaction)}"' in renderer
    assert 'data-proxy-probe="thermal"' in renderer
    assert 'direct_specimen_drag' in renderer


def test_portal_freight_controls_preserve_l4_and_bind_direct_canvas_input() -> None:
    env_name = "portal_freight_oversized_parcel_env"
    mechanic = "portal_freight_oversized_parcel"
    controls = controls_for(env_name)
    grader = load_module(
        "controlled_portal_freight_grader",
        BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{mechanic}.py",
    )
    assert controls["baseline"] == {"difficulty": 4, "interaction": "simplified", "real_time": "live"}
    assert controls["real_time"] == {
        "play_time_seconds": 180,
        "observation_window_ms": 0,
        "frames_per_observation": 1,
    }

    for seed in ("portal-freight-baseline-a", "portal-freight-baseline-b"):
        original_public, original_truth = SETUP.generate_task_state(base_task_for(env_name, mechanic), seed)
        baseline_public, baseline_truth = SETUP.generate_task_state(
            task_for_level(env_name, 4, "simplified"), seed
        )
        assert original_public["challenge_id"] == baseline_public["challenge_id"]
        assert without_control_identity(original_public) == without_control_identity(baseline_public)
        assert without_control_identity(original_truth) == without_control_identity(baseline_truth)

    for level in range(1, 6):
        seed = f"portal-freight-profile-{level}"
        simplified_public, simplified_truth = SETUP.generate_task_state(
            task_for_level(env_name, level, "simplified"), seed
        )
        full_public, full_truth = SETUP.generate_task_state(
            task_for_level(env_name, level, "full"), seed
        )
        parameters = controls["difficulty"][str(level)]["parameters"]
        assert simplified_public["control_condition"]["difficulty_parameters"] == parameters
        assert simplified_public["challenge_id"] == full_public["challenge_id"]
        assert without_control_identity(simplified_public) == without_control_identity(full_public)
        assert without_control_identity(simplified_truth) == without_control_identity(full_truth)
        assert simplified_public["parcel"]["initial_angle_deg"] in parameters["initial_angles_deg"]
        assert simplified_public["controls"]["portal_half_width"] in parameters["portal_half_widths"]
        assert simplified_public["controls"]["push_step"] == parameters["push_step"]
        assert simplified_truth["delivery"] == full_truth["delivery"]

    public, truth = SETUP.generate_task_state(task_for_level(env_name, 4, "full"), "portal-freight-surface")
    payload = {
        "mechanic_id": mechanic,
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction_mode": "full",
        "events": [
            {"seq": 1, "t_ms": 0, "type": "challenge_start"},
            {
                "seq": 2,
                "t_ms": 1,
                "type": "aim",
                "space": "A",
                "delta_deg": 15,
                "before_deg": public["tools"]["A"]["yaw_deg"],
                "after_deg": public["tools"]["A"]["yaw_deg"] + 15,
                "input_surface": "proxy_control",
            },
        ],
        "final_state": {},
    }
    rejected = grader.grade(payload, truth, public)
    assert rejected["passed"] is False
    assert rejected["feedback"] == "aim event 2 uses the wrong interaction input"

    stale = copy.deepcopy(payload)
    stale["challenge_id"] = "stale-portal-freight-challenge"
    rejected = grader.grade(stale, truth, public)
    assert rejected["passed"] is False
    assert rejected["feedback"] == "stale challenge"

    malformed = copy.deepcopy(payload)
    malformed["events"] = []
    rejected = grader.grade(malformed, truth, public)
    assert rejected["passed"] is False
    assert rejected["feedback"] == "freight transcript is missing or too long"

    renderer = (BENCHMARK / "shared_runtime" / "app" / "mechanics" / f"{mechanic}.js").read_text(encoding="utf-8")
    assert 'inputSurface(){return interaction()==="full"?"direct_canvas":"proxy_control";}' in renderer
    assert 'installDirectCanvasControls' in renderer
    assert 'input_surface:surface' in renderer
