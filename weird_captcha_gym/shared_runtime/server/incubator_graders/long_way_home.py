"""Independent replay and geometry verification for The Long Way Home."""
from collections import deque
MECHANIC_ID='long_way_home'


def inspect(board,g):
    w,h=g['width'],g['height']
    floors={i for i,v in enumerate(board) if v==0}
    unseen=set(floors); components=[]; path=[]
    while unseen:
        first=min(unseen); group={first}; queue=deque([first]); unseen.remove(first)
        while queue:
            i=queue.popleft();x,y=i%w,i//w
            for nx,ny in ((x+1,y),(x,y+1),(x-1,y),(x,y-1)):
                j=ny*w+nx
                if 0<=nx<w and 0<=ny<h and j in unseen:
                    unseen.remove(j);group.add(j);queue.append(j)
        components.append(sorted(group))
    start,end=g['entrance'],g['exit']
    if start in floors:
        prev={start:None};queue=deque([start])
        while queue:
            i=queue.popleft();x,y=i%w,i//w
            for nx,ny in ((x+1,y),(x,y+1),(x-1,y),(x,y-1)):
                j=ny*w+nx
                if 0<=nx<w and 0<=ny<h and j in floors and j not in prev:
                    prev[j]=i;queue.append(j)
        if end in prev:
            i=end
            while i is not None: path.append(i);i=prev[i]
            path.reverse()
    return dict(components=len(components),distance=len(path)-1 if path else None,path=path)


def grade(payload,ground_truth,public_state):
    def fail(msg): return dict(graded=True,passed=False,feedback=msg)
    if not all(isinstance(x,dict) for x in (payload,ground_truth,public_state)):return fail('Malformed result')
    for field in ('mechanic_id','task_id','challenge_id'):
        if not ground_truth.get(field) or payload.get(field)!=ground_truth[field] or public_state.get(field)!=ground_truth[field]:return fail('Stale or mismatched '+field)
    if ground_truth['mechanic_id']!=MECHANIC_ID:return fail('Wrong mechanic')
    g=ground_truth.get('garden')
    if g!=public_state.get('garden') or ground_truth.get('control_condition')!=public_state.get('control_condition'):return fail('World or condition mismatch')
    mode=(ground_truth.get('control_condition') or {}).get('interaction','full')
    if mode not in ('full','simplified') or payload.get('interaction')!=mode:return fail('Wrong interaction')
    events=payload.get('events')
    if not isinstance(events,list) or len(events)>10000:return fail('Invalid event list')
    board=g['initial'][:]; locked=set(g['locked'])|{g['entrance'],g['exit']}
    for event in events:
        if not isinstance(event,dict):return fail('Malformed event')
        kind=event.get('kind')
        if kind=='reset':board=g['initial'][:]
        elif kind=='edit':
            i,v=event.get('cell'),event.get('value')
            if type(i)!=int or not 0<=i<len(board) or type(v)!=int or v not in (0,1):return fail('Invalid tile')
            if i in locked:return fail('Protected tile')
            if event.get('input_source')!= {'full':'brush','simplified':'tile_controls'}[mode]:return fail('Wrong input surface')
            board[i]=v
        elif kind=='test':
            if event.get('report')!=inspect(board,g):return fail('Route report differs from geometry')
        else:return fail('Unknown event')
    if payload.get('board')!=board:return fail('Final geometry differs from edits')
    result=inspect(board,g)
    passed=result['components']==1 and result['distance']==g['target']
    return dict(graded=True,passed=passed,feedback=f"Walkable regions: {result['components']}; shortest route: {result['distance']}; required: {g['target']}",**result)


def cheat(public_state,ground_truth):
    return {'answers': [], 'solution_board':ground_truth['solution_board'],'instruction':'Edit geometry using the visible tools, test, and certify.'}
