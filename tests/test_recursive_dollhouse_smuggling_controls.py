from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "weird_captcha_gym"
ENVIRONMENT = BENCHMARK / "environments" / "recursive_dollhouse_smuggling_env"
MECHANIC = "recursive_dollhouse_smuggling"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SETUP = _load("recursive_dollhouse_control_setup", BENCHMARK / "shared_scripts" / "setup_task.py")
MATERIALIZER = _load("recursive_dollhouse_control_materializer", BENCHMARK / "tools" / "materialize_controlled_tasks.py")
GRADER = _load("recursive_dollhouse_control_grader", BENCHMARK / "shared_runtime" / "server" / "incubator_graders" / f"{MECHANIC}.py")
CONTROLS = json.loads((ENVIRONMENT / "controls.json").read_text(encoding="utf-8"))
BASE_TASK = json.loads((ENVIRONMENT / "tasks" / f"{MECHANIC}_seed_0001" / "task.json").read_text(encoding="utf-8"))


def _task(level: int, interaction: str) -> dict:
    return MATERIALIZER.controlled_task(
        BASE_TASK,
        mechanic_id=MECHANIC,
        level=level,
        interaction=interaction,
        profile=CONTROLS["difficulty"][str(level)],
        task_dir_name=f"{MECHANIC}_d{level}_{interaction}_seed_0001",
    )


def _without_control_identity(value: dict) -> dict:
    result = copy.deepcopy(value)
    for field in ("task_id", "challenge_id", "control_condition"):
        result.pop(field, None)
    return result


def _project(view: dict, point: list[float]) -> list[float]:
    matrix, origin = view["matrix"], view["origin"]
    return [
        origin[0] + matrix[0][0] * point[0] + matrix[0][1] * point[1],
        origin[1] + matrix[1][0] * point[0] + matrix[1][1] * point[1],
    ]


def _accepted_payload(public: dict, truth: dict, interaction: str) -> dict:
    views = {view["id"]: view for view in truth["views"]}
    gates = ([truth["gate"]] if truth.get("gate") else []) + list(truth.get("additional_gates") or [])
    centers = {gate["id"]: list(gate["center"]) for gate in gates}
    parked = {
        gate["id"]
        for gate in gates
        if gate.get("initially_parked")
    }
    parcel_center = list(truth["parcel"]["initial_center"])
    scale = int(truth["parcel"]["initial_scale"])
    events: list[dict] = []
    views_used: set[str] = set()
    transitions: list[str] = []
    source = "route_card" if interaction == "simplified" else "direct_canvas"

    def emit(kind: str, **details: object) -> None:
        events.append({"sequence": len(events) + 1, "kind": kind, **details})

    def surface(proxy_action: str | None) -> dict:
        value = {"input_source": source}
        if proxy_action is not None:
            value["proxy_action"] = proxy_action
        return value

    def drag(entity: str, view_id: str, start: list[float], waypoints: list[list[float]], *, gate_id: str | None, proxy_action: str) -> None:
        nonlocal parcel_center
        view = views[view_id]
        emit("drag_start", entity=entity, view_id=view_id, screen=_project(view, start), canonical=start, **({"gate_id": gate_id} if gate_id else {}), **surface(proxy_action if interaction == "simplified" else None))
        views_used.add(view_id)
        for point in waypoints:
            emit("drag_sample", entity=entity, view_id=view_id, screen=_project(view, point), canonical=point, center=point, accepted=True, **({"gate_id": gate_id} if gate_id else {}), **surface(proxy_action if interaction == "simplified" else None))
        final = waypoints[-1] if waypoints else start
        emit("drag_end", entity=entity, center=final, **({"gate_id": gate_id} if gate_id else {}), **surface(proxy_action if interaction == "simplified" else None))
        if entity == "gate":
            centers[gate_id] = final
        else:
            parcel_center = final

    required_gates = truth["requirements"].get("required_gate_ids") or (["gate"] if truth.get("gate") else [])
    for gate in gates:
        gate_id = gate["id"]
        if gate_id not in required_gates or gate_id in parked:
            continue
        drag("gate", gate["movable_in_view"], centers[gate_id], truth["solver_waypoints"][gate_id], gate_id=gate_id, proxy_action=f"park:{gate_id}")
        emit("gate_parked", gate_id=gate_id, **surface(f"park:{gate_id}" if interaction == "simplified" else None))
        parked.add(gate_id)

    required_portals = truth["requirements"].get("required_portal_ids") or ["frame-mini-human", "frame-human-giant"]
    while scale < int(truth["bay"]["scale"]):
        view_id = ("mini", "human", "giant")[scale]
        start = parcel_center
        drag("parcel", view_id, start, truth["solver_waypoints"][f"scale_{scale}"], gate_id=None, proxy_action=f"carry:{scale}")
        portal = next(item for item in truth["portals"] if item["from_scale"] == scale)
        emit("portal_transition", portal_id=portal["id"], from_scale=scale, to_scale=scale + 1, **surface(f"carry:{scale}" if interaction == "simplified" else None))
        transitions.append(portal["id"])
        scale += 1
    drag("parcel", "giant", parcel_center, truth["solver_waypoints"]["scale_2"], gate_id=None, proxy_action=f"carry:{scale}")
    emit("delivery", **surface(f"carry:{scale}" if interaction == "simplified" else None))
    return {
        "mechanic_id": MECHANIC,
        "task_id": public["task_id"],
        "challenge_id": public["challenge_id"],
        "events": events,
        "delivered": True,
        "parcel_scale": scale,
        "portal_ids": transitions,
        "gate_parked": "gate" in parked,
        "gate_parked_ids": sorted(parked),
        "collisions": 0,
        "resets": 0,
        "views_used": sorted(views_used),
        "parcel_center": [round(value, 3) for value in parcel_center],
        "gate_center": [round(value, 3) for value in centers.get("gate", [0, 0])],
    }


