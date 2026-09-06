from __future__ import annotations

import copy
import importlib.util
import json
from collections import deque
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "weird_captcha_gym"
ENV = BENCH / "environments" / "flip_gate_cascade_env"
GENERATOR_PATH = BENCH / "shared_scripts" / "incubator_generators" / "flip_gate_cascade.py"
GRADER_PATH = BENCH / "shared_runtime" / "server" / "incubator_graders" / "flip_gate_cascade.py"
VERIFIER_PATH = ENV / "tasks" / "flip_gate_cascade_seed_0001" / "verifier.py"
TASK_PATH = ENV / "tasks" / "flip_gate_cascade_seed_0001" / "task.json"
CONTROLS = json.loads((ENV / "controls.json").read_text(encoding="utf-8"))
TASK = json.loads(TASK_PATH.read_text(encoding="utf-8"))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = _load("flip_gate_test_generator", GENERATOR_PATH)
GRADER = _load("flip_gate_test_grader", GRADER_PATH)
VERIFIER = _load("flip_gate_test_verifier", VERIFIER_PATH)


def _task(level: int, interaction: str) -> dict:
    task = copy.deepcopy(TASK)
    task["id"] = f"flip_gate_cascade_d{level}_{interaction}_seed_0001@0.2"
    task["_control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": "live",
        "difficulty_parameters": copy.deepcopy(
            CONTROLS["difficulty"][str(level)]["parameters"]
        ),
    }
    return task


def _solve_payload(truth: dict, input_source: str) -> dict:
    machine = truth["machine"]
    state = tuple(machine["initial_state"])
    events = []
    for sequence, chute in enumerate(truth["solution_chutes"], start=1):
        after, path = GENERATOR.transition(
            state,
            chute,
            machine["top_chutes"],
            machine["row_count"],
            machine["entry_columns"],
        )
        events.append(
            {
                "sequence": sequence,
                "chute": chute,
                "input_source": input_source,
                "before_state": list(state),
                "path": list(path),
                "after_state": list(after),
                "drops_after": sequence,
                "settled": True,
            }
        )
        state = after
    return {
        "mechanic_id": "flip_gate_cascade",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "events": events,
        "final_state": list(state),
        "drops_used": len(events),
        "completed": True,
        "budget_exhausted": False,
    }


def _failure_payload(truth: dict, input_source: str) -> dict:
    machine = truth["machine"]
    state = tuple(machine["initial_state"])
    events = []
    target = tuple(machine["target_state"])
    for sequence, chute in enumerate(truth["failure_chutes"], start=1):
        after, path = GENERATOR.transition(
            state,
            chute,
            machine["top_chutes"],
            machine["row_count"],
            machine["entry_columns"],
        )
        assert after != target
        events.append(
            {
                "sequence": sequence,
                "chute": chute,
                "input_source": input_source,
                "before_state": list(state),
                "path": list(path),
                "after_state": list(after),
                "drops_after": sequence,
                "settled": True,
            }
        )
        state = after
    return {
        "mechanic_id": "flip_gate_cascade",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "events": events,
        "final_state": list(state),
        "drops_used": len(events),
        "completed": False,
        "budget_exhausted": True,
    }


def _independent_distance(
    initial: tuple[int, ...],
    target: tuple[int, ...],
    chutes: int,
    rows: int,
    entry_columns: list[int],
) -> int:
    queue = deque([(initial, 0)])
    seen = {initial}
    while queue:
        state, depth = queue.popleft()
        if state == target:
            return depth
        for chute in range(chutes):
            nxt, _ = GENERATOR.transition(
                state, chute, chutes, rows, entry_columns
            )
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, depth + 1))
    raise AssertionError("target was not reachable")


def test_baseline_is_the_selected_four_chute_fifteen_vane_machine() -> None:
    assert CONTROLS["baseline"] == {
        "difficulty": 4,
        "interaction": "simplified",
        "real_time": "live",
    }
    public, truth = GENERATOR.generate(TASK, "baseline-fixed-seed")
    machine = public["machine"]
    assert machine["top_chutes"] == 4
    assert machine["row_count"] == 3
    assert machine["row_counts"] == [4, 5, 6]
    assert machine["gate_count"] == 15
    assert machine["optimal_depth"] == 7
    assert machine["drop_budget"] == 10
    assert sorted({gate["center"][1] for gate in machine["gates"]}) == [
        158.0,
        300.0,
        442.0,
    ]
    assert sorted(machine["entry_columns"]) == list(range(4))
    assert all(
        chute != column for chute, column in enumerate(machine["entry_columns"])
    )
    assert truth["machine"] == machine


