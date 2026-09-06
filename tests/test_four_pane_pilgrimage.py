from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "four_pane_pilgrimage_env"
MECHANIC = "four_pane_pilgrimage"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SETUP = _load("four_pane_setup", BENCHMARK / "shared_scripts" / "setup_task.py")
MATERIALIZER = _load(
    "four_pane_materializer", BENCHMARK / "tools" / "materialize_controlled_tasks.py"
)
GRADER = _load(
    "four_pane_grader",
    BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{MECHANIC}.py",
)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


BASE_TASK = _read(
    ENVIRONMENT / "tasks" / "four_pane_pilgrimage_seed_0001" / "task.json"
)
CONTROLS = _read(ENVIRONMENT / "controls.json")


def _task(level: int, interaction: str) -> dict:
    return MATERIALIZER.controlled_task(
        BASE_TASK,
        mechanic_id=MECHANIC,
        level=level,
        interaction=interaction,
        profile=CONTROLS["difficulty"][str(level)],
        task_dir_name=f"{MECHANIC}_d{level}_{interaction}_seed_0001",
    )


def _world(value: dict) -> dict:
    result = copy.deepcopy(value)
    result.pop("control_condition", None)
    result.pop("task_id", None)
    result.pop("prompt", None)
    return result


def _desired_slots(state: dict) -> list[str]:
    desired = ["", "", "", ""]
    for route_index, slot in enumerate(state["route_slots"]):
        desired[slot] = state["route_panel_ids"][route_index]
    return desired


