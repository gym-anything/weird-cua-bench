from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "weird_captcha_gym" / "environments" / "cockpit_preflight_checklist_env"
GENERATOR_PATH = ROOT / "weird_captcha_gym" / "shared_scripts" / "incubator_generators" / "cockpit_preflight_checklist.py"
GRADER_PATH = ROOT / "weird_captcha_gym" / "shared_runtime" / "server" / "incubator_graders" / "cockpit_preflight_checklist.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("cockpit_generator_test", GENERATOR_PATH)
GRADER = _load("cockpit_grader_test", GRADER_PATH)


def _task(level: int, interaction: str, real_time: str = "live") -> dict:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/cockpit_preflight_checklist_seed_0001/task.json").read_text(encoding="utf-8"))
    task["_control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": copy.deepcopy(controls["difficulty"][str(level)]["parameters"]),
    }
    return task


def _solution(public: dict, interaction: str) -> dict:
    panel = copy.deepcopy(public["panel"])
    events = []

    def add(event: dict) -> None:
        events.append({"sequence": len(events) + 1, **event})

    def item_by_id(item_id: str) -> dict:
        return next(item for item in panel["ranges"] + panel["dials"] if item["id"] == item_id)

    def coupling_effects(source: dict, field: str, before: int, after: int) -> tuple[list[dict], list[str]]:
        effects = []
        revealed = []
        source_steps = (after - before) // source["step"]
        source_target_field = {"low": "target_low", "high": "target_high", "value": "target"}[field]
        releases_target = after == source[source_target_field]
        for coupling in panel.get("couplings") or []:
            if coupling["source"] != {"id": source["id"], "field": field}:
                continue
            target = item_by_id(coupling["target"]["id"])
            target_field = coupling["target"]["field"]
            target_before = target[target_field]
            target_after = target_before + source_steps * target["step"] * coupling["ratio"]
            target_after = max(target["minimum"], min(target["maximum"], target_after))
            if target_field == "low":
                target_after = min(target_after, target["high"] - target["step"])
            elif target_field == "high":
                target_after = max(target_after, target["low"] + target["step"])
            target[target_field] = target_after
            effects.append({"coupling_id": coupling["id"], "id": target["id"], "field": target_field, "before": target_before, "after": target_after})
            if releases_target:
                revealed.append(coupling["id"])
        return effects, revealed

    def gesture(item: dict, before: int, after: int) -> dict:
        start = (before - item["minimum"]) / (item["maximum"] - item["minimum"])
        end = (after - item["minimum"]) / (item["maximum"] - item["minimum"])
        return {"start_fraction": start, "end_fraction": end, "travel_px": max(12, abs(end - start) * 500), "sample_count": 4}

    def move(item: dict, field: str, after: int, kind: str) -> None:
        before = item[field]
        source = "range_thumb_drag" if kind == "range" and interaction == "full" else "range_step_button" if kind == "range" else "rotary_pointer" if interaction == "full" else "dial_step_button"
        event = {"type": kind, "id": item["id"], "before": before, "after": after, "input_source": source}
        if kind == "range":
            event["thumb"] = field
        if interaction == "full":
            fraction = (after - item["minimum"]) / (item["maximum"] - item["minimum"])
            event.update({"pointer_fraction": fraction, "gesture": gesture(item, before, after)})
        item[field] = after
        effects, revealed = coupling_effects(item, field, before, after)
        event.update({"effects": effects, "revealed_coupling_ids": revealed})
        add(event)

    def feeds(item: dict, field: str) -> bool:
        return any(coupling["source"] == {"id": item["id"], "field": field} for coupling in panel.get("couplings") or [])

    def detour(item: dict, field: str) -> int:
        for candidate in (item[field] + item["step"], item[field] - item["step"]):
            if not item["minimum"] <= candidate <= item["maximum"]:
                continue
            if field in {"low", "high"}:
                paired = next((
                    coupling for coupling in panel.get("couplings") or []
                    if coupling["source"] == {"id": item["id"], "field": field}
                    and coupling["target"]["id"] == item["id"]
                ), None)
                other_field = "high" if field == "low" else "low"
                predicted_other = item[other_field]
                if paired:
                    predicted_other += ((candidate - item[field]) // item["step"]) * item["step"] * paired["ratio"]
                    predicted_other = max(item["minimum"], min(item["maximum"], predicted_other))
                if field == "low" and candidate > predicted_other - item["step"]:
                    continue
                if field == "high" and candidate < predicted_other + item["step"]:
                    continue
            return candidate
        raise AssertionError((item["id"], field))

    for item in panel["ranges"]:
        for thumb, target in (("low", item["target_low"]), ("high", item["target_high"])):
            if item[thumb] == target and feeds(item, thumb):
                after = detour(item, thumb)
                paired = next((
                    coupling for coupling in panel.get("couplings") or []
                    if coupling["source"] == {"id": item["id"], "field": thumb}
                    and coupling["target"]["id"] == item["id"]
                ), None)
                if paired:
                    other_field = "high" if thumb == "low" else "low"
                    predicted_other = item[other_field] + ((after - item[thumb]) // item["step"]) * item["step"] * paired["ratio"]
                    predicted_other = max(item["minimum"], min(item["maximum"], predicted_other))
                    after = min(after, predicted_other - item["step"]) if thumb == "low" else max(after, predicted_other + item["step"])
                else:
                    after = min(after, item["high"] - item["step"]) if thumb == "low" else max(after, item["low"] + item["step"])
                move(item, thumb, after, "range")
            for _attempt in range(100):
                if item[thumb] == target:
                    break
                if interaction == "full":
                    after = target
                    paired = next((
                        coupling for coupling in panel.get("couplings") or []
                        if coupling["source"] == {"id": item["id"], "field": thumb}
                        and coupling["target"]["id"] == item["id"]
                    ), None)
                    if thumb == "low" and paired:
                        predicted_high = item["high"] + ((after - item[thumb]) // item["step"]) * item["step"] * paired["ratio"]
                        predicted_high = max(item["minimum"], min(item["maximum"], predicted_high))
                        after = min(after, predicted_high - item["step"])
                    else:
                        after = min(after, item["high"] - item["step"]) if thumb == "low" else max(after, item["low"] + item["step"])
                else:
                    after = item[thumb] + item["step"] * (1 if target > item[thumb] else -1)
                if after == item[thumb]:
                    raise AssertionError((item["id"], thumb, item[thumb], target, item["low"], item["high"]))
                move(item, thumb, after, "range")
            else:
                raise AssertionError((item["id"], thumb, "range did not converge"))
    for item in panel["dials"]:
        if item["value"] == item["target"] and feeds(item, "value"):
            move(item, "value", detour(item, "value"), "dial")
        for _attempt in range(100):
            if item["value"] == item["target"]:
                break
            after = item["target"] if interaction == "full" else item["value"] + (1 if item["target"] > item["value"] else -1)
            move(item, "value", after, "dial")
        else:
            raise AssertionError((item["id"], "dial did not converge"))
    for branch in panel["branches"]:
        if not branch["expanded"]:
            add({"type": "branch", "id": branch["id"], "before": False, "after": True, "input_source": "tree_disclosure" if interaction == "full" else "tree_navigator"})
            branch["expanded"] = True
        for row in branch["rows"]:
            while row["state"] != row["target"]:
                before = row["state"]
                row["state"] = panel["tree_states"][(panel["tree_states"].index(before) + 1) % len(panel["tree_states"])]
                add({"type": "circuit", "id": row["id"], "before": before, "after": row["state"], "input_source": "tree_cell" if interaction == "full" else "tree_cycle_button"})
    final = {}
    for item in panel["ranges"]:
        final[item["id"]] = {"low": item["low"], "high": item["high"]}
    for item in panel["dials"]:
        final[item["id"]] = {"value": item["value"]}
    for branch in panel["branches"]:
        final[branch["id"]] = {"expanded": branch["expanded"]}
        for row in branch["rows"]:
            final[row["id"]] = {"state": row["state"]}
    return {
        "mechanic_id": public["mechanic_id"], "task_id": public["task_id"], "challenge_id": public["challenge_id"],
        "interaction_mode": interaction, "events": events, "final_state": final, "completed": True,
    }


def test_all_ten_control_conditions_generate_and_grade() -> None:
    for level in range(1, 6):
        worlds = []
        for interaction in ("simplified", "full"):
            public, truth = GENERATOR.generate(_task(level, interaction), "same-visible-world")
            decision = GRADER.grade(_solution(public, interaction), truth, public)
            assert decision["passed"] is True, (level, interaction, decision)
            worlds.append(public["panel"])
        assert worlds[0] == worlds[1]


def test_hundred_seed_reachability_in_both_interaction_modes() -> None:
    for level in range(1, 6):
        for seed_index in range(100):
            seed = f"reachability-{level}-{seed_index}"
            for interaction in ("simplified", "full"):
                public, truth = GENERATOR.generate(_task(level, interaction), seed)
                decision = GRADER.grade(_solution(public, interaction), truth, public)
                assert decision["passed"] is True, (level, interaction, seed, decision)


def test_live_and_paused_generation_have_identical_decision_state() -> None:
    live, _ = GENERATOR.generate(_task(3, "full", "live"), "observation-equivalence")
    paused, _ = GENERATOR.generate(_task(3, "full", "paused"), "observation-equivalence")
    assert live["panel"] == paused["panel"]
    assert live["parameters"] == paused["parameters"]
    assert live["control_condition"]["real_time"] == "live"
    assert paused["control_condition"]["real_time"] == "paused"


def test_wrong_interaction_surface_and_stale_challenge_are_rejected() -> None:
    public, truth = GENERATOR.generate(_task(3, "full"), "negative-contract")
    payload = _solution(public, "full")
    payload["events"][0]["input_source"] = "range_step_button"
    assert GRADER.grade(payload, truth, public)["passed"] is False
    payload = _solution(public, "full")
    payload["challenge_id"] = "stale"
    assert GRADER.grade(payload, truth, public)["passed"] is False


def test_stationary_click_and_forged_coupling_effect_are_rejected() -> None:
    public, truth = GENERATOR.generate(_task(2, "full"), "negative-gesture-contract")
    locked = public["panel"]["couplings"][0]["target"]
    locked_item = next(item for item in public["panel"]["ranges"] if item["id"] == locked["id"])
    locked_before = locked_item[locked["field"]]
    locked_payload = {
        "mechanic_id": public["mechanic_id"], "task_id": public["task_id"],
        "challenge_id": public["challenge_id"], "interaction_mode": "full",
        "events": [{
            "sequence": 1, "type": "range", "id": locked["id"], "thumb": locked["field"],
            "before": locked_before, "after": locked_before, "input_source": "range_thumb_drag",
        }],
        "final_state": {}, "completed": True,
    }
    assert "bus-locked" in GRADER.grade(locked_payload, truth, public)["feedback"]

    payload = _solution(public, "full")
    analog = next(event for event in payload["events"] if event["type"] in {"range", "dial"})
    analog["gesture"]["travel_px"] = 0
    analog["gesture"]["sample_count"] = 1
    assert "gesture" in GRADER.grade(payload, truth, public)["feedback"]

    payload = _solution(public, "full")
    coupled = next(event for event in payload["events"] if event["effects"])
    coupled["effects"][0]["after"] += 1
    assert "calibration-bus" in GRADER.grade(payload, truth, public)["feedback"]


def test_original_configuration_is_l2_and_harder_profiles_change_dependencies() -> None:
    controls = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
    assert controls["baseline"] == {"difficulty": 2, "interaction": "full", "real_time": "live"}
    l2 = controls["difficulty"]["2"]["parameters"]
    assert {key: l2[key] for key in (
        "range_count", "dial_count", "branch_count", "rows_per_branch", "nested_branch",
        "initial_collapsed", "readout_mode", "step_span",
    )} == {
        "range_count": 2, "dial_count": 2, "branch_count": 3, "rows_per_branch": 2,
        "nested_branch": False, "initial_collapsed": 2, "readout_mode": "all", "step_span": 8,
    }
    assert [controls["difficulty"][str(level)]["parameters"]["coupling_count"] for level in range(1, 6)] == [1, 2, 5, 6, 8]

    public3, _ = GENERATOR.generate(_task(3, "full"), "nested-contract")
    nested = next(branch for branch in public3["panel"]["branches"] if branch["depth"] == 2)
    assert nested["parent_id"] is not None
    assert len(public3["panel"]["couplings"]) == 5


def test_environment_contract_records_sources_and_static_observation() -> None:
    env = json.loads((ENV / "env.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/cockpit_preflight_checklist_seed_0001/task.json").read_text(encoding="utf-8"))
    split = json.loads((ROOT / "weird_captcha_gym/splits/cockpit_preflight_checklist_split.json").read_text(encoding="utf-8"))
    assert env["runner_options"] == {"observation_window_ms": 0, "frames_per_observation": 1, "play_time_seconds": 240}
    assert task["metadata"]["source_anchors"] == ["TAE-182", "BGUI-388"]
    assert task["metadata"]["status"] == "prototype_visual_candidate"
    assert task["difficulty"] == "easy"
    assert len(split["variations_tasks"]) == 20
