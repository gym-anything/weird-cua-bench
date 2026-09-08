from __future__ import annotations

import copy
import importlib.util
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "branch_repair_env"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SETUP = _load("branch_repair_setup_test", BENCHMARK / "shared_scripts" / "setup_task.py")
MATERIALIZER = _load("branch_repair_materializer_test", BENCHMARK / "tools" / "materialize_controlled_tasks.py")
GRADER = _load("branch_repair_grader_test", BENCHMARK / "shared_runtime/server/incubator_graders/branch_repair.py")


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _base_task() -> dict:
    return _read(ENVIRONMENT / "tasks" / "branch_repair_seed_0001" / "task.json")


def _controls() -> dict:
    return _read(ENVIRONMENT / "controls.json")


def _task(level: int, interaction: str) -> dict:
    return MATERIALIZER.controlled_task(
        _base_task(), mechanic_id="branch_repair", level=level, interaction=interaction,
        profile=_controls()["difficulty"][str(level)],
        task_dir_name=f"branch_repair_d{level}_{interaction}_seed_0001",
    )


def _event(events: list[dict], kind: str, **fields) -> None:
    events.append({"sequence": len(events) + 1, "kind": kind, **fields})


def _passing_payload(public: dict, truth: dict, interaction: str) -> dict:
    events: list[dict] = []
    focus = list(public["focus"])
    source = "slice_controls" if interaction == "simplified" else "slice_scroll"
    count = int(public["slice_contract"]["index_count"])
    edges = {GRADER._edge(edge[0], edge[1]) for edge in public["initial_edges"]}

    def slice_change(axis: str, index: int, inspection: str) -> None:
        before = list(focus)
        focus["xyz".index(axis)] = index
        views = {view: GRADER._slice_records(public, focus, view) for view in GRADER.VIEWS}
        _event(
            events,
            "slice_change",
            source=source,
            axis=axis,
            index=index,
            before=before,
            focus=list(focus),
            views=views,
            digest=GRADER._views_digest(public, focus),
            topology=GRADER._topology_digest(public, focus, edges),
            inspection=inspection,
        )

    # One initial linked-view observation is enough before the first repair.
    initial_index = 0 if focus[2] != 0 else count - 1
    slice_change("z", initial_index, "initial")

    yaw, pitch = 0.0, 0.35
    orbit_source = "orbit_controls" if interaction == "simplified" else "orbit_drag"
    before = [GRADER._round(yaw), GRADER._round(pitch)]
    if interaction == "simplified":
        yaw = GRADER._round(yaw + 0.25)
        _event(events, "orbit", source=orbit_source, direction="right", before=before, after=[yaw, pitch])
    else:
        dx, dy = 11, 4
        yaw = GRADER._round(yaw + dx * 0.012)
        pitch = GRADER._round(max(-1.0, min(1.0, pitch + dy * 0.008)))
        _event(events, "orbit", source=orbit_source, dx=dx, dy=dy, before=before, after=[yaw, pitch])

    def inspect_after_edit(repair_index: int) -> None:
        axis = "xyz"[repair_index % 3]
        axis_index = "xyz".index(axis)
        slice_change(axis, (focus[axis_index] + 1) % count, "after_edit")

    for missing in truth["missing_edges"]:
        left, right = missing
        if interaction == "simplified":
            _event(events, "select_segment", source="segment_palette", node_id=left)
            _event(events, "select_segment", source="segment_palette", node_id=right)
            _event(events, "merge", source="merge_button", a=left, b=right)
        else:
            start = GRADER._project(next(node["p"] for node in public["nodes"] if node["id"] == left), yaw, pitch)
            end = GRADER._project(next(node["p"] for node in public["nodes"] if node["id"] == right), yaw, pitch)
            _event(events, "merge", source="mesh_drag_merge", a=left, b=right, start=start, end=end)
        edges.add(GRADER._edge(left, right))
        inspect_after_edit(len([event for event in events if event["kind"] in {"merge", "split"}]) - 1)
    node_map = {node["id"]: node for node in public["nodes"]}
    for false_edge in truth["false_edges"]:
        chosen: tuple[str, int, int] | None = None
        for candidate in GRADER.VIEWS:
            candidate_normal = GRADER.SLICE_AXES[candidate][2]
            for candidate_index in range(count):
                candidate_focus = list(focus)
                candidate_focus[candidate_normal] = candidate_index
                candidate_ids = {item["id"] for item in GRADER._slice_records(public, candidate_focus, candidate)}
                if false_edge[0] in candidate_ids and false_edge[1] in candidate_ids:
                    chosen = (candidate, candidate_normal, candidate_index)
                    break
            if chosen is not None:
                break
        assert chosen is not None
        view, normal, index = chosen
        if focus[normal] != index:
            before = list(focus); focus[normal] = index
            views = {candidate: GRADER._slice_records(public, focus, candidate) for candidate in GRADER.VIEWS}
            _event(
                events,
                "slice_change",
                source=source,
                axis="xyz"[normal],
                index=index,
                before=before,
                focus=list(focus),
                views=views,
                digest=GRADER._views_digest(public, focus),
                topology=GRADER._topology_digest(public, focus, edges),
                inspection="initial",
            )
        records = GRADER._slice_records(public, focus, view)
        by_id = {item["id"]: item for item in records}
        assert false_edge[0] in by_id and false_edge[1] in by_id
        seed_source = "seed_palette" if interaction == "simplified" else "slice_seed"
        red_fields = {"source": seed_source, "color": "red", "node_id": false_edge[0], "view": view}
        green_fields = {"source": seed_source, "color": "green", "node_id": false_edge[1], "view": view}
        if interaction == "full":
            red_fields["screen"] = GRADER._screen_for_record(public, view, by_id[false_edge[0]])
            green_fields["screen"] = GRADER._screen_for_record(public, view, by_id[false_edge[1]])
        _event(events, "seed", **red_fields); _event(events, "seed", **green_fields)
        _event(events, "split", source="split_button", red=false_edge[0], green=false_edge[1])
        edges.remove(GRADER._edge(false_edge[0], false_edge[1]))
        inspect_after_edit(len([event for event in events if event["kind"] in {"merge", "split"}]) - 1)
    _event(events, "submit", source="certify_button")
    slice_events = [event for event in events if event["kind"] == "slice_change"]
    return {
        "mechanic_id": "branch_repair", "task_id": public["task_id"], "challenge_id": public["challenge_id"], "interaction": interaction,
        "events": events, "final_edges": [list(edge) for edge in sorted(edges)], "focus": focus,
        "orbit": [GRADER._round(yaw), GRADER._round(pitch)],
        "summary": {
            "slice_observations": len({event["topology"] for event in slice_events}),
            "post_edit_inspections": sum(event["inspection"] == "after_edit" for event in slice_events),
            "orbit_actions": 1,
            "component_size": len(truth["target_nodes"]),
        },
    }