def test_all_profiles_change_lattice_and_exact_planning_depth() -> None:
    expected = {
        1: (2, 2, 5, 2, 4),
        2: (3, 2, 7, 3, 5),
        3: (3, 3, 12, 5, 7),
        4: (4, 3, 15, 7, 10),
        5: (4, 4, 22, 9, 12),
    }
    for level, profile in expected.items():
        public, truth = GENERATOR.generate(_task(level, "simplified"), "profile-check")
        machine = public["machine"]
        assert (
            machine["top_chutes"],
            machine["row_count"],
            machine["gate_count"],
            machine["optimal_depth"],
            machine["drop_budget"],
        ) == profile
        assert len(truth["solution_chutes"]) == profile[3]
        assert len(truth["failure_chutes"]) == profile[4]
        assert _independent_distance(
            tuple(machine["initial_state"]),
            tuple(machine["target_state"]),
            machine["top_chutes"],
            machine["row_count"],
            machine["entry_columns"],
        ) == profile[3]


def test_l5_full_size_top_vanes_clear_the_sealed_manifold() -> None:
    public, _ = GENERATOR.generate(_task(5, "full"), "l5-manifold-clearance")
    machine = public["machine"]
    top_row = [gate for gate in machine["gates"] if gate["row"] == 0]

    # The normal vane is 76x16 and rotates by 34 degrees. Its vertical half
    # extent is about 27.9 SVG units. The manifold's lower edge is y=133 with a
    # five-unit stroke, so require visible clearance beyond y=135.5.
    vane_half_height = 38 * GENERATOR.math.sin(
        GENERATOR.math.radians(34)
    ) + 8 * GENERATOR.math.cos(GENERATOR.math.radians(34))
    manifold_stroked_bottom = 133.0 + 2.5
    assert len(top_row) == 4
    assert all(gate["center"][1] - vane_half_height > manifold_stroked_bottom for gate in top_row)


def test_interaction_modes_share_the_world_at_every_level() -> None:
    for level in range(1, 6):
        simplified, simple_truth = GENERATOR.generate(
            _task(level, "simplified"), "interaction-pair"
        )
        full, full_truth = GENERATOR.generate(_task(level, "full"), "interaction-pair")
        assert simplified["machine"] == full["machine"]
        assert simple_truth["solution_chutes"] == full_truth["solution_chutes"]
        assert simple_truth["failure_chutes"] == full_truth["failure_chutes"]


def test_generation_is_deterministic_varied_and_public_state_hides_solutions() -> None:
    task = _task(4, "full")
    public_a, truth_a = GENERATOR.generate(task, "variation-a")
    public_b, truth_b = GENERATOR.generate(task, "variation-a")
    public_c, truth_c = GENERATOR.generate(task, "variation-b")
    assert (public_a, truth_a) == (public_b, truth_b)
    assert truth_a["challenge_id"] != truth_c["challenge_id"]
    assert (
        public_a["machine"]["initial_state"],
        public_a["machine"]["target_state"],
    ) != (
        public_c["machine"]["initial_state"],
        public_c["machine"]["target_state"],
    )
    assert "solution_chutes" not in public_a
    assert "failure_chutes" not in public_a
    assert "seed" not in public_a
    inlet_variants = {
        tuple(GENERATOR.generate(task, f"inlet-{index}")[0]["machine"]["entry_columns"])
        for index in range(12)
    }
    assert len(inlet_variants) > 1


def test_flip_gate_action_operators_commute_without_hiding_that_source_property() -> None:
    public, _ = GENERATOR.generate(_task(4, "simplified"), "commutativity")
    machine = public["machine"]
    initial = tuple(machine["initial_state"])
    for left in range(machine["top_chutes"]):
        for right in range(machine["top_chutes"]):
            state_lr, _ = GENERATOR.transition(
                initial,
                left,
                machine["top_chutes"],
                machine["row_count"],
                machine["entry_columns"],
            )
            state_lr, _ = GENERATOR.transition(
                state_lr,
                right,
                machine["top_chutes"],
                machine["row_count"],
                machine["entry_columns"],
            )
            state_rl, _ = GENERATOR.transition(
                initial,
                right,
                machine["top_chutes"],
                machine["row_count"],
                machine["entry_columns"],
            )
            state_rl, _ = GENERATOR.transition(
                state_rl,
                left,
                machine["top_chutes"],
                machine["row_count"],
                machine["entry_columns"],
            )
            assert state_lr == state_rl


def test_grader_replays_both_surfaces_and_rejects_cross_mode_transcripts() -> None:
    for interaction, source in (("simplified", "chute_click"), ("full", "marble_drag")):
        public, truth = GENERATOR.generate(_task(4, interaction), f"grade-{interaction}")
        payload = _solve_payload(truth, source)
        assert GRADER.grade(payload, truth, public)["passed"] is True
        wrong = copy.deepcopy(payload)
        wrong["events"][0]["input_source"] = "marble_drag" if source == "chute_click" else "chute_click"
        assert GRADER.grade(wrong, truth, public)["passed"] is False


