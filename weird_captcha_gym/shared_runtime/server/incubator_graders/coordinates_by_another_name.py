"""Independent replay of actual selector operations, designations and fleet hits."""
from __future__ import annotations
import math

MECHANIC_ID='coordinates_by_another_name'


def options(world):
    return [sorted(world['bands']),list('ABC'),list(range(1,world['columns']+1))+['*']]


def resolve(world, designation):
    band,block,count=designation
    return sorted(c['id'] for c in world['cells'] if c['band']==band and c['block']==block
                  and (count=='*' or c['count']==count))


def grade(payload, ground_truth, public_state):
    def fail(message):return {'graded':True,'passed':False,'score':0,'feedback':message}
    if not all(isinstance(x,dict) for x in [payload,ground_truth,public_state]):return fail('malformed envelope')
    for key in ['mechanic_id','task_id','challenge_id']:
        value=ground_truth.get(key)
        if not value or payload.get(key)!=value or public_state.get(key)!=value:return fail(f'{key} identity mismatch')
    if ground_truth['mechanic_id']!=MECHANIC_ID:return fail('mechanic mismatch')
    world=ground_truth['world']
    if public_state.get('world')!=world or public_state.get('runtime_fleet')!=ground_truth['fleet']:return fail('world commitment mismatch')
    condition=ground_truth.get('control_condition')
    if public_state.get('control_condition')!=condition:return fail('condition mismatch')
    mode=(condition or {}).get('interaction','full')
    if mode not in ['full','simplified']:return fail('invalid interaction')
    opts=options(world);indices=[0,0,0];seen=set();shots=0;sweeps=world['sweeps'];fleet=ground_truth['fleet'];sunk=[]
    events=payload.get('events')
    if not isinstance(events,list) or len(events)>5000:return fail('invalid event tape')
    for i,e in enumerate(events):
        if not isinstance(e,dict) or e.get('sequence')!=i+1:return fail('event sequence mismatch')
        if len(sunk)==len(fleet):return fail('action after fleet sunk')
        if e.get('action')=='select':
            axis=e.get('axis');index=e.get('index')
            if type(axis)!=int or axis not in range(3) or type(index)!=int or index not in range(len(opts[axis])):return fail('invalid selector')
            if e.get('input_source')!=('rotary_drag' if mode=='full' else 'value_button'):return fail('wrong interaction input')
            if mode=='full':
                xy=e.get('release')
                start=e.get('start')
                if any(not isinstance(point,list) or len(point)!=2 or any(type(x) not in [int,float] or not math.isfinite(x) for x in point) for point in [start,xy]):return fail('invalid rotary gesture')
                x,y=xy;radius=math.hypot(x-84,y-84)
                if math.hypot(start[0]-84,start[1]-84)>43 or math.hypot(x-start[0],y-start[1])<8:return fail('rotary input must drag the visible knob')
                angle=math.atan2(y-84,x-84)*180/math.pi
                delta=(angle+210)%360
                half_step=120/(len(opts[axis])-1)
                if not 24<=radius<=86 or 240+half_step<delta<360-half_step:return fail('rotary geometry mismatch')
                delta=0 if delta>=360-half_step else min(240,delta)
                if int(math.floor(delta/240*(len(opts[axis])-1)+0.5))!=index:return fail('rotary detent mismatch')
            indices[axis]=index
        elif e.get('action')=='fire':
            if e.get('input_source')!='fire_button':return fail('wrong fire surface')
            address=[opts[a][indices[a]] for a in range(3)]
            if e.get('designation')!=address:return fail('designation does not match selectors')
            targets=resolve(world,address)
            outcome='invalid' if not targets else 'no_sweeps' if address[2]=='*' and sweeps==0 else 'repeat' if set(targets)<=seen else 'shot'
            newly=[]
            if outcome=='shot':
                shots+=1
                if address[2]=='*':sweeps-=1
                seen.update(targets)
                newly=[n for n,ship in enumerate(fleet) if n not in sunk and set(ship['cells'])<=seen]
                sunk+=newly
            hits=sorted(c for c in targets if any(c in ship['cells'] for ship in fleet)) if outcome=='shot' else []
            if e.get('outcome')!=outcome or e.get('hits')!=hits or e.get('sunk')!=newly:return fail('shot feedback mismatch')
        else:return fail('unknown action')
    final={'shots':shots,'sweeps':sweeps,'seen':sorted(seen),'sunk':sorted(sunk)}
    if payload.get('final')!=final:return fail('claimed final state differs from replay')
    passed=len(sunk)==len(fleet)
    efficiency=round(100*ground_truth['omniscient_min_shots']/max(1,shots),1) if passed else 0
    # Completion and search quality are separate: completing by enumeration
    # must not receive the same score as a solution using fewer shots.
    return {'graded':True,'passed':passed,'score':efficiency,'feedback':f'{len(sunk)}/{len(fleet)} vessels sunk; {shots} shots; omniscient efficiency {efficiency}%', 'shots':shots,'efficiency_percent':efficiency}


def cheat(public_state,ground_truth):
    return {'fleet':ground_truth['fleet'],'omniscient_min_shots':ground_truth['omniscient_min_shots']}
