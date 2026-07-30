from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "tomographic_baggage_surgery_env"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SETUP = _load("tomography_control_setup", BENCHMARK / "shared_scripts" / "setup_task.py")
MATERIALIZER = _load("tomography_control_materializer", BENCHMARK / "tools" / "materialize_controlled_tasks.py")
GRADER = _load(
    "tomography_control_grader",
    BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / "tomographic_baggage_surgery.py",
)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _base_task() -> dict:
    return _read(ENVIRONMENT / "tasks" / "tomographic_baggage_surgery_seed_0001" / "task.json")


def _controls() -> dict:
    return _read(ENVIRONMENT / "controls.json")


def _task(level: int, interaction: str = "simplified") -> dict:
    return MATERIALIZER.controlled_task(
        _base_task(),
        mechanic_id="tomographic_baggage_surgery",
        level=level,
        interaction=interaction,
        profile=_controls()["difficulty"][str(level)],
        task_dir_name=f"tomographic_baggage_surgery_d{level}_{interaction}_seed_0001",
    )


def _without_identity(value: dict) -> dict:
    result = copy.deepcopy(value)
    for field in ("task_id", "challenge_id", "control_condition"):
        result.pop(field, None)
    return result


def _screen(view: dict, coordinate: list[float]) -> list[float]:
    axis = {"x": 0, "y": 1, "z": 2}
    return [
        round(view["center"][index] + view["scale"] * view["signs"][index] * coordinate[axis[name]], 4)
        for index, name in enumerate(view["axes"])
    ]


def _world_x(target: list[float], rotation: int) -> float:
    x, _, z = target
    return (x, z, -x, -z)[rotation % 4]


def _passing_payload(public: dict, truth: dict, interaction: str) -> dict:
    scan_source = {"simplified": "slice_controls", "full": "direct_slice_drag"}[interaction]
    rotation_source = {"simplified": "case_rotate_button", "full": "case_handle_drag"}[interaction]
    target = [float(value) for value in truth["solver"]["target"]]
    safe_y = float(truth["solver"]["safe_y"])
    requirements = truth["requirements"]
    events: list[dict] = []

    def append(kind: str, **details) -> None:
        events.append({"sequence": len(events) + 1, "kind": kind, **details})

    rotations = max(int(requirements["min_rotations"]), int(requirements["min_target_observations"]))
    observed = 0
    for rotation in range(rotations):
        if rotation:
            append("rotate_case", **{"from": rotation - 1, "to": rotation, "input_source": rotation_source})
        hot_offset = _world_x(target, rotation)
        records = GRADER.intersection_records(truth, "x", hot_offset, rotation)
        append(
            "slice_observation",
            axis="x",
            offset=hot_offset,
            rotation=rotation,
            records=records,
            digest=GRADER._digest(records),
            input_source=scan_source,
        )
        observed += 1
        if rotation == 0:
            records = GRADER.intersection_records(truth, "x", -2.5, rotation)
            append(
                "slice_observation",
                axis="x",
                offset=-2.5,
                rotation=rotation,
                records=records,
                digest=GRADER._digest(records),
                input_source=scan_source,
            )
            observed += 1
    while observed < int(requirements["min_observations"]):
        records = GRADER.intersection_records(truth, "x", 2.5, rotations - 1)
        append(
            "slice_observation",
            axis="x",
            offset=2.5,
            rotation=rotations - 1,
            records=records,
            digest=GRADER._digest(records),
            input_source=scan_source,
        )
        observed += 1
    append("lock_case", from_rotation=rotations - 1, rotation=0)

    initial = [float(value) for value in truth["probe"]["initial"]]
    top = truth["views"]["top"]
    append("probe_drag_start", view_id="top", screen=_screen(top, initial))
    top_point = [target[0], safe_y, target[2]]
    append("probe_sample", view_id="top", screen=_screen(top, top_point), coordinate=top_point, accepted=True)
    append("probe_drag_end", view_id="top")
    front = truth["views"]["front"]
    append("probe_drag_start", view_id="front", screen=_screen(front, top_point))
    append("probe_sample", view_id="front", screen=_screen(front, target), coordinate=target, accepted=True)
    append("probe_drag_end", view_id="front")
    if int(requirements.get("min_views", 2)) >= 3:
        side = truth["views"]["side"]
        append("probe_drag_start", view_id="side", screen=_screen(side, target))
        if int(requirements.get("min_moving_views", 0)) >= 3:
            append("probe_sample", view_id="side", screen=_screen(side, top_point), coordinate=top_point, accepted=True)
            append("probe_sample", view_id="side", screen=_screen(side, target), coordinate=target, accepted=True)
        append("probe_drag_end", view_id="side")
    append("capture")
    append("probe_drag_start", view_id="front", screen=_screen(front, target))
    append("probe_sample", view_id="front", screen=_screen(front, top_point), coordinate=top_point, accepted=True)
    append("probe_drag_end", view_id="front")
    append("withdrawal")
    target_rotations = sorted({event["rotation"] for event in events if event["kind"] == "slice_observation" and any(record["id"] == truth["target_id"] for record in event["records"])})
    payload = {
        "mechanic_id": public["mechanic_id"],
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "interaction": interaction,
        "events": events,
        "extracted": True,
        "captured": True,
        "probe": [round(value, 4) for value in top_point],
        "observations": observed,
        "rotations": list(range(rotations)),
        "target_observations": rotations,
        "damages": 0,
        "resets": 0,
        "views_used": ["front", "side", "top"] if int(requirements.get("min_views", 2)) >= 3 else ["front", "top"],
    }
    if "min_target_rotations" in requirements:
        payload["target_rotations"] = target_rotations
    if "min_moving_views" in requirements:
        payload["moving_views"] = ["front", "side", "top"] if int(requirements["min_moving_views"]) >= 3 else ["front", "top"]
    return payload


