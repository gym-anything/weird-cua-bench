"""Original PCGRL-inspired garden geometry; no source code or assets copied."""
from __future__ import annotations
import copy
import hashlib
import random
from collections import deque

MECHANIC_ID = 'long_way_home'
PROFILES = {1: (5, 5, 2), 2: (7, 7, 4), 3: (9, 9, 8), 4: (11, 9, 14), 5: (13, 11, 22)}


def distances(board, w, h, start):
    seen = {start: 0}
    queue = deque([start])
    while queue:
        i = queue.popleft()
        x, y = i % w, i // w
        for nx, ny in ((x+1,y),(x,y+1),(x-1,y),(x,y-1)):
            j = ny*w+nx
            if 0 <= nx < w and 0 <= ny < h and not board[j] and j not in seen:
                seen[j] = seen[i]+1
                queue.append(j)
    return seen


def generate(task, seed):
    condition = copy.deepcopy(task.get('_control_condition'))
    level = int((condition or {}).get('difficulty', 3))
    w, h, openings = PROFILES[level]
    params = (condition or {}).get('difficulty_parameters') or {}
    w, h, openings = int(params.get('width', w)), int(params.get('height', h)), int(params.get('openings', openings))
    rng = random.Random(int(hashlib.sha256(f'{seed}|{MECHANIC_ID}'.encode()).hexdigest(),16))
    # Random spanning maze provides a constructive existence proof, never rendered.
    for attempt in range(200):
        board = [1]*(w*h)
        start = rng.choice([y*w+x for y in range(0,h,2) for x in range(0,w,2)])
        board[start] = 0
        stack = [start]
        while stack:
            i = stack[-1]; x,y = i%w,i//w
            options = [(nx,ny) for nx,ny in ((x+2,y),(x,y+2),(x-2,y),(x,y-2)) if 0<=nx<w and 0<=ny<h and board[ny*w+nx]]
            if not options:
                stack.pop(); continue
            nx,ny = rng.choice(options)
            board[((y+ny)//2)*w+(x+nx)//2] = 0
            board[ny*w+nx] = 0
            stack.append(ny*w+nx)
        a = max(distances(board,w,h,start), key=distances(board,w,h,start).get)
        ds = distances(board,w,h,a); b = max(ds,key=ds.get)
        target = ds[b]
        walls = [i for i,v in enumerate(board) if v]
        initial = board[:]
        for i in rng.sample(walls,min(openings,len(walls))): initial[i]=0
        # A route must need redesign rather than accepting the generated starting map.
        if distances(initial,w,h,a)[b] < target:
            break
    else:
        raise ValueError('could not construct an unsolved reachable garden')
    # A few immovable stone planters require solutions to respond to the seed.
    remaining = [i for i in walls if initial[i]]
    locked = sorted(rng.sample(remaining,min(level,len(remaining))))
    task_id = task.get('id','long_way_home_seed_0001@0.1')
    cid = hashlib.sha256(f'{seed}|{task_id}|{level}|{MECHANIC_ID}'.encode()).hexdigest()[:16]
    garden = dict(width=w,height=h,initial=initial,entrance=a,exit=b,target=target,locked=locked)
    public = dict(benchmark='weird_captcha_gym', mechanic_id=MECHANIC_ID,task_id=task_id,challenge_id=cid,
                  prompt='Design the long way home.',garden=garden, generator={'name':'long_way_home_v0'},
                  asset_manifest='shared_runtime/assets/provenance/long_way_home_v0.json')
    truth = dict(mechanic_id=MECHANIC_ID,task_id=task_id,challenge_id=cid,seed=seed,garden=copy.deepcopy(garden),solution_board=board)
    if condition:
        public['control_condition']=copy.deepcopy(condition);truth['control_condition']=condition
    return public,truth
