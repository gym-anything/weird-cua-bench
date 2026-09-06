from __future__ import annotations

import copy
import importlib.util
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "weird_captcha_gym"
ENV = BENCH / "environments" / "circle_limit_twist_env"
GENERATOR_PATH = BENCH / "shared_scripts" / "incubator_generators" / "circle_limit_twist.py"
GRADER_PATH = BENCH / "shared_runtime" / "server" / "incubator_graders" / "circle_limit_twist.py"
VERIFIER_PATH = ENV / "tasks" / "circle_limit_twist_seed_0001" / "verifier.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("circle_limit_twist_generator_test", GENERATOR_PATH)
GRADER = _load("circle_limit_twist_grader_test", GRADER_PATH)
VERIFIER = _load("circle_limit_twist_verifier_test", VERIFIER_PATH)
CONTROLS = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))


def _task(level: int, interaction: str, time_mode: str = "live") -> dict:
    profile = CONTROLS["difficulty"][str(level)]
    return {
        "id": f"circle_limit_twist_d{level}_{interaction}_seed_0001_t{time_mode}",
        "_control_condition": {
            "difficulty": level,
            "interaction": interaction,
            "time_mode": time_mode,
            "difficulty_parameters": copy.deepcopy(profile["parameters"]),
        },
    }


def _multiply(left: tuple[complex, ...], right: tuple[complex, ...]) -> tuple[complex, ...]:
    a, b, c, d = left
    e, f, g, h = right
    return (a * e + b * g, a * f + b * h, c * e + d * g, c * f + d * h)


def _apply(matrix: tuple[complex, ...], point: complex) -> complex:
    a, b, c, d = matrix
    return (a * point + b) / (c * point + d)


def _phi(point: complex) -> tuple[complex, ...]:
    return (1 + 0j, -point, -point.conjugate(), 1 + 0j)


def _inverse_phi(point: complex) -> tuple[complex, ...]:
    return (1 + 0j, point, point.conjugate(), 1 + 0j)


def _solution_payload(public: dict, truth: dict) -> dict:
    puzzle = truth["puzzle"]
    state = tuple(tuple(face) for face in puzzle["initial_state"])
    centers = {int(face["id"]): complex(*face["center"]) for face in puzzle["faces"]}
    matrix = (1 + 0j, 0j, 0j, 1 + 0j)
    interaction = truth["control_condition"]["interaction"]
    events = []
    views = 0
    twists = 0
    for move in truth["solution_moves"]:
        face_id, direction = int(move["face_id"]), int(move["direction"])
        current = _apply(matrix, centers[face_id])
        if interaction == "simplified":
            events.append({"sequence": len(events) + 1, "kind": "focus", "input_source": "focus_click", "face_id": face_id})
            matrix = _multiply(_phi(current), matrix)
        else:
            assert abs(current) < .98
            if abs(current) >= .001:
                events.append({
                    "sequence": len(events) + 1,
                    "kind": "pan",
                    "input_source": "mobius_drag",
                    "start": [current.real, current.imag],
                    "end": [0.0, 0.0],
                })
                matrix = _multiply(_multiply(_inverse_phi(0j), _phi(current)), matrix)
        views = sum(event["kind"] in ("focus", "pan") for event in events)
        before = state
        state = GENERATOR.apply_twist(state, puzzle["twist_cycles"], face_id, direction)
        twists += 1
        events.append({
            "sequence": len(events) + 1,
            "kind": "twist",
            "input_source": "proxy_buttons" if interaction == "simplified" else "canvas_click",
            "face_id": face_id,
            "direction": direction,
            "focus_distance": abs(_apply(matrix, centers[face_id])),
            "before_state": [list(face) for face in before],
            "after_state": [list(face) for face in state],
            "twists_after": twists,
        })
    return {
        "mechanic_id": "circle_limit_twist",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "events": events,
        "final_state": [list(face) for face in state],
        "twist_count": twists,
        "view_event_count": views,
        "completed": True,
    }


