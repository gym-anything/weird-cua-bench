from __future__ import annotations

import hashlib
import random
from typing import Any


MECHANIC_ID = "exit_vim_terminal_escape"
CALLSIGNS = ("MOTH", "KITE", "EMBER", "NOVA", "RAVEN", "MICA", "ORBIT", "LATCH")
ROUTES = ("NORTH-7", "BAY-12", "VAULT-3", "RING-9", "ECHO-4", "DOCK-8")
TOKENS = ("K7Q2", "V4MX", "P9RA", "D2WN", "H8LC", "T5ZF", "B3JK")
WINDOWS = ("03:14", "05:40", "08:25", "11:50", "17:05", "22:30")
CIPHERS = ("SABLE", "MERCURY", "CINDER", "GLASS", "FERN", "COBALT")
PORTS = ("2049", "3321", "4180", "6077", "7443", "8812")
LAYER_NAMES = ("pager", "job", "ssh", "mux")
EXTENDED_TARGETS = (
    ("AGENT", CALLSIGNS),
    ("ROUTE", ROUTES),
    ("TOKEN", TOKENS),
    ("WINDOW", WINDOWS),
    ("CIPHER", CIPHERS),
    ("PORT", PORTS),
    ("SECTOR", ("ALPHA-2", "BRAVO-6", "DELTA-4", "GAMMA-8", "OMEGA-1", "SIGMA-5")),
    ("PROTOCOL", ("LOCKSTEP", "NIGHTFALL", "RELAY-7", "SILENT-ARC", "TWIN-KEY", "WITNESS")),
)
REFERENCE_SPECS = (
    ("dispatch.ref", (0, 3), "UPLINK DISPATCH / TWO AUTHORITATIVE FIELDS"),
    ("seal.ref", (1, 4), "SEALED ROUTING NOTE / TWO AUTHORITATIVE FIELDS"),
    ("handoff.ref", (2, 5), "SHIFT HANDOFF / TWO AUTHORITATIVE FIELDS"),
    ("relay.ref", (6, 7), "RELAY AUTHORIZATION / TWO AUTHORITATIVE FIELDS"),
)
CONTROL_REFERENCE_SPECS = (
    ("dispatch.ref", (0, 1), "UPLINK DISPATCH / TWO AUTHORITATIVE FIELDS"),
    ("seal.ref", (2, 3), "SEALED ROUTING NOTE / TWO AUTHORITATIVE FIELDS"),
    ("handoff.ref", (4, 5), "SHIFT HANDOFF / TWO AUTHORITATIVE FIELDS"),
    ("relay.ref", (6, 7), "RELAY AUTHORIZATION / TWO AUTHORITATIVE FIELDS"),
)


def _seed_int(seed: str, salt: str) -> int:
    digest = hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _different(rng: random.Random, values: tuple[str, ...], target: str) -> str:
    return rng.choice([value for value in values if value != target])


