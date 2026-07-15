from __future__ import annotations

import hashlib
import random
from typing import Any


MECHANIC_ID = "fake_desktop_automation_inversion"
DESKTOP_WIDTH = 900
DESKTOP_HEIGHT = 510
MAPPINGS = ("normal", "mirror_x", "mirror_y", "rotate_180")
KEYFILE_NAMES = (
    "HUMAN_OVERRIDE.KEY",
    "PARADOX_TOKEN.KEY",
    "ORGANIC_INPUT.KEY",
    "OPERATOR_PROOF.KEY",
    "MANUAL_ONLY.KEY",
    "HANDOFF_SEAL.KEY",
)


def _seed_int(seed: str, salt: str) -> int:
    digest = hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _window(window_id: str, title: str, x: int, y: int, width: int, height: int, z: int) -> dict[str, Any]:
    return {"id": window_id, "title": title, "x": x, "y": y, "width": width, "height": height, "z": z, "closed": False, "closable": True}


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed_int(seed, MECHANIC_ID))
    mappings = list(MAPPINGS)
    rng.shuffle(mappings)
    mapping_sequence = mappings[:3]

    target_names = rng.sample(list(KEYFILE_NAMES), 2)
    decoy_pool = [name for name in KEYFILE_NAMES if name not in target_names]
    file_names = target_names + rng.sample(decoy_pool, 2)
    rng.shuffle(file_names)
    files: list[dict[str, Any]] = []
    ids_by_name: dict[str, str] = {}
    for index, name in enumerate(file_names):
        file_id = f"file-{hashlib.sha256(f'{seed}|{name}'.encode('utf-8')).hexdigest()[:8]}"
        ids_by_name[name] = file_id
        files.append({"id": file_id, "name": name, "slot": index})
    target_file_ids = [ids_by_name[name] for name in target_names]

    jitter_x = rng.randint(-12, 12)
    jitter_y = rng.randint(-9, 9)
    windows = [
        _window("directive", "MANUAL OPERATOR DIRECTIVE", 20, 28, 334, 118, 2),
        _window("vault", "LOCAL KEY VAULT", 72 + jitter_x, 154 + jitter_y, 382, 272, 1),
        _window("verifier", "AUTOMATION VERIFIER", 538 - jitter_x, 214 - jitter_y, 342, 270, 3),
        _window("interceptor", "BOT ACTIVITY INTERCEPTOR", 214 + jitter_x, 108 + jitter_y, 352, 230, 4),
    ]
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}".encode("utf-8")).hexdigest()[:12]
    task_id = str(task.get("id") or "fake_desktop_automation_inversion_seed_0001@0.1")
    geometry = {
        "title_height": 38,
        "close_width": 44,
        "file_origin": [22, 76],
        "file_size": [156, 62],
        "file_gap": [10, 10],
        "file_columns": 2,
        "drop_zone": [20, 70, 302, 112],
        "arm_control": [20, 204, 206, 44],
    }
    public_state = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language") or "Use the remapped remote cursor to transfer both seals in order, then arm the final channel.",
        "submit_label": "SUBMIT MANUAL AUDIT",
        "asset_manifest": "shared_runtime/assets/provenance/incubator_full_build_v1.json",
        "generator": {"name": "three_channel_automation_inversion_desktop_v2", "variant_count": 28_800_000},
        "desktop": {"width": DESKTOP_WIDTH, "height": DESKTOP_HEIGHT},
        "mapping_sequence": mapping_sequence,
        "mapping_labels": {
            "normal": "DIRECT / X→X · Y→Y",
            "mirror_x": "MIRROR X / X→−X · Y→Y",
            "mirror_y": "MIRROR Y / X→X · Y→−Y",
            "rotate_180": "ROTATE 180° / X→−X · Y→−Y",
        },
        "windows": windows,
        "files": files,
        "target_filenames": target_names,
        "required_blocker_id": "interceptor",
        "required_moved_window_ids": ["vault", "verifier"],
        "workflow": [
            "Close the interceptor and reposition the vault to expose both rows.",
            f"Transfer {target_names[0]} through channel 1.",
            f"After remap, reposition the verifier and transfer {target_names[1]}.",
            "After the second remap, arm MANUAL CONTROL on channel 3.",
        ],
        "geometry": geometry,
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "seed": seed,
        "challenge_id": challenge_id,
        "desktop": public_state["desktop"],
        "mapping_sequence": mapping_sequence,
        "initial_windows": windows,
        "files": files,
        "target_file_ids": target_file_ids,
        "target_filenames": target_names,
        "required_blocker_id": "interceptor",
        "required_moved_window_ids": ["vault", "verifier"],
        "geometry": geometry,
        "minimum_window_move": 44,
        "variant_count": public_state["generator"]["variant_count"],
    }
    assert len(windows) == 4 and len(files) == 4
    assert len(set(mapping_sequence)) == 3
    assert len(set(target_file_ids)) == 2 and all(sum(1 for item in files if item["id"] == target) == 1 for target in target_file_ids)
    return public_state, ground_truth