def test_reflected_tiling_and_twist_permutations_are_exact() -> None:
    public, truth = GENERATOR.generate(_task(5, "full"), "geometry-seed")
    puzzle = public["puzzle"]
    assert puzzle["model"] == "poincare_heptagonal_reflection_v1"
    assert len(puzzle["tiles"]) == 85
    assert len(puzzle["faces"]) == 15
    radii = [abs(complex(*face["center"])) for face in puzzle["faces"]]
    assert min(radii) == 0
    assert max(radii) > .75
    assert all(abs(complex(*vertex)) < 1 for tile in puzzle["tiles"] for vertex in tile["vertices"])
    search_operators = GENERATOR._move_operators(puzzle["twist_cycles"], 15)
    for face_id in range(15):
        state = tuple(tuple(face) for face in puzzle["initial_state"])
        encoded = bytes(color for face in state for color in face)
        for direction, offset in ((-1, 0), (1, 1)):
            physical = GENERATOR.apply_twist(state, puzzle["twist_cycles"], face_id, direction)
            searched = GENERATOR._apply_operator(encoded, search_operators[face_id * 2 + offset])
            assert searched == bytes(color for face in physical for color in face)
        turned = GENERATOR.apply_twist(state, puzzle["twist_cycles"], face_id, 1)
        restored = GENERATOR.apply_twist(turned, puzzle["twist_cycles"], face_id, -1)
        assert restored == state
    solved = tuple(tuple([index] * 7) for index in range(15))
    state = solved
    for move in truth["scramble_moves"]:
        state = GENERATOR.apply_twist(state, puzzle["twist_cycles"], move["face_id"], move["direction"])
    assert [list(face) for face in state] == puzzle["initial_state"]


def test_all_ten_difficulty_interaction_conditions_generate_and_grade() -> None:
    for level in range(1, 6):
        parameters = CONTROLS["difficulty"][str(level)]["parameters"]
        worlds = []
        for interaction in ("simplified", "full"):
            public, truth = GENERATOR.generate(_task(level, interaction), "ten-condition-seed")
            puzzle = public["puzzle"]
            assert len(puzzle["faces"]) == parameters["face_count"]
            assert len(truth["solution_moves"]) == parameters["scramble_length"]
            assert puzzle["move_budget"] == parameters["move_budget"]
            assert "solution_moves" not in public and "scramble_moves" not in public
            decision = GRADER.grade(_solution_payload(public, truth), truth, public)
            assert decision["passed"] is True, decision
            worlds.append(copy.deepcopy(puzzle))
        assert worlds[0] == worlds[1]


def test_live_and_paused_schedules_share_one_static_world() -> None:
    live, live_truth = GENERATOR.generate(_task(4, "full", "live"), "clock-seed")
    paused, paused_truth = GENERATOR.generate(_task(4, "full", "paused"), "clock-seed")
    assert live["puzzle"] == paused["puzzle"]
    assert live_truth["solution_moves"] == paused_truth["solution_moves"]
    assert CONTROLS["real_time"] == {"play_time_seconds": 180, "observation_window_ms": 0, "frames_per_observation": 1}


def test_grader_and_independent_verifier_reject_surface_identity_and_physics_tampering() -> None:
    public, truth = GENERATOR.generate(_task(3, "simplified"), "tamper-seed")
    payload = _solution_payload(public, truth)
    exported = {"result": payload, "ground_truth": truth, "public_state": public}
    assert GRADER.grade(payload, truth, public)["passed"] is True
    assert VERIFIER._verify_export(exported)[0] is True
    twist_index = next(index for index, event in enumerate(payload["events"]) if event["kind"] == "twist")
    wrong_surface = copy.deepcopy(payload)
    wrong_surface["events"][twist_index]["input_source"] = "canvas_click"
    assert "wrong twist input" in GRADER.grade(wrong_surface, truth, public)["feedback"]
    forged = copy.deepcopy(payload)
    forged["events"][twist_index]["after_state"] = forged["events"][twist_index]["before_state"]
    assert "permutation" in GRADER.grade(forged, truth, public)["feedback"]
    forged_distance = copy.deepcopy(payload)
    forged_distance["events"][twist_index]["focus_distance"] = .8
    assert "focus distance" in GRADER.grade(forged_distance, truth, public)["feedback"]
    stale = copy.deepcopy(payload)
    stale["challenge_id"] = "expired"
    assert GRADER.grade(stale, truth, public)["feedback"] == "stale challenge"
    assert VERIFIER._verify_export({**exported, "result": forged})[0] is False


def test_unsolved_empty_replay_fails_without_solution_oracle() -> None:
    public, truth = GENERATOR.generate(_task(2, "full"), "empty-seed")
    state = public["puzzle"]["initial_state"]
    payload = {
        "mechanic_id": "circle_limit_twist",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "events": [],
        "final_state": state,
        "twist_count": 0,
        "view_event_count": 0,
        "completed": False,
    }
    decision = GRADER.grade(payload, truth, public)
    assert decision["passed"] is False
    assert "incomplete" in decision["feedback"]


def test_generation_is_deterministic_and_varied() -> None:
    first = GENERATOR.generate(_task(5, "full"), "same-seed")
    second = GENERATOR.generate(_task(5, "full"), "same-seed")
    assert first == second
    fingerprints = {
        json.dumps(GENERATOR.generate(_task(4, "full"), f"seed-{index}")[0]["puzzle"]["initial_state"])
        for index in range(30)
    }
    assert len(fingerprints) >= 27


