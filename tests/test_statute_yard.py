from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "weird_captcha_gym"
ENV = BENCH / "environments" / "statute_yard_env"
GENERATOR_PATH = BENCH / "shared_scripts" / "incubator_generators" / "statute_yard.py"
GRADER_PATH = BENCH / "shared_runtime" / "server" / "incubator_graders" / "statute_yard.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("statute_yard_generator_test", GENERATOR_PATH)
GRADER = _load("statute_yard_grader_test", GRADER_PATH)
CONTROLS = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
BASE_TASK = json.loads((ENV / "tasks/statute_yard_seed_0001/task.json").read_text(encoding="utf-8"))


def _task(level: int, interaction: str, real_time: str = "live") -> dict:
    task = copy.deepcopy(BASE_TASK)
    task["_control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": real_time,
        "difficulty_parameters": copy.deepcopy(CONTROLS["difficulty"][str(level)]["parameters"]),
    }
    return task


def _solution(public: dict, truth: dict, interaction: str) -> dict:
    _, replay = GENERATOR.replay(truth["yard"], truth["solution"])
    source = "direction_buttons" if interaction == "simplified" else "keyboard"
    return {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "completed": True,
        "actions": [
            {
                "seq": index,
                "type": "move",
                "direction": direction,
                "input_source": source,
                "outcome": replay[index - 1]["outcome"],
            }
            for index, direction in enumerate(truth["solution"], start=1)
        ],
        "reset_count": 0,
        "final_state": truth["solution_trace"]["final_state"],
    }


def test_all_ten_control_conditions_share_the_generated_world_and_grade() -> None:
    for level in range(1, 6):
        worlds = []
        for interaction in ("simplified", "full"):
            public, truth = GENERATOR.generate(_task(level, interaction), f"same-world-{level}")
            decision = GRADER.grade(_solution(public, truth, interaction), truth, public)
            assert decision["passed"] is True, (level, interaction, decision)
            worlds.append((public["challenge_id"], public["yard"], public["initial_state"], public["opening_rules"]))
        assert worlds[0] == worlds[1]


def test_live_and_paused_are_identical_static_decision_worlds() -> None:
    live, live_truth = GENERATOR.generate(_task(4, "full", "live"), "clock-equivalence")
    paused, paused_truth = GENERATOR.generate(_task(4, "full", "paused"), "clock-equivalence")
    for key in ("challenge_id", "yard", "initial_state", "opening_rules"):
        assert live[key] == paused[key]
    assert live_truth["solution"] == paused_truth["solution"]
    assert live["control_condition"]["real_time"] == "live"
    assert paused["control_condition"]["real_time"] == "paused"


