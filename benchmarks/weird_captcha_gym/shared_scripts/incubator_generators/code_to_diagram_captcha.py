from __future__ import annotations

import hashlib
import random
from typing import Any


MECHANIC_ID = "code_to_diagram_captcha"
PALETTES = ("oxide", "cyanotype", "signal")
NODE_POSITIONS = (
    (13, 16), (46, 16), (79, 16),
    (13, 50), (46, 50), (79, 50),
    (13, 84), (46, 84), (79, 84),
)
PROBE_DOMAIN = tuple(range(-15, 33))


def _seed_int(seed: str, salt: str) -> int:
    digest = hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _node_ids(rng: random.Random) -> list[str]:
    letters = list("ABCDEFGHJKLMNPQRSTUVWXYZ")
    digits = list("23456789") * 2
    rng.shuffle(letters)
    rng.shuffle(digits)
    return [f"{letters[index]}{digits[index]}" for index in range(9)]


def _condition(rng: random.Random) -> dict[str, Any]:
    kind = rng.choice(("gte", "lt", "even", "mod3"))
    if kind == "gte":
        threshold = rng.randint(-2, 12)
        return {"kind": kind, "value": threshold, "display": f"acc >= {threshold}"}
    if kind == "lt":
        threshold = rng.randint(-1, 11)
        return {"kind": kind, "value": threshold, "display": f"acc < {threshold}"}
    if kind == "even":
        return {"kind": kind, "value": 0, "display": "acc % 2 == 0"}
    residue = rng.randint(0, 2)
    return {"kind": kind, "value": residue, "display": f"acc % 3 == {residue}"}


def _condition_result(condition: dict[str, Any], value: int) -> bool:
    kind = condition["kind"]
    target = int(condition["value"])
    if kind == "gte":
        return value >= target
    if kind == "lt":
        return value < target
    if kind == "even":
        return value % 2 == 0
    return value % 3 == target


def _trace(nodes: list[dict[str, Any]], entry_id: str, probe: int) -> dict[str, Any]:
    by_id = {str(node["id"]): node for node in nodes}
    current = entry_id
    accumulator = probe
    steps: list[dict[str, Any]] = []
    for sequence in range(1, 14):
        node = by_id[current]
        before = accumulator
        kind = str(node["kind"])
        if kind == "entry":
            accumulator = probe
            branch = "NEXT"
        elif kind == "decision":
            branch = "TRUE" if _condition_result(node["condition"], accumulator) else "FALSE"
        elif kind in {"operation", "merge"}:
            amount = int(node["amount"])
            accumulator = accumulator + amount if node["operator"] == "add" else accumulator - amount
            branch = "NEXT"
        elif kind == "audit":
            accumulator = accumulator * int(node["multiplier"]) + int(node.get("bias", 0))
            branch = "NEXT"
        elif kind == "halt":
            branch = "HALT"
        else:
            raise AssertionError(f"unknown node kind {kind}")
        next_node = (node.get("transitions") or {}).get(branch)
        steps.append({
            "sequence": sequence,
            "node_id": current,
            "value_before": before,
            "value_after": accumulator,
            "branch": branch,
            "next_node_id": next_node,
        })
        if branch == "HALT":
            return {"input": probe, "steps": steps, "halted": True, "output": accumulator}
        if not next_node:
            raise AssertionError("generated control-flow program did not halt")
        current = str(next_node)
    raise AssertionError("generated control-flow program exceeded replay bound")


