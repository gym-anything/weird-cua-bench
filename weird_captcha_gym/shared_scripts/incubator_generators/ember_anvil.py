"""Original finite-volume smithing; reverse legal construction proves reachability."""
from __future__ import annotations
import copy
import hashlib
import random

MECHANIC_ID = 'ember_anvil'
N = 7
DIRS = ((1, 0), (0, 1), (-1, 0), (0, -1))
DEFAULT = dict(span=5, max_height=3, scramble_steps=10, excess=2, relief=True, cooling_ms=45000)


def neighbor(cell, direction):
    x, y = cell % N, cell // N
    dx, dy = DIRS[direction]
    return (y + dy) * N + x + dx if 0 <= x + dx < N and 0 <= y + dy < N else None


def move(heights, cell, mode, direction, cap):
    out = heights[:]
    if not 0 <= cell < N*N or heights[cell] == 0:
        return None
    if mode == 'split':
        out[cell] -= 1
        return out
    dest = neighbor(cell, direction)
    if dest is None or heights[dest] >= cap:
        return None
    if mode == 'draw' and heights[dest] >= heights[cell]:
        return None
    if mode == 'upset' and heights[dest] != heights[cell]:
        return None
    if mode not in ('draw', 'upset'):
        return None
    out[cell] -= 1
    out[dest] += 1
    return out


def connected(h):
    occupied = {i for i, v in enumerate(h) if v}
    if not occupied:
        return False
    seen = {min(occupied)}
    todo = list(seen)
    while todo:
        i = todo.pop()
        for d in range(4):
            j = neighbor(i, d)
            if j in occupied and j not in seen:
                seen.add(j); todo.append(j)
    return seen == occupied


def generate(task, seed):
    condition = task.get('_control_condition') or (task.get('metadata') or {}).get('control_condition')
    p = dict(DEFAULT)
    p.update((condition or {}).get('difficulty_parameters') or {})
    rng = random.Random(int.from_bytes(hashlib.sha256(f'{seed}|ember-anvil-v0'.encode()).digest()[:8], 'big'))
    span, cap = p['span'], p['max_height']
    target = [0] * (N*N)
    for y in range(2, 5):
        for x in range(1, span + 1):
            target[y*N+x] = 1
    # A generated cutting edge, socket depth and shoulder alter volume, not palette.
    if span >= 4:
        target[1*N+span] = 1
        target[5*N+span] = 1
        if rng.choice((False, True)):
            target[1*N+span-1] = 1
    if p['relief']:
        for y in range(2, 5):
            for x in (1, 2):
                target[y*N+x] = cap - 1
        target[3*N+1] = 0  # the through-eye is part of the solid target
        target[rng.choice((2, 4))*N+2] = cap
    turns = rng.randrange(4)
    for _ in range(turns):
        target = [target[(N-1-x)*N+y] for y in range(N) for x in range(N)]
    h = target[:]
    excess_cells = []
    for _ in range(p['excess']):
        i = rng.choice([i for i, v in enumerate(h) if 0 < v < cap])
        h[i] += 1; excess_cells.append(i)
    undo = []
    seen = {tuple(h)}
    for _ in range(p['scramble_steps']):
        choices = []
        for i in range(N*N):
            for d in range(4):
                for mode in ('draw', 'upset'):
                    after = move(h, i, mode, d, cap)
                    if after is None or tuple(after) in seen or not connected(after):
                        continue
                    j = neighbor(i, d)
                    reverse = 'draw' if after[i] < after[j] else 'upset'
                    if move(after, j, reverse, (d+2)%4, cap) != h:
                        continue
                    distance = sum(abs(a-b) for a,b in zip(after,target))
                    choices.append((distance + rng.random()*5, after, dict(cell=j, mode=reverse, direction=(d+2)%4)))
        if not choices:
            raise ValueError('no reversible smithing deformation')
        _, h, action = max(choices, key=lambda c:c[0])
        seen.add(tuple(h)); undo.append(action)
    solution = list(reversed(undo)) + [dict(cell=i,mode='split',direction=0) for i in reversed(excess_cells)]
    replay = h[:]
    for a in solution:
        replay = move(replay, a['cell'], a['mode'], a['direction'], cap)
    assert replay == target and h != target
    task_id = task['id']
    challenge_id = hashlib.sha256(f'{seed}|{task_id}|ember-v0'.encode()).hexdigest()[:16]
    world = dict(size=N, initial=h, target=target, max_height=cap, cooling_ms=p['cooling_ms'], heat_ms=2400, workable=0.35, initial_heat=1.0, title='Socket axe' if p['relief'] else 'Tapered blade')
    public = dict(benchmark='weird_captcha_gym',mechanic_id=MECHANIC_ID,task_id=task_id,challenge_id=challenge_id,prompt='Forge the complete tool head.',submit_label='STAMP TOOL',world=world,asset_manifest='shared_runtime/assets/provenance/ember_anvil_v0.json',generator={'name':'ember_anvil_v0'})
    truth = dict(mechanic_id=MECHANIC_ID,task_id=task_id,challenge_id=challenge_id,seed=seed,world=copy.deepcopy(world),solution=solution)
    if condition:
        public['control_condition']=copy.deepcopy(condition);truth['control_condition']=copy.deepcopy(condition)
    return public,truth
