"""Seeded membrane-transport worlds for Cell Gatekeeper.

The generator exposes the geometry, particle counts, targets, and transporter
rules needed to render one honest visual task.  The solver route is not stored:
the browser and the independent grader both replay the same small discrete
transport model from the visible initial world.
"""

from __future__ import annotations

import copy
import hashlib
import json
import random
from typing import Any


MECHANIC_ID = "cell_gatekeeper"

# The uncontrolled task is the baseline configuration.  It is deliberately
# kept as a named constant so controlled L3 materialization can prove that the
# current task did not move when the five profiles were added.
BASELINE_PARAMETERS: dict[str, Any] = {
    "species_count": 2,
    "slot_count": 4,
    "required_leak_count": 1,
    "pump_cycles": 4,
    "goal_width": 2,
    "passive_period": 3,
    "pump_period": 3,
    "atp_batch": 4,
    "observation_ticks": 6,
    "max_ticks": 240,
    "numeric_readout": True,
    "toolbox_decoys": 0,
}


SOLUTES: tuple[dict[str, Any], ...] = (
    {
        "id": "sodium",
        "label": "Sodium ion",
        "short": "Na+",
        "color": "#ff7466",
        "shape": "dot",
        "pump_direction": "inside_to_outside",
    },
    {
        "id": "potassium",
        "label": "Potassium ion",
        "short": "K+",
        "color": "#62b5ff",
        "shape": "diamond",
        "pump_direction": "outside_to_inside",
    },
    {
        "id": "glucose",
        "label": "Glucose",
        "short": "GLU",
        "color": "#f6c85f",
        "shape": "hex",
        "pump_direction": "outside_to_inside",
    },
)


def _seed_int(seed: str, salt: str) -> int:
    return int(hashlib.sha256(f"{seed}|{salt}".encode("utf-8")).hexdigest()[:16], 16)


