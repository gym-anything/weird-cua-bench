"""Deterministic 2D rigid rectangle physics; no reported outcome is trusted.

Fixed 1/60 s steps, separating-axis contacts, normal/angular impulses,
Coulomb friction and positional penetration correction. Units are pixels/tick.
The browser implements the same equations independently.
"""
import copy
import math

MECHANIC_ID = 'load_bearing_idol'

def body(spec):
    b = dict(spec)
    b.update(vx=0., vy=0., av=0., angle=spec.get('angle', 0.))
    mass = b['w'] * b['h'] / 1000
    b['im'] = 0. if b.get('fixed') else 1 / mass
    b['ii'] = 0. if b.get('fixed') else 12 / (mass * (b['w']**2 + b['h']**2))
    return b

def vertices(b):
    c,s=math.cos(b['angle']),math.sin(b['angle'])
    return [(b['x']+x*c-y*s,b['y']+x*s+y*c) for x,y in [(-b['w']/2,-b['h']/2),(b['w']/2,-b['h']/2),(b['w']/2,b['h']/2),(-b['w']/2,b['h']/2)]]

def contact(a,b,margin=0.):
    va,vb=vertices(a),vertices(b);best=None
    for idx,q in enumerate((a,b)):
        c,s=math.cos(q['angle']),math.sin(q['angle'])
        for axis,(nx,ny) in enumerate([(c,s),(-s,c)]):
            pa=[x*nx+y*ny for x,y in va];pb=[x*nx+y*ny for x,y in vb]
            depth=min(max(pa),max(pb))-max(min(pa),min(pb))
            if depth < -margin:return None
            if best is None or depth<best[0]:best=(depth,nx,ny,idx,axis)
    depth,nx,ny,idx,axis=best
    if (b['x']-a['x'])*nx+(b['y']-a['y'])*ny<0:nx,ny=-nx,-ny
    ref,inc=(a,b) if idx==0 else (b,a)
    rx,ry=(nx,ny) if idx==0 else (-nx,-ny)
    tx,ty=-ry,rx
    plane=ref['x']*rx+ref['y']*ry+ref['w' if axis==0 else 'h']/2
    mid=ref['x']*tx+ref['y']*ty;extent=ref['h' if axis==0 else 'w']/2
    c,si=math.cos(inc['angle']),math.sin(inc['angle'])
    choices=[(c,si,inc['w']/2,inc['h']/2),(-si,c,inc['h']/2,inc['w']/2)]
    ux,uy,un,ut=max(choices,key=lambda q:abs(q[0]*rx+q[1]*ry))
    if ux*rx+uy*ry>0:ux,uy=-ux,-uy
    center=(inc['x']+ux*un,inc['y']+uy*un)
    p=(center[0]-uy*ut,center[1]+ux*ut);q=(center[0]+uy*ut,center[1]-ux*ut)
    pval=p[0]*tx+p[1]*ty;qval=q[0]*tx+q[1]*ty
    lo,hi=0.,1.
    if abs(qval-pval)>1e-10:
        u,v=(mid-extent-pval)/(qval-pval),(mid+extent-pval)/(qval-pval)
        lo=max(lo,min(u,v));hi=min(hi,max(u,v))
    points=[]
    for t in (lo,hi):
        x,y=p[0]+(q[0]-p[0])*t,p[1]+(q[1]-p[1])*t
        penetration=plane-x*rx-y*ry
        if lo<=hi and penetration>=-margin-.02:points.append((x+rx*penetration/2,y+ry*penetration/2))
    if not points:points=[((a['x']+b['x'])/2,(a['y']+b['y'])/2)]
    return depth,nx,ny,points

