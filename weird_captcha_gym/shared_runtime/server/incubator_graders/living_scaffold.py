"""Exact discrete articulated-body physics; no client outcome is trusted."""
from collections import deque

MECHANIC_ID = 'living_scaffold'
DELTAS = {'N': (0,-1), 'E': (1,0), 'S': (0,1), 'W': (-1,0)}


def initial(board):
    return (tuple(tuple(tuple(p) for p in s) for s in board['creatures']), tuple(sorted(tuple(p) for p in board['food'])), False)


def settle(board, bodies, food):
    """Support is the transitive closure from rock. Unsupported cycles fall together."""
    rocks = set(map(tuple, board['rocks']))
    bodies = list(bodies)
    for _ in range(board['height'] + 2):
        # Blossoms open only once all food is eaten. Exiting removes support immediately.
        if not food:
            bodies = [() if s and s[0] == tuple(board['exits'][i]) else s for i,s in enumerate(bodies)]
        supported = set()
        changed = True
        while changed:
            changed = False
            solid = rocks | {p for i in supported for p in bodies[i]}
            for i,s in enumerate(bodies):
                own = set(s)
                if s and i not in supported and any((x,y+1) in solid and (x,y+1) not in own for x,y in s):
                    supported.add(i); changed = True
        falling = [i for i,s in enumerate(bodies) if s and i not in supported]
        if not falling:
            return (tuple(bodies), tuple(sorted(food)), False)
        for i in falling:
            bodies[i] = tuple((x,y+1) for x,y in bodies[i])
        if any(y >= board['height'] for s in bodies for x,y in s):
            return (tuple(bodies), tuple(sorted(food)), True)
    raise ValueError('gravity failed to settle')


def step(board, state, creature, direction):
    bodies, fruits, dead = state
    if dead or not 0 <= creature < len(bodies) or not bodies[creature]:
        return state
    dx,dy = DELTAS[direction]
    head = bodies[creature][0]
    dest = (head[0]+dx, head[1]+dy)
    food = set(fruits)
    growing = dest in food
    occupied = set(map(tuple, board['rocks']))
    for i,s in enumerate(bodies):
        occupied.update(s if i != creature or growing else s[:-1])
    if dest in occupied or not 0 <= dest[0] < board['width'] or dest[1] < 0 or dest[1] >= board['height']:
        return state
    new = list(bodies)
    new[creature] = (dest,) + (bodies[creature] if growing else bodies[creature][:-1])
    food.discard(dest)
    return settle(board, new, food)


def solved(state):
    return not state[2] and not state[1] and not any(state[0])


def solve(board, limit=150000):
    # Weighted best-first search certifies reachability, not optimality.
    import heapq
    import itertools
    serial=itertools.count()
    def estimate(state):
        bodies,food,_=state
        heads=[s[0] for s in bodies if s]
        fruit_cost=sum(min(abs(x-a)+abs(y-b) for a,b in heads) for x,y in food) if heads else 0
        exit_cost=sum(abs(s[0][0]-board['exits'][i][0])+abs(s[0][1]-board['exits'][i][1]) for i,s in enumerate(bodies) if s)
        return fruit_cost*3 + exit_cost + len(food)*4 + len(heads)*3
    start=initial(board)
    queue=[(estimate(start)*3,next(serial),0,start)]
    previous={start:None}; costs={start:0}; end=None
    while queue and len(previous)<=limit:
        _,_,cost,state=heapq.heappop(queue)
        if cost!=costs[state]: continue
        if solved(state): end=state; break
        for i,s in enumerate(state[0]):
            if not s: continue
            for d in DELTAS:
                nxt=step(board,state,i,d)
                if nxt[2] or cost+1 >= costs.get(nxt,10**9): continue
                previous[nxt]=(state,i,d);costs[nxt]=cost+1
                heapq.heappush(queue,(cost+1+3*estimate(nxt),next(serial),cost+1,nxt))
    if end is None: return None
    path=[]
    while previous[end] is not None:
        old,i,d=previous[end];path.append([i,d]);end=old
    return list(reversed(path))


def grade(payload, ground_truth, public_state):
    def fail(reason): return dict(graded=True,passed=False,score=0,feedback=reason)
    if not all(isinstance(x,dict) for x in (payload,ground_truth,public_state)): return fail('Malformed result')
    for key in ('mechanic_id','task_id','challenge_id'):
        if not ground_truth.get(key) or payload.get(key) != ground_truth[key] or public_state.get(key) != ground_truth[key]:
            return fail('Stale or mismatched identity')
    if ground_truth['mechanic_id'] != MECHANIC_ID: return fail('Wrong mechanic')
    if public_state.get('board') != ground_truth.get('board'): return fail('Geometry mismatch')
    condition=ground_truth.get('control_condition')
    if public_state.get('control_condition') != condition or payload.get('control_condition') != condition: return fail('Condition mismatch')
    source = 'keyboard' if (condition or {}).get('interaction','full') == 'full' else 'buttons'
    actions=payload.get('actions')
    if not isinstance(actions,list) or not 1 <= len(actions) <= 2000: return fail('Missing or oversized transcript')
    board=ground_truth['board']; state=initial(board); history=[]
    for a in actions:
        if not isinstance(a,dict): return fail('Malformed action')
        kind=a.get('type')
        if kind=='undo':
            if history: state=history.pop()
        elif kind=='reset': state=initial(board); history=[]
        elif kind=='move':
            if a.get('input_source')!=source or type(a.get('creature')) is not int or not isinstance(a.get('direction'),str) or a['direction'] not in DELTAS: return fail('Wrong input surface or move')
            if not 0 <= a['creature'] < len(state[0]): return fail('Invalid creature')
            nxt=step(board,state,a['creature'],a['direction'])
            if nxt!=state: history.append(state)
            state=nxt
        else: return fail('Unknown action')
    if not solved(state): return fail('Collect every fruit and guide every creature into its blossom; undo a fall.')
    return dict(graded=True,passed=True,score=100,feedback='PASS — all creatures and food replayed with support and gravity.')


def cheat(public_state,ground_truth):
    return {'solution_path':ground_truth['solution_path']}