def test_recursive_dollhouse_controls_preserve_l4_and_bind_interaction() -> None:
    MATERIALIZER.validate_controls(CONTROLS, ENVIRONMENT)
    assert CONTROLS["baseline"] == {"difficulty": 4, "interaction": "full", "real_time": "live"}
    for seed in ("recursive-dollhouse-baseline-a", "recursive-dollhouse-baseline-b"):
        original_public, original_truth = SETUP.generate_task_state(BASE_TASK, seed)
        baseline_public, baseline_truth = SETUP.generate_task_state(_task(4, "full"), seed)
        assert original_public["challenge_id"] == baseline_public["challenge_id"]
        assert _without_control_identity(original_public) == _without_control_identity(baseline_public)
        assert _without_control_identity(original_truth) == _without_control_identity(baseline_truth)

    for level in range(1, 6):
        simplified_public, simplified_truth = SETUP.generate_task_state(_task(level, "simplified"), f"recursive-dollhouse-{level}")
        full_public, full_truth = SETUP.generate_task_state(_task(level, "full"), f"recursive-dollhouse-{level}")
        assert simplified_public["challenge_id"] == full_public["challenge_id"]
        assert _without_control_identity(simplified_public) == _without_control_identity(full_public)
        assert _without_control_identity(simplified_truth) == _without_control_identity(full_truth)
        for public, truth, interaction in ((simplified_public, simplified_truth, "simplified"), (full_public, full_truth, "full")):
            payload = _accepted_payload(public, truth, interaction)
            accepted = GRADER.grade(payload, truth, public)
            assert accepted["passed"] is True, accepted
            wrong_surface = copy.deepcopy(payload)
            for event in wrong_surface["events"]:
                if "input_source" in event:
                    event["input_source"] = "direct_canvas" if interaction == "simplified" else "route_card"
            rejected = GRADER.grade(wrong_surface, truth, public)
            assert rejected["passed"] is False


def test_recursive_dollhouse_l3_requires_an_easier_gate_clearance_than_l4() -> None:
    l2_public, _ = SETUP.generate_task_state(_task(2, "full"), "recursive-dollhouse-ladder")
    l3_public, l3_truth = SETUP.generate_task_state(_task(3, "full"), "recursive-dollhouse-ladder")
    l4_public, l4_truth = SETUP.generate_task_state(_task(4, "full"), "recursive-dollhouse-ladder")

    assert "gate" not in l2_public
    assert l3_public["requirements"]["required_gate_ids"] == ["gate"]
    assert l3_public["gate"].get("initially_parked") is None
    assert l3_public["gate"]["center"] == [28, 50]
    assert l3_public["gate"]["size"] == [4, 12]
    assert l3_public["parking"]["size"] == [16, 24]
    assert l3_public["requirements"]["collision_substep"] > l4_public["requirements"]["collision_substep"]
    assert l4_public["gate"]["size"] == [6, 16]
    assert l4_public["parking"]["size"] == [13, 20]

    missing_clearance = _accepted_payload(l3_public, l3_truth, "full")
    missing_clearance["events"] = [
        event
        for event in missing_clearance["events"]
        if event.get("entity") != "gate" and event.get("kind") != "gate_parked"
    ]
    for sequence, event in enumerate(missing_clearance["events"], 1):
        event["sequence"] = sequence
    missing_clearance["gate_parked"] = False
    missing_clearance["gate_parked_ids"] = []
    rejected = GRADER.grade(missing_clearance, l3_truth, l3_public)
    assert rejected["passed"] is False
