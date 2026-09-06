from __future__ import annotations

import copy
from collections import deque
import importlib.util
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "weird_captcha_gym"
ENV = BENCH / "environments" / "unmarked_landfall_env"
GENERATOR_PATH = BENCH / "shared_scripts" / "incubator_generators" / "unmarked_landfall.py"
GRADER_PATH = BENCH / "shared_runtime" / "server" / "incubator_graders" / "unmarked_landfall.py"
VERIFIER_PATH = ENV / "tasks" / "unmarked_landfall_seed_0001" / "verifier.py"
TASK_PATH = ENV / "tasks" / "unmarked_landfall_seed_0001" / "task.json"
CONTROLS_PATH = ENV / "controls.json"
FRONTEND_PATH = BENCH / "shared_runtime" / "app" / "mechanics" / "unmarked_landfall.js"
STYLES_PATH = BENCH / "shared_runtime" / "app" / "mechanics" / "unmarked_landfall.css"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generator = _load("unmarked_landfall_generator_test", GENERATOR_PATH)
grader = _load("unmarked_landfall_grader_test", GRADER_PATH)
verifier = _load("unmarked_landfall_verifier_test", VERIFIER_PATH)
controls = json.loads(CONTROLS_PATH.read_text(encoding="utf-8"))
canonical_task = json.loads(TASK_PATH.read_text(encoding="utf-8"))


def _condition(level: int, interaction: str) -> dict:
    profile = controls["difficulty"][str(level)]
    return {
        "difficulty": level,
        "difficulty_label": profile["label"],
        "difficulty_parameters": copy.deepcopy(profile["parameters"]),
        "interaction": interaction,
        "real_time": "live",
    }


def _generated(level: int, interaction: str, seed: str = "landfall-test"):
    task = copy.deepcopy(canonical_task)
    task["id"] = f"unmarked_landfall_d{level}_{interaction}_seed_0001@0.2"
    task["_control_condition"] = _condition(level, interaction)
    return generator.generate(task, seed)


def _delta(angle: float) -> float:
    return (angle + 180.0) % 360.0 - 180.0


