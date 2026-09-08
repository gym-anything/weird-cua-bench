"""Owned fixed-step particle dynamics with unilateral, inextensible ropes.

The parcel is a disk. A rope removes outward radial velocity only while taut;
cutting preserves position and velocity. Contacts are swept each 10 ms step.
This module is self-contained for the exported WebAssembly grader.
"""
import copy
import math

MECHANIC_ID = 'pendulum_post'


def initial(w):
    return dict(tick=0, x=w['start'][0], y=w['start'][1], vx=0., vy=0., active=[True]*len(w['ropes']), seals=[], status='active')


def distance(p, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    t = max(0., min(1., ((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy))) if dx*dx+dy*dy else 0.
    return math.hypot(p[0]-a[0]-t*dx, p[1]-a[1]-t*dy)


def advance(s, w):
    if s['status'] != 'active': return
    s['tick'] += 1
    a = [s['x'], s['y']]
    dt = .01
    s['vy'] += w['gravity']*dt
    s['x'] += s['vx']*dt
    s['y'] += s['vy']*dt
    # Sequential impulse/projection iterations resolve simultaneous taut ropes.
    for _ in range(12):
        for i,r in enumerate(w['ropes']):
            if not s['active'][i]: continue
            dx,dy=s['x']-r['x'],s['y']-r['y']
            d=math.hypot(dx,dy)
            if d > r['length']:
                nx,ny=dx/d,dy/d
                s['x'],s['y']=r['x']+nx*r['length'],r['y']+ny*r['length']
                outward=max(0.,s['vx']*nx+s['vy']*ny)
                s['vx']-=outward*nx
                s['vy']-=outward*ny
    b=[s['x'],s['y']]
    for i,p in enumerate(w['seals']):
        if i not in s['seals'] and distance(p,a,b)<=w['radius']+w['seal_radius']: s['seals'].append(i)
    if any(distance(h[:2],a,b)<=w['radius']+h[2] for h in w['hazards']): s['status']='damaged'
    basket=w['basket']
    if s['status']=='active' and a[1]+w['radius'] < basket['y'] <= b[1]+w['radius']:
        t=(basket['y']-w['radius']-a[1])/(b[1]-a[1])
        x=a[0]+t*(b[0]-a[0])
        if abs(x-basket['x'])<=basket['width']/2-w['radius'] and not any(s['active']):
            s['status']='delivered' if len(s['seals'])==len(w['seals']) else 'missing_seals'
        elif abs(x-basket['x'])<=basket['width']/2+w['radius']:
            s['status']='damaged'
    if s['status']=='active' and (s['x']<w['radius'] or s['x']>900-w['radius'] or s['y']>470-w['radius']): s['status']='lost'
    if s['status']=='active' and s['tick']>=9000: s['status']='timeout'


def crossing(a,b,c,d):
    def cross(u,v): return u[0]*v[1]-u[1]*v[0]
    r=[b[0]-a[0],b[1]-a[1]]; q=[d[0]-c[0],d[1]-c[1]]
    den=cross(r,q)
    if abs(den)<1e-9:return False
    v=[c[0]-a[0],c[1]-a[1]]
    t,u=cross(v,q)/den,cross(v,r)/den
    return 0<=t<=1 and .04<=u<=.96


def rope_points(r,s):
    a=[r['x'],r['y']];b=[s['x'],s['y']]
    dx,dy=b[0]-a[0],b[1]-a[1];d=math.hypot(dx,dy)
    sag=math.sqrt(max(0.,r['length']**2-d*d))/2
    nx,ny=(-dy/d,dx/d) if d else (0.,1.)
    if ny<0:nx,ny=-nx,-ny
    return [a,[(a[0]+b[0])/2+nx*sag,(a[1]+b[1])/2+ny*sag],b]


def grade(payload, truth, public):
    def fail(reason): return dict(graded=True,passed=False,feedback=reason)
    try:
        if any(not isinstance(value, dict) for value in (payload, truth, public)):
            return fail('Malformed parcel contract')
        if any(value.get('mechanic_id') != MECHANIC_ID for value in (payload, truth, public)):
            return fail('Mechanic mismatch')
        for key in ('mechanic_id','task_id','challenge_id'):
            if not truth.get(key) or any(z.get(key)!=truth[key] for z in (payload,public)):return fail('Stale challenge or task')
        if truth['world']!=public['world'] or truth.get('control_condition')!=public.get('control_condition'):return fail('World or condition mismatch')
        mode=(truth.get('control_condition') or {}).get('interaction','full')
        if payload.get('interaction_mode')!=mode:return fail('Wrong interaction mode')
        events=payload.get('events')
        if not isinstance(events,list) or not 1<=len(events)<=100:return fail('Missing cut transcript')
        w=truth['world']; s=initial(w)
        for e in events:
            if not isinstance(e, dict):
                return fail('Malformed cut event')
            tick=e.get('tick')
            if type(tick)!=int or not s['tick']<=tick<=9000:return fail('Invalid event time')
            while s['tick']<tick and s['status']=='active':advance(s,w)
            if s['status']!='active':return fail('Action after terminal state')
            i=e.get('rope')
            if type(i)!=int or not 0<=i<len(s['active']) or not s['active'][i]:return fail('Invalid rope')
            if e.get('input_source')!=('rope_button' if mode=='simplified' else 'rope_swipe'):return fail('Wrong input surface')
            if mode=='full':
                a,b=e['a'],e['b']
                if not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and -100<=v<=1000 for p in (a,b) for v in p) or len(a)!=2 or len(b)!=2:return fail('Invalid swipe')
                r=w['ropes'][i]
                points=rope_points(r,s)
                if not any(crossing(a,b,points[j],points[j+1]) for j in (0,1)):return fail('Swipe missed rope')
            s['active'][i]=False
        terminal=payload.get('terminal_tick')
        if type(terminal)!=int or not s['tick']<=terminal<=9000:return fail('Invalid terminal time')
        while s['tick']<terminal and s['status']=='active':advance(s,w)
        passed=s['status']=='delivered' and s['tick']==terminal and payload.get('completed') is True
        return dict(graded=True,passed=passed,feedback='Intact parcel delivered with every seal' if passed else 'Parcel not delivered with every seal', replay=s)
    except (KeyError,TypeError,ValueError,OverflowError,IndexError):return fail('Malformed parcel transcript')
