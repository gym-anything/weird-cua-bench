"""Independent volume, heat, tool and input-surface replay. No generator imports."""
from __future__ import annotations
import math
MECHANIC_ID = 'ember_anvil'
DIRECTIONS = ((1,0),(0,1),(-1,0),(0,-1))


def fail(message):
    return dict(graded=True,passed=False,feedback=message)


def integer(v):
    return isinstance(v,int) and not isinstance(v,bool)


def grade(payload, truth, public):
    try:
        if not all(isinstance(x,dict) for x in (payload,truth,public)):
            return fail('malformed result')
        for key in ('mechanic_id','task_id','challenge_id'):
            if not truth.get(key) or any(x.get(key)!=truth[key] for x in (payload,public)):
                return fail('stale task, challenge or mechanic')
        if truth['mechanic_id'] != MECHANIC_ID:
            return fail('wrong mechanic')
        if public.get('world') != truth.get('world') or public.get('control_condition') != truth.get('control_condition'):
            return fail('render/replay contract mismatch')
        mode=(truth.get('control_condition') or {}).get('interaction','simplified')
        surface={'full':'direct_drag','simplified':'proxy_click'}.get(mode)
        if surface is None:return fail('unknown interaction')
        w=truth['world']; n=w['size']; cap=w['max_height']; h=w['initial'][:]; target=w['target']
        if n!=7 or not integer(cap) or not 2<=cap<=4 or len(h)!=n*n or len(target)!=n*n or any(not integer(v) or not 0<=v<=cap for v in h+target):
            return fail('invalid solid')
        events=payload.get('events')
        if not isinstance(events,list) or not 1<=len(events)<=2000:return fail('missing or oversized transcript')
        heat=float(w['initial_heat']); location='anvil'; last=0; tool='draw'; direction=0; discarded=0; reheats=0; terminal=False
        for seq,e in enumerate(events,1):
            if not isinstance(e,dict) or e.get('seq')!=seq or terminal:return fail('invalid event sequence')
            t=e.get('t'); typ=e.get('type')
            if not integer(t) or not last<=t<=900000:return fail('invalid task time')
            dt=t-last;last=t
            heat=min(1.0,heat+dt/w['heat_ms']) if location=='forge' else max(0.0,heat-dt/w['cooling_ms'])
            if e.get('input_source') != (surface if typ in ('strike','transfer','orbit') else 'tool_control'):
                return fail('wrong interaction input')
            if typ=='mode':
                if e.get('mode') not in ('draw','upset','split'):return fail('illegal hammer mode')
                tool=e['mode']
            elif typ=='direction':
                if not integer(e.get('direction')) or e['direction'] not in range(4):return fail('illegal direction')
                direction=e['direction']
            elif typ=='orbit':
                if e.get('delta') not in (-1,1):return fail('illegal orbit')
            elif typ=='transfer':
                dest='forge' if location=='anvil' else 'anvil'
                if e.get('to')!=dest:return fail('illegal forge transfer')
                if dest=='forge':reheats+=1
                location=dest
            elif typ=='strike':
                i=e.get('cell')
                if not integer(i) or not 0<=i<n*n:return fail('invalid contact')
                outcome='moved'
                if location!='anvil':outcome='in_forge'
                elif heat+1e-9<w['workable']:outcome='cold'
                elif h[i]==0:outcome='empty'
                elif tool=='split':h[i]-=1;discarded+=1;outcome='split'
                else:
                    dx,dy=DIRECTIONS[direction];x=i%n+dx;y=i//n+dy
                    j=y*n+x
                    if not (0<=x<n and 0<=y<n) or h[j]>=cap or (tool=='draw' and h[j]>=h[i]) or (tool=='upset' and h[j]!=h[i]):outcome='blocked'
                    else:h[i]-=1;h[j]+=1
                if e.get('mode')!=tool or e.get('direction')!=direction or e.get('outcome')!=outcome or e.get('heights')!=h:
                    return fail('strike disagrees with solid/temperature replay')
            elif typ=='stamp':
                terminal=True
                if location!='anvil':return fail('tool must be on anvil')
            else:return fail('unknown event')
        if not terminal or events[-1]['type']!='stamp':return fail('missing final stamp')
        if payload.get('heights')!=h or payload.get('discarded')!=discarded or payload.get('reheats')!=reheats:return fail('false volume or ledger')
        if sum(h)+discarded!=sum(w['initial']):return fail('material conservation violated')
        passed=h==target
        return dict(graded=True,passed=passed,feedback=f"{'Complete solid accepted' if passed else 'FAIL · solid differs from target'}; discarded {discarded}; reheats {reheats}")
    except (KeyError,TypeError,ValueError,IndexError,ZeroDivisionError,OverflowError):
        return fail('malformed smithing transcript')