def test_seed_breadth_measures_decision_layout_and_route_variation() -> None:
    observed_bands: dict[int, tuple[int, int]] = {}
    minimum_topologies = {1: 10, 2: 8, 3: 2, 4: 6, 5: 6}
    for level in range(1, 6):
        layouts: set[str] = set()
        topologies: set[str] = set()
        routes: set[str] = set()
        lengths: list[int] = []
        for seed_index in range(30):
            seed = f"breadth-{level}-{seed_index}"
            public, truth = GENERATOR.generate(_task(level, "full"), seed)
            parameters = CONTROLS["difficulty"][str(level)]["parameters"]
            assert parameters["minimum_solution_steps"] <= len(truth["solution"]) <= parameters["maximum_solution_steps"]
            assert truth["solution_trace"]["final_state"]["broken_opening_rules"]
            certificate = truth["opening_law_break_certificate"]
            assert certificate["method"] == "exhaustive_bfs_no_opening_rule_break"
            assert certificate["result"] == "no winning state reachable"
            assert certificate["explored_states"] > 0
            assert public["generator"]["no_break_states_exhausted"] == certificate["explored_states"]
            assert GRADER.grade(_solution(public, truth, "full"), truth, public)["passed"] is True
            layouts.add(truth["decision_layout_signature"])
            routes.add(truth["route_signature"])
            topology = {
                key: truth["yard"][key] for key in ("width", "height", "walls", "words")
            }
            topologies.add(
                hashlib.sha256(
                    json.dumps(topology, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest()
            )
            lengths.append(len(truth["solution"]))
        assert len(layouts) >= 20, (level, len(layouts))
        assert len(topologies) >= minimum_topologies[level], (level, len(topologies))
        assert len(routes) >= 16, (level, len(routes))
        observed_bands[level] = (min(lengths), max(lengths))

        public_again, truth_again = GENERATOR.generate(_task(level, "full"), f"breadth-{level}-0")
        public_first, truth_first = GENERATOR.generate(_task(level, "full"), f"breadth-{level}-0")
        assert public_again == public_first and truth_again == truth_first

    for easier, harder in zip(range(1, 5), range(2, 6)):
        assert observed_bands[easier][1] < observed_bands[harder][0]


def test_original_uncontrolled_configuration_is_preserved_exactly_at_l3() -> None:
    expected = (
        "8f2e054bb9db04f805f7020f59285b06f2eb3aa5caed546e99f35806a463dd42",
        "fcb3b1d84a364dbaf843e26d89007e6d2067ec69785d96213b1ab67c87b40a3d",
        "9eec9a124f9b2c5e0e745dfdee5488667632793bd86013a8d869b75ec9b1fb53",
    )
    for variant, expected_digest in enumerate(expected):
        yard = GENERATOR._template(3, variant)
        decision_geometry = {
            key: yard[key] for key in ("width", "height", "walls", "entities", "words")
        }
        encoded = json.dumps(decision_geometry, sort_keys=True, separators=(",", ":"))
        assert hashlib.sha256(encoded.encode("utf-8")).hexdigest() == expected_digest


def test_profiles_change_the_actual_decision_problem() -> None:
    generated = {level: GENERATOR.generate(_task(level, "full"), f"profile-{level}")[1] for level in range(1, 6)}
    assert generated[1]["solution_trace"]["deadly_break_step"] is not None
    assert generated[1]["solution_trace"]["transfers"] == []
    assert generated[2]["solution_trace"]["deadly_break_step"] is not None
    assert generated[2]["solution_trace"]["exit_make_step"] is not None
    assert generated[3]["solution_trace"]["deadly_break_step"] is not None
    assert generated[3]["solution_trace"]["transfers"]
    assert generated[3]["solution_trace"]["exit_make_step"] is None
    assert generated[4]["solution_trace"]["deadly_break_step"] is not None
    assert generated[4]["solution_trace"]["transfers"]
    assert generated[4]["solution_trace"]["exit_make_step"] is not None
    assert generated[4]["solution_trace"]["stop_break_step"] is None
    assert generated[5]["solution_trace"]["deadly_break_step"] is not None
    assert generated[5]["solution_trace"]["transfers"]
    assert generated[5]["solution_trace"]["exit_make_step"] is not None
    assert generated[5]["solution_trace"]["stop_break_step"] is not None


def test_grader_rejects_forgery_stale_identity_wrong_surface_and_post_terminal_moves() -> None:
    public, truth = GENERATOR.generate(_task(4, "full"), "negative-replay")

    stale = _solution(public, truth, "full")
    stale["challenge_id"] = "stale"
    assert "stale" in GRADER.grade(stale, truth, public)["feedback"]

    forged = _solution(public, truth, "full")
    forged["actions"][0]["outcome"] = "exit_reached"
    assert "outcome differs" in GRADER.grade(forged, truth, public)["feedback"]

    wrong_surface = _solution(public, truth, "full")
    wrong_surface["actions"][0]["input_source"] = "direction_buttons"
    assert "wrong interaction" in GRADER.grade(wrong_surface, truth, public)["feedback"]

    false_snapshot = _solution(public, truth, "full")
    false_snapshot["final_state"]["entities"][0]["x"] += 1
    assert "final yard" in GRADER.grade(false_snapshot, truth, public)["feedback"]

    post_terminal = _solution(public, truth, "full")
    post_terminal["actions"].append({
        "seq": len(post_terminal["actions"]) + 1,
        "type": "move", "direction": "LEFT", "input_source": "keyboard", "outcome": "move",
    })
    assert "terminal" in GRADER.grade(post_terminal, truth, public)["feedback"]


def test_public_state_exposes_no_route_or_final_answer() -> None:
    public, truth = GENERATOR.generate(_task(5, "full"), "secrecy")
    encoded = json.dumps(public)
    assert "solution_trace" not in encoded
    assert '"solution"' not in encoded
    assert truth["solution"]
    assert public["generator"]["solver"] == "breadth_first_minimum"
    assert public["generator"]["variation_kind"].startswith("solver-accepted")
    assert "variant_count" not in public["generator"]
    assert "route_signature" not in encoded


def test_registration_sources_static_clock_and_split_contract() -> None:
    env = json.loads((ENV / "env.json").read_text(encoding="utf-8"))
    task = json.loads((ENV / "tasks/statute_yard_seed_0001/task.json").read_text(encoding="utf-8"))
    split = json.loads((BENCH / "splits/statute_yard_split.json").read_text(encoding="utf-8"))
    manifest = json.loads((BENCH / "benchmark_manifest.json").read_text(encoding="utf-8"))
    real_time = json.loads((BENCH / "real_time.json").read_text(encoding="utf-8"))["environments"]
    assert CONTROLS["baseline"] == {"difficulty": 3, "interaction": "full", "real_time": "live"}
    assert env["runner_options"] == {"observation_window_ms": 0, "frames_per_observation": 1, "play_time_seconds": 120}
    assert task["name"] == "Statute Yard"
    assert task["difficulty"] == "medium"
    assert task["metadata"]["source_anchors"] == ["RLE-203", "TRR-022", "XAGT-363"]
    assert task["metadata"]["capabilities"] == ["visual_understanding_2d", "reasoning_and_planning"]
    assert len(split["variations_tasks"]) == 20
    assert manifest["environment_count"] == len(manifest["environments"])
    assert manifest["environments"].count("statute_yard_env") == 1
    assert real_time["statute_yard"] == env["runner_options"]


def test_browser_module_binds_exact_input_surfaces_and_visible_feedback() -> None:
    source = (BENCH / "shared_runtime/app/mechanics/statute_yard.js").read_text(encoding="utf-8")
    styles = (BENCH / "shared_runtime/app/mechanics/statute_yard.css").read_text(encoding="utf-8")
    for token in ("direction_buttons", "keyboard", "deadly_contact", "exit_reached", "law_shift", "broken_opening_rules"):
        assert token in source
    for selector in (".statute-board", ".law-stone", ".yard-object", ".statute-verdict", ".rule-ledger-list"):
        assert selector in styles
    assert "setInterval" not in source and "requestAnimationFrame" not in source
