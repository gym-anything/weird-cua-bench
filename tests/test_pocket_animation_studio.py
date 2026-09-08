from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
ENV_ROOT = BENCHMARK / "environments" / "pocket_animation_studio_env"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generator = _load(
    "pocket_animation_studio_test_generator",
    BENCHMARK / "shared_scripts" / "incubator_generators" / "pocket_animation_studio.py",
)
grader = _load(
    "pocket_animation_studio_test_grader",
    BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "pocket_animation_studio.py",
)
materializer = _load(
    "pocket_animation_studio_test_materializer",
    BENCHMARK / "tools" / "materialize_controlled_tasks.py",
)

BASE_TASK = json.loads(
    (ENV_ROOT / "tasks" / "pocket_animation_studio_seed_0001" / "task.json").read_text(
        encoding="utf-8"
    )
)
CONTROLS = json.loads((ENV_ROOT / "controls.json").read_text(encoding="utf-8"))


def _task(level: int, interaction: str) -> dict:
    task = copy.deepcopy(BASE_TASK)
    task["id"] = f"pocket_animation_studio_d{level}_{interaction}_seed_0001"
    task["_control_condition"] = {
        "difficulty": level,
        "interaction": interaction,
        "real_time": "live",
        "difficulty_parameters": copy.deepcopy(CONTROLS["difficulty"][str(level)]["parameters"]),
    }
    return task