def step(bs):
    for b in bs:
        if b['im']:
            b['vy']+=.16
            b['vx']*=.995;b['vy']*=.995;b['av']*=.99
            b['x']+=b['vx'];b['y']+=b['vy'];b['angle']+=b['av']
    contacts=[]
    for _ in range(8):
        for i,a in enumerate(bs):
            for b in bs[i+1:]:
                inv=a['im']+b['im']
                if not inv:continue
                hit=contact(a,b)
                if hit is None:continue
                depth,nx,ny,points=hit
                if _==0:contacts.append((a['id'],b['id']))
                correction=max(0.,depth-.015)*.65/inv
                a['x']-=nx*correction*a['im'];a['y']-=ny*correction*a['im']
                b['x']+=nx*correction*b['im'];b['y']+=ny*correction*b['im']
                data=[]
                for px,py in points:
                    ra=(px-a['x'],py-a['y']);rb=(px-b['x'],py-b['y'])
                    rv=(b['vx']-b['av']*rb[1]-a['vx']+a['av']*ra[1],b['vy']+b['av']*rb[0]-a['vy']-a['av']*ra[0])
                    ca=ra[0]*ny-ra[1]*nx;cb=rb[0]*ny-rb[1]*nx
                    data.append((ra,rb,rv[0]*nx+rv[1]*ny,ca,cb))
                impulses=[0.]*len(data)
                if len(data)==2:
                    u,v=data;k1=inv+u[3]**2*a['ii']+u[4]**2*b['ii'];k2=inv+v[3]**2*a['ii']+v[4]**2*b['ii'];k12=inv+u[3]*v[3]*a['ii']+u[4]*v[4]*b['ii'];det=k1*k2-k12*k12
                    if det>1e-9:
                        impulses=[(-u[2]*k2+v[2]*k12)/det,(-v[2]*k1+u[2]*k12)/det]
                if len(data)==1 or min(impulses)<0 or max(impulses)==0:
                    impulses=[max(0.,-d[2]/(inv+d[3]**2*a['ii']+d[4]**2*b['ii']))/len(data) for d in data]
                for d,impulse in zip(data,impulses):
                    ra,rb,vn,ca,cb=d
                    a['vx']-=impulse*nx*a['im'];a['vy']-=impulse*ny*a['im'];a['av']-=ca*impulse*a['ii']
                    b['vx']+=impulse*nx*b['im'];b['vy']+=impulse*ny*b['im'];b['av']+=cb*impulse*b['ii']
                px=sum(p[0] for p in points)/len(points);py=sum(p[1] for p in points)/len(points)
                ra=(px-a['x'],py-a['y']);rb=(px-b['x'],py-b['y']);tx,ty=-ny,nx
                rv=(b['vx']-b['av']*rb[1]-a['vx']+a['av']*ra[1],b['vy']+b['av']*rb[0]-a['vy']-a['av']*ra[0])
                ta=ra[0]*ty-ra[1]*tx;tb=rb[0]*ty-rb[1]*tx
                friction=-(rv[0]*tx+rv[1]*ty)/(inv+ta*ta*a['ii']+tb*tb*b['ii'])
                mu=.015 if 'plank' in (a['kind'],b['kind']) else .45
                limit=sum(impulses)*mu;friction=max(-limit,min(limit,friction))
                a['vx']-=friction*tx*a['im'];a['vy']-=friction*ty*a['im'];a['av']-=ta*friction*a['ii']
                b['vx']+=friction*tx*b['im'];b['vy']+=friction*ty*b['im'];b['av']+=tb*friction*b['ii']
    return contacts

def local(b,p):
    c,s=math.cos(b['angle']),math.sin(b['angle']);x,y=p[0]-b['x'],p[1]-b['y']
    return x*c+y*s,-x*s+y*c

def contains(b,p):
    x,y=local(b,p);return abs(x)<=b['w']/2 and abs(y)<=b['h']/2