def test_every_profile_scramble_has_the_configured_exact_minimum_depth() -> None:
    for level in range(1, 6):
        expected = CONTROLS["difficulty"][str(level)]["parameters"]["scramble_length"]
        for sample in range(12):
            public, truth = GENERATOR.generate(_task(level, "full"), f"exact-depth-{level}-{sample}")
            state = tuple(tuple(face) for face in public["puzzle"]["initial_state"])
            moves = truth["scramble_moves"]
            assert len(moves) == expected
            assert truth["minimum_solution_depth"] == expected
            assert all(first["face_id"] != second["face_id"] for first, second in zip(moves, moves[1:]))
            assert GENERATOR.has_solution_shorter_than(
                state,
                public["puzzle"]["twist_cycles"],
                expected,
            ) is False
    public, _truth = GENERATOR.generate(_task(3, "full"), "color-quotient-goal")
    cycles = public["puzzle"]["twist_cycles"]
    color_permuted_goal = tuple(tuple([(face_id + 1) % 12] * 7) for face_id in range(12))
    assert GENERATOR.has_solution_shorter_than(color_permuted_goal, cycles, 1) is True


def test_files_registries_policy_and_independent_verifier() -> None:
    task = json.loads((ENV / "tasks" / "circle_limit_twist_seed_0001" / "task.json").read_text(encoding="utf-8"))
    policy = (task["description"] + " " + task["natural_language"]).lower()
    for phrase in ("screenshots and visible controls", "developer tools", "dom", "terminal", "address-bar", "reload", "external applications", "unrelated tab"):
        assert phrase in policy
    assert task["name"] == "Circle Limit Twist"
    assert task["metadata"]["source_anchors"] == ["PHY-030", "PHY-029", "PHY-002"]
    assert task["metadata"]["capabilities"] == [
        "visual understanding: 2D",
        "reasoning and planning",
        "exploration and interface understanding",
    ]
    manifest = json.loads((BENCH / "benchmark_manifest.json").read_text(encoding="utf-8"))
    assert manifest["environment_count"] == len(manifest["environments"])
    assert manifest["environments"].count("circle_limit_twist_env") == 1
    clocks = json.loads((BENCH / "real_time.json").read_text(encoding="utf-8"))["environments"]
    assert clocks["circle_limit_twist"] == CONTROLS["real_time"]
    verifier_source = VERIFIER_PATH.read_text(encoding="utf-8")
    assert "incubator_graders" not in verifier_source
    assert "def _twist" in verifier_source and "def _translation" in verifier_source
    frontend = (BENCH / "shared_runtime" / "app" / "mechanics" / "circle_limit_twist.js").read_text(encoding="utf-8")
    assert "mobius_drag" in frontend and "canvas_click" in frontend and "proxy_buttons" in frontend and "focus_click" in frontend
    assert "pointermove" in frontend and "setPointerCapture" in frontend and "releasePointerCapture" in frontend
    pointermove = frontend[frontend.index('canvas.addEventListener("pointermove"'):frontend.index('canvas.addEventListener("pointerdown"')]
    finish = frontend[frontend.index("const finish ="):frontend.index('canvas.addEventListener("pointerup"')]
    assert "pushViewEvent" not in pointermove
    assert 'kind: "pan"' in finish and "drag.start" in finish and "drag.last" in finish
    assert "Path2D" in frontend and "geodesicPoint" in frontend
    assert "setTimeout" not in frontend
    for prohibited_visible_copy in (
        "Mouse gesture legend",
        "DRAG DISC",
        "LEFT CLICK",
        "RIGHT CLICK",
        "CENTER A FACE INSIDE THE BRASS APERTURE",
        "FACE CENTERED — CHOOSE A TURN",
        "CLICK A VISIBLE FACE TO CENTER IT",
        "TURNING APERTURE",
        "VERIFYING EXACT STICKER REPLAY",
        "Every face is monochrome and the twist record agrees",
    ):
        assert prohibited_visible_copy not in frontend


def test_provenance_declares_sources_but_no_copied_assets() -> None:
    provenance = json.loads((BENCH / "shared_runtime" / "assets" / "provenance" / "circle_limit_twist_v0.json").read_text(encoding="utf-8"))
    assert provenance["mechanic_id"] == "circle_limit_twist"
    assert provenance["source_anchors"] == ["PHY-030", "PHY-029", "PHY-002"]
    assert provenance["assets"] == []
    assert len(provenance["sources"]) == 4
