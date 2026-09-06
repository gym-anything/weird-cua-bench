from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

from weird_captcha_gym.tools.materialize_controlled_tasks import controlled_task


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "weird_captcha_gym"
ENV = BENCH / "environments" / "after_hours_at_the_reliquary_env"
GENERATOR_PATH = BENCH / "shared_scripts/incubator_generators/after_hours_at_the_reliquary.py"
GRADER_PATH = BENCH / "shared_runtime/server/incubator_graders/after_hours_at_the_reliquary.py"
SOLVER_PATH = BENCH / "tools/incubator_solvers/after_hours_at_the_reliquary.py"
VERIFIER_PATH = ENV / "tasks/after_hours_at_the_reliquary_seed_0001/verifier.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("after_hours_generator_test", GENERATOR_PATH)
GRADER = _load("after_hours_grader_test", GRADER_PATH)
SOLVER = _load("after_hours_solver_test", SOLVER_PATH)
VERIFIER = _load("after_hours_verifier_test", VERIFIER_PATH)


def _task(level: int, interaction: str, real_time: str = "live") -> dict:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/after_hours_at_the_reliquary_seed_0001/task.json").read_text(encoding="utf-8"))
    task["_control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": copy.deepcopy(controls["difficulty"][str(level)]["parameters"]),
    }
    return task


def _center(target: dict) -> list[float]:
    x, y, width, height = target["rect"]
    return [round(x + width / 2, 6), round(y + height / 2, 6)]


def _card_rect(public: dict, inventory: list[str], item_id: str) -> list[float]:
    layout = public["item_card_layout"]
    slot = inventory.index(item_id)
    return [
        layout["left"] + slot * (layout["width"] + layout["gap"]),
        layout["top"],
        layout["width"],
        layout["height"],
    ]


def _card_center(public: dict, inventory: list[str], item_id: str) -> list[float]:
    x, y, width, height = _card_rect(public, inventory, item_id)
    return [round(x + width / 2, 6), round(y + height / 2, 6)]