def _success_payload(public: dict, truth: dict, interaction: str) -> dict:
    events = []
    for shape in truth["target_program"]:
        if interaction == "full":
            events.append({"type": "drag_shape", "shape_id": shape["id"], "kind": shape["kind"]})
            for field in shape["expressions"]:
                expression = shape["expressions"][field]
                events.append(
                    {
                        "type": "drag_expression",
                        "shape_id": shape["id"],
                        "field": field,
                        "kind": expression["kind"],
                    }
                )
                for part in ("a", "b", "frequency"):
                    events.append(
                        {
                            "type": "numeric_edit",
                            "shape_id": shape["id"],
                            "field": field,
                            "part": part,
                            "value": expression[part],
                        }
                    )
        else:
            events.append({"type": "proxy_shape", "shape_id": shape["id"], "kind": shape["kind"]})
            for field in shape["expressions"]:
                expression = shape["expressions"][field]
                events.append(
                    {
                        "type": "proxy_expression",
                        "shape_id": shape["id"],
                        "field": field,
                        "kind": expression["kind"],
                    }
                )
                for part in ("a", "b", "frequency"):
                    events.append(
                        {
                            "type": "numeric_edit",
                            "shape_id": shape["id"],
                            "field": field,
                            "part": part,
                            "value": expression[part],
                        }
                    )
    events.append({"type": "run", "accepted": True, "run_index": 1})
    events.append({"type": "preview_complete", "duration_ms": truth["duration_ms"]})
    events.append({"type": "certify", "max_error": 0, "mean_error": 0})
    return {
        "mechanic_id": "pocket_animation_studio",
        "task_id": truth["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction": interaction,
        "program": copy.deepcopy(truth["target_program"]),
        "events": events,
        "run_count": 1,
        "preview_complete": True,
        "completed": True,
    }


def test_controls_materialize_ten_visible_ui_variants(tmp_path):
    materializer.validate_controls(CONTROLS, ENV_ROOT)
    written = materializer.materialize_environment(ENV_ROOT, tmp_path)
    assert len(written) == 10
    assert {path.name for path in written} == {
        f"pocket_animation_studio_d{level}_{interaction}_seed_0001"
        for level in range(1, 6)
        for interaction in ("simplified", "full")
    }
    for path in written:
        task = json.loads((path / "task.json").read_text(encoding="utf-8"))
        assert task["metadata"]["control_condition"]["real_time"] == "live"
        assert task["metadata"]["control_condition"]["interaction"] in {"simplified", "full"}
        assert "Use only screenshots and visible controls" in task["natural_language"]
        assert "Do not use code, scripts, automation" in task["natural_language"]


def test_original_world_is_preserved_at_l4():
    _, original = generator.generate(BASE_TASK, "original-baseline")
    _, controlled = generator.generate(_task(4, "full"), "original-baseline")
    assert original["target_program"] == controlled["target_program"]
    assert original["target_frames"] == controlled["target_frames"]
    assert original["duration_ms"] == controlled["duration_ms"]


def test_catalog_uses_original_baseline_and_retains_all_controls():
    from weird_captcha_gym.dashboard.catalog import build_catalog
    environment = next(e for e in build_catalog()["environments"] if e["id"] == ENV_ROOT.name)
    assert environment["tasks"][0]["id"] == "pocket_animation_studio_seed_0001"
    assert "four-layer moving scene" in environment["instruction"]
    controls = environment["difficulty_control"]
    assert controls["baseline_level"] == 4
    assert controls["baseline_interaction"] == "full"
    assert len(controls["profiles"]) == 5
    assert set(controls["interactions"]) == {"full", "simplified"}


def test_difficulty_and_pairwise_worlds_are_distinct_but_interaction_invariant():
    shape_counts = []
    for level in range(1, 6):
        simplified_public, simplified_truth = generator.generate(
            _task(level, "simplified"), "pocket-animation-pair-seed"
        )
        full_public, full_truth = generator.generate(
            _task(level, "full"), "pocket-animation-pair-seed"
        )
        assert simplified_public["reference"] == full_public["reference"]
        assert simplified_public["studio"] == full_public["studio"]
        assert simplified_truth["target_program"] == full_truth["target_program"]
        assert "target_program" not in json.dumps(simplified_public, sort_keys=True)
        allowed = set(CONTROLS["difficulty"][str(level)]["parameters"]["allowed_expression_types"])
        assert all(
            expression["kind"] in allowed
            for shape in simplified_truth["target_program"]
            for expression in shape["expressions"].values()
        )
        shape_counts.append(len(simplified_truth["target_program"]))
    assert shape_counts == [2, 3, 3, 4, 5]


def test_replay_accepts_both_surfaces_and_rejects_wrong_visual_or_transcript():
    for interaction in ("simplified", "full"):
        public, truth = generator.generate(_task(4, interaction), "pocket-animation-grade-seed")
        payload = _success_payload(public, truth, interaction)
        decision = grader.grade(payload, truth, public)
        assert decision["passed"] is True, decision
        assert decision["metrics"]["frames"] == truth["sample_count"]
        wrong = copy.deepcopy(payload)
        wrong["program"][0]["expressions"][next(iter(wrong["program"][0]["expressions"]))]["a"] += 10
        assert grader.grade(wrong, truth, public)["passed"] is False
        stale = copy.deepcopy(payload)
        stale["challenge_id"] = "stale"
        assert grader.grade(stale, truth, public)["passed"] is False
        incomplete = copy.deepcopy(payload)
        incomplete["preview_complete"] = False
        assert grader.grade(incomplete, truth, public)["passed"] is False
        missing_certification = copy.deepcopy(payload)
        missing_certification["events"] = [
            event for event in missing_certification["events"] if event["type"] != "certify"
        ]
        assert grader.grade(missing_certification, truth, public)["passed"] is False


def test_grader_rejects_expression_kinds_outside_active_profile():
    for level in (1, 2):
        public, truth = generator.generate(_task(level, "full"), f"pocket-animation-restriction-{level}")
        payload = _success_payload(public, truth, "full")
        first_shape = payload["program"][0]
        first_field = next(iter(first_shape["expressions"]))
        first_shape["expressions"][first_field]["kind"] = "wave"
        first_shape["expressions"][first_field]["b"] = 0
        for event in payload["events"]:
            if (
                event.get("type") == "drag_expression"
                and event.get("shape_id") == first_shape["id"]
                and event.get("field") == first_field
                ):
                    event["kind"] = "wave"
            if (
                event.get("type") == "numeric_edit"
                and event.get("shape_id") == first_shape["id"]
                and event.get("field") == first_field
                and event.get("part") == "b"
            ):
                event["value"] = 0
        decision = grader.grade(payload, truth, public)
        assert decision["passed"] is False
        assert "allowed" in decision["feedback"]


def test_interaction_transcripts_cannot_cross_the_pair_boundary():
    public, truth = generator.generate(_task(4, "full"), "pocket-animation-transcript-seed")
    payload = _success_payload(public, truth, "full")
    payload["interaction"] = "simplified"
    assert grader.grade(payload, truth, public)["passed"] is False


def test_replay_accepts_corrections_removal_and_untouched_defaults():
    for interaction in ("full", "simplified"):
        public, truth = generator.generate(_task(4, interaction), "editor-corrections")
        payload = _success_payload(public, truth, interaction)
        prefix = "drag" if interaction == "full" else "proxy"
        # A mistaken block may be removed; historical kinds need not equal the final kind.
        payload["events"][:0] = [
            {"type": f"{prefix}_shape", "shape_id": "shape-1", "kind": "line"},
            {"type": "remove_shape", "shape_id": "shape-1"},
        ]
        placement = next(e for e in payload["events"] if e["type"] == f"{prefix}_expression")
        index = payload["events"].index(placement)
        payload["events"].insert(index, {**placement, "kind": "wave"})
        payload["events"].insert(index + 1, {
            "type": "numeric_edit", "shape_id": placement["shape_id"],
            "field": placement["field"], "part": "kind", "value": "linear",
        })
        # Native inputs need not emit change events for their unchanged defaults.
        payload["events"] = [e for e in payload["events"] if not (
            e["type"] == "numeric_edit" and e["part"] == "frequency" and e["value"] == 1
        )]
        const_fields = {(s["id"], f) for s in payload["program"] for f, e in s["expressions"].items() if e["kind"] == "const"}
        payload["events"] = [e for e in payload["events"] if not (
            e["type"] == "numeric_edit" and e["part"] == "b"
            and (e["shape_id"], e["field"]) in const_fields
        )]
        decision = grader.grade(payload, truth, public)
        assert decision["passed"], decision


def test_replay_requires_current_run_completion_and_certification():
    public, truth = generator.generate(_task(4, "full"), "preview-contract")
    original = _success_payload(public, truth, "full")
    for event_type in ("run", "preview_complete", "certify"):
        payload = copy.deepcopy(original)
        payload["events"] = [e for e in payload["events"] if e["type"] != event_type]
        assert not grader.grade(payload, truth, public)["passed"]
    for run_count in (None, "bad", {}, -1, 0, 1.5):
        payload = copy.deepcopy(original)
        payload["run_count"] = run_count
        assert not grader.grade(payload, truth, public)["passed"]
    edit = next(e for e in original["events"] if e["type"] == "numeric_edit")
    for position in (-1, -2):
        payload = copy.deepcopy(original)
        payload["events"].insert(len(payload["events"]) + position, copy.deepcopy(edit))
        assert not grader.grade(payload, truth, public)["passed"]
        payload["events"] = payload["events"][:-2] if position == -2 else payload["events"][:-1]
        payload["events"].extend(copy.deepcopy(original["events"][-3:]))
        payload["run_count"] = 2
        assert grader.grade(payload, truth, public)["passed"]
    payload = copy.deepcopy(original)
    payload["events"][-2]["duration_ms"] = 1
    assert not grader.grade(payload, truth, public)["passed"]
    payload = _success_payload(public, truth, "full")
    payload["events"].append({"type": "drag_expression", "shape_id": "shape-1", "field": "not-a-field", "kind": "const"})
    assert grader.grade(payload, truth, public)["passed"] is False


def test_transcript_replay_accepts_default_a_and_rejects_malformed_events():
    public, truth = generator.generate(_task(4, "full"), "default-a")
    payload = _success_payload(public, truth, "full")
    shape = payload["program"][0]
    field = next(iter(shape["expressions"]))
    shape["expressions"][field]["a"] = 50
    payload["events"] = [e for e in payload["events"] if not (
        e["type"] == "numeric_edit" and e["shape_id"] == shape["id"]
        and e["field"] == field and e["part"] == "a"
    )]
    assert grader._validate_interaction(payload, truth, payload["program"]) is None
    for event in ({"type": []}, {"type": "drag_shape", "kind": {}}, {"type": "numeric_edit", "shape_id": "shape-1", "field": []}):
        malformed = copy.deepcopy(payload)
        malformed["events"].append(event)
        assert not grader.grade(malformed, truth, public)["passed"]
    public, truth = generator.generate(_task(4, "simplified"), "pocket-animation-transcript-seed")
    payload = _success_payload(public, truth, "simplified")
    payload["events"].append({"type": "drag_shape", "shape_id": "forged"})
    assert grader.grade(payload, truth, public)["passed"] is False


def test_line_endpoint_reversal_preserves_visual_grade():
    for interaction in ("full", "simplified"):
        public, truth = generator.generate(_task(4, interaction), "endpoint-reversal")
        submitted = copy.deepcopy(truth)
        line = next(shape for shape in submitted["target_program"] if shape["kind"] == "line")
        expressions = line["expressions"]
        for first, second in (("x1", "x2"), ("y1", "y2")):
            expressions[first], expressions[second] = expressions[second], expressions[first]
        payload = _success_payload(public, submitted, interaction)
        decision = grader.grade(payload, truth, public)
        assert decision["passed"], decision
        assert decision["metrics"]["max_error"] < 0.001
        for field in ("x1", "width"):
            wrong = copy.deepcopy(submitted)
            shape = next(shape for shape in wrong["target_program"] if shape["kind"] == "line")
            shape["expressions"][field] = {"kind": "const", "a": 100, "b": 0, "frequency": 1}
            rejected = grader.grade(_success_payload(public, wrong, interaction), truth, public)
            assert not rejected["passed"], rejected
            assert "animation mismatch" in rejected["feedback"]
