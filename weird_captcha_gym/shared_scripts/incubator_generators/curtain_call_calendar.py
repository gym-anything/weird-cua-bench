"""Seeded theatre scheduling; the witness never enters the browser state."""
from __future__ import annotations
import copy
import hashlib
import json
import random

MECHANIC_ID = 'curtain_call_calendar'
BASELINE_PARAMETERS = {'bookings': 5, 'fixed': 1, 'slack': 3, 'edges': 3, 'bounded_records': False}
NAMES = ['Moon Ballet', 'Paper Dragon', 'Clockwork Choir', 'Velvet Storm', 'Lantern Waltz', 'Silver Circus', 'Fox Masquerade']


def generate(task, seed):
    condition = copy.deepcopy(task.get('_control_condition') or task.get('metadata', {}).get('control_condition'))
    p = dict((condition or {}).get('difficulty_parameters') or BASELINE_PARAMETERS)
    n, fixed, slack, edges = (p[k] for k in ('bookings', 'fixed', 'slack', 'edges'))
    if not (3 <= n <= 7 and 0 <= fixed < n and 0 <= slack <= 8 and 0 <= edges <= n*(n-1)//2):
        raise ValueError('invalid scheduling parameters')
    rng = random.Random(hashlib.sha256((str(seed)+json.dumps(p,sort_keys=True)).encode()).hexdigest())
    names = rng.sample(NAMES, n)
    order = list(range(n)); rng.shuffle(order)
    lengths = [rng.randint(2, 3) for _ in range(n)]
    gaps = [0]*n
    for _ in range(slack): gaps[rng.randrange(n)] += 1
    witness = {}; cursor = 0
    for i in order:
        if cursor % 16 + lengths[i] > 16: cursor = (cursor//16+1)*16
        witness[str(i)] = [cursor, cursor+lengths[i]]
        cursor += lengths[i]+gaps[i]
    horizon = ((max(x[1] for x in witness.values())-1)//16+1)*16
    fixed_ids = set(rng.sample(order[1:-1], min(fixed,n-2)))
    candidates = [(str(order[a]),str(order[b])) for a in range(n) for b in range(a+1,n)]
    rng.shuffle(candidates); precedence = [list(x) for x in candidates[:edges]]
    permitted_end = min(horizon,cursor)
    bookings=[]
    for i in range(n):
        a,b = witness[str(i)]
        lo,hi = (max(0,a-rng.randint(1,3)),min(permitted_end,b+rng.randint(1,3))) if p['bounded_records'] else (0,permitted_end)
        start = rng.randrange(horizon-lengths[i]+1)
        end = min(horizon,start+lengths[i]+(1 if i%2 == 0 else 0))
        if i in fixed_ids: start,end=a,b
        bookings.append({'id':str(i),'name':names[i],'duration':lengths[i], 'fixed':i in fixed_ids,'window':[lo,hi], 'initial':[start,end], 'color':i})
    # Always seed a visible defect without relying on a lucky random overlap.
    editable = [x for x in bookings if not x['fixed']]
    editable[0]['initial']=[0,1]
    date = f'2027-{rng.randint(1,12):02d}-{rng.randint(10,24):02d}'
    world={'bookings':bookings,'precedence':precedence,'horizon':horizon,'date':date,'slots_per_day':16,'slot_minutes':30,'opening_hour':9}
    identity = hashlib.sha256(f'{seed}|{task.get("id")}|{p}|{condition}'.encode()).hexdigest()[:20]
    public={'mechanic_id':MECHANIC_ID,'task_id':task['id'],'challenge_id':identity,'prompt':'Curtain Call Calendar','asset_manifest':'shared_runtime/assets/provenance/curtain_call_calendar_v0.json','world':world,'control_condition':condition or {'difficulty':3,'interaction':'full','real_time':'live','difficulty_parameters':p},'generator':{'name':'curtain_call_calendar_v0','variant_count':1000000}}
    truth=copy.deepcopy(public); truth['solution']=witness; truth['seed']=str(seed)
    return public,truth
