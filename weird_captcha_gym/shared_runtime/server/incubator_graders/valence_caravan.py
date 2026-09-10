"""Replay primitive grid actions; never trust a client success flag or solution route."""
from __future__ import annotations
import copy
MECHANIC_ID='valence_caravan'

def initial(world):
    return {'positions':copy.deepcopy(world['positions']), 'bonds':[]}

def connected(bonds):
    group={0}
    for _ in range(len(bonds)+1):
        for a,b in bonds:
            if a in group or b in group:group.update((a,b))
    return group

def advance(world,state,command):
    group=connected(state['bonds']);p=state['positions'];out=copy.deepcopy(state)
    delta={'N':(0,-1),'E':(1,0),'S':(0,1),'W':(-1,0)}
    if command in delta:
        dx,dy=delta[command]
        for i in group:out['positions'][i]=[p[i][0]+dx,p[i][1]+dy]
    elif command in ('CW','CCW') and p[0] in world['turntables']:
        sign=1 if command=='CW' else -1
        for i in group:out['positions'][i]=[p[0][0]-sign*(p[i][1]-p[0][1]),p[0][1]+sign*(p[i][0]-p[0][0])]
    else:return out
    q=out['positions']
    if len({tuple(v) for v in q})!=len(q) or any(v not in world['floor'] for v in q):return copy.deepcopy(state)
    degrees=[0]*len(p)
    for a,b in out['bonds']:degrees[a]+=1;degrees[b]+=1
    for a in range(len(p)):
        for b in range(a+1,len(p)):
            if a not in group and b not in group:continue
            if [a,b] not in out['bonds'] and degrees[a]<world['valences'][a] and degrees[b]<world['valences'][b] and abs(q[a][0]-q[b][0])+abs(q[a][1]-q[b][1])==1:
                out['bonds'].append([a,b]);degrees[a]+=1;degrees[b]+=1
    out['bonds'].sort()
    return out

def complete(world,state):
    degrees=[0]*len(world['valences'])
    for a,b in state['bonds']:degrees[a]+=1;degrees[b]+=1
    return degrees==world['valences'] and len(connected(state['bonds']))==len(degrees)

def grade(payload, ground_truth, public_state):
    def fail(msg):return {'graded':True,'passed':False,'score':0,'feedback':msg}
    if not all(isinstance(v,dict) for v in (payload,ground_truth,public_state)):return fail('Malformed submission')
    for key in ('mechanic_id','challenge_id','task_id'):
        if not ground_truth.get(key) or payload.get(key)!=ground_truth[key] or public_state.get(key)!=ground_truth[key]:return fail('Stale challenge or task identity')
    if ground_truth['mechanic_id']!=MECHANIC_ID:return fail('Wrong mechanic')
    if public_state.get('world')!=ground_truth.get('world') or public_state.get('control_condition')!=ground_truth.get('control_condition'):return fail('World or condition mismatch')
    mode=(ground_truth.get('control_condition') or {}).get('interaction','full')
    expected={'full':'keyboard','simplified':'buttons'}.get(mode)
    if expected is None:return fail('Invalid interaction mode')
    actions=payload.get('actions')
    if not isinstance(actions,list) or not actions:return fail('Missing action history')
    world=ground_truth['world'];state=initial(world);history=[]
    for i,event in enumerate(actions):
        if not isinstance(event,dict) or type(event.get('seq')) is not int or event['seq']!=i+1:return fail('Invalid action sequence')
        cmd=event.get('command')
        if cmd in ('undo','reset'):
            if event.get('source')!='toolbar':return fail('Invalid recovery input')
            if cmd=='reset':state=initial(world);history=[]
            elif history:state=history.pop()
        elif cmd in ('N','E','S','W','CW','CCW'):
            if event.get('source')!=expected:return fail('Wrong interaction input')
            history.append(copy.deepcopy(state));state=advance(world,state,cmd)
        else:return fail('Unknown command')
        if event.get('state')!=state:return fail('Movement, collision or bonding disagrees with replay')
    if payload.get('final_state')!=state:return fail('Final state disagrees with replay')
    if not complete(world,state):return fail('Assembly incomplete: join every atom and fill every slot')
    return {'graded':True,'passed':True,'score':100,'feedback':'PASS · one connected assembly; every valence filled'}

def cheat(public_state,ground_truth):return {'solution_path':ground_truth['solution_path']}
