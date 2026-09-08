"""Original seeded gardens, accepted only after exact body/gravity search."""
import copy
import hashlib
import importlib.util
import json
import random
from pathlib import Path

MECHANIC_ID = 'living_scaffold'
_spec = importlib.util.spec_from_file_location('living_scaffold_physics', Path(__file__).resolve().parents[2] / 'shared_runtime/server/incubator_graders/living_scaffold.py')
physics = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(physics)
PROFILES = {
    1: {'creature_count':1,'return_blossom':False,'high_canopy':False,'overhang':False},
    2: {'creature_count':2,'return_blossom':False,'high_canopy':False,'overhang':False},
    3: {'creature_count':2,'return_blossom':True,'high_canopy':True,'overhang':False},
    4: {'creature_count':3,'return_blossom':False,'high_canopy':True,'overhang':False},
    5: {'creature_count':3,'return_blossom':True,'high_canopy':True,'overhang':True},
}


def generate(task, seed):
    condition=copy.deepcopy(task.get('_control_condition'))
    p=dict((condition or {}).get('difficulty_parameters') or PROFILES[2])
    if p not in PROFILES.values(): raise ValueError('Unsupported garden profile')
    level=next(k for k,v in PROFILES.items() if v==p)
    rng=random.Random(int(hashlib.sha256(f'{seed}|{MECHANIC_ID}|{level}'.encode()).hexdigest(),16))
    for attempt in range(80):
        n=p['creature_count']
        left=rng.choice([[1,2],[1],[2]])
        right=rng.choice([[6,7],[6],[6,7,8]])
        board=dict(width=10,height=8,rocks=[[x,6] for x in left+right],
                   creatures=[[[3,5],[2,5],[1,5]]],food=[[4,5]],exits=[[rng.choice([6,7]),5]])
        if n>=2:
            board['creatures'].append([[2,4],[1,4]])
            board['food'].append([rng.choice([4,5,6]),3 if p['high_canopy'] else 4])
            board['exits'].append([rng.choice([1,2,3] if p['return_blossom'] else [5,6,7]),2 if p['high_canopy'] else 3])
        if n==3:
            board['creatures'].append([[1,3],[2,3]])
            board['food'].append([rng.choice([3,4,5]),2])
            board['exits'].append([rng.choice([5,6,7]),1])
        if p['overhang']:
            board['rocks'] += [[rng.choice([4,5,6]),1]]
        occupied=[tuple(q) for s in board['creatures'] for q in s]+list(map(tuple,board['food']))+list(map(tuple,board['exits']))+list(map(tuple,board['rocks']))
        if len(set(occupied))!=len(occupied): continue
        if physics.settle(board,physics.initial(board)[0],physics.initial(board)[1])!=physics.initial(board): continue
        path=physics.solve(board,25000)
        if path: break
    else: raise ValueError('Could not certify garden within generation budget')
    # Reflection and identity permutation preserve vertical gravity while changing input paths.
    mirror=rng.choice([False,True])
    if mirror:
        for key in ('rocks','food','exits'):
            board[key]=[[board['width']-1-x,y] for x,y in board[key]]
        board['creatures']=[[[board['width']-1-x,y] for x,y in s] for s in board['creatures']]
        path=[[i,{'E':'W','W':'E'}.get(d,d)] for i,d in path]
    order=list(range(n));rng.shuffle(order)
    board['creatures']=[board['creatures'][i] for i in order]
    board['exits']=[board['exits'][i] for i in order]
    path=[[order.index(i),d] for i,d in path]
    state=physics.initial(board)
    for i,d in path: state=physics.step(board,state,i,d)
    assert physics.solved(state)
    task_id=task.get('id','living_scaffold_seed_0001@0.1')
    identity=json.dumps([seed,task_id,p],sort_keys=True)
    public=dict(benchmark='weird_captcha_gym',mechanic_id=MECHANIC_ID,task_id=task_id,
                challenge_id=hashlib.sha256(identity.encode()).hexdigest()[:16],
                board=board,prompt=task.get('natural_language','Gather every fruit. Guide each creature into its matching blossom.'),
                generator={'name':'living_scaffold_v0','certification':'exact articulated-body replay'},
                asset_manifest='shared_runtime/assets/provenance/living_scaffold_v0.json')
    truth=copy.deepcopy(public);truth.update(seed=seed,solution_path=path,generation_attempts=attempt+1)
    if condition:
        public['control_condition']=copy.deepcopy(condition);truth['control_condition']=condition
    return public,truth