def _solution(public: dict, interaction: str, *, seize_lock: str | None = None) -> dict:
    targets = {target["id"]: target for target in public["targets"]}
    events: list[dict] = []
    view_id = 0
    flags: set[str] = set()
    inventory: list[str] = []
    collected: set[str] = set()
    released: set[str] = set()
    wrong = {lock: 0 for lock in public["active_locks"]}
    seized = None
    completed = False
    misses = 0

    def add(event: dict) -> None:
        events.append({"sequence": len(events) + 1, **event})

    def turn_to(destination: int) -> None:
        nonlocal view_id
        count = len(public["views"])
        while view_id != destination:
            right_steps = (destination - view_id) % count
            left_steps = (view_id - destination) % count
            direction = "right" if right_steps <= left_steps else "left"
            after = (view_id + (1 if direction == "right" else -1)) % count
            add({
                "type": "turn", "from_view": view_id, "to_view": after, "direction": direction,
                "input_source": "edge_arrow" if interaction == "full" else "turn_button",
            })
            view_id = after

    direct_actions = {
        "flip_label": ("label_flipped", None),
        "collect_empty_frame": ("collected_empty_frame", "empty_frame"),
        "open_lens_drawer": ("lens_drawer_open", None),
        "collect_lens": ("collected_lens", "lens"),
        "remove_dust_sheet": ("color_revealed", None),
        "collect_hook": ("collected_hook", "hook"),
        "lift_floor_tile": ("floor_open", None),
        "collect_handle": ("collected_handle", "handle"),
        "collect_wire": ("collected_wire", "wire"),
        "reveal_order": ("order_revealed", None),
    }

    def scene(target_id: str) -> None:
        target = targets[target_id]
        turn_to(target["view_id"])
        add({"type": "scene", "target_id": target_id, "point": _center(target), "input_source": "scene_click"})
        if target["action"] == "open_door":
            nonlocal completed
            flags.add("door_open")
            completed = True
            return
        flag, item = direct_actions[target["action"]]
        flags.add(flag)
        if item:
            inventory.append(item)
            collected.add(item)

    def gesture(source_item: str, *, destination_item: str | None = None, target_id: str | None = None) -> dict:
        proof = {
            "start_root": [0.20, 0.86],
            "start_inventory": _card_center(public, inventory, source_item),
            "end_root": [0.52, 0.86] if destination_item is not None else [0.50, 0.48],
            "travel_px": 320, "sample_count": 8,
        }
        if destination_item is not None:
            proof["end_inventory"] = _card_center(public, inventory, destination_item)
        if target_id is not None:
            proof["end_scene"] = _center(targets[target_id])
        return proof

    def combine(first: str, second: str, result: str) -> None:
        event = {
            "type": "combine", "first": first, "second": second, "result": result,
            "input_source": "inventory_drag_item" if interaction == "full" else "inventory_select_pair",
        }
        if interaction == "full":
            event["gesture"] = gesture(first, destination_item=second)
        add(event)
        inventory.remove(first)
        inventory.remove(second)
        inventory.append(result)
        flags.add(f"crafted_{result}")

    def use(item_id: str, target_id: str) -> None:
        target = targets[target_id]
        turn_to(target["view_id"])
        event = {
            "type": "use", "item_id": item_id, "target_id": target_id,
            "input_source": "inventory_drag_scene" if interaction == "full" else "inventory_select_scene",
        }
        if interaction == "full":
            event["gesture"] = gesture(item_id, target_id=target_id)
        add(event)
        if target["action"] == "use_loupe":
            flags.add("digit_revealed")
        elif target["action"] == "use_hook":
            flags.add("collected_ward_key")
            inventory.append("ward_key")
            collected.add("ward_key")
        else:
            released.add("key")
            flags.add("key_released")
            inventory.remove("ward_key")

    scene("label_frame")
    scene("empty_frame")
    scene("lens_drawer")
    scene("lens")
    combine("empty_frame", "lens", "loupe")
    use("loupe", "label_code")
    if "color" in public["active_locks"]:
        scene("dust_sheet")
    if "key" in public["active_locks"]:
        if public["parameters"]["hook_mode"] == "ready":
            scene("ready_hook")
        else:
            scene("floor_tile")
            scene("handle")
            scene("radiator_wire")
            combine("handle", "wire", "hook")
        if public["parameters"]["cross_view_order"]:
            scene("order_drawer")
        use("hook", "grate")

    turn_to(0)
    if seize_lock == "digit":
        for strike in range(1, 4):
            add({
                "type": "digit_submit", "guess": "0" * int(public["parameters"]["digit_length"]),
                "accepted": False, "input_source": "digit_controls",
            })
            wrong["digit"] = strike
        seized = "digit"
    elif seize_lock == "color":
        answer = list(public["runtime_lock_answers"]["color"])
        guess = answer[1:] + answer[:1]
        for strike in range(1, 4):
            add({
                "type": "color_submit", "guess": guess,
                "accepted": False, "input_source": "color_controls",
            })
            wrong["color"] = strike
        seized = "color"
    elif seize_lock == "key":
        misses = 3
        for strike in range(1, 4):
            event = {
                "type": "misuse", "item_id": "loupe", "target_id": "keyhole",
                "input_source": "inventory_drag_scene" if interaction == "full" else "inventory_select_scene",
            }
            if interaction == "full":
                event["gesture"] = gesture("loupe", target_id="keyhole")
            add(event)
            wrong["key"] = strike
        seized = "key"
    else:
        if "digit" in public["active_locks"]:
            add({
                "type": "digit_submit", "guess": public["runtime_lock_answers"]["digit"],
                "accepted": True, "input_source": "digit_controls",
            })
            released.add("digit")
            flags.add("digit_released")
        if "color" in public["active_locks"]:
            add({
                "type": "color_submit", "guess": public["runtime_lock_answers"]["color"],
                "accepted": True, "input_source": "color_controls",
            })
            released.add("color")
            flags.add("color_released")
        if "key" in public["active_locks"]:
            use("ward_key", "keyhole")
        scene("door_handle")

    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction_mode": interaction,
        "events": events,
        "final_state": {
            "view_id": view_id,
            "flags": sorted(flags),
            "inventory": inventory,
            "released_locks": [lock for lock in public["active_locks"] if lock in released],
            "wrong_entries": wrong,
            "seized_lock": seized,
            "completed": completed,
        },
        "counters": {
            "locks_released": len(released),
            "items_collected": len(collected),
            "items_total": len(public["collectible_item_ids"]),
            "misses": misses,
            "wrong_lock_entries": sum(wrong.values()),
        },
        "completed": completed,
    }