def _payload_for_route(truth: dict, interaction: str, route: list[str]) -> dict:
    events: list[dict] = []
    yaw = float(truth["journey"]["initial_yaw"])
    node = str(route[0])
    visited = [node]
    nodes = {item["id"]: item for item in truth["journey"]["nodes"]}

    def record(kind: str, **details) -> None:
        events.append({"sequence": len(events) + 1, "kind": kind, **details})

    def orient_to(bearing: float) -> None:
        nonlocal yaw
        if interaction == "full":
            while abs(_delta(bearing - yaw)) > 0.02:
                change = max(-100.0, min(100.0, _delta(bearing - yaw)))
                start = [480.0, 250.0]
                end = [480.0 - change / 0.32, 250.0]
                record(
                    "pan_start",
                    point=start,
                    yaw_before=round(yaw, 2),
                    input_source="panorama_drag",
                )
                yaw = round((yaw + change) % 360.0, 2)
                record(
                    "pan_move",
                    point=end,
                    yaw_after=yaw,
                    input_source="panorama_drag",
                )
                record(
                    "pan_end",
                    point=end,
                    yaw=yaw,
                    input_source="panorama_drag",
                )
        else:
            while abs(_delta(bearing - yaw)) > 42.0:
                before = yaw
                turn = 30.0 if _delta(bearing - yaw) > 0 else -30.0
                yaw = round((yaw + turn) % 360.0, 2)
                record(
                    "turn_step",
                    yaw_before=before,
                    delta=turn,
                    yaw_after=yaw,
                    input_source="turn_buttons",
                )

    def observe(node_id: str) -> None:
        current = nodes[node_id]
        for visible_object in (current.get("clue"), current.get("landmark")):
            if visible_object:
                orient_to(float(visible_object["bearing"]))

    for source, destination in zip(route, route[1:]):
        assert source == node
        observe(source)
        road = next(item for item in nodes[source]["roads"] if item["to"] == destination)
        orient_to(float(road["bearing"]))
        if interaction == "full":
            difference = _delta(float(road["bearing"]) - yaw)
            arrow = [
                480.0 + difference / 52.0 * 960.0 * 0.43,
                540.0 * 0.78 + min(abs(difference) / 52.0, 1.0) * 18.0,
            ]
            record(
                "road_click",
                **{"from": source, "to": destination},
                yaw=round(yaw, 2),
                point=arrow,
                input_source="road_arrow",
            )
        else:
            record(
                "road_button",
                **{"from": source, "to": destination},
                yaw=round(yaw, 2),
                input_source="road_buttons",
            )
        node = destination
        if node not in visited:
            visited.append(node)
    observe(node)

    panorama_kinds = {"pan_move", "turn_step"}
    if not any(event["kind"] in panorama_kinds for event in events):
        orient_to((yaw + 60.0) % 360.0)

    record("surface_tab", surface="deposition")
    selections = copy.deepcopy(truth["target"]["signature"])
    for feature in truth["active_features"]:
        record("answer_select", feature=feature, value=selections[feature], input_source="deposition_buttons")
    record("surface_tab", surface="map")
    point = truth["target"]["landing_point"]
    map_zoom = 1.0
    map_pan = [0.0, 0.0]
    if interaction == "full":
        focus = [float(point["x"]), float(point["y"])]
        map_zoom = 1.18
        map_pan = [round(focus[0] * (1.0 - map_zoom), 2), round(focus[1] * (1.0 - map_zoom), 2)]
        record(
            "map_wheel",
            point=focus,
            delta=-1,
            zoom_before=1.0,
            zoom_after=map_zoom,
            pan_after=map_pan,
            input_source="map_wheel",
        )
        drag_start = [360.0, 240.0]
        drag_delta = [24.0 if focus[0] < 360 else -24.0, 18.0 if focus[1] < 240 else -18.0]
        drag_end = [drag_start[0] + drag_delta[0], drag_start[1] + drag_delta[1]]
        record(
            "map_drag_start",
            point=drag_start,
            pan_before=map_pan,
            input_source="map_drag",
        )
        map_pan = [
            round(
                max(
                    float(truth["map"]["width"]) * (1.0 - map_zoom),
                    min(0.0, map_pan[0] + drag_delta[0]),
                ),
                2,
            ),
            round(
                max(
                    float(truth["map"]["height"]) * (1.0 - map_zoom),
                    min(0.0, map_pan[1] + drag_delta[1]),
                ),
                2,
            ),
        ]
        record(
            "map_drag_move",
            point=drag_end,
            pan_after=map_pan,
            input_source="map_drag",
        )
        record(
            "map_drag_end",
            point=drag_end,
            pan_after=map_pan,
            input_source="map_drag",
        )
    view_point = [
        round(map_pan[0] + float(point["x"]) * map_zoom, 2),
        round(map_pan[1] + float(point["y"]) * map_zoom, 2),
    ]
    record("map_pin", view_point=view_point, world_point=view_point, input_source="map_direct")
    events[-1]["world_point"] = [round(float(point["x"]), 2), round(float(point["y"]), 2)]
    record("submit")
    return {
        "mechanic_id": "unmarked_landfall",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "events": events,
        "current_node": node,
        "step_count": len(route) - 1,
        "visited_nodes": visited,
        "final_yaw": round(yaw, 2),
        "selections": selections,
        "pin": {"x": round(point["x"], 2), "y": round(point["y"], 2)},
        "map_zoom": map_zoom,
        "map_pan": map_pan,
        "submission_count": 1,
        "completed": True,
    }


def _winning_payload(truth: dict, interaction: str) -> dict:
    return _payload_for_route(
        truth,
        interaction,
        list(truth["target"]["solution_route"]),
    )


