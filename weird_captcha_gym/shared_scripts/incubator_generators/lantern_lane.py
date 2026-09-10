"""Original finite-fleet road settlement, grounded in survey TRW-051."""
from __future__ import annotations
import copy
import hashlib
import json
import random

MECHANIC_ID = 'lantern_lane'
BASELINE_PARAMETERS = dict(colors=3, river=True, crossed=True, fleet=2, queue_limit=5,
                           demand_interval=68, growth_percent=20, road_budget=62,
                           trip_ticks=4, quota=6, tick_ms=100, max_ticks=1800)


def generate(task, seed):
    condition = copy.deepcopy(task.get('_control_condition') or (task.get('metadata') or {}).get('control_condition'))
    p = copy.deepcopy(condition['difficulty_parameters'] if condition else BASELINE_PARAMETERS)
    if set(p) != set(BASELINE_PARAMETERS):
        raise ValueError('unknown or missing Lantern Lane parameter')
    for key in ('river', 'crossed'):
        if type(p[key]) is not bool: raise ValueError(key)
    for key in set(p) - {'river', 'crossed'}:
        if type(p[key]) is not int or p[key] < 0: raise ValueError(key)
    if not 1 <= p['colors'] <= 3 or not 1 <= p['fleet'] <= 4 or not 2 <= p['trip_ticks'] <= 10 or not 3 <= p['queue_limit'] < p['quota'] <= 12 or not 40 <= p['demand_interval'] <= 150 or not 0 <= p['growth_percent'] <= 40 or p['tick_ms'] != 100 or p['max_ticks'] != 1800 or not 25 <= p['road_budget'] <= 100:
        raise ValueError('unsupported settlement profile')
    rng = random.Random(int(hashlib.sha256(f'{seed}|lantern_lane-v1'.encode()).hexdigest()[:16], 16))
    rows = [1, 3, 5]
    rng.shuffle(rows)
    rows = rows[:p['colors']]
    dest_rows = rows[1:] + rows[:1] if p['crossed'] and len(rows)>1 else rows[:]
    bridges = sorted(rng.sample([1, 3, 5], 2)) if p['river'] else list(range(7))
    palette = ['#efb65a', '#78d6c7', '#cc9cfa']; rng.shuffle(palette)
    homes = [dict(node=y*11+1, color=i, entrance=y*11+2) for i,y in enumerate(rows)]
    sites = []
    satellite_x = rng.choice([7, 8])
    satellite_rows = [0, 3, 6]
    rng.shuffle(satellite_rows)
    for i,y in enumerate(dest_rows):
        sites.append(dict(node=y*11+9, color=i, parent=-1, interval=p['demand_interval']+rng.randrange(0,9), phase=rng.randrange(12,28)))
    for i,y in enumerate(satellite_rows[:p['colors']]):
        sites.append(dict(node=y*11+satellite_x, color=i, parent=i, interval=p['demand_interval']+rng.randrange(0,9), phase=0))
    world = dict(width=11, height=7, homes=homes, sites=sites, bridges=bridges, palette=palette, parameters=p,
                 initial_roads=[[h['node'],h['entrance']] for h in homes])
    token=json.dumps(world,sort_keys=True)
    challenge=hashlib.sha256(f'{seed}|{token}'.encode()).hexdigest()[:16]
    identity=dict(mechanic_id=MECHANIC_ID,task_id=task['id'],challenge_id=challenge)
    public=dict(**identity, benchmark='weird_captcha_gym', world=copy.deepcopy(world),
                prompt=task.get('natural_language','Keep the lantern carts moving. Connect matching homes and workshops, expand as new workshops open, and complete every order before a queue overflows.'),
                generator=dict(name='lantern_lane_v1',variant_count=1000000),asset_manifest='shared_runtime/assets/provenance/lantern_lane_v0.json')
    truth=dict(**identity,world=copy.deepcopy(world),seed=str(seed))
    if condition:
        public['control_condition']=copy.deepcopy(condition); truth['control_condition']=copy.deepcopy(condition)
    return public,truth