def _solution_payload(public: dict, truth: dict, interaction: str) -> dict:
    events: list[dict] = []

    def add(kind: str, **details) -> None:
        events.append({"sequence": len(events) + 1, "kind": kind, **details})

    source = "proxy_controls" if interaction == "simplified" else "direct_manipulation"
    header_point = lambda slot: [.25 + .5 * (slot % 2), .025 + .5 * (slot // 2)]
    slots = list(public["initial_slots"])
    for target_slot, wanted in enumerate(_desired_slots(public)):
        current_slot = slots.index(wanted)
        if current_slot == target_slot:
            continue
        displaced = slots[target_slot]
        add(
            "panel_move",
            panel_id=wanted,
            from_slot=current_slot,
            to_slot=target_slot,
            displaced_panel_id=displaced,
            input_source=source,
            interaction_proof=(
                {"type": "button", "control": "move_slot", "selected_panel_id": wanted, "value": target_slot}
                if interaction == "simplified"
                else {"type": "header_drag", "start_slot": current_slot, "end_slot": target_slot, "start_board": header_point(current_slot), "end_board": header_point(target_slot), "trace": [[.18, .18], [.48, .31], [.78, .58]]}
            ),
        )
        slots[current_slot], slots[target_slot] = displaced, wanted

    transforms = copy.deepcopy(public["initial_transforms"])
    for panel_id in public["route_panel_ids"]:
        current = transforms[panel_id]
        target = truth["solution_transforms"][panel_id]
        while abs(current["zoom"] - target["zoom"]) > .001:
            before = current["zoom"]
            direction = 1 if target["zoom"] > before else -1
            current["zoom"] = round(before + direction * public["limits"]["zoom_step"], 3)
            add(
                "zoom",
                panel_id=panel_id,
                before=before,
                after=current["zoom"],
                input_source=source,
                interaction_proof=(
                    {"type": "button", "control": "zoom", "selected_panel_id": panel_id, "direction": direction}
                    if interaction == "simplified"
                    else {"type": "wheel", "point": [.5, .5], "delta_y": -120 if direction > 0 else 120}
                ),
            )
        if interaction == "simplified":
            for axis, key in enumerate(("pan_x", "pan_y")):
                while abs(current[key] - target[key]) > .001:
                    before = [current["pan_x"], current["pan_y"]]
                    direction = 1 if target[key] > current[key] else -1
                    current[key] = round(
                        current[key] + direction * public["limits"]["pan_step"], 3
                    )
                    add(
                        "pan",
                        panel_id=panel_id,
                        before=before,
                        after=[current["pan_x"], current["pan_y"]],
                        input_source=source,
                        interaction_proof={"type": "button", "control": "pan", "selected_panel_id": panel_id, "vector": [direction, 0] if key == "pan_x" else [0, direction]},
                    )
        else:
            remaining_x = target["pan_x"] - current["pan_x"]
            remaining_y = target["pan_y"] - current["pan_y"]
            while abs(remaining_x) > .001 or abs(remaining_y) > .001:
                part_x = max(-70.0, min(70.0, remaining_x))
                part_y = max(-55.0, min(55.0, remaining_y))
                before = [current["pan_x"], current["pan_y"]]
                current["pan_x"] = round(current["pan_x"] + part_x, 3)
                current["pan_y"] = round(current["pan_y"] + part_y, 3)
                start = [.5, .5]
                end = [round(.5 + part_x / 300.0, 4), round(.5 + part_y / 200.0, 4)]
                add(
                    "pan",
                    panel_id=panel_id,
                    before=before,
                    after=[current["pan_x"], current["pan_y"]],
                    input_source=source,
                    interaction_proof={"type": "canvas_drag", "start": start, "end": end, "trace": [[.3, .3], [.4, .4], [.55, .55]]},
                )
                remaining_x -= part_x
                remaining_y -= part_y

    plates = {plate["id"]: plate for plate in public["plates"]}
    plate_targets: dict[str, str] = {}
    for stage, join in enumerate(public["joins"]):
        plate_id = join.get("required_plate_id")
        if plate_id:
            plate = plates[plate_id]
            add(
                "plate_peel",
                plate_id=plate_id,
                source_panel_id=plate["source_panel_id"],
                input_source=source,
                interaction_proof=(
                    {"type": "button", "control": "peel", "plate_id": plate_id}
                    if interaction == "simplified"
                    else {"type": "plate_drag", "start_region": "bound_fragment", "end_region": "tray", "start_local": [.5, .5], "end_local": [.5, .5], "trace": [[.68, .32], [.76, .47], [.83, .62]]}
                ),
            )
            add(
                "plate_stack",
                plate_id=plate_id,
                target_panel_id=join["target_panel_id"],
                pose=plate["target_pose"],
                input_source=source,
                interaction_proof=(
                    {"type": "button", "control": "stack", "plate_id": plate_id, "target_panel_id": join["target_panel_id"]}
                    if interaction == "simplified"
                    else {"type": "plate_drag", "start_region": "tray_fragment", "end_region": "aperture", "start_local": [.5, .5], "end_local": [.5, .5], "trace": [[.84, .58], [.7, .48], [.53, .38]], "target_plate_id": plate_id}
                ),
            )
            plate_targets[plate_id] = join["target_panel_id"]
        add(
            "crossing",
            stage=stage,
            source_panel_id=join["source_panel_id"],
            target_panel_id=join["target_panel_id"],
            alignment_error={"source": 0.0, "target": 0.0},
        )
    add("submit", input_source="shared_control")
    return {
        "mechanic_id": MECHANIC,
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "interaction_mode": interaction,
        "events": events,
        "final_state": {
            "slots": slots,
            "transforms": transforms,
            "stage": 3,
            "plate_targets": plate_targets,
            "plate_poses": {plate_id: plates[plate_id]["target_pose"] for plate_id in plate_targets},
        },
        "completed": True,
    }


def test_generation_is_deterministic_and_interaction_preserves_the_world() -> None:
    for level in range(1, 6):
        simplified = SETUP.generate_incubator_candidate(
            _task(level, "simplified"), "four-pane-world-pair"
        )
        full = SETUP.generate_incubator_candidate(
            _task(level, "full"), "four-pane-world-pair"
        )
        again = SETUP.generate_incubator_candidate(
            _task(level, "full"), "four-pane-world-pair"
        )
        assert full == again
        assert _world(simplified[0]) == _world(full[0])
        assert _world(simplified[1]) == _world(full[1])
        assert simplified[1]["challenge_id"] == full[1]["challenge_id"]


def test_l4_reproduces_the_uncontrolled_baseline_world() -> None:
    uncontrolled = SETUP.generate_incubator_candidate(BASE_TASK, "four-pane-baseline")
    controlled = SETUP.generate_incubator_candidate(
        _task(4, "full"), "four-pane-baseline"
    )
    assert _world(uncontrolled[0]) == _world(controlled[0])
    assert _world(uncontrolled[1]) == _world(controlled[1])


def test_profiles_change_the_visible_correspondence_problem() -> None:
    generated = [
        SETUP.generate_incubator_candidate(_task(level, "full"), "four-pane-levels")
        for level in range(1, 6)
    ]
    required_counts = [
        sum(join.get("required_plate_id") is not None for join in public["joins"])
        for public, _truth in generated
    ]
    clutter_counts = [len(public["panels"][0]["strokes"]) for public, _truth in generated]
    displaced_counts = [
        sum(
            public["initial_transforms"][panel_id] != truth["solution_transforms"][panel_id]
            for panel_id in public["route_panel_ids"]
        )
        for public, truth in generated
    ]
    assert required_counts == [1, 1, 2, 3, 3]
    assert clutter_counts == [4, 6, 9, 12, 18]
    assert displaced_counts == [1, 2, 3, 4, 4]
    assert generated[0][0]["initial_slots"] == _desired_slots(generated[0][0])
    assert all(
        a[0]["limits"]["alignment_tolerance_units"]
        > b[0]["limits"]["alignment_tolerance_units"]
        for a, b in zip(generated, generated[1:])
    )
    for public, _truth in generated:
        route_styles = [panel["route_style"] for panel in public["panels"]]
        assert len({style["ink_key"] for style in route_styles}) == 4
        for stage, join in enumerate(public["joins"]):
            if not join.get("required_plate_id"):
                continue
            required = next(plate for plate in public["plates"] if plate["id"] == join["required_plate_id"])
            decoys = [plate for plate in public["plates"] if plate["unlock_stage"] == stage and plate["kind"] == "near_match_fragment"]
            assert all(decoy["outline"]["motif"] == required["outline"]["motif"] for decoy in decoys)
            assert all(decoy["fragment"] != required["fragment"] for decoy in decoys)

    def minimum_swaps(current: list[str], desired: list[str]) -> int:
        destination = {value: index for index, value in enumerate(desired)}
        permutation = [destination[value] for value in current]
        visited = [False] * 4
        cycles = 0
        for start in range(4):
            if visited[start]:
                continue
            cycles += 1
            cursor = start
            while not visited[cursor]:
                visited[cursor] = True
                cursor = permutation[cursor]
        return 4 - cycles

    assert minimum_swaps(generated[4][0]["initial_slots"], _desired_slots(generated[4][0])) == 3


def test_independent_replay_accepts_both_surfaces_and_rejects_cross_surface_transcripts() -> None:
    for interaction in ("simplified", "full"):
        public, truth = SETUP.generate_incubator_candidate(
            _task(4, interaction), f"four-pane-grade-{interaction}"
        )
        payload = _solution_payload(public, truth, interaction)
        assert GRADER.grade(payload, truth, public)["passed"] is True
        wrong = copy.deepcopy(payload)
        wrong["interaction_mode"] = "full" if interaction == "simplified" else "simplified"
        assert GRADER.grade(wrong, truth, public)["passed"] is False
        stale = copy.deepcopy(payload)
        stale["challenge_id"] = "stale"
        assert GRADER.grade(stale, truth, public)["passed"] is False


def test_whole_transcript_source_relabel_is_rejected_in_both_directions_at_every_level() -> None:
    for level in range(1, 6):
        generated = {
            interaction: SETUP.generate_incubator_candidate(
                _task(level, interaction), f"four-pane-whole-relabel-{level}"
            )
            for interaction in ("simplified", "full")
        }
        for source_mode, target_mode in (("simplified", "full"), ("full", "simplified")):
            source_public, source_truth = generated[source_mode]
            target_public, target_truth = generated[target_mode]
            payload = _solution_payload(source_public, source_truth, source_mode)
            payload["task_id"] = target_truth["task_id"]
            payload["challenge_id"] = target_truth["challenge_id"]
            payload["interaction_mode"] = target_mode
            replacement = "direct_manipulation" if target_mode == "full" else "proxy_controls"
            for event in payload["events"]:
                if event.get("input_source") in {"proxy_controls", "direct_manipulation"}:
                    event["input_source"] = replacement
            outcome = GRADER.grade(payload, target_truth, target_public)
            assert outcome["passed"] is False
            assert "proof" in outcome["feedback"] or "drag" in outcome["feedback"] or "wheel" in outcome["feedback"]


def test_replay_rejects_forged_crossing_and_client_terminal_claims() -> None:
    public, truth = SETUP.generate_incubator_candidate(
        _task(4, "full"), "four-pane-forgery"
    )
    payload = _solution_payload(public, truth, "full")
    first_crossing = next(
        index for index, event in enumerate(payload["events"]) if event["kind"] == "crossing"
    )
    forged = copy.deepcopy(payload)
    forged["events"][first_crossing]["alignment_error"]["source"] = 999
    assert GRADER.grade(forged, truth, public)["passed"] is False
    empty = {
        "mechanic_id": MECHANIC,
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "interaction_mode": "full",
        "events": [],
        "completed": True,
        "final_state": payload["final_state"],
    }
    assert GRADER.grade(empty, truth, public)["passed"] is False


def test_metadata_registration_and_observation_schedule_agree() -> None:
    task = BASE_TASK
    assert task["name"] == "Four-Pane Pilgrimage"
    assert task["metadata"]["source_anchors"] == ["IND-110", "VGE-338"]
    assert "visual understanding: 2D" in task["metadata"]["capabilities"]
    assert "temporal understanding and memory" not in task["metadata"]["capabilities"]
    assert CONTROLS["baseline"] == {
        "difficulty": 4,
        "interaction": "full",
        "real_time": "live",
    }
    real_time = _read(BENCHMARK / "real_time.json")["environments"][MECHANIC]
    assert real_time == CONTROLS["real_time"]
    manifest = _read(BENCHMARK / "benchmark_manifest.json")
    assert "four_pane_pilgrimage_env" in manifest["environments"]