def _legacy_generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Generate the original L4 world without consuming an extra random draw.

    Keeping this path separate makes the current task and a controlled L4 task
    byte-for-byte equivalent apart from task/control metadata.
    """
    rng = random.Random(_seed_int(seed, MECHANIC_ID))
    targets = [
        ("AGENT", rng.choice(CALLSIGNS), CALLSIGNS),
        ("ROUTE", rng.choice(ROUTES), ROUTES),
        ("TOKEN", rng.choice(TOKENS), TOKENS),
        ("WINDOW", rng.choice(WINDOWS), WINDOWS),
        ("CIPHER", rng.choice(CIPHERS), CIPHERS),
        ("PORT", rng.choice(PORTS), PORTS),
    ]
    target_buffer = [f"{name}={value}" for name, value, _pool in targets]
    initial_buffer = [f"{name}={_different(rng, pool, value)}" for name, value, pool in targets]

    reference_specs = [
        ("dispatch.ref", (0, 3), "UPLINK DISPATCH / TWO AUTHORITATIVE FIELDS"),
        ("seal.ref", (1, 4), "SEALED ROUTING NOTE / TWO AUTHORITATIVE FIELDS"),
        ("handoff.ref", (2, 5), "SHIFT HANDOFF / TWO AUTHORITATIVE FIELDS"),
    ]
    reference_buffers: list[dict[str, Any]] = []
    for name, indices, heading in reference_specs:
        first, second = indices
        lines = [
            f"# {heading}",
            f"FIELD {first + 1:02d} :: {target_buffer[first]}",
            f"FIELD {second + 1:02d} :: {target_buffer[second]}",
            f"# checksum {rng.randint(100000, 999999)} / READ ONLY",
        ]
        reference_buffers.append({"name": name, "lines": lines, "field_indices": list(indices), "writable": False})

    layer_order = list(LAYER_NAMES)
    rng.shuffle(layer_order)
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}".encode("utf-8")).hexdigest()[:12]
    task_id = str(task.get("id") or "")
    host = f"gate-{rng.randint(12, 98)}.verify"
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language") or "Inspect every read-only buffer, repair the manifest in Vim, then unwind the entire terminal stack.",
        "asset_manifest": "shared_runtime/assets/provenance/incubator_full_build_v1.json",
        "generator": {"name": "multi_buffer_modal_terminal_escape_v2", "variant_count": 36_000_000_000},
        "initial_buffer": initial_buffer,
        # The authoritative values are intentionally distributed across three
        # buffers. Keeping this reconstructed list in browser state is not a
        # secrecy claim; ordinary users must visit the rendered buffers.
        "target_buffer": target_buffer,
        "reference_buffers": reference_buffers,
        "layer_order": layer_order,
        "host": host,
        "session_label": f"TTY-{challenge_id[:6].upper()}",
        "submit_label": "VERIFY SESSION",
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "initial_buffer": initial_buffer,
        "target_buffer": target_buffer,
        "reference_buffers": reference_buffers,
        "layer_order": layer_order,
        "host": host,
        "variant_count": 36_000_000_000,
    }
    covered = sorted(index for item in reference_buffers for index in item["field_indices"])
    assert len(initial_buffer) == len(target_buffer) == 6
    assert all(initial != target for initial, target in zip(initial_buffer, target_buffer))
    assert covered == list(range(6))
    assert len(layer_order) == 4 and set(layer_order) == set(LAYER_NAMES)
    return public_state, ground_truth


def _controlled_generate(task: dict[str, Any], seed: str, condition: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    parameters = dict(condition.get("difficulty_parameters") or {})
    field_count = int(parameters.get("field_count", 6))
    reference_count = int(parameters.get("reference_count", 3))
    layer_count = int(parameters.get("layer_count", 4))
    if field_count not in {2, 4, 6, 8} or reference_count * 2 != field_count:
        raise ValueError("terminal field_count must be two fields per reference buffer")
    if not 1 <= reference_count <= len(REFERENCE_SPECS):
        raise ValueError("terminal reference_count is outside supported limits")
    if not 1 <= layer_count <= len(LAYER_NAMES):
        raise ValueError("terminal layer_count is outside supported limits")

    rng = random.Random(_seed_int(seed, f"{MECHANIC_ID}|d{condition['difficulty']}"))
    targets = [
        (name, rng.choice(pool), pool)
        for name, pool in EXTENDED_TARGETS[:field_count]
    ]
    target_buffer = [f"{name}={value}" for name, value, _pool in targets]
    initial_buffer = [f"{name}={_different(rng, pool, value)}" for name, value, pool in targets]

    reference_buffers: list[dict[str, Any]] = []
    for name, indices, heading in CONTROL_REFERENCE_SPECS[:reference_count]:
        first, second = indices
        reference_buffers.append({
            "name": name,
            "lines": [
                f"# {heading}",
                f"FIELD {first + 1:02d} :: {target_buffer[first]}",
                f"FIELD {second + 1:02d} :: {target_buffer[second]}",
                f"# checksum {rng.randint(100000, 999999)} / READ ONLY",
            ],
            "field_indices": list(indices),
            "writable": False,
        })

    layer_order = list(LAYER_NAMES[:layer_count])
    rng.shuffle(layer_order)
    challenge_id = hashlib.sha256(
        f"{seed}|{MECHANIC_ID}|d{condition['difficulty']}".encode("utf-8")
    ).hexdigest()[:12]
    task_id = str(task.get("id") or "")
    host = f"gate-{rng.randint(12, 98)}.verify"
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language") or "Inspect every read-only buffer, repair the manifest in Vim, then unwind the entire terminal stack.",
        "asset_manifest": "shared_runtime/assets/provenance/incubator_full_build_v1.json",
        "generator": {"name": "multi_buffer_modal_terminal_escape_v3", "variant_count": 72_000_000_000},
        "initial_buffer": initial_buffer,
        "target_buffer": target_buffer,
        "reference_buffers": reference_buffers,
        "layer_order": layer_order,
        "host": host,
        "session_label": f"TTY-{challenge_id[:6].upper()}",
        "submit_label": "VERIFY SESSION",
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "initial_buffer": initial_buffer,
        "target_buffer": target_buffer,
        "reference_buffers": reference_buffers,
        "layer_order": layer_order,
        "host": host,
        "variant_count": 72_000_000_000,
    }
    covered = sorted(index for item in reference_buffers for index in item["field_indices"])
    assert covered == list(range(field_count))
    assert all(initial != target for initial, target in zip(initial_buffer, target_buffer))
    return public_state, ground_truth


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition = task.get("_control_condition")
    if not isinstance(condition, dict):
        return _legacy_generate(task, seed)
    difficulty = int(condition.get("difficulty") or 0)
    if difficulty == 4:
        public_state, ground_truth = _legacy_generate(task, seed)
    else:
        public_state, ground_truth = _controlled_generate(task, seed, condition)
    public_state["control_condition"] = condition.copy()
    ground_truth["control_condition"] = condition.copy()
    return public_state, ground_truth