def test_all_ten_difficulty_and_interaction_conditions_grade_and_preserve_world() -> None:
    expected_prompts = {
        1: "ONE WARD · ONE EXIT",
        2: "TWO WARDS · ONE EXIT",
        3: "THREE WARDS · ONE EXIT",
        4: "THREE WARDS · ONE EXIT",
        5: "THREE WARDS · ONE EXIT",
    }
    for level in range(1, 6):
        worlds = []
        for interaction in ("simplified", "full"):
            public, truth = GENERATOR.generate(_task(level, interaction), "same-world")
            assert public["prompt"] == expected_prompts[level]
            outcome = GRADER.grade(_solution(public, interaction), truth, public)
            assert outcome["passed"] is True, (level, interaction, outcome)
            worlds.append({key: public[key] for key in (
                "challenge_id", "views", "targets", "recipes", "raw_digit_clue", "raw_color_clue",
                "read_directions", "runtime_lock_answers", "parameters", "item_card_layout",
            )})
        assert worlds[0] == worlds[1]


def test_live_and_paused_are_the_same_static_world() -> None:
    for level in range(1, 6):
        live, _ = GENERATOR.generate(_task(level, "full", "live"), "clock-invariant")
        paused, _ = GENERATOR.generate(_task(level, "full", "paused"), "clock-invariant")
        assert live["challenge_id"] == paused["challenge_id"]
        assert live["targets"] == paused["targets"]
        assert live["runtime_lock_answers"] == paused["runtime_lock_answers"]


def test_three_wrong_entries_seize_every_ward_without_becoming_a_pass() -> None:
    for interaction in ("simplified", "full"):
        public, truth = GENERATOR.generate(_task(5, interaction), f"seizure-{interaction}")
        for lock in public["active_locks"]:
            payload = _solution(public, interaction, seize_lock=lock)
            outcome = GRADER.grade(payload, truth, public)
            assert outcome["graded"] is True
            assert outcome["passed"] is False, (interaction, lock, outcome)
            assert payload["final_state"]["seized_lock"] == lock
            assert payload["final_state"]["wrong_entries"][lock] == 3
            assert "wrong entries 3" in outcome["feedback"]


def test_replay_rejects_cross_mode_drag_claims_stale_identity_and_forged_state() -> None:
    public, truth = GENERATOR.generate(_task(3, "full"), "tamper")
    payload = _solution(public, "full")
    recoverable_misuse = copy.deepcopy(payload)
    dust_index = next(
        index
        for index, event in enumerate(recoverable_misuse["events"])
        if event.get("type") == "scene" and event.get("target_id") == "dust_sheet"
    )
    recoverable_misuse["events"].insert(
        dust_index,
        {
            "type": "misuse",
            "item_id": "loupe",
            "target_id": "dust_sheet",
            "input_source": "inventory_drag_scene",
            "gesture": {
                "start_root": [0.20, 0.86],
                "start_inventory": _card_center(public, ["loupe"], "loupe"),
                "end_root": [0.50, 0.48],
                "end_scene": _center(next(target for target in public["targets"] if target["id"] == "dust_sheet")),
                "travel_px": 320,
                "sample_count": 8,
            },
        },
    )
    for sequence, event in enumerate(recoverable_misuse["events"], 1):
        event["sequence"] = sequence
    recoverable_misuse["counters"]["misses"] = 1
    assert GRADER.grade(recoverable_misuse, truth, public)["passed"] is True
    wrong_mode = copy.deepcopy(payload)
    wrong_mode["interaction_mode"] = "simplified"
    assert GRADER.grade(wrong_mode, truth, public)["passed"] is False
    stale = copy.deepcopy(payload)
    stale["challenge_id"] = "rel-stale"
    assert "stale" in GRADER.grade(stale, truth, public)["feedback"]
    forged = copy.deepcopy(payload)
    forged["counters"]["items_collected"] += 1
    assert "counters" in GRADER.grade(forged, truth, public)["feedback"]
    bad_drag = copy.deepcopy(payload)
    use_event = next(event for event in bad_drag["events"] if event["type"] == "use")
    use_event["gesture"]["travel_px"] = 0
    assert "stationary" in GRADER.grade(bad_drag, truth, public)["feedback"]


