"""Original XART-226 transformation: continuous sun-relative dance dispatch."""
from __future__ import annotations
import copy
import hashlib
import math
import random

MECHANIC_ID = 'waggle_dispatch'
BASELINE = {'site_radius': 18, 'sun_speed': 4, 'site_gap_deg': 65}


def generate(task, seed):
    condition = task.get('_control_condition')
    p = dict(condition['difficulty_parameters'] if condition else BASELINE)
    if not 10 <= p['site_radius'] <= 32 or not 0 <= p['sun_speed'] <= 8 or not 45 <= p['site_gap_deg'] <= 120:
        raise ValueError('unsupported meadow profile')
    rng = random.Random(hashlib.sha256(f'{seed}|{MECHANIC_ID}|v1'.encode()).digest())
    bearing = rng.uniform(0, 360)
    names = ['Oak', 'Quarry', 'Chapel']; rng.shuffle(names)
    sites = []
    for i in range(3):
        a = math.radians(bearing + (i-1)*p['site_gap_deg'])
        distance = rng.choice([108, 144, 180])
        sites.append({'id': i, 'name': names[i], 'x': round(math.sin(a)*distance, 5), 'y': round(-math.cos(a)*distance, 5), 'radius': p['site_radius']})
    world = {'sites': sites, 'target': rng.randrange(3), 'required': 6, 'distance_per_second': 36,
             'flight_ms': 2400, 'max_hold_ms': 6500, 'parameters': p,
             'sun_phase': rng.uniform(0,360), 'sun_direction': rng.choice([-1,1]), 'sun_wave': rng.uniform(0,6.28)}
    token = hashlib.sha256((str(seed)+repr(p)+MECHANIC_ID).encode()).hexdigest()[:16]
    public = {'benchmark':'weird_captcha_gym','mechanic_id':MECHANIC_ID,'task_id':task['id'],'challenge_id':token,
              'prompt':task.get('natural_language',''), 'world':world,
              'generator':{'name':'waggle_dispatch_v1','variant_count':1000000000},
              'asset_manifest':'shared_runtime/assets/provenance/waggle_dispatch_v0.json'}
    truth = copy.deepcopy(public); truth['seed'] = seed
    if condition:
        public['control_condition']=copy.deepcopy(condition);truth['control_condition']=copy.deepcopy(condition)
    return public, truth