def action(bs,e,mode):
    b=next((b for b in bs if b['id']==e.get('body')),None)
    if b is None or b['kind'] not in ('chalk','plank','timber'):raise ValueError('piece cannot be removed')
    if e.get('source')!=mode:raise ValueError('wrong interaction surface')
    p,q=e.get('start'),e.get('end')
    if not all(isinstance(v,list) and len(v)==2 and all(isinstance(n,(int,float)) and not isinstance(n,bool) and math.isfinite(n) for n in v) for v in (p,q)):raise ValueError('invalid gesture')
    if b['kind']=='chalk':
        if not contains(b,p) or math.dist(p,q)>8:raise ValueError('chalk needs a click')
        bs.remove(b)
    elif b['kind']=='plank':
        if not contains(b,p) or abs(q[1]-p[1])>12 or abs(q[0]-p[0])<b['w']+30:raise ValueError('extract sideways beyond the stack')
        # Displacement is executed through physics ticks, never a teleport.
        b['extract'] = 1 if q[0]>p[0] else -1
        b['extract_origin']=b['x']
    else:
        a,z=local(b,p),local(b,q)
        if not ((a[1]<-b['h']/2 and z[1]>b['h']/2) or (z[1]<-b['h']/2 and a[1]>b['h']/2)):raise ValueError('cut must cross both timber edges')
        cut=a[0]+(z[0]-a[0])*(-a[1])/(z[1]-a[1])
        if abs(cut)>b['w']/2-12 or abs(a[0]-z[0])>12:raise ValueError('make a straight crosscut')
        bs.remove(b)
        for suffix,left,right in [('a',-b['w']/2,cut-.5),('b',cut+.5,b['w']/2)]:
            mid=(left+right)/2;c,s=math.cos(b['angle']),math.sin(b['angle'])
            n=body({**b,'id':b['id']+suffix,'w':right-left,'x':b['x']+mid*c,'y':b['y']+mid*s,'kind':'fragment'})
            n.update(vx=b['vx']-b['av']*mid*s,vy=b['vy']+b['av']*mid*c,av=b['av']);bs.append(n)
    return b['id']

def tick(bs):
    for b in list(bs):
        if 'extract' in b:
            b['vx']=4*b['extract']
            # A blocked pull must never erase a supporting body on a timer.
            if (b['x']-b['extract_origin'])*b['extract'] >= b['w']+60:
                bs.remove(b)
    pairs=step(bs)
    by={b['id']:b for b in bs}
    for i in range(2):
        g=by.get(f'glass{i}');ledge=by.get(f'ledge{i}')
        if g and ledge and (g['y']>ledge['y']+45 or any(set(pair)=={g['id'],'floor'} for pair in pairs)):g['lost']=True
    return pairs

def outcome(bs,removed,quota,floor_hit):
    by={b['id']:b for b in bs};idol=by['idol']
    glasses=all(contact(by[f'glass{i}'],by[f'ledge{i}'],.5) is not None and not by[f'glass{i}'].get('lost',False) for i in range(2))
    resting=abs(idol['vx'])<.1 and abs(idol['vy'])<.3 and abs(idol['av'])<.01
    return not any('extract' in b for b in bs) and not floor_hit and glasses and resting and contact(idol,by['cradle'],.5) is not None and len(removed)>=quota

def grade(payload,truth,public):
    def fail(s):return {'graded':True,'passed':False,'feedback':s}
    try:
        for key in ('mechanic_id','task_id','challenge_id'):
            if not truth.get(key) or payload.get(key)!=truth[key] or public.get(key)!=truth[key]:return fail('stale task or challenge')
        if public.get('bodies')!=truth['bodies'] or public.get('control_condition')!=truth.get('control_condition'):return fail('world or condition mismatch')
        mode=(truth.get('control_condition') or {}).get('interaction','full')
        events=payload['events'];end=payload['ticks']
        if not isinstance(events,list) or len(events)>80 or type(end)!=int or not 0<=end<=18000:return fail('invalid transcript length')
        bs=[body(b) for b in truth['bodies']];removed=set();floor_hit=False;now=0;last=-180
        for e in events:
            t=e['tick']
            if type(t)!=int or t<now or t-last<180 or t>end:return fail('action before resettling')
            while now<t:
                pairs=tick(bs);floor_hit |= any(set(p)=={'idol','floor'} for p in pairs);now+=1
            removed.add(action(bs,e,mode));last=t
        while now<end:
            pairs=tick(bs);floor_hit |= any(set(p)=={'idol','floor'} for p in pairs);now+=1
        if end-last<180:return fail('structure still settling')
        passed=outcome(bs,removed,truth['quota'],floor_hit)
        return {'graded':True,'passed':passed,'feedback':'Idol cradled; both ampoules supported.' if passed else 'Idol or ampoules not safely supported.', 'removed':len(removed),'floor_contact':floor_hit}
    except (KeyError,TypeError,ValueError,OverflowError) as e:return fail('invalid physics transcript: '+str(e))
