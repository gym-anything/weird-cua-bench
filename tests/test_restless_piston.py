from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "weird_captcha_gym" / "environments" / "restless_piston_env"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = load_module(
    "restless_piston_test_generator",
    ROOT / "weird_captcha_gym" / "shared_scripts" / "incubator_generators" / "restless_piston.py",
)
GRADER = load_module(
    "restless_piston_test_grader",
    ROOT / "weird_captcha_gym" / "shared_runtime" / "server" / "incubator_graders" / "restless_piston.py",
)
MATERIALIZER = load_module(
    "restless_piston_test_materializer",
    ROOT / "weird_captcha_gym" / "tools" / "materialize_controlled_tasks.py",
)


def controls() -> dict:
    return json.loads((ENV / "controls.json").read_text(encoding="utf-8"))


def controlled_task(level: int, interaction: str) -> dict:
    base = json.loads((ENV / "tasks/restless_piston_seed_0001/task.json").read_text())
    value = MATERIALIZER.controlled_task(
        base, mechanic_id="restless_piston", level=level, interaction=interaction,
        profile=controls()["difficulty"][str(level)],
        task_dir_name=f"restless_piston_d{level}_{interaction}_seed_0001")
    value["_control_condition"] = copy.deepcopy(value["metadata"]["control_condition"])
    return value


def generated(level: int, interaction: str, seed: str = "restless-piston-test") -> tuple[dict, dict]:
    return GENERATOR.generate(controlled_task(level, interaction), seed)


def passing_payload(public: dict, truth: dict, interaction: str) -> dict:
    state = copy.deepcopy(truth["initial"])
    source = {"full": "direct_manipulation", "simplified": "proxy_control"}[interaction]
    events = [{
        "seq": 1,
        "type": "mode_select",
        "tick": 0,
        "mode": truth["goal"]["required_mode"],
        "input_source": "mode_selector",
    }]
    for tick, item in enumerate(truth["planned_actions"], 1):
        before = copy.deepcopy(state)
        assert GRADER._apply(
            state,
            item["action"],
            item["direction"],
            truth["physics"],
            truth["goal"]["required_mode"],
            truth["reference_pressure"],
        )
        events.append({
            "seq": len(events) + 1,
            "type": "action",
            "tick": tick,
            "action": item["action"],
            "direction": item["direction"],
            "input_source": source,
            "before": before,
            "after": copy.deepcopy(state),
        })
    events.append({
        "seq": len(events) + 1,
        "type": "certify",
        "tick": len(truth["planned_actions"]) + int(truth["physics"]["settle_ticks"]),
        "mode": truth["goal"]["required_mode"],
        "stable_ticks": int(truth["physics"]["settle_ticks"]),
        "accepted": True,
        "state": {
            "pressure": round(GRADER._pressure(state), 6),
            "temperature": round(state["temperature"], 6),
            "volume": round(state["volume"], 6),
        },
    })
    return {
        "mechanic_id": "restless_piston",
        "task_id": truth["task_id"],
        "challenge_id": truth["challenge_id"],
        "interaction_mode": interaction,
        "events": events,
        "completed": True,
    }


def test_controls_materialize_exactly_ten_variants(tmp_path):
    target = tmp_path / "materialized"
    written = MATERIALIZER.materialize_environment(ENV, target)
    assert len(written) == 10
    assert {path.name for path in written} == {
        f"restless_piston_d{level}_{interaction}_seed_0001"
        for level in range(1, 6)
        for interaction in ("full", "simplified")
    }
    for path in written:
        task = json.loads((path / "task.json").read_text(encoding="utf-8"))
        condition = task["metadata"]["control_condition"]
        assert condition["difficulty"] in range(1, 6)
        assert condition["interaction"] in {"full", "simplified"}
        assert condition["real_time"] == "live"


def test_full_and_simplified_share_the_generated_world():
    for level in range(1, 6):
        full_public, full_truth = generated(level, "full")
        simple_public, simple_truth = generated(level, "simplified")
        for key in ("generator", "mode_options", "initial", "reference_pressure", "goal", "physics", "particles", "chamber"):
            assert full_public[key] == simple_public[key], (level, key)
        for key in ("initial", "goal", "physics", "reference_pressure", "planned_actions"):
            assert full_truth[key] == simple_truth[key], (level, key)
        assert full_public["control_condition"]["interaction"] == "full"
        assert simple_public["control_condition"]["interaction"] == "simplified"


def test_every_controlled_variant_passes_independent_replay():
    for level in range(1, 6):
        for interaction in ("full", "simplified"):
            public, truth = generated(level, interaction)
            decision = GRADER.grade(passing_payload(public, truth, interaction), truth, public)
            assert decision["passed"] is True, (level, interaction, decision)


def test_interaction_surface_and_challenge_identity_are_enforced():
    public, truth = generated(3, "simplified")
    payload = passing_payload(public, truth, "simplified")
    wrong_surface = copy.deepcopy(payload)
    next(event for event in wrong_surface["events"] if event["type"] == "action")["input_source"] = "direct_manipulation"
    assert GRADER.grade(wrong_surface, truth, public)["passed"] is False

    stale = copy.deepcopy(payload)
    stale["challenge_id"] = "stale-chamber"
    assert GRADER.grade(stale, truth, public)["passed"] is False