def _with_shared_y_plane(payload: dict, truth: dict, interaction: str) -> dict:
    result = copy.deepcopy(payload)
    source = {"simplified": "slice_controls", "full": "direct_slice_drag"}[interaction]
    insertion_index = next(
        index
        for index, event in enumerate(result["events"])
        if event["kind"] in {"rotate_case", "lock_case"}
    )
    # Zero is inside every generated target's Y extent and is one of the
    # visible 0.25-plane increments, so both input surfaces can reproduce it.
    records = GRADER.intersection_records(truth, "y", 0.0, 0)
    result["events"].insert(
        insertion_index,
        {
            "kind": "slice_observation",
            "axis": "y",
            "offset": 0.0,
            "rotation": 0,
            "records": records,
            "digest": GRADER._digest(records),
            "input_source": source,
        },
    )
    for sequence, event in enumerate(result["events"], 1):
        event["sequence"] = sequence
    result["observations"] += 1
    result["target_observations"] += 1
    return result


def test_tomography_controls_materialize_and_preserve_the_historical_l3_world(tmp_path: Path) -> None:
    controls = _controls()
    MATERIALIZER.validate_controls(controls, ENVIRONMENT)
    written = MATERIALIZER.materialize_environment(ENVIRONMENT, tmp_path)
    assert len(written) == 10

    for seed in ("tomography-baseline-a", "tomography-baseline-b"):
        original_public, original_truth = SETUP.generate_task_state(_base_task(), seed)
        baseline_public, baseline_truth = SETUP.generate_task_state(_task(3), seed)
        assert _without_identity(baseline_public) == _without_identity(original_public)
        assert _without_identity(baseline_truth) == _without_identity(original_truth)
        original_payload = _passing_payload(original_public, original_truth, "simplified")
        baseline_payload = _passing_payload(baseline_public, baseline_truth, "simplified")
        assert GRADER.grade(baseline_payload, baseline_truth, baseline_public) == GRADER.grade(
            original_payload, original_truth, original_public
        )


