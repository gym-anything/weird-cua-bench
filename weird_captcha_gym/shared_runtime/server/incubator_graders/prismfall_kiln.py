"""Owned fixed-step disc physics and independent primitive-drop replay."""
import copy
import math
MECHANIC_ID = 'prismfall_kiln'
RADII = [16, 23, 32, 44, 59, 78, 102]

def body(t, x, y):
    return dict(t=t, x=float(x), y=float(y), vx=0., vy=0.)

def tick(bs, world):
    """Semi-implicit gravity, mass-weighted contact projection and impulses."""
    w,h=world['width'],world['height']
    merges=0
    for b in bs:
        b['vy']=(b['vy']+.11)*.992;b['vx']*=.992
        b['x']+=b['vx'];b['y']+=b['vy']
    for iteration in range(6):
        for b in bs:
            r=RADII[b['t']]
            if b['x']<r: b['x']=float(r);b['vx']=abs(b['vx'])*.15
            if b['x']>w-r:b['x']=float(w-r);b['vx']=-abs(b['vx'])*.15
            if b['y']>h-r:b['y']=float(h-r);b['vy']=-abs(b['vy'])*.1;b['vx']*=.94
        merged=False
        for i in range(len(bs)):
            if merged:break
            for j in range(i+1,len(bs)):
                a,b=bs[i],bs[j];ra,rb=RADII[a['t']],RADII[b['t']]
                dx,dy=b['x']-a['x'],b['y']-a['y'];d=math.sqrt(dx*dx+dy*dy)
                if d>ra+rb:continue
                if a['t']==b['t'] and a['t']<6:
                    c=body(a['t']+1,(a['x']+b['x'])/2,(a['y']+b['y'])/2)
                    c['vx']=(a['vx']+b['vx'])/2;c['vy']=(a['vy']+b['vy'])/2
                    bs.pop(j);bs.pop(i);bs.append(c);merges+=1;merged=True;break
                nx,ny=(dx/d,dy/d) if d>1e-9 else (1.,0.)
                ia,ib=1/(2**a['t']),1/(2**b['t']);total=ia+ib
                overlap=ra+rb-d
                a['x']-=nx*overlap*ia/total;a['y']-=ny*overlap*ia/total
                b['x']+=nx*overlap*ib/total;b['y']+=ny*overlap*ib/total
                v=(b['vx']-a['vx'])*nx+(b['vy']-a['vy'])*ny
                if v<0:
                    impulse=-1.1*v/total
                    a['vx']-=impulse*ia*nx;a['vy']-=impulse*ia*ny
                    b['vx']+=impulse*ib*nx;b['vy']+=impulse*ib*ny
    return merges

def settle(bs,world):
    quiet=0
    for n in range(1200):
        before=[(b['x'],b['y']) for b in bs];m=tick(bs,world)
        motion=max((abs(b['x']-p[0])+abs(b['y']-p[1]) for b,p in zip(bs,before)),default=0)
        quiet=quiet+1 if not m and motion<.045 else 0
        if quiet>=24:
            for b in bs:b['vx']=b['vy']=0.
            return n+1
    return 1200

def drop(bs,world,t,x):
    bs=copy.deepcopy(bs);bs.append(body(t,x,38));n=settle(bs,world)
    overflow=n==1200 or any(b['y']-RADII[b['t']]<world['overflow'] for b in bs)
    return bs,n,overflow

def choose(bs,world,t,target,candidates=None):
    candidates=candidates or sorted(set([RADII[t]+2,world['width']-RADII[t]-2,world['width']/2]+[round(b['x'],3) for b in bs]+[world['width']*i/10 for i in range(1,10)]))
    best=None
    for x in candidates:
        x=math.floor(x*10+.5)/10
        if not RADII[t]<=x<=world['width']-RADII[t]:continue
        after,n,over=drop(bs,world,t,x)
        score=(not over, max(b['t'] for b in after)>=target, sum(3**b['t'] for b in after), min(b['y']-RADII[b['t']] for b in after))
        if best is None or score>best[0]:best=(score,x,after,n,over)
    return best[1:]

def grade(payload,truth,public):
    def result(ok,msg):return dict(graded=True,passed=ok,feedback=msg)
    try:
        if not all(isinstance(value,dict) for value in (payload,truth,public)):
            return result(False,'malformed kiln ledger')
        for k in ('mechanic_id','task_id','challenge_id'):
            if not truth.get(k) or public.get(k)!=truth[k] or payload.get(k)!=truth[k]:return result(False,'stale task or challenge')
        for k in ('world','initial','offers','target','control_condition'):
            if public.get(k)!=truth.get(k):return result(False,'world or condition mismatch')
        mode=(truth.get('control_condition') or {}).get('interaction','full')
        source={'full':'rail_click','simplified':'position_button'}[mode]
        events=payload.get('events')
        if not isinstance(events,list) or not 1<=len(events)<=len(truth['offers']):return result(False,'empty or oversized drop ledger')
        bs=copy.deepcopy(truth['initial']);won=False
        for i,e in enumerate(events):
            if won or not isinstance(e,dict) or type(e.get('seq')) is not int or e['seq']!=i+1 or e.get('input_source')!=source:return result(False,'invalid drop surface or sequence')
            x=e.get('x');t=truth['offers'][i]
            if isinstance(x,bool) or not isinstance(x,(float,int)) or not math.isfinite(x) or not RADII[t]<=x<=truth['world']['width']-RADII[t]:return result(False,'illegal release')
            bs,n,over=drop(bs,truth['world'],t,x)
            if type(e.get('ticks')) is not int or e['ticks']!=n:return result(False,'settling ledger mismatch')
            reported=e.get('bodies')
            if not isinstance(reported,list) or len(reported)!=len(bs):return result(False,'body count mismatch')
            for a,b in zip(reported,bs):
                if not isinstance(a,dict) or type(a.get('t')) is not int or a['t']!=b['t'] or any(type(a.get(k)) not in (int,float) or not math.isfinite(a[k]) or abs(a[k]-b[k])>.01 for k in ('x','y')):return result(False,'contact geometry mismatch')
            if over:return result(False,'unsettled batch' if n==1200 else 'overflow line crossed')
            won=any(b['t']>=truth['target'] for b in bs)
        return result(won,'largest glass form created' if won else 'target form not created')
    except (KeyError,ValueError,TypeError,OverflowError):return result(False,'malformed kiln ledger')