def test_full_replay_binds_claimed_item_cards_at_every_drag_endpoint() -> None:
    public, truth = GENERATOR.generate(_task(3, "full"), "card-geometry")
    payload = _solution(public, "full")
    combine_index = next(index for index, event in enumerate(payload["events"]) if event["type"] == "combine")
    source_rect = _card_rect(public, ["empty_frame", "lens"], "empty_frame")
    destination_rect = _card_rect(public, ["empty_frame", "lens"], "lens")

    just_inside = copy.deepcopy(payload)
    inside_gesture = just_inside["events"][combine_index]["gesture"]
    inside_gesture["start_inventory"] = [source_rect[0] + 0.000001, source_rect[1] + 0.000001]
    inside_gesture["end_inventory"] = [
        destination_rect[0] + destination_rect[2] - 0.000001,
        destination_rect[1] + destination_rect[3] - 0.000001,
    ]
    assert GRADER.grade(just_inside, truth, public)["passed"] is True

    cases = {}
    cases["blank_tray"] = copy.deepcopy(payload)
    cases["blank_tray"]["events"][combine_index]["gesture"].update({
        "start_root": [0.65, 0.90],
        "end_root": [0.72, 0.90],
        "start_inventory": [0.65, 0.50],
        "end_inventory": [0.72, 0.50],
    })
    cases["source_just_outside"] = copy.deepcopy(payload)
    cases["source_just_outside"]["events"][combine_index]["gesture"]["start_inventory"] = [
        source_rect[0] + source_rect[2] + 0.002,
        source_rect[1] + source_rect[3] / 2,
    ]
    cases["destination_just_outside"] = copy.deepcopy(payload)
    cases["destination_just_outside"]["events"][combine_index]["gesture"]["end_inventory"] = [
        destination_rect[0] + destination_rect[2] + 0.002,
        destination_rect[1] + destination_rect[3] / 2,
    ]
    cases["wrong_source_card"] = copy.deepcopy(payload)
    cases["wrong_source_card"]["events"][combine_index]["gesture"]["start_inventory"] = _center({"rect": destination_rect})
    cases["wrong_destination_card"] = copy.deepcopy(payload)
    cases["wrong_destination_card"]["events"][combine_index]["gesture"]["end_inventory"] = _center({"rect": source_rect})

    scene_source = copy.deepcopy(payload)
    scene_use = next(event for event in scene_source["events"] if event["type"] == "use")
    scene_use["gesture"]["start_inventory"] = [0.65, 0.50]
    cases["scene_use_blank_source"] = scene_source

    for name, forged in cases.items():
        outcome = GRADER.grade(forged, truth, public)
        assert outcome["passed"] is False, name
        assert "claimed object card" in outcome["feedback"], (name, outcome)


def test_seeded_geometry_and_answers_vary_but_remain_reachable() -> None:
    challenge_ids = set()
    digit_answers = set()
    for index in range(40):
        public, truth = GENERATOR.generate(_task(3, "full"), f"reach-{index}")
        challenge_ids.add(public["challenge_id"])
        digit_answers.add(public["runtime_lock_answers"]["digit"])
        assert GRADER.grade(_solution(public, "full"), truth, public)["passed"] is True
        for target in public["targets"]:
            x, y, width, height = target["rect"]
            assert 0 <= x < x + width <= 1
            assert 0 <= y < y + height <= 1
            assert width >= 0.05 and height >= 0.05
    assert len(challenge_ids) == 40
    assert len(digit_answers) > 30


