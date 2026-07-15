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


def _seed_int(seed: str, salt: str) -> int:
    digest = hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _different(rng: random.Random, values: tuple[str, ...], target: str) -> str:
    return rng.choice([value for value in values if value != target])


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
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