def _branch_pair(first: dict[str, Any], second: dict[str, Any], probe: int, add_amount: int, subtract_amount: int) -> tuple[bool, bool]:
    first_branch = _condition_result(first, probe)
    accumulator = probe + add_amount if first_branch else probe - subtract_amount
    return first_branch, _condition_result(second, accumulator)


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed_int(seed, MECHANIC_ID))
    ids = _node_ids(rng)
    entry_id, gate_one_id, true_id, false_id, gate_two_id, audit_a_id, audit_b_id, merge_id, halt_id = ids

    # Admit only programs for which four probes can expose all four combinations
    # of the two transient branches. This is structural coverage, not a quota.
    for _ in range(400):
        condition_one = _condition(rng)
        condition_two = _condition(rng)
        true_amount = rng.randint(2, 9)
        false_amount = rng.randint(2, 9)
        groups: dict[tuple[bool, bool], list[int]] = {(a, b): [] for a in (False, True) for b in (False, True)}
        for probe in PROBE_DOMAIN:
            groups[_branch_pair(condition_one, condition_two, probe, true_amount, false_amount)].append(probe)
        if all(groups.values()):
            break
    else:
        raise AssertionError("could not generate a fully observable two-gate controller")

    audit_a_multiplier = rng.choice((2, 3))
    audit_a_bias = rng.choice((-2, -1, 1, 2))
    audit_b_multiplier = rng.choice((-2, -1))
    audit_b_bias = rng.choice((-3, -1, 1, 3))
    merge_amount = rng.choice((2, 3, 4, 5))
    nodes: list[dict[str, Any]] = [
        {"id": entry_id, "kind": "entry", "title": "ENTRY", "code": f"acc <- probe   GOTO {gate_one_id}", "transitions": {"NEXT": gate_one_id}, "ports": ["NEXT"]},
        {"id": gate_one_id, "kind": "decision", "title": "GATE α", "code": f"IF {condition_one['display']}   T:{true_id} / F:{false_id}", "condition": condition_one, "transitions": {"TRUE": true_id, "FALSE": false_id}, "ports": ["TRUE", "FALSE"]},
        {"id": true_id, "kind": "operation", "title": "TRUE BAY", "code": f"acc <- acc + {true_amount}   GOTO {gate_two_id}", "operator": "add", "amount": true_amount, "transitions": {"NEXT": gate_two_id}, "ports": ["NEXT"]},
        {"id": false_id, "kind": "operation", "title": "FALSE BAY", "code": f"acc <- acc - {false_amount}   GOTO {gate_two_id}", "operator": "subtract", "amount": false_amount, "transitions": {"NEXT": gate_two_id}, "ports": ["NEXT"]},
        {"id": gate_two_id, "kind": "decision", "title": "GATE β", "code": f"IF {condition_two['display']}   T:{audit_a_id} / F:{audit_b_id}", "condition": condition_two, "transitions": {"TRUE": audit_a_id, "FALSE": audit_b_id}, "ports": ["TRUE", "FALSE"]},
        {"id": audit_a_id, "kind": "audit", "title": "AUDIT A", "code": f"acc <- acc * {audit_a_multiplier} {audit_a_bias:+d}   GOTO {merge_id}", "multiplier": audit_a_multiplier, "bias": audit_a_bias, "transitions": {"NEXT": merge_id}, "ports": ["NEXT"]},
        {"id": audit_b_id, "kind": "audit", "title": "AUDIT B", "code": f"acc <- acc * {audit_b_multiplier} {audit_b_bias:+d}   GOTO {merge_id}", "multiplier": audit_b_multiplier, "bias": audit_b_bias, "transitions": {"NEXT": merge_id}, "ports": ["NEXT"]},
        {"id": merge_id, "kind": "merge", "title": "CHECKSUM", "code": f"acc <- acc + {merge_amount}   GOTO {halt_id}", "operator": "add", "amount": merge_amount, "transitions": {"NEXT": halt_id}, "ports": ["NEXT"]},
        {"id": halt_id, "kind": "halt", "title": "EMIT", "code": "HALT / EMIT acc", "transitions": {}, "ports": []},
    ]

    positions = list(NODE_POSITIONS)
    rng.shuffle(positions)
    for index, node in enumerate(nodes):
        node["x"], node["y"] = positions[index]

    probe_inputs = [rng.choice(groups[key]) for key in ((False, False), (False, True), (True, False), (True, True))]
    rng.shuffle(probe_inputs)
    probe_runs = [_trace(nodes, entry_id, probe) for probe in probe_inputs]

    expected_edges = [
        {"from_port": f"{node['id']}:{label}", "label": label, "to_node": str(target)}
        for node in nodes
        for label, target in (node.get("transitions") or {}).items()
    ]
    expected_edges.sort(key=lambda edge: edge["from_port"])

    public_nodes: list[dict[str, Any]] = []
    for node in nodes:
        visible = {key: value for key, value in node.items() if key not in {"transitions", "code"}}
        if node["kind"] == "entry":
            visible["code"] = "acc <- probe   DISPATCH NEXT"
        elif node["kind"] == "decision":
            visible["code"] = f"IF {node['condition']['display']}   DISPATCH TRUE / FALSE"
        elif node["kind"] in {"operation", "merge"}:
            sign = "+" if node["operator"] == "add" else "-"
            visible["code"] = f"acc <- acc {sign} {node['amount']}   DISPATCH NEXT"
        elif node["kind"] == "audit":
            visible["code"] = f"acc <- acc * {node['multiplier']} {int(node.get('bias', 0)):+d}   DISPATCH NEXT"
        else:
            visible["code"] = "HALT / EMIT acc"
        public_nodes.append(visible)

    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}".encode("utf-8")).hexdigest()[:12]
    task_id = str(task.get("id") or "")
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language") or "Probe the transient controller, then reconstruct its directed patch field.",
        "asset_manifest": "shared_runtime/assets/provenance/incubator_full_build_v1.json",
        "generator": {"name": "dual_gate_transient_wiring_lab_v2", "variant_count": 18_000_000_000},
        "palette": rng.choice(PALETTES),
        "program_id": f"CF-{challenge_id.upper()}",
        "entry_id": entry_id,
        "nodes": public_nodes,
        "probe_inputs": probe_inputs,
        # Trace frames are revealed one physical debugger step at a time. The
        # static plugin seam necessarily keeps them in page state; the grader
        # independently simulates the private program and trusts none of them.
        "runtime_probe_runs": probe_runs,
        "required_probe_count": len(probe_inputs),
        "expected_edge_count": len(expected_edges),
        "submit_label": "VALIDATE HARNESS",
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "entry_id": entry_id,
        "nodes": nodes,
        "node_ids": sorted(ids),
        "probe_inputs": probe_inputs,
        "expected_probe_runs": probe_runs,
        "expected_edges": expected_edges,
        "variant_count": 18_000_000_000,
    }
    covered = {step["node_id"] for run in probe_runs for step in run["steps"]}
    branch_pairs = {
        tuple(step["branch"] for step in run["steps"] if step["node_id"] in {gate_one_id, gate_two_id})
        for run in probe_runs
    }
    assert covered == set(ids)
    assert branch_pairs == {("FALSE", "FALSE"), ("FALSE", "TRUE"), ("TRUE", "FALSE"), ("TRUE", "TRUE")}
    assert len(expected_edges) == 10 and len(probe_inputs) == 4 and all(len(run["steps"]) == 7 for run in probe_runs)
    return public_state, ground_truth
