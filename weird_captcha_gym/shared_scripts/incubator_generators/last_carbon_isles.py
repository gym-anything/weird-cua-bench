from __future__ import annotations

import copy
import hashlib
import random
from typing import Any


MECHANIC_ID = "last_carbon_isles"

REGION_NAMES = (
    ("Cinder Key", "cinder", "#ef765d"),
    ("Morrow Atoll", "morrow", "#f0bd63"),
    ("Vesper Isle", "vesper", "#8ed4ad"),
    ("Lumen Shoal", "lumen", "#82c8ed"),
    ("Thorn Cay", "thorn", "#c8a7e8"),
    ("Orchid Reach", "orchid", "#e59ac0"),
    ("Sable Haven", "sable", "#b9c5cc"),
    ("Rookery", "rookery", "#e2df9a"),
)

LAYOUTS = (
    (13, 21, 18, 22, -5),
    (38, 13, 20, 21, 4),
    (69, 20, 18, 22, -3),
    (23, 57, 19, 22, 6),
    (51, 47, 20, 23, -4),
    (78, 59, 17, 21, 5),
    (5, 69, 16, 18, -7),
    (63, 78, 17, 17, 3),
)

POLICY_NAMES = (
    ("Tidal Weave", "TIDAL", "A braided tidal generator and dockyard retrofit."),
    ("Sunken Solar", "SOLAR", "Floating solar rafts with a crew-owned maintenance guild."),
    ("Mangrove Union", "MANGROVE", "A living seawall and paid restoration flotilla."),
    ("Wind Loom", "WIND", "A kite-turbine field stitched into the island's trade route."),
    ("Low-Heat Foundry", "FOUNDRY", "A clean kiln conversion that keeps the old makers employed."),
    ("Compost Current", "COMPOST", "A circular food loop with a small fleet of biogas skiffs."),
    ("Night Grid", "GRID", "A demand-shifting grid charter for the midnight tide."),
    ("Reef Ledger", "REEF", "A carbon drawdown trust that pays for living reefs."),
)

DEFAULT_PARAMETERS = {
    "region_count": 5,
    "initial_target_count": 2,
    "hand_size": 3,
    "research_stages": 3,
    "decoy_count": 6,
    "wrong_jobs_penalty": 4,
    "wrong_emissions_reduction": 4,
    "budget_slack": 4,
    "spare_turns": 1,
    "research_cost": 2,
}


def _seed(seed: str, salt: str = "world-v1") -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}|{MECHANIC_ID}|{salt}".encode()).digest()[:8], "big")


def _id(seed: str, prefix: str, index: int) -> str:
    return f"{prefix}-{index + 1}-{hashlib.sha256(f'{seed}|{prefix}|{index}'.encode()).hexdigest()[:8]}"