def _one_step_private_truth_payload(truth: dict, interaction: str) -> dict:
    landing = str(truth["journey"]["landing_node"])
    nodes = {item["id"]: item for item in truth["journey"]["nodes"]}
    return _payload_for_route(
        truth,
        interaction,
        [landing, str(nodes[landing]["roads"][0]["to"])],
    )


def _shortest_required_route(truth: dict) -> list[str]:
    nodes = {item["id"]: item for item in truth["journey"]["nodes"]}
    required = {
        node_id
        for node_id, node in nodes.items()
        if node.get("clue") is not None or node.get("landmark") is not None
    }
    bits = {node_id: 1 << index for index, node_id in enumerate(sorted(required))}
    target_mask = sum(bits.values())
    start = str(truth["journey"]["landing_node"])
    start_mask = bits.get(start, 0)
    queue = deque([(start, start_mask, [start])])
    seen = {(start, start_mask)}
    while queue:
        node_id, mask, route = queue.popleft()
        if mask == target_mask:
            return route
        for road in nodes[node_id]["roads"]:
            destination = str(road["to"])
            next_mask = mask | bits.get(destination, 0)
            state = (destination, next_mask)
            if state not in seen:
                seen.add(state)
                queue.append((destination, next_mask, route + [destination]))
    raise AssertionError("generated evidence route is unreachable")


def test_all_ten_control_profiles_are_deterministic_and_replay_to_pass() -> None:
    for level in range(1, 6):
        paired_worlds = []
        for interaction in ("simplified", "full"):
            public, truth = _generated(level, interaction)
            repeated = _generated(level, interaction)
            assert (public, truth) == repeated
            outcome = grader.grade(_winning_payload(truth, interaction), truth, public)
            assert outcome["passed"] is True, (level, interaction, outcome)
            paired_worlds.append(
                (
                    public["world_fingerprint"],
                    public["map"],
                    public["guide"],
                    public["journey"],
                    public["active_features"],
                )
            )
        assert paired_worlds[0] == paired_worlds[1]


def test_private_truth_one_step_shortcut_is_rejected_in_all_ten_profiles() -> None:
    for level in range(1, 6):
        for interaction in ("simplified", "full"):
            public, truth = _generated(level, interaction, f"shortcut-{level}")
            outcome = grader.grade(
                _one_step_private_truth_payload(truth, interaction),
                truth,
                public,
            )
            assert outcome["passed"] is False, (level, interaction, outcome)
            assert "observations" in outcome["feedback"]


def test_shortest_accepted_l4_route_can_skip_an_unmarked_node_in_both_modes() -> None:
    for interaction in ("simplified", "full"):
        public, truth = _generated(4, interaction, "audit-min-route-0")
        route = _shortest_required_route(truth)
        assert len(truth["target"]["solution_route"]) - 1 == 8
        assert len(route) - 1 == 6
        assert set(route) != {node["id"] for node in truth["journey"]["nodes"]}
        outcome = grader.grade(
            _payload_for_route(truth, interaction, route),
            truth,
            public,
        )
        assert outcome["passed"] is True, (interaction, route, outcome)
        assert "observations 6/6; landmark 1/1;" in outcome["feedback"]
        assert "steps 6/8" in outcome["feedback"]


def test_full_winning_replay_contains_and_validates_a_moved_map_drag() -> None:
    public, truth = _generated(4, "full", "moved-map-drag")
    payload = _winning_payload(truth, "full")
    start = next(event for event in payload["events"] if event["kind"] == "map_drag_start")
    move = next(event for event in payload["events"] if event["kind"] == "map_drag_move")
    assert move["pan_after"] != start["pan_before"]
    assert grader.grade(payload, truth, public)["passed"] is True
    tampered = copy.deepcopy(payload)
    tampered_move = next(
        event for event in tampered["events"] if event["kind"] == "map_drag_move"
    )
    tampered_move["pan_after"][0] += 5
    assert grader.grade(tampered, truth, public)["passed"] is False