def test_tomography_profiles_change_active_geometry_and_keep_interaction_worlds_equal() -> None:
    expected_neutral_counts = [1, 2, 3, 3, 5]
    expected_target_radii = [.72, .66, .56, .56, .5]
    for level, (neutral_count, radius) in enumerate(zip(expected_neutral_counts, expected_target_radii), start=1):
        simplified_public, simplified_truth = SETUP.generate_task_state(
            _task(level, "simplified"), f"tomography-profile-{level}"
        )
        full_public, full_truth = SETUP.generate_task_state(
            _task(level, "full"), f"tomography-profile-{level}"
        )
        assert len(simplified_public["solids"]) == neutral_count + 1
        target = next(solid for solid in simplified_public["solids"] if solid["material"] == "hot")
        assert target["radius"] == radius
        simplified_world = _without_identity(simplified_public)
        full_world = _without_identity(full_public)
        simplified_world.pop("prompt", None)
        full_world.pop("prompt", None)
        assert simplified_world == full_world
        simplified_truth_world = _without_identity(simplified_truth)
        full_truth_world = _without_identity(full_truth)
        simplified_truth_world.pop("prompt", None)
        full_truth_world.pop("prompt", None)
        assert simplified_truth_world == full_truth_world
    l1_public, _ = SETUP.generate_task_state(_task(1), "tomography-profile-order")
    l3_public, l3_truth = SETUP.generate_task_state(_task(3), "tomography-profile-order")
    l4_public, l4_truth = SETUP.generate_task_state(_task(4), "tomography-profile-order")
    l5_public, _ = SETUP.generate_task_state(_task(5), "tomography-profile-order")
    assert l1_public["requirements"]["min_rotations"] < l5_public["requirements"]["min_rotations"]
    assert l1_public["requirements"].get("min_views", 2) < l5_public["requirements"].get("min_views", 2)
    assert l3_public["solids"] == l4_public["solids"]
    assert l3_truth["probe"] == l4_truth["probe"]
    assert "min_target_rotations" not in l3_public["requirements"]
    assert "min_moving_views" not in l3_public["requirements"]
    assert l4_public["requirements"]["min_target_rotations"] == 2
    assert l4_public["requirements"]["min_moving_views"] == 2
    assert l5_public["requirements"]["min_target_rotations"] == 3
    assert l5_public["requirements"]["min_moving_views"] == 3


def test_tomography_grader_binds_every_difficulty_and_interaction_surface() -> None:
    for level in range(1, 6):
        for interaction in ("simplified", "full"):
            public, truth = SETUP.generate_task_state(
                _task(level, interaction), f"tomography-grader-d{level}-{interaction}"
            )
            payload = _passing_payload(public, truth, interaction)
            accepted = GRADER.grade(payload, truth, public)
            assert accepted["passed"] is True, (level, interaction, accepted)
            wrong_mode = copy.deepcopy(payload)
            wrong_mode["interaction"] = "full" if interaction == "simplified" else "simplified"
            assert GRADER.grade(wrong_mode, truth, public)["passed"] is False
            wrong_source = copy.deepcopy(payload)
            scan = next(event for event in wrong_source["events"] if event["kind"] == "slice_observation")
            scan["input_source"] = "direct_slice_drag" if interaction == "simplified" else "slice_controls"
            assert GRADER.grade(wrong_source, truth, public)["feedback"] == "slice sweep uses the wrong interaction input"


def test_tomography_y_plane_has_equal_records_on_both_visible_interaction_surfaces() -> None:
    simplified_public, simplified_truth = SETUP.generate_task_state(
        _task(4, "simplified"), "tomography-y-plane-equivalence"
    )
    full_public, full_truth = SETUP.generate_task_state(
        _task(4, "full"), "tomography-y-plane-equivalence"
    )
    simplified_payload = _with_shared_y_plane(
        _passing_payload(simplified_public, simplified_truth, "simplified"),
        simplified_truth,
        "simplified",
    )
    full_payload = _with_shared_y_plane(
        _passing_payload(full_public, full_truth, "full"), full_truth, "full"
    )
    simplified_y = next(event for event in simplified_payload["events"] if event.get("axis") == "y")
    full_y = next(event for event in full_payload["events"] if event.get("axis") == "y")
    assert {key: simplified_y[key] for key in ("axis", "offset", "rotation", "records", "digest")} == {
        key: full_y[key] for key in ("axis", "offset", "rotation", "records", "digest")
    }
    assert simplified_y["input_source"] == "slice_controls"
    assert full_y["input_source"] == "direct_slice_drag"
    assert GRADER.grade(simplified_payload, simplified_truth, simplified_public)["passed"] is True
    assert GRADER.grade(full_payload, full_truth, full_public)["passed"] is True


