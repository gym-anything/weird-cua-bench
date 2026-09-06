"""Original, deterministic fluke identity worlds; no solver route in render state."""
from __future__ import annotations
import copy
import hashlib
import json
import math
import random

MECHANIC_ID = 'fluke_census'
BASELINE = dict(animal_count=9, notch_difference=8, rotation_range=180, scale_range=.20)

BODY = [(42,0),(34,-12),(10,-17),(-18,-10),(-28,-5),(-34,-19),(-47,-25),(-42,-9),(-35,0),(-42,9),(-47,25),(-34,19),(-28,5),(-18,10),(10,17),(34,12)]

def swept_bounds(item):
    a=math.radians(item['angle']);s=item['scale']
    xs=[s*(x*math.cos(a)-y*math.sin(a))+item['x'] for x,y in BODY]
    ys=[s*(x*math.sin(a)+y*math.cos(a))+item['y'] for x,y in BODY]
    return min(xs)-16,min(ys)-12,max(xs)+16,max(ys)+12

def separated(layout):
    boxes=[swept_bounds(item) for item in layout]
    for i,(l,t,r,b) in enumerate(boxes):
        if l<12 or t<12 or r>808 or b>418:return False
        for ll,tt,rr,bb in boxes[:i]:
            if not (r+4<ll or rr+4<l or b+4<tt or bb+4<t):return False
    return True

def generate(task, seed):
    condition = task.get('_control_condition') or (task.get('metadata') or {}).get('control_condition')
    params = dict(BASELINE)
    params.update((condition or {}).get('difficulty_parameters') or {})
    n = params['animal_count']
    if n not in (3, 6, 9, 12) or not 5 <= params['notch_difference'] <= 22 or not 0 <= params['rotation_range'] <= 180 or not 0 <= params['scale_range'] <= .28:
        raise ValueError('unsupported census parameters')
    rng = random.Random(hashlib.sha256(f'{seed}|fluke-census-v1'.encode()).hexdigest())
    # Individuals share a body envelope; tail-edge notches carry identity.
    animals = []
    for species in range(3):
        base = [rng.choice([10, 15, 20]) for _ in range(8)]
        positions = rng.sample(range(8), n // 3)
        for position in positions:
            depths = base.copy()
            depths[position] += params['notch_difference']
            animals.append({'id': rng.getrandbits(48).__format__('012x'), 'species': species, 'notches': depths})
    rng.shuffle(animals)
    listed = rng.sample(range(3), 2)
    # Separated cells provide enough reserve for full body rotation + drift.
    slots = [(110 + x * 195, 95 + y * 125) for y in range(3) for x in range(4)]
    rng.shuffle(slots)
    slots = slots[:n]
    layouts = []
    last_order = None
    for _ in range(n + 1):
        order = list(range(n))
        while True:
            rng.shuffle(order)
            if last_order is None or all(a != b for a, b in zip(order, last_order)):
                break
        last_order = order.copy()
        while True:
            layout = [{'id': animals[j]['id'], 'x': slots[i][0] + rng.uniform(-10, 10),
                         'y': slots[i][1] + rng.uniform(-7, 7), 'angle': rng.uniform(-params['rotation_range'], params['rotation_range']),
                         'scale': rng.uniform(1 - params['scale_range'], 1 + params['scale_range']),
                         'phase': rng.uniform(0, 6.283185307179586), 'omega': rng.uniform(.22, .38)} for i, j in enumerate(order)]
            if separated(layout):
                layouts.append(layout)
                break
    world = {'animals': animals, 'layouts': layouts, 'listed_species': listed, 'parameters': params}
    identity = {'mechanic_id': MECHANIC_ID, 'task_id': task['id'], 'challenge_id': hashlib.sha256((str(seed) + task['id'] + json.dumps(condition,sort_keys=True)).encode()).hexdigest()[:20], 'control_condition': copy.deepcopy(condition)}
    public = {**identity, **copy.deepcopy(world), 'asset_manifest': 'shared_runtime/assets/provenance/fluke_census_v0.json', 'title': 'Fluke Census', 'prompt': 'One photograph. Each individual. No repeats.', 'generator': {'name': 'fluke_identity_census_v1', 'variant_count': 10**12}}
    truth = {**identity, 'world': copy.deepcopy(world), 'required_ids': [a['id'] for a in animals if a['species'] in listed]}
    return public, truth