def test_difficulty_profiles_change_the_actual_identification_and_navigation_problem() -> None:
    assert controls["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    signatures = []
    for level in range(1, 6):
        public, truth = _generated(level, "full")
        params = public["parameters"]
        signatures.append(tuple(params.items()))
        assert len(public["guide"]["provinces"]) == params["province_count"]
        assert len(public["journey"]["nodes"]) == params["road_node_count"]
        assert len(public["active_features"]) == params["feature_count"]
        assert len(truth["target"]["critical_features"]) == params["ambiguity_depth"]
        assert len(truth["target"]["solution_route"]) - 1 <= params["step_budget"]
    assert len(set(signatures)) == 5
    assert signatures[2] != signatures[3] != signatures[4]
    assert controls["difficulty"]["3"]["parameters"]["pin_radius"] > 16
    assert controls["difficulty"]["5"]["parameters"]["pin_radius"] < 16


def test_unconditioned_task_matches_the_declared_level_four_world() -> None:
    uncontrolled, uncontrolled_truth = generator.generate(canonical_task, "same-landfall")
    controlled, controlled_truth = _generated(4, "full", "same-landfall")
    for key in ("world_fingerprint", "map", "guide", "journey", "active_features", "parameters"):
        assert uncontrolled[key] == controlled[key]
        assert uncontrolled_truth[key] == controlled_truth[key]


def test_target_is_uniquely_identified_and_near_matches_each_isolate_one_critical_feature() -> None:
    for level in range(1, 6):
        _public, truth = _generated(level, "full", f"uniqueness-{level}")
        target = truth["target"]["signature"]
        provinces = truth["guide"]["provinces"]
        matches = [province for province in provinces if province["signature"] == target]
        assert [province["id"] for province in matches] == [truth["target"]["province_id"]]
        differences = [
            {feature for feature in truth["active_features"] if province["signature"][feature] != target[feature]}
            for province in provinces
            if province["id"] != truth["target"]["province_id"]
        ]
        for feature in truth["target"]["critical_features"]:
            assert {feature} in differences


def test_generated_evidence_and_landmarks_do_not_overlap_road_affordances() -> None:
    def separation(left: float, right: float) -> float:
        return abs((left - right + 180.0) % 360.0 - 180.0)

    for level in range(1, 6):
        for index in range(40):
            public, _truth = _generated(
                level,
                "full",
                f"clear-bearing-{level}-{index}",
            )
            for node in public["journey"]["nodes"]:
                road_bearings = [float(road["bearing"]) for road in node["roads"]]
                clue = node.get("clue")
                landmark = node.get("landmark")
                if clue:
                    assert all(
                        separation(float(clue["bearing"]), road) >= 30.0
                        for road in road_bearings
                    )
                if landmark:
                    assert all(
                        separation(float(landmark["bearing"]), road) >= 24.0
                        for road in road_bearings
                    )
                if clue and landmark:
                    assert separation(
                        float(clue["bearing"]),
                        float(landmark["bearing"]),
                    ) >= 30.0


def test_replay_rejects_stale_identity_wrong_surface_and_summary_tampering() -> None:
    public, truth = _generated(4, "full")
    payload = _winning_payload(truth, "full")
    stale = copy.deepcopy(payload)
    stale["challenge_id"] = "stale"
    assert grader.grade(stale, truth, public)["passed"] is False
    wrong_surface = copy.deepcopy(payload)
    road_event = next(event for event in wrong_surface["events"] if event["kind"] == "road_click")
    road_event["kind"] = "road_button"
    road_event["input_source"] = "road_buttons"
    assert grader.grade(wrong_surface, truth, public)["passed"] is False
    hidden_deposition = copy.deepcopy(payload)
    deposition_tab = next(
        event
        for event in hidden_deposition["events"]
        if event.get("kind") == "surface_tab"
        and event.get("surface") == "deposition"
    )
    deposition_tab["surface"] = "guide"
    assert grader.grade(hidden_deposition, truth, public)["passed"] is False
    hidden_map = copy.deepcopy(payload)
    map_tab = next(
        event
        for event in hidden_map["events"]
        if event.get("kind") == "surface_tab" and event.get("surface") == "map"
    )
    map_tab["surface"] = "guide"
    assert grader.grade(hidden_map, truth, public)["passed"] is False
    tampered = copy.deepcopy(payload)
    tampered["step_count"] = 0
    assert grader.grade(tampered, truth, public)["passed"] is False
    wrong_pin = copy.deepcopy(payload)
    wrong_pin["pin"]["x"] = 0
    assert grader.grade(wrong_pin, truth, public)["passed"] is False


def test_exported_verifier_replays_the_server_contract(tmp_path: Path) -> None:
    public, truth = _generated(4, "simplified")
    exported = {"result": _winning_payload(truth, "simplified"), "public_state": public, "ground_truth": truth}
    source = tmp_path / "task_result.json"
    source.write_text(json.dumps(exported), encoding="utf-8")

    def copy_from_env(_remote: str, local: str) -> None:
        shutil.copyfile(source, local)

    outcome = verifier.verify_task(env_info={"copy_from_env": copy_from_env})
    assert outcome["passed"] is True
    assert outcome["score"] == 100


def test_task_carries_source_anchors_and_visible_ui_only_rule() -> None:
    metadata = canonical_task["metadata"]
    assert canonical_task["name"] == "Unmarked Landfall"
    assert metadata["source_anchors"] == ["WEB-120", "WEB-124", "TRW-486"]
    assert metadata["capabilities"] == [
        "visual understanding: 2D",
        "temporal understanding and memory",
        "reasoning and planning",
        "exploration and interface understanding",
    ]
    restriction = canonical_task["description"] + canonical_task["natural_language"]
    for forbidden in ("Developer Tools", "DOM", "terminal", "address-bar", "unrelated tab"):
        assert forbidden in restriction


def test_frontend_binds_each_mode_to_distinct_controls_and_shared_geometry() -> None:
    source = FRONTEND_PATH.read_text(encoding="utf-8")
    styles = STYLES_PATH.read_text(encoding="utf-8")
    assert 'interaction === "simplified"' in source
    assert 'input_source: "panorama_drag"' in source
    assert 'input_source: "turn_buttons"' in source
    assert 'travel(road.to, "road_click", "road_arrow", point)' in source
    assert 'travel(button.dataset.roadTarget, "road_button", "road_buttons")' in source
    assert 'input_source: "map_wheel"' in source
    assert 'input_source: "map_buttons"' in source
    assert 'window.unmarkedLandfallModel = model' in source
    assert ".unmarked-landfall" in styles
    assert "@media (max-width: 1050px)" in styles
    assert "target.signature" not in source
    assert '`ROAD ${clean(model.currentNode' not in source
    assert 'state.journey.landing_node.replace("road-", "ROAD ")' not in source
    assert '<dt>POSITION</dt><dd id="landfall-current-road">UNMARKED</dd>' in source
    assert "POSITION UNMARKED" in source
    assert "getScreenCTM" in source
    assert "createSVGPoint" in source
    assert "candidateProvinces" not in source
    assert "data-eliminated" not in source
    assert "landfall-candidates" not in source
    assert "CANDIDATES STRIKE THROUGH" not in source
    assert "TURN UNTIL A ROAD ARROW" not in source
    assert "DRAG THE VIEW" not in source
    assert "SCROLL TO ZOOM" not in source
    assert "Enter one plate impression" not in source
    assert "setTimeout" not in source
    assert "clearFreshFailure" in source
    assert "pointer-events: none" in styles


def test_real_time_annotation_is_static_and_single_frame() -> None:
    annotation = json.loads((BENCH / "real_time.json").read_text(encoding="utf-8"))["environments"]["unmarked_landfall"]
    assert annotation == {"play_time_seconds": 240, "observation_window_ms": 0, "frames_per_observation": 1}
    assert controls["real_time"] == annotation