def _card_view(card: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(card)


def _card_effect(emissions: int, jobs: int, *, home: bool, wrong_jobs_penalty: int, wrong_emissions_reduction: int) -> dict[str, int]:
    if home:
        return {"emissions": -int(emissions), "jobs": max(1, 101 - int(jobs))}
    return {"emissions": -int(wrong_emissions_reduction), "jobs": -int(wrong_jobs_penalty)}


def generate(task: dict[str, Any], seed: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(_seed(seed))
    raw_condition = task.get("_control_condition")
    condition = copy.deepcopy(raw_condition) if raw_condition else None
    parameters = dict(DEFAULT_PARAMETERS)
    if condition:
        parameters.update(condition.get("difficulty_parameters") or {})
    if parameters.get("network_level"):
        return _network(task, seed, parameters)

    region_count = int(parameters["region_count"])
    initial_target_count = int(parameters["initial_target_count"])
    hand_size = int(parameters["hand_size"])
    research_stages = int(parameters["research_stages"])
    decoy_count = int(parameters["decoy_count"])
    wrong_jobs_penalty = int(parameters["wrong_jobs_penalty"])
    wrong_emissions_reduction = int(parameters["wrong_emissions_reduction"])
    budget_slack = int(parameters["budget_slack"])
    spare_turns = int(parameters["spare_turns"])
    research_cost = int(parameters["research_cost"])
    research_offer_count = int(parameters.get("research_offer_count", 1))
    show_home_labels = bool(parameters.get("show_home_labels", True))
    show_decoy_warning = bool(parameters.get("show_decoy_warning", True))

    if not 3 <= region_count <= len(REGION_NAMES):
        raise ValueError("last carbon isles region_count is outside supported range")
    if not 1 <= initial_target_count <= region_count:
        raise ValueError("last carbon isles initial_target_count is invalid")
    if hand_size < initial_target_count or hand_size > 5:
        raise ValueError("last carbon isles hand_size is invalid")
    if research_stages != region_count - initial_target_count:
        raise ValueError("last carbon isles research stages must cover remaining target policies")
    if research_offer_count < 1:
        raise ValueError("last carbon isles research_offer_count must be positive")
    required_decoys = max(0, hand_size - initial_target_count) + research_stages * research_offer_count
    if decoy_count < required_decoys:
        raise ValueError("last carbon isles needs enough decoys for initial and research offers")
    if min(wrong_jobs_penalty, wrong_emissions_reduction, budget_slack, spare_turns, research_cost) < 0:
        raise ValueError("last carbon isles parameters cannot be negative")

    order = list(range(region_count))
    rng.shuffle(order)
    regions: list[dict[str, Any]] = []
    for visual_index, template_index in enumerate(order):
        name, slug, color = REGION_NAMES[template_index]
        x, y, width, height, rotation = LAYOUTS[visual_index]
        emissions = rng.randint(19 + region_count // 3, 25 + region_count)
        jobs = rng.randint(88 - min(3, region_count // 2), 95 - min(1, region_count // 4))
        region_id = _id(seed, "isle", visual_index)
        regions.append({
            "id": region_id,
            "name": name,
            "slug": slug,
            "color": color,
            "x": round(x + rng.uniform(-2.0, 2.0), 2),
            "y": round(y + rng.uniform(-2.0, 2.0), 2),
            "width": width,
            "height": height,
            "rotation": rotation + rng.uniform(-2.0, 2.0),
            "emissions": emissions,
            "jobs": jobs,
            "target_jobs": 100,
        })

    target_cards: list[dict[str, Any]] = []
    for index, region in enumerate(regions):
        title, eyebrow, description = POLICY_NAMES[(index + rng.randrange(len(POLICY_NAMES))) % len(POLICY_NAMES)]
        cost = 4 + ((index + region_count) % 3)
        target_effect = _card_effect(
            int(region["emissions"]),
            int(region["jobs"]),
            home=True,
            wrong_jobs_penalty=wrong_jobs_penalty,
            wrong_emissions_reduction=wrong_emissions_reduction,
        )
        effects = {}
        for candidate in regions:
            effects[candidate["id"]] = _card_effect(
                int(candidate["emissions"]),
                int(candidate["jobs"]),
                home=candidate["id"] == region["id"],
                wrong_jobs_penalty=wrong_jobs_penalty,
                wrong_emissions_reduction=wrong_emissions_reduction,
            )
        target_cards.append({
            "id": _id(seed, "policy", index),
            "title": title,
            "eyebrow": eyebrow,
            "description": description,
            "kind": "home_policy",
            "home_region": region["id"],
            "home_name": region["name"],
            "cost": cost,
            "target_effect": target_effect,
            "effects": effects,
            "accent": region["color"],
        })

    decoy_cards: list[dict[str, Any]] = []
    for index in range(decoy_count):
        home = regions[(index * 3 + rng.randrange(region_count)) % region_count]
        title = ("Emergency Rationing", "Fast Carbon Credit", "Diesel Bridge", "Private Retrofit", "Export Boom")[index % 5]
        effects = {}
        for candidate in regions:
            if candidate["id"] == home["id"]:
                effects[candidate["id"]] = {
                    "emissions": -max(2, int(candidate["emissions"]) // 3),
                    "jobs": -max(3, wrong_jobs_penalty),
                }
            else:
                effects[candidate["id"]] = {"emissions": 0, "jobs": -1}
        decoy_cards.append({
            "id": _id(seed, "decoy", index),
            "title": title,
            "eyebrow": "SHORTCUT" if show_decoy_warning else "FIELD NOTE",
            "description": "A tempting fast fix. It cuts smoke, but it does not protect the island's crews.",
            "kind": "decoy_policy",
            "home_region": home["id"],
            "home_name": home["name"],
            "cost": 3 + (index % 3),
            "target_effect": effects[home["id"]],
            "effects": effects,
            "accent": "#a8a3a0",
        })

    initial_cards = target_cards[:initial_target_count]
    initial_decoys = decoy_cards[: max(0, hand_size - initial_target_count)]
    initial_hand = [_card_view(card) for card in (*initial_cards, *initial_decoys)]
    rng.shuffle(initial_hand)

    research_tracks: list[dict[str, Any]] = []
    for stage in range(research_stages):
        target = target_cards[initial_target_count + stage]
        decoy_start = max(0, hand_size - initial_target_count) + stage * research_offer_count
        decoy_offers = decoy_cards[decoy_start : decoy_start + research_offer_count]
        if len(decoy_offers) != research_offer_count:
            raise ValueError("last carbon isles research offers exceed the generated decoy deck")
        offers = [_card_view(target), *(_card_view(card) for card in decoy_offers)]
        if research_offer_count == 1:
            if rng.random() < 0.5:
                offers.reverse()
        else:
            rng.shuffle(offers)
        research_tracks.append({"stage": stage, "cost": research_cost, "offers": offers})

    target_cost = sum(int(card["cost"]) for card in target_cards)
    initial_budget = target_cost + research_stages * research_cost + budget_slack
    max_turns = region_count + spare_turns
    challenge_id = hashlib.sha256(
        f"{seed}|{MECHANIC_ID}|d{condition.get('difficulty', 3) if condition else 3}".encode()
    ).hexdigest()[:12]
    prompt = task.get("natural_language") or DEFAULT_PARAMETERS and "Restore all five isles: research the right policies, drag each to its home, and finish with zero smoke and full crews."
    card_catalog = [_card_view(card) for card in (*target_cards, *decoy_cards)]
    research_offers = copy.deepcopy(research_tracks[0]["offers"]) if research_tracks else []

    public: dict[str, Any] = {
        "benchmark": "weird_cua_bench",
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "challenge_id": challenge_id,
        "prompt": prompt,
        "submit_label": "CERTIFY ISLES",
        "asset_manifest": "shared_runtime/assets/provenance/last_carbon_isles_v0.json",
        "generator": {"name": "last_carbon_isles_card_map_v1", "variant_count": region_count * max(1, decoy_count) * 4096},
        "world": {"name": "The Last Carbon Isles", "subtitle": "A small chain of islands. One shared budget. No clean air left to waste.", "palette": rng.randrange(6)},
        "regions": copy.deepcopy(regions),
        "cards": card_catalog,
        "hand": initial_hand,
        "research_tracks": copy.deepcopy(research_tracks),
        "research_offers": research_offers,
        "research_stage": 0,
        "research_cost": research_cost,
        "budget": initial_budget,
        "initial_budget": initial_budget,
        "turns": 0,
        "max_turns": max_turns,
        "goal": {"emissions": 0, "jobs": 100},
    }
    truth: dict[str, Any] = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task["id"],
        "seed": seed,
        "challenge_id": challenge_id,
        "control_condition": copy.deepcopy(condition) if condition else None,
        "parameters": copy.deepcopy(parameters),
        "regions": copy.deepcopy(regions),
        "cards": card_catalog,
        "initial_hand_ids": [str(card["id"]) for card in initial_hand],
        "research_tracks": copy.deepcopy(research_tracks),
        "initial_budget": initial_budget,
        "max_turns": max_turns,
        "goal": {"emissions": 0, "jobs": 100},
        "target_card_ids": [str(card["id"]) for card in target_cards],
    }
    if condition:
        public["control_condition"] = copy.deepcopy(condition)
    return public, truth


def _network(task: dict[str, Any], seed: str, parameters: dict[str, Any]):
    """Upper profiles: funded local anchor, then finite inter-isle crew transfers."""
    level = int(parameters['network_level'])
    count = int(parameters['region_count'])
    research_cost = int(parameters['research_cost'])
    legacy = copy.deepcopy(task)
    legacy['_control_condition']['difficulty_parameters'] = {
        **DEFAULT_PARAMETERS, 'region_count': count, 'initial_target_count': 1,
        'hand_size': 1, 'research_stages': count - 1, 'decoy_count': count - 1,
    }
    public, truth = generate(legacy, seed)
    rng = random.Random(_seed(seed, 'crew-network-v2'))
    regions = public['regions']
    route = list(regions)
    rng.shuffle(route)
    edges = [(route[i]['id'], route[i + 1]['id']) for i in range(count - 1)]
    if level >= 4:
        edges.append((route[0]['id'], route[2]['id']))
        candidates = [(route[i]['id'], route[i + 2]['id']) for i in range(1, count - 2)]
        candidates += [(route[i + 2]['id'], route[i + 1]['id']) for i in range(count - 2)]
        edges += [edge for edge in candidates if rng.random() < 0.65]
    tolls = {edge: (rng.choice((3, 7)) if level == 5 else 6) for edge in edges}
    if level == 5:
        # Every instance requires at least one budgeted training decision.
        tolls[(route[1]['id'], route[2]['id'])] = 7
        for edge in edges:
            if edge[1] == route[-1]['id']:
                tolls[edge] = 7
        tolls[(route[2]['id'], route[3]['id'])] = 3
    lookup = {r['id']: r for r in regions}
    cards = []

    def card(destination, donor=None, reserve=6, cost=2):
        rid = destination['id']
        effect = {'emissions': -destination['emissions'], 'jobs': 100 + reserve - destination['jobs']}
        toll = tolls[(donor, rid)] if donor else 0
        result = {
            'id': _id(seed, 'network-card', len(cards)), 'kind': 'network_policy',
            'title': 'Local academy' if donor is None else ('Training retrofit' if reserve == 8 else 'Relay retrofit'),
            'eyebrow': 'POLICY', 'home_region': rid, 'home_name': destination['name'],
            'cost': cost, 'accent': destination['color'], 'target_effect': effect,
            'effects': {rid: effect}, 'reserve': reserve,
            'requirements': [] if donor is None else [{'region_id': donor, 'jobs': 100 + toll, 'emissions': 0}],
            'side_effects': {} if donor is None else {donor: {'jobs': -toll, 'emissions': 0}},
            'description': (f'Local training; leaves {reserve} spare crews.' if donor is None else
                            f"From {lookup[donor]['name']}: needs 0 smoke and {100+toll} crews; transfers {toll} crews. Leaves {reserve} spare here."),
        }
        cards.append(result)
        return result

    anchor = card(route[0], reserve=8 if level == 5 else 6, cost=8)
    tracks = []
    # Research order is geographical, independent of the required transfer route.
    for region in regions:
        if region['id'] == route[0]['id']:
            continue
        offers = []
        for donor, destination in edges:
            if destination == region['id']:
                offers.append(card(region, donor, reserve=4 if level == 5 else 6))
                if level == 5:
                    offers.append(card(region, donor, reserve=8, cost=4))
        offers.append(card(region, reserve=8 if level == 5 else 6, cost=30))
        rng.shuffle(offers)
        tracks.append({'stage': len(tracks), 'cost': research_cost, 'offers': offers})
    witness = [anchor['id']]
    for index in range(1, count):
        reserve = (8 if index < count - 1 and tolls[(route[index]['id'], route[index+1]['id'])] == 7 else 4) if level == 5 else 6
        selected = next(c for c in cards if c['home_region'] == route[index]['id'] and
                        c['requirements'] and c['requirements'][0]['region_id'] == route[index-1]['id'] and c['reserve'] == reserve)
        witness.append(selected['id'])
    budget = sum(c['cost'] for c in cards if c['id'] in witness) + len(tracks) * research_cost
    # Even at the highest training cost the budget cannot buy a second local academy.
    assert budget - len(tracks) * research_cost - 8 < 30
    # The atlas uses the shuffled offer order, never the witness-route construction order.
    cards = [anchor] + [c for track in tracks for c in track['offers']]
    public.update({
        'generator': {'name': 'last_carbon_isles_crew_network_v2', 'variant_count': 4096 * count},
        'cards': copy.deepcopy(cards), 'hand': [copy.deepcopy(anchor)],
        'research_tracks': copy.deepcopy(tracks), 'research_offers': copy.deepcopy(tracks[0]['offers']),
        'research_cost': research_cost, 'budget': budget, 'initial_budget': budget, 'max_turns': count,
        'control_condition': copy.deepcopy(task['_control_condition']),
        'network': True,
        'world': {**public['world'], 'subtitle': 'Restore an isle. Share its spare crews. Plan the connections before spending.'},
    })
    truth.update({
        'cards': copy.deepcopy(cards), 'initial_hand_ids': [anchor['id']],
        'research_tracks': copy.deepcopy(tracks), 'initial_budget': budget, 'max_turns': count,
        'control_condition': copy.deepcopy(task['_control_condition']),
        'parameters': copy.deepcopy(task['_control_condition']['difficulty_parameters']),
        'target_card_ids': [], 'witness_route': witness,
    })
    return public, truth