def test_branch_repair_is_deterministic_and_hides_construction_truth() -> None:
    public_a, truth_a = SETUP.generate_task_state(_base_task(), "branch-deterministic")
    public_b, truth_b = SETUP.generate_task_state(_base_task(), "branch-deterministic")
    public_c, truth_c = SETUP.generate_task_state(_base_task(), "branch-other")
    assert (public_a, truth_a) == (public_b, truth_b)
    assert truth_a["challenge_id"] != truth_c["challenge_id"]
    assert "true_edges" not in public_a and "missing_edges" not in public_a and "target_nodes" not in public_a


def test_branch_repair_public_identity_is_opaque_and_target_varies() -> None:
    target_fibres = set()
    for index in range(8):
        public, truth = SETUP.generate_task_state(_base_task(), f"branch-opaque-{index}")
        labels = [str(node["label"]) for node in public["nodes"]]
        identifiers = [str(node["id"]) for node in public["nodes"]]
        assert all(re.fullmatch(r"S[0-9]{3}", label) for label in labels)
        assert all(not identifier.startswith("seg-") for identifier in identifiers)
        assert not str(public["seed_segment_id"]).startswith("seg-")
        assert "node_fiber" not in public
        assert "min_slice_observations" not in truth["requirements"]
        assert "min_orbit_actions" not in truth["requirements"]
        target_fibres.add(truth["node_fiber"][truth["target_nodes"][0]])
    assert len(target_fibres) >= 2


def test_branch_repair_profiles_and_surfaces_share_the_same_world() -> None:
    for level in range(1, 6):
        simplified, simplified_truth = SETUP.generate_task_state(_task(level, "simplified"), f"branch-profile-{level}")
        full, full_truth = SETUP.generate_task_state(_task(level, "full"), f"branch-profile-{level}")
        assert simplified["nodes"] == full["nodes"]
        assert simplified["initial_edges"] == full["initial_edges"]
        assert simplified_truth["true_edges"] == full_truth["true_edges"]
        assert simplified_truth["missing_edges"] == full_truth["missing_edges"]
        assert simplified_truth["false_edges"] == full_truth["false_edges"]
        assert simplified["challenge_id"] == full["challenge_id"]
    sizes = []
    for level in range(1, 6):
        public, _ = SETUP.generate_task_state(_task(level, "full"), f"branch-size-{level}")
        sizes.append((len(public["nodes"]), public["requirements"]["repair_count"], public["slice_contract"]["index_count"]))
    assert sizes == sorted(sizes)


def test_branch_repair_grader_accepts_both_surfaces_at_all_levels() -> None:
    for level in range(1, 6):
        for interaction in ("simplified", "full"):
            public, truth = SETUP.generate_task_state(_task(level, interaction), f"branch-grade-{level}-{interaction}")
            payload = _passing_payload(public, truth, interaction)
            grade = GRADER.grade(payload, truth, public)
            assert grade["passed"] is True, (level, interaction, grade)
            broken = copy.deepcopy(payload)
            inspection_index = next(index for index, event in enumerate(broken["events"]) if event.get("inspection") == "after_edit")
            del broken["events"][inspection_index]
            for sequence, event in enumerate(broken["events"], 1):
                event["sequence"] = sequence
            assert GRADER.grade(broken, truth, public)["passed"] is False
            wrong = copy.deepcopy(payload)
            wrong["interaction"] = "full" if interaction == "simplified" else "simplified"
            assert GRADER.grade(wrong, truth, public)["passed"] is False
            wrong_task = copy.deepcopy(payload); wrong_task["task_id"] = "another-task@0.1"
            assert GRADER.grade(wrong_task, truth, public)["passed"] is False
            stale = copy.deepcopy(payload); stale["challenge_id"] = "stale"
            assert GRADER.grade(stale, truth, public)["passed"] is False