def _profile(task: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    condition = task.get("_control_condition")
    if condition:
        return copy.deepcopy(condition["difficulty_parameters"]), copy.deepcopy(condition)
    return copy.deepcopy(BASELINE_PARAMETERS), None


def _protein_catalog(species: list[dict[str, Any]], rng: random.Random) -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    for solute in species:
        sid = str(solute["id"])
        short = str(solute["short"])
        catalog.append(
            {
                "id": f"{sid}_leak",
                "species": sid,
                "kind": "leak",
                "short": f"{short} leak",
                "label": f"{short} selective leak",
                "rule": "PASSIVE · high concentration → low concentration",
                "direction": "high_to_low",
                "requires_atp": False,
                "color": solute["color"],
            }
        )
        direction = str(solute["pump_direction"])
        direction_text = "inside → outside" if direction == "inside_to_outside" else "outside → inside"
        catalog.append(
            {
                "id": f"{sid}_pump",
                "species": sid,
                "kind": "pump",
                "short": f"{short} pump",
                "label": f"{short} ATP pump",
                "rule": f"ACTIVE · {direction_text} · ATP required",
                "direction": direction,
                "requires_atp": True,
                "color": solute["color"],
            }
        )
    rng.shuffle(catalog)
    return catalog


def _directional_delta(direction: str) -> tuple[str, str]:
    if direction == "inside_to_outside":
        return "inside", "outside"
    return "outside", "inside"


def generate(task: dict[str, Any], seed: str):
    parameters, condition = _profile(task)
    rng = random.Random(_seed_int(str(seed), "cell-gatekeeper"))
    species_count = int(parameters["species_count"])
    species = [copy.deepcopy(item) for item in SOLUTES[:species_count]]
    pump_cycles = int(parameters["pump_cycles"])
    required_leak_count = int(parameters["required_leak_count"])
    leak_species = [str(item["id"]) for item in species[:required_leak_count]]
    required_proteins = [f"{item['id']}_pump" for item in species]
    required_proteins.extend(f"{sid}_leak" for sid in leak_species)

    counts: dict[str, dict[str, int]] = {}
    goals: dict[str, dict[str, Any]] = {}
    for index, solute in enumerate(species):
        sid = str(solute["id"])
        low = rng.randint(4, 6)
        high = rng.randint(11, 14)
        pump_source, pump_target = _directional_delta(str(solute["pump_direction"]))
        # Alternate which side starts crowded.  The pump must create the
        # requested gradient rather than merely preserve an already-correct one.
        if pump_source == "inside":
            start = {"outside": low, "inside": high}
        else:
            start = {"outside": high, "inside": low}
        passive_credit = 1 if sid in leak_species else 0
        expected = dict(start)
        expected[pump_source] -= pump_cycles + passive_credit
        expected[pump_target] += pump_cycles + passive_credit
        width = int(parameters["goal_width"])
        lower_offset = width // 2
        upper_offset = width - lower_offset
        goals[sid] = {
            "outside": [max(0, expected["outside"] - lower_offset), expected["outside"] + upper_offset],
            "inside": [max(0, expected["inside"] - lower_offset), expected["inside"] + upper_offset],
            "target_direction": pump_target,
            "why": (
                "use the ATP pump to build the outside gradient"
                if pump_target == "outside"
                else "use the ATP pump to build the inside gradient"
            ),
        }
        counts[sid] = start

    catalog = _protein_catalog(species, rng)
    # At least one unused catalog item is retained at the harder levels.  It is
    # a visible distractor, not a hidden answer token.
    extra_decoys = int(parameters.get("toolbox_decoys", 0))
    if extra_decoys:
        all_extra = [
            {
                "id": "buffer_channel",
                "species": str(species[0]["id"]),
                "kind": "decoy",
                "short": "BUFFER",
                "label": "buffer channel",
                "rule": "DECORATIVE · does not carry task solutes",
                "direction": "none",
                "requires_atp": False,
                "color": "#a9a9bd",
            },
            {
                "id": "sealed_pore",
                "species": str(species[-1]["id"]),
                "kind": "decoy",
                "short": "SEALED",
                "label": "sealed pore",
                "rule": "CLOSED · no crossing",
                "direction": "none",
                "requires_atp": False,
                "color": "#a9a9bd",
            },
        ]
        catalog.extend(copy.deepcopy(all_extra[:extra_decoys]))
        rng.shuffle(catalog)

    surface = {
        "width": 900,
        "height": 430,
        "membrane_x": 450,
        "capacity": 30,
        "theme": rng.randrange(6),
        "particle_seed": rng.randrange(1_000_000),
    }
    recipe = []
    for protein_id in required_proteins:
        item = next(item for item in catalog if item["id"] == protein_id)
        if item["kind"] == "leak":
            instruction = "Place it, watch one passive crossing, then eject it before the final lock."
        else:
            instruction = f"Place it and fuel it with ATP until the {item['species']} bars enter the target bands."
        recipe.append({"protein_id": protein_id, "instruction": instruction})

    initial_state = {
        "tick": 0,
        "counts": copy.deepcopy(counts),
        "slots": [None] * int(parameters["slot_count"]),
        "atp": 0,
        "crossings": {"passive": {}, "active": {}},
        "installed_history": [],
        "removed_history": [],
        "stable_ticks": 0,
        "status": "active",
    }
    challenge_id = hashlib.sha256(
        f"{seed}|{json.dumps(parameters, sort_keys=True)}|{MECHANIC_ID}".encode("utf-8")
    ).hexdigest()[:16]
    public_state: dict[str, Any] = {
        "benchmark": "weird_captcha_gym",
        "mechanic_id": MECHANIC_ID,
        "task_id": task.get("id", "cell_gatekeeper_seed_0001@0.1"),
        "challenge_id": challenge_id,
        "prompt": task.get("natural_language") or "Gate the membrane: establish every target concentration gradient.",
        "submit_label": "LOCK GRADIENT",
        "asset_manifest": "shared_runtime/assets/provenance/cell_gatekeeper_v0.json",
        "generator": {"name": "cell_gatekeeper_v0", "variant_count": 1_000_000},
        "parameters": copy.deepcopy(parameters),
        "surface": surface,
        "species": species,
        "protein_catalog": catalog,
        "slot_count": int(parameters["slot_count"]),
        "counts": copy.deepcopy(counts),
        "goal": goals,
        "recipe": recipe,
        "required_proteins": required_proteins,
        "initial_state": initial_state,
    }
    if condition is not None:
        public_state["control_condition"] = copy.deepcopy(condition)
    truth = copy.deepcopy(public_state)
    truth["seed"] = str(seed)
    truth["required_proteins"] = required_proteins
    truth["leak_species"] = leak_species
    return public_state, truth
