"""Independent graph, gesture and synchronous-threshold-cascade replay."""
from __future__ import annotations
import math
MECHANIC_ID='threshold_grapevine'


def cascade(world, edges):
    active=set(world['seeds']); rounds=[sorted(active)]
    while True:
        new=set(active)
        for node in world['nodes']:
            i=node['id']; neighbors={b if a==i else a for a,b in edges if i in (a,b)}
            num,den=node['threshold']
            if neighbors and len(neighbors&active)*den>=len(neighbors)*num:new.add(i)
        if new==active:return rounds
        active=new;rounds.append(sorted(active))


def intersects(p,q,a,b):
    def cross(u,v,w):return (v[0]-u[0])*(w[1]-u[1])-(v[1]-u[1])*(w[0]-u[0])
    return cross(p,q,a)*cross(p,q,b)<0 and cross(a,b,p)*cross(a,b,q)<0


def grade(payload, truth, public):
    def fail(message):return dict(graded=True,passed=False,score=0,feedback=message)
    if any(not isinstance(v,dict) for v in (payload,truth,public)):return fail('Malformed result')
    for key in ('mechanic_id','task_id','challenge_id'):
        if not truth.get(key) or any(v.get(key)!=truth[key] for v in (payload,public)):return fail('Stale task or challenge')
    if truth['mechanic_id']!=MECHANIC_ID:return fail('Wrong mechanic')
    condition=truth.get('control_condition')
    if any(v.get('control_condition')!=condition for v in (public,payload)):return fail('Wrong control condition')
    mode=(condition or {}).get('interaction','full')
    if mode not in ('full','simplified'):return fail('Invalid interaction')
    try:
        w=truth['world']
        if w!=public['world']:return fail('World mismatch')
        if condition and condition['difficulty_parameters']!=truth['parameters']:return fail('Profile mismatch')
        nodes=w['nodes'];n=len(nodes)
        initial={tuple(e) for e in w['edges']};fixed={tuple(e) for e in w['fixed_edges']}
        if not 5<=n<=12 or not fixed<=initial:return fail('Invalid graph')
        edges=set(initial);stage=0;run=None;last_time=0;finished=False
        events=payload.get('events')
        if not isinstance(events,list) or not 1<=len(events)<=2000:return fail('Missing graph actions')
        for seq,e in enumerate(events,1):
            if not isinstance(e,dict) or e.get('seq')!=seq or type(e.get('seq')) is not int or finished:return fail('Invalid action sequence')
            t=e.get('t');kind=e.get('type')
            if type(t) not in (int,float) or not math.isfinite(t) or t<last_time or e.get('stage')!=stage:return fail('Invalid action time or stage')
            last_time=t
            if run and t<run['end']:return fail('Action during cascade')
            if kind=='edit':
                if e.get('input_source')!=('graph_gesture' if mode=='full' else 'pair_buttons'):return fail('Wrong interaction input')
                edge=e.get('edge')
                if not isinstance(edge,list) or len(edge)!=2 or any(type(i) is not int for i in edge):return fail('Invalid endpoints')
                a,b=edge
                if not 0<=a<b<n or (a,b) in fixed:return fail('Fixed or invalid friendship')
                adding=(a,b) not in edges
                if e.get('operation')!=('add' if adding else 'cut'):return fail('Stale friendship')
                if mode=='full':
                    path=e.get('path')
                    if not isinstance(path,list) or not 2<=len(path)<=512 or any(not isinstance(p,list) or len(p)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in p) for p in path):return fail('Invalid graph gesture')
                    if any(not 0<=p[0]<=860 or not 0<=p[1]<=470 for p in path):return fail('Gesture outside board')
                    points=[(node['x'],node['y']) for node in nodes]
                    hit=lambda p:next((i for i,v in enumerate(points) if math.dist(p,v)<=25),None)
                    if adding:
                        if sorted([hit(path[0]) if hit(path[0]) is not None else -1,hit(path[-1]) if hit(path[-1]) is not None else -1])!=edge:return fail('Drag misses portrait')
                    else:
                        if hit(path[0]) is not None:return fail('Scratch begins on portrait')
                        crossed={item for item in edges-fixed if any(intersects(p,q,points[item[0]],points[item[1]]) for p,q in zip(path,path[1:]))}
                        # One visible cut per stroke, nearest intersection from its beginning.
                        if (a,b) not in crossed:return fail('Scratch misses friendship')
                        if len(crossed)!=1:return fail('Ambiguous scratch')
                changed=edges.symmetric_difference({(a,b)})
                if len(changed^initial)>w['edit_limit']:return fail('Edit reserve exceeded')
                edges=changed;run=None
            elif kind=='reset':edges=set(initial);run=None
            elif kind=='run':
                rounds=cascade(w,edges)
                run=dict(end=t+len(rounds)*w['round_ms'],rounds=rounds)
            elif kind=='accept':
                if not run or run['rounds'][-1]!=w['targets'][stage]:return fail('Cascade does not satisfy stage goal')
                if e.get('rounds')!=run['rounds']:return fail('False cascade report')
                stage+=1;run=None;edges=set(initial)
                if stage==len(w['targets']):finished=True
            elif kind=='abandon':return fail('FAIL · Board abandoned')
            else:return fail('Unknown graph action')
        if not finished or payload.get('completed') is not True:return fail('Both graph goals have not been certified')
        return dict(graded=True,passed=True,score=100,feedback=f'PASS · {stage} threshold cascade goals independently replayed')
    except (KeyError,TypeError,ValueError,IndexError,OverflowError):return fail('Malformed graph contract or transcript')
