"""Replay primitive dance endpoints and elapsed times; never trust scout counts."""
from __future__ import annotations
import math
MECHANIC_ID = 'waggle_dispatch'


def sun(world, ms):
    t = ms / 1000
    return world['sun_phase'] + world['sun_direction'] * world['parameters']['sun_speed'] * (t + 1.5*(math.sin(t/6+world['sun_wave'])-math.sin(world['sun_wave'])))


def landing(world, start, end, x, y):
    angle = math.atan2(x, -y) + math.radians(sun(world, end))
    distance = (end-start)/1000*world['distance_per_second']
    px, py = math.sin(angle)*distance, -math.cos(angle)*distance
    target = next((s['id'] for s in world['sites'] if math.hypot(px-s['x'],py-s['y']) <= s['radius']), None)
    return target, px, py


def grade(payload, truth, public):
    def fail(s):return {'graded':True,'passed':False,'feedback':s}
    if not all(isinstance(v,dict) for v in (payload,truth,public)):return fail('Malformed result envelope')
    try:
        for key in ('mechanic_id','task_id','challenge_id'):
            if not truth.get(key) or payload.get(key)!=truth[key] or public.get(key)!=truth[key]:return fail('Stale task or challenge')
        if truth['mechanic_id'] != MECHANIC_ID or public['world'] != truth['world'] or public.get('control_condition') != truth.get('control_condition'):return fail('World or condition mismatch')
        mode=(truth.get('control_condition') or {}).get('interaction','full')
        if payload.get('interaction_mode')!=mode:return fail('Wrong interaction mode')
        events=payload.get('events');w=truth['world']
        if not isinstance(events,list) or not 1<=len(events)<=300:return fail('Missing dance transcript')
        last=0;ready=0;committed=[];terminal=False
        def number(v):
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v):raise ValueError('Non-finite input')
            return v
        for seq,e in enumerate(events):
            if not isinstance(e,dict) or terminal or e.get('seq')!=seq:return fail('Invalid event sequence')
            t=number(e['t']);
            if not last<=t<=240000 or t<ready:return fail('Event during scout flight or invalid clock')
            last=t
            if e['type']=='dance':
                if e.get('source')!={'full':'comb_drag_hold','simplified':'comb_toggle'}[mode]:return fail('Wrong dance input surface')
                start=number(e['start']);x=number(e['x']);y=number(e['y'])
                if not ready<=start<=t or not 100<=t-start<=w['max_hold_ms'] or not 35<=math.hypot(x,y)<=155:return fail('Invalid aimed hold')
                hit,_,_=landing(w,start,t,x,y);committed.append(hit);ready=t+w['flight_ms']
            elif e['type']=='recall':
                if not committed:return fail('No scout to recall')
                committed.pop();ready=t
            elif e['type']=='certify':terminal=True
            else:return fail('Unknown event')
        counts=[committed.count(i) for i in range(3)]
        passed=terminal and counts==[w['required'] if i==w['target'] else 0 for i in range(3)]
        return {'graded':True,'passed':passed,'feedback':('Six scouts committed to '+w['sites'][w['target']]['name'] if passed else 'Recruitment does not match the brief'),'counts':counts}
    except (KeyError,TypeError,ValueError,OverflowError):return fail('Malformed dance transcript')