def test_l3_preserves_the_historical_same_orientation_hot_proof_but_l4_l5_reject_it() -> None:
    def concentrate_hot_slices_at_first_rotation(payload: dict, truth: dict) -> dict:
        reduced = copy.deepcopy(payload)
        hot_slices = [
            event
            for event in reduced["events"]
            if event["kind"] == "slice_observation"
            and any(record["id"] == truth["target_id"] for record in event["records"])
        ]
        assert len(hot_slices) >= 2
        first_rotation = int(hot_slices[0]["rotation"])
        insertion_index = next(index for index, event in enumerate(reduced["events"]) if event["kind"] == "rotate_case")
        target_offset = float(hot_slices[0]["offset"])
        source = str(hot_slices[0]["input_source"])
        for index in range(1, len(hot_slices)):
            offset = target_offset + .2 * index
            records = GRADER.intersection_records(truth, "x", offset, first_rotation)
            reduced["events"].insert(
                insertion_index,
                {
                    "kind": "slice_observation",
                    "axis": "x",
                    "offset": offset,
                    "rotation": first_rotation,
                    "records": records,
                    "digest": GRADER._digest(records),
                    "input_source": source,
                },
            )
            insertion_index += 1
        for event in hot_slices[1:]:
            event["offset"] = -2.5
            event["records"] = GRADER.intersection_records(truth, "x", -2.5, int(event["rotation"]))
            event["digest"] = GRADER._digest(event["records"])
        for sequence, event in enumerate(reduced["events"], 1):
            event["sequence"] = sequence
        observed = [event for event in reduced["events"] if event["kind"] == "slice_observation"]
        target_events = [
            event for event in observed if any(record["id"] == truth["target_id"] for record in event["records"])
        ]
        reduced["observations"] = len(observed)
        reduced["target_observations"] = len({(event["rotation"], event["axis"], event["offset"]) for event in target_events})
        if "target_rotations" in reduced:
            reduced["target_rotations"] = [first_rotation]
        return reduced

    l3_public, l3_truth = SETUP.generate_task_state(_task(3), "tomography-l3-historical-proof")
    l3_payload = concentrate_hot_slices_at_first_rotation(_passing_payload(l3_public, l3_truth, "simplified"), l3_truth)
    assert GRADER.grade(l3_payload, l3_truth, l3_public)["passed"] is True

    l4_public, l4_truth = SETUP.generate_task_state(_task(4), "tomography-l4-hot-rotation-proof")
    l4_payload = concentrate_hot_slices_at_first_rotation(_passing_payload(l4_public, l4_truth, "simplified"), l4_truth)
    assert GRADER.grade(l4_payload, l4_truth, l4_public)["passed"] is False

    l5_public, l5_truth = SETUP.generate_task_state(_task(5), "tomography-l5-hot-rotation-proof")
    l5_payload = concentrate_hot_slices_at_first_rotation(_passing_payload(l5_public, l5_truth, "simplified"), l5_truth)
    assert GRADER.grade(l5_payload, l5_truth, l5_public)["passed"] is False


def test_l5_requires_a_nonzero_probe_move_in_each_registered_view() -> None:
    public, truth = SETUP.generate_task_state(_task(5), "tomography-l5-moving-views")
    payload = _passing_payload(public, truth, "simplified")
    payload["events"] = [
        event for event in payload["events"]
        if not (event.get("kind") == "probe_sample" and event.get("view_id") == "side")
    ]
    for sequence, event in enumerate(payload["events"], 1):
        event["sequence"] = sequence
    payload["moving_views"] = ["front", "top"]
    assert GRADER.grade(payload, truth, public)["passed"] is False


def test_tomography_negative_zero_replay_normalization_is_representation_only() -> None:
    assert GRADER._round(-0.00001) == 0.0
    assert GRADER._round(-0.00011) == -0.0001
    assert GRADER._round(0.00011) == 0.0001