def test_profile_parameters_are_active_in_public_physics_and_plan():
    profile_data = controls()["difficulty"]
    for level in range(1, 6):
        public, truth = generated(level, "simplified")
        parameters = profile_data[str(level)]["parameters"]
        assert len(truth["planned_actions"]) == parameters["action_count"]
        assert public["initial"]["particles"] in range(parameters["particle_count"] - 2, parameters["particle_count"] + 3)
        for name in ("pump_delta", "heat_delta", "wall_delta", "settle_ticks", "max_ticks", "gauge_noise_ratio", "tick_ms"):
            assert truth["physics"][name] == parameters[name]
        assert truth["goal"]["tolerances"] == {
            "pressure": parameters["pressure_tolerance"],
            "temperature": parameters["temperature_tolerance"],
            "volume": parameters["volume_tolerance"],
        }


def test_profile_mode_pool_is_visible_and_authoritative():
    all_modes = set(GRADER.MODES)
    profile_data = controls()["difficulty"]
    for level in range(1, 6):
        public, truth = generated(level, "simplified")
        expected = list(profile_data[str(level)]["parameters"]["mode_pool"])
        assert [option["id"] for option in public["mode_options"]] == expected
        assert truth["mode_options"] == expected

        inactive = sorted(all_modes.difference(expected))[0] if all_modes.difference(expected) else None
        if inactive is None:
            continue
        invalid = passing_payload(public, truth, "simplified")
        invalid["events"][0]["mode"] = inactive
        decision = GRADER.grade(invalid, truth, public)
        assert decision["passed"] is False


def test_visible_mode_error_can_recover_after_a_state_change():
    public, truth = generated(3, "simplified", seed="mode-probe-3-51")
    assert truth["goal"]["required_mode"] == "volume"
    payload = passing_payload(public, truth, "simplified")
    # The first four planned actions reduce particle count while Volume is
    # held.  A pressure-with-volume request would put the wall below its
    # physical lower bound, so the browser records a recoverable mode_error
    # and continues using the selected Volume coupling.
    payload["events"].insert(
        5,
        {
            "seq": 0,
            "type": "mode_error",
            "tick": 4,
            "mode": "pressure_v",
            "reason": "PRESSURE HOLD WOULD DRIVE THE PISTON OUT OF RANGE",
            "input_source": "mode_selector",
        },
    )
    for sequence, event in enumerate(payload["events"], 1):
        event["seq"] = sequence
    decision = GRADER.grade(payload, truth, public)
    assert decision["passed"] is True, decision

    unjustified = copy.deepcopy(payload)
    error = next(event for event in unjustified["events"] if event["type"] == "mode_error")
    error["mode"] = "volume"
    assert GRADER.grade(unjustified, truth, public)["passed"] is False

    inactive = copy.deepcopy(payload)
    next(event for event in inactive["events"] if event["type"] == "mode_error")["mode"] = "pressure_t"
    assert GRADER.grade(inactive, truth, public)["passed"] is False


def test_uncontrolled_seed_keeps_the_original_baseline_configuration():
    task = json.loads((ENV / "tasks" / "restless_piston_seed_0001" / "task.json").read_text(encoding="utf-8"))
    public, truth = GENERATOR.generate(task, "restless-piston-uncontrolled-baseline")
    baseline = controls()["difficulty"]["3"]["parameters"]
    assert truth["mode_options"] == baseline["mode_pool"]
    assert len(truth["planned_actions"]) == baseline["action_count"]
    assert truth["physics"]["settle_ticks"] == baseline["settle_ticks"]
    assert truth["physics"]["gauge_noise_ratio"] == baseline["gauge_noise_ratio"]
    assert public["mode_options"] == [{"id": mode, "label": GENERATOR.MODE_LABELS[mode]} for mode in baseline["mode_pool"]]


def test_normal_surface_keeps_development_telemetry_offscreen():
    source = (ROOT / "weird_captcha_gym" / "shared_runtime" / "app" / "mechanics" / "restless_piston.js").read_text(encoding="utf-8")
    for forbidden in ("TRUE P", "FRAME ${model.tick}", "rp-settle", "rp-telemetry", "rp-mode-note"):
        assert forbidden not in source
    assert "PRESSURE · NOISY" in source
    assert "SELECT A SETTING" in source


def test_feasible_mode_changes_after_actions_preserve_recovery():
    public, truth = generated(3, "simplified")
    payload = passing_payload(public, truth, "simplified")
    # Re-selecting the active setting is a real UI event, even after controls.
    payload["events"].insert(2, {
        "type": "mode_select", "tick": 1, "mode": truth["goal"]["required_mode"],
        "input_source": "mode_selector",
    })
    for seq, event in enumerate(payload["events"], 1):
        event["seq"] = seq
    assert GRADER.grade(payload, truth, public)["passed"]


def test_mode_selection_restarts_settling_interval():
    public, truth = generated(3, "simplified")
    payload = passing_payload(public, truth, "simplified")
    final = payload["events"][-1]
    payload["events"].insert(-1, {
        "type": "mode_select", "tick": final["tick"],
        "mode": truth["goal"]["required_mode"], "input_source": "mode_selector",
    })
    for seq, event in enumerate(payload["events"], 1):
        event["seq"] = seq
    assert not GRADER.grade(payload, truth, public)["passed"]
    final["tick"] += truth["physics"]["settle_ticks"]
    assert GRADER.grade(payload, truth, public)["passed"]


def test_malformed_timing_fails_without_raising():
    public, truth = generated(3, "simplified")
    for value in (None, "bad", {}, [], float("inf"), float("nan"), True, 2.5):
        payload = passing_payload(public, truth, "simplified")
        payload["events"][-1]["stable_ticks"] = value
        assert not GRADER.grade(payload, truth, public)["passed"]
        payload = passing_payload(public, truth, "simplified")
        payload["events"][-1]["tick"] = value
        assert not GRADER.grade(payload, truth, public)["passed"]