def test_all_levels_keep_simultaneously_available_targets_non_overlapping() -> None:
    def overlap_area(first: list[float], second: list[float]) -> float:
        ax, ay, aw, ah = first
        bx, by, bw, bh = second
        return max(0.0, min(ax + aw, bx + bw) - max(ax, bx)) * max(
            0.0, min(ay + ah, by + bh) - max(ay, by)
        )

    def may_coexist(first: dict, second: dict) -> bool:
        return not (
            set(first["requires_flags"]) & set(second["forbids_flags"])
            or set(second["requires_flags"]) & set(first["forbids_flags"])
        )

    for level in range(1, 6):
        for index in range(100):
            public, _truth = GENERATOR.generate(_task(level, "full"), f"non-overlap-{level}-{index}")
            for position, first in enumerate(public["targets"]):
                for second in public["targets"][position + 1 :]:
                    if first["view_id"] != second["view_id"] or not may_coexist(first, second):
                        continue
                    assert overlap_area(first["rect"], second["rect"]) == 0, (
                        level,
                        index,
                        first["id"],
                        second["id"],
                    )


def test_unmarked_scene_objects_do_not_leak_through_keyboard_focus() -> None:
    frontend = (BENCH / "shared_runtime/app/mechanics/after_hours_at_the_reliquary.js").read_text(encoding="utf-8")
    assert 'data-hotspot-id="${esc(id)}"' in frontend
    assert 'tabindex="-1"' in frontend


def test_public_metadata_source_anchors_boundary_and_registration() -> None:
    task = json.loads((ENV / "tasks/after_hours_at_the_reliquary_seed_0001/task.json").read_text(encoding="utf-8"))
    assert task["metadata"]["source_anchors"] == ["TRW-060", "TRW-072", "TRW-052", "WEB-220", "WEB-221"]
    assert task["metadata"]["capabilities"] == [
        "visual understanding: 2D",
        "temporal understanding and memory",
        "reasoning and planning",
        "exploration and interface understanding",
    ]
    required_boundary_terms = (
        "isolated agent sandbox", "provided gateway", "developer tools", "console", "debugger",
        "inspector", "network", "source", "dom", "page-state inspection", "terminal",
        "shell", "address-bar", "url/query edits", "reload", "navigation",
        "extensions", "external applications", "unrelated tabs",
    )
    assert "every active door ward" in task["description"].lower()
    assert "six-view" not in task["description"].lower()
    assert "all three" not in task["description"].lower()
    for field in (task["description"], task["natural_language"]):
        normalized = field.lower()
        for forbidden in required_boundary_terms:
            assert forbidden in normalized
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    for level_text, profile in controls["difficulty"].items():
        normalized = profile["natural_language"].lower()
        for forbidden in required_boundary_terms:
            assert forbidden in normalized
        materialized = controlled_task(
            task,
            mechanic_id=GENERATOR.MECHANIC_ID,
            level=int(level_text),
            interaction="full",
            profile=profile,
            task_dir_name=f"reliquary-test-d{level_text}-full",
        )
        assert materialized["description"] == task["description"]
        assert materialized["natural_language"] == profile["natural_language"]
        for field in (materialized["description"], materialized["natural_language"]):
            normalized = field.lower()
            for forbidden in required_boundary_terms:
                assert forbidden in normalized
    assert controls["baseline"] == {"difficulty": 3, "interaction": "full", "real_time": "live"}
    assert controls["real_time"] == {"play_time_seconds": 240, "observation_window_ms": 0, "frames_per_observation": 1}
    assert (BENCH / "shared_runtime/assets/provenance/after_hours_at_the_reliquary_v0.json").is_file()
    assert SOLVER.MECHANIC_ID == GENERATOR.MECHANIC_ID == GRADER.MECHANIC_ID
    assert callable(VERIFIER.verify_task)