def test_grader_rejects_stale_tampered_and_incomplete_results() -> None:
    public, truth = GENERATOR.generate(_task(5, "simplified"), "adversarial")
    payload = _solve_payload(truth, "chute_click")
    stale = copy.deepcopy(payload)
    stale["challenge_id"] = "stale"
    assert GRADER.grade(stale, truth, public)["passed"] is False
    tampered = copy.deepcopy(payload)
    tampered["events"][0]["path"][0] += 1
    assert GRADER.grade(tampered, truth, public)["passed"] is False
    malformed_truth = copy.deepcopy(truth)
    malformed_public = copy.deepcopy(public)
    malformed_truth["machine"]["entry_columns"] = list(
        range(truth["machine"]["top_chutes"])
    )
    malformed_public["machine"] = copy.deepcopy(malformed_truth["machine"])
    assert GRADER.grade(payload, malformed_truth, malformed_public)["passed"] is False
    failure = _failure_payload(truth, "chute_click")
    result = GRADER.grade(failure, truth, public)
    assert result["graded"] is True
    assert result["passed"] is False
    assert "12 of 12" in result["feedback"]


def test_exported_verifier_independently_replays_the_result() -> None:
    public, truth = GENERATOR.generate(_task(3, "full"), "verify")
    payload = _solve_payload(truth, "marble_drag")
    passed, feedback = VERIFIER._verify_export(
        {"result": payload, "ground_truth": truth, "public_state": public}
    )
    assert passed is True
    assert "independent flip-gate replay" in feedback
    payload["events"][-1]["after_state"][0] ^= 1
    assert VERIFIER._verify_export(
        {"result": payload, "ground_truth": truth, "public_state": public}
    )[0] is False


def test_task_metadata_provenance_and_registries_are_complete() -> None:
    metadata = TASK["metadata"]
    assert TASK["name"] == "Flip-Gate Cascade"
    assert metadata["source_anchors"] == ["TRP-033", "PHY-137"]
    assert metadata["capabilities"] == [
        "visual understanding: 2D",
        "temporal understanding and memory",
        "reasoning and planning",
        "exploration and interface understanding",
    ]
    assert metadata["status"] == "prototype_visual_candidate"
    assert metadata["legacy_agent_sample_population"] is False
    assert "Developer Tools" in TASK["description"]
    provenance = json.loads(
        (BENCH / "shared_runtime" / "assets" / "provenance" / "flip_gate_cascade_v0.json").read_text(encoding="utf-8")
    )
    assert provenance["source_anchors"] == metadata["source_anchors"]
    assert provenance["assets"] == []
    manifest = json.loads((BENCH / "benchmark_manifest.json").read_text(encoding="utf-8"))
    assert manifest["environment_count"] == len(manifest["environments"])
    assert manifest["environments"].count("flip_gate_cascade_env") == 1
    clocks = json.loads((BENCH / "real_time.json").read_text(encoding="utf-8"))["environments"]
    assert clocks["flip_gate_cascade"] == CONTROLS["real_time"]


def test_frontend_uses_time_driven_fall_and_mode_specific_physical_inputs() -> None:
    frontend = (BENCH / "shared_runtime" / "app" / "mechanics" / "flip_gate_cascade.js").read_text(encoding="utf-8")
    assert "requestAnimationFrame(frame)" in frontend
    assert "setPointerCapture" in frontend
    assert '"chute_click"' in frontend
    assert '"marble_drag"' in frontend
    assert "model.current[gateId] = simulated.after[gateId]" in frontend
    assert 'beginAction("flip-gate-marble-transit")' in frontend
    assert "cascade-inspection-trace" in frontend
    assert "cascade-last-route" not in frontend
    assert "pointerenter" in frontend
    assert "outcome.passed === true" in frontend
    assert "completed: same" not in frontend
    assert "Drag the loose marble into a mouth." not in frontend
    assert "Press a lettered mouth on the cabinet." not in frontend
    assert "HOVER A MOUTH" not in frontend
    assert "Only one concealed route is shown at a time." not in frontend
    assert "TRAY EXHAUSTED" not in frontend
    assert "LOAD NEW PATTERN" not in frontend
    assert "PATTERN VERIFIED" not in frontend
    assert 'class="cascade-fail-card"><b>FAIL</b>' in frontend
    assert 'class="cascade-pass-card"><b>PASS</b>' in frontend
    assert "await helpers.render(outcome.state)" in frontend
    styles = (BENCH / "shared_runtime" / "app" / "mechanics" / "flip_gate_cascade.css").read_text(encoding="utf-8")
    assert ".feed-marble" in styles
    assert "#cascade-marble.is-visible" in styles
    assert "#cascade-active-trace.is-settled{opacity:0" in styles
