from __future__ import annotations

import copy
import hashlib
import random
from typing import Any


MECHANIC_ID = "pocket_radio_repair"
ASSET_MANIFEST = "shared_runtime/assets/provenance/pocket_radio_repair_v0.json"


def _condition(task: dict[str, Any]) -> dict[str, Any] | None:
    raw = task.get("_control_condition")
    return copy.deepcopy(raw) if isinstance(raw, dict) else None


def _parameters(condition: dict[str, Any] | None) -> dict[str, Any]:
    if condition:
        return dict(condition.get("difficulty_parameters") or {})
    return {
        "cover_count": 3, "screws_per_cover": 2, "component_count": 4,
        "dirty_count": 2, "missing_count": 1, "tool_count": 3,
        "screw_turn_degrees": 450, "clean_strokes": 4, "target_scale": 0.9,
    }


def _seed(seed: str) -> int:
    return int(hashlib.sha256(f"{seed}|{MECHANIC_ID}".encode()).hexdigest()[:16], 16)


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    condition = _condition(task)
    p = _parameters(condition)
    rng = random.Random(_seed(seed))
    cover_count = max(1, min(4, int(p.get("cover_count", 3))))
    screws_per_cover = max(1, min(3, int(p.get("screws_per_cover", 2))))
    component_count = max(1, min(5, int(p.get("component_count", 4))))
    dirty_count = max(0, min(component_count, int(p.get("dirty_count", 2))))
    missing_count = max(0, min(component_count - dirty_count, int(p.get("missing_count", 1))))
    tool_count = max(1, min(4, int(p.get("tool_count", 3))))
    target_scale = float(p.get("target_scale", 1.0))
    cover_names = ["REAR SHELL", "SHIELD PLATE", "FACE BEZEL", "BATTERY LID"]
    component_names = ["speaker cone", "tuning coil", "battery cell", "antenna contact", "volume wheel"]
    tool_names = [("flat", "FLAT DRIVER", "#f4b45c"), ("cross", "CROSS DRIVER", "#78c7ff"), ("precision", "PRECISION DRIVER", "#d39cff"), ("stubby", "STUBBY DRIVER", "#8fe0af")]

    covers: list[dict[str, Any]] = []
    screws: list[dict[str, Any]] = []
    for layer in range(cover_count):
        cover_id = f"cover-{layer + 1}"
        screw_ids = []
        for local in range(screws_per_cover):
            screw_id = f"screw-{layer + 1}-{local + 1}"
            screw_ids.append(screw_id)
            x = 316 + (local % 2) * 278 + (layer % 2) * 10
            y = 177 + layer * 48 + (local // 2) * 70
            tool = tool_names[(layer + local + rng.randrange(tool_count)) % tool_count][0]
            screws.append({"id": screw_id, "cover_id": cover_id, "tool_id": tool, "installed": True, "x": x, "y": y, "radius": max(18, round(24 * target_scale))})
        covers.append({"id": cover_id, "layer": layer, "label": cover_names[layer], "installed": True, "screw_ids": screw_ids, "x": 276 + layer * 7, "y": 120 + layer * 7, "w": 410 - layer * 14, "h": 300 - layer * 14})

    components: list[dict[str, Any]] = []
    component_cover_layers = [min(cover_count - 1, index * cover_count // component_count) for index in range(component_count)]
    fault_indices = list(range(component_count))
    rng.shuffle(fault_indices)
    missing_indices = set(fault_indices[:missing_count])
    dirty_indices = set(fault_indices[missing_count:missing_count + dirty_count])
    colors = ["#f17c72", "#76d6d2", "#e1b66e", "#a791ee", "#88cf83"]
    for index in range(component_count):
        condition_name = "missing" if index in missing_indices else ("dirty" if index in dirty_indices else "intact")
        components.append({
            "id": f"component-{index + 1}", "label": component_names[index],
            "cover_id": f"cover-{component_cover_layers[index] + 1}",
            "condition": condition_name, "installed": condition_name != "missing", "repaired": condition_name == "intact",
            "x": 330 + (index % 3) * 145, "y": 226 + (index // 3) * 86,
            "w": max(76, round(112 * target_scale)), "h": max(44, round(64 * target_scale)), "color": colors[index % len(colors)],
            "tray_x": 700 + (index % 2) * 76, "tray_y": 160 + (index // 2) * 86,
        })

    tools = [{"id": tool_id, "label": label, "color": color, "x": 64 + index * 76, "y": 470, "w": 62, "h": 44} for index, (tool_id, label, color) in enumerate(tool_names[:tool_count])]
    challenge_id = hashlib.sha256(f"{seed}|{MECHANIC_ID}|{condition.get('difficulty') if condition else 4}".encode()).hexdigest()[:14]
    public: dict[str, Any] = {
        "benchmark": "weird_captcha_gym", "mechanic_id": MECHANIC_ID, "task_id": task.get("id"), "challenge_id": challenge_id,
        "prompt": task.get("natural_language") or "Repair the radio and run its power test.", "asset_manifest": ASSET_MANIFEST,
        "generator": {"name": "pocket_radio_repair_staged_v1", "variant_count": 4 * 3 * 5 * 4 * 16},
        "view": {"canvas_width": 900, "canvas_height": 560, "target_scale": target_scale},
        "radio": {"body": {"x": 260, "y": 112, "w": 430, "h": 320}, "covers": covers, "screws": screws, "components": components, "tools": tools,
                  "mat_name": rng.choice(["SUNLIT REPAIR MAT", "BLUE FELT BENCH", "AMBER WORK CLOTH"]), "finish": rng.choice(["coral", "moss", "indigo", "cream"])},
        "display": {"model": rng.choice(["MICA-7", "ORBIT 12", "TINY TUNER", "FIELD NOTE 3"]), "power_label": "POWER TEST"},
    }
    truth = {
        "mechanic_id": MECHANIC_ID, "task_id": task.get("id"), "seed": seed, "challenge_id": challenge_id,
        "control_condition": copy.deepcopy(condition), "tools": copy.deepcopy(tools), "covers": copy.deepcopy(covers),
        "screws": copy.deepcopy(screws), "components": copy.deepcopy(components), "turn_degrees": float(p.get("screw_turn_degrees", 450)),
        "clean_strokes": int(p.get("clean_strokes", 4)), "variant_count": 4 * 3 * 5 * 4 * 16,
    }
    if condition is not None:
        public["control_condition"] = copy.deepcopy(condition)
    else:
        truth["control_condition"] = {"difficulty": 4, "interaction": "full", "real_time": "live", "difficulty_parameters": _parameters(None)}
        public["control_condition"] = copy.deepcopy(truth["control_condition"])
    return public, truth
