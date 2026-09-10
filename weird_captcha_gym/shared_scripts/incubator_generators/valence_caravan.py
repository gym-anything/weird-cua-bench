"""Original, search-validated growing-body chambers. No source layouts/assets used."""
from __future__ import annotations
import copy
import hashlib
import json
import random
from collections import deque

MECHANIC_ID = 'valence_caravan'
DELTAS = {'N':(0,-1),'E':(1,0),'S':(0,1),'W':(-1,0)}
PROFILES = {
 1: {'valences':[2,1,1], 'size':5, 'obstacles':1, 'turntables':0},
 2: {'valences':[2,2,1,1], 'size':5, 'obstacles':2, 'turntables':0},
 3: {'valences':[3,1,1,1], 'size':6, 'obstacles':4, 'turntables':2},
 4: {'valences':[2,2,2,1,1], 'size':6, 'obstacles':5, 'turntables':2},
 5: {'valences':[3,2,2,1,1,1], 'size':6, 'obstacles':6, 'turntables':2},
}

def component(edges):
    found={0}
    while True:
        new=found | {b for a,b in edges if a in found} | {a for a,b in edges if b in found}
        if new==found:return found
        found=new

def transition(world, state, command):
    positions, edges=state
    moving=component(edges)
    if command in DELTAS:
        dx,dy=DELTAS[command]
        proposed=tuple((x+dx,y+dy) if i in moving else (x,y) for i,(x,y) in enumerate(positions))
    elif command in ('CW','CCW') and list(positions[0]) in world['turntables']:
        px,py=positions[0]; sign=1 if command=='CW' else -1
        proposed=tuple((px-sign*(y-py),py+sign*(x-px)) if i in moving else (x,y) for i,(x,y) in enumerate(positions))
    else:return state
    floor=world['_floor'] if '_floor' in world else {tuple(p) for p in world['floor']}
    if len(set(proposed))!=len(proposed) or any(p not in floor for p in proposed):return state
    bonds=set(edges); degree=[0]*len(positions)
    for a,b in bonds:degree[a]+=1;degree[b]+=1
    # Simultaneous contacts resolved by visible atom label order, A then B etc.
    for a in range(len(positions)):
        for b in range(a+1,len(positions)):
            if a not in moving and b not in moving:continue
            if (a,b) not in bonds and degree[a]<world['valences'][a] and degree[b]<world['valences'][b] and sum(abs(proposed[a][k]-proposed[b][k]) for k in (0,1))==1:
                bonds.add((a,b));degree[a]+=1;degree[b]+=1
    return proposed,tuple(sorted(bonds))

def solved(world,state):
    degree=[0]*len(world['valences'])
    for a,b in state[1]:degree[a]+=1;degree[b]+=1
    return degree==world['valences'] and len(component(state[1]))==len(degree)

def solve_world(world, limit=24000):
    world={**world,'_floor':{tuple(p) for p in world['floor']}}
    initial=(tuple(map(tuple,world['positions'])),())
    queue=deque([initial]); parents={initial:None}
    while queue and len(parents)<limit:
        state=queue.popleft()
        if solved(world,state):
            route=[]
            while parents[state] is not None:
                state,cmd=parents[state];route.append(cmd)
            return route[::-1],len(parents)
        for cmd in (*DELTAS, 'CW','CCW'):
            nxt=transition(world,state,cmd)
            if nxt not in parents:
                parents[nxt]=(state,cmd);queue.append(nxt)
    return None,len(parents)

def generate(task,seed):
    condition=copy.deepcopy(task.get('_control_condition') or task.get('metadata',{}).get('control_condition'))
    params=copy.deepcopy((condition or {}).get('difficulty_parameters') or PROFILES[4])
    if params not in PROFILES.values():raise ValueError('Unsupported chamber profile')
    rng=random.Random(hashlib.sha256(f'{MECHANIC_ID}|{seed}|{json.dumps(params, sort_keys=True)}'.encode()).digest())
    size=params['size'];cells=[(x,y) for y in range(size) for x in range(size)]
    for attempt in range(300):
        walls=set(rng.sample(cells,params['obstacles']))
        floor=[p for p in cells if p not in walls]
        pos=rng.sample(floor,len(params['valences']))
        if any(abs(a[0]-b[0])+abs(a[1]-b[1])==1 for i,a in enumerate(pos) for b in pos[i+1:]):continue
        pads=rng.sample([p for p in floor if p not in pos],params['turntables'])
        world={'size':size,'floor':[list(p) for p in floor],'positions':[list(p) for p in pos], 'valences':params['valences'],'turntables':[list(p) for p in pads]}
        route,nodes=solve_world(world)
        if not route or len(route)<len(pos)+2:
            continue
        if pads:
            if not any(c in ('CW','CCW') for c in route):
                continue
            plain_route, plain_nodes=solve_world({**world,'turntables':[]})
            # A search cutoff is not evidence that turning is necessary.
            if plain_route is not None or plain_nodes>=24000:
                continue
        break
    else:raise ValueError('Could not construct a reachable chamber')
    identity=hashlib.sha256(f'{seed}|{world}'.encode()).hexdigest()[:20]
    public={'benchmark':'weird_captcha_gym','mechanic_id':MECHANIC_ID,'task_id':task['id'],'challenge_id':identity,
      'prompt':task.get('natural_language','Join every atom and fill every bond slot.'), 'world':world,
      'generator':{'name':'valence_caravan_v0','variant_count':1000000},
      'asset_manifest':'shared_runtime/assets/provenance/valence_caravan_v0.json'}
    if condition:public['control_condition']=condition
    truth=copy.deepcopy(public);truth.update(seed=seed,solution_path=route,search_nodes=nodes)
    return public,truth
