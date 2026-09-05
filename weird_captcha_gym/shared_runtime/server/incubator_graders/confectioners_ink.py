"""Independent fixed-step point-grain/contact replay; never trusts jar claims."""
from __future__ import annotations
import math

MECHANIC_ID='confectioners_ink'

def fail(message):return dict(graded=True,passed=False,feedback=message)
def quant(x):return math.floor(x*1000000+0.5)/1000000

def contact(g,a,b,radius,gate=None,paint=None):
    dx=b[0]-a[0];dy=b[1]-a[1];l2=dx*dx+dy*dy
    if not l2:return
    u=max(0,min(1,((g['x']-a[0])*dx+(g['y']-a[1])*dy)/l2))
    x=a[0]+u*dx;y=a[1]+u*dy;nx=g['x']-x;ny=g['y']-y;dist=math.hypot(nx,ny)
    if dist>=radius+2:return
    # Matching grains pass downward only; upward contact stays solid.
    if gate==g['colour'] and g['vy']>=0:return
    if dist<1e-10:
        length=math.sqrt(l2);nx=-dy/length;ny=dx/length
        approach=nx*g['vx']+ny*g['vy']
        if approach>0 or (approach==0 and (ny>0 or (ny==0 and nx>0))):nx=-nx;ny=-ny
    else:nx/=dist;ny/=dist
    g['x']=x+nx*(radius+2);g['y']=y+ny*(radius+2)
    vn=g['vx']*nx+g['vy']*ny
    if vn<0:
        g['vx']-=vn*nx;g['vy']-=vn*ny
        g['vx']*=.985;g['vy']*=.985
    if paint is not None:g['colour']=paint

class Simulation:
    def __init__(self,w):
        self.w=w;self.tick=0;self.grains=[];self.lines=[];self.ink=0.;self.waste=0;self.spawned=0
        self.tallies=[{} for _ in w['jars']];self.done=False;self.lost=False
    def add(self,a,b):
        length=math.dist(a,b)
        if self.ink+length>self.w['ink_budget']+1e-6:self.lost=True;return False
        self.ink+=length;self.lines.append((a,b));return True
    def step(self):
        if self.done or self.lost:return
        self.tick+=1;w=self.w
        stage=(self.tick-1)//w['batch_ticks']
        if stage<len(w['jars']) and (self.tick-1)%w['emit_every']==0:
            i=self.spawned;self.spawned+=1
            colour=w['colours'][stage]
            if stage==2 and w['plate']:colour='white'
            self.grains.append(dict(x=w['hopper'][0]+((i*17)%11-5),y=w['hopper'][1],vx=0.,vy=0.,colour=colour))
        alive=[]
        for g in self.grains:
            old_y=g['y']
            for _ in range(2):
                g['vy']=min(5.5,g['vy']+.07);g['vx']*=.998
                g['x']+=g['vx']*.5;g['y']+=g['vy']*.5
                for a,b in self.lines:contact(g,a,b,2)
                p=w['plate']
                if p:contact(g,p['a'],p['b'],p['radius'],paint=p['colour'])
                for p in w['pegs']:
                    # A tiny segment is a circle with the same visible radius.
                    contact(g,[p['x']-.000001,p['y']],[p['x']+.000001,p['y']],p['radius'])
                for j in w['jars']:
                    x=j['x'];r=j['width']/2;y=j['y']
                    contact(g,[x-r,y-16],[x+r,y-16],2,gate=j['colour'])
                    contact(g,[x-r,y],[x-r,515],3)
                    contact(g,[x+r,y],[x+r,515],3)
                for k in ('x','y','vx','vy'):g[k]=quant(g[k])
            collected=False
            for i,j in enumerate(w['jars']):
                if old_y<j['y']<=g['y'] and abs(g['x']-j['x'])<j['width']/2-3:
                    self.tallies[i][g['colour']]=self.tallies[i].get(g['colour'],0)+1
                    if g['colour']!=j['colour']:self.waste+=1
                    collected=True;break
            if collected:continue
            if g['y']>530 or g['x']<0 or g['x']>900:self.waste+=1
            else:alive.append(g)
        self.grains=alive
        self.done=all(t.get(j['colour'],0)>=j['required'] and all(c==j['colour'] or n==0 for c,n in t.items()) for t,j in zip(self.tallies,w['jars']))
        self.lost=self.waste>w['max_waste'] or self.tick>=w['max_ticks']
    def advance(self,t):
        if t<self.tick or t>self.w['max_ticks']:raise ValueError('invalid tick')
        while self.tick<t:
            if self.done or self.lost:raise ValueError('time continued beyond terminal state')
            self.step()

def grade(payload,truth,public):
    try:
        if not all(isinstance(x,dict) for x in (payload,truth,public)):return fail('malformed contract')
        for k in ('mechanic_id','task_id','challenge_id'):
            if not truth.get(k) or payload.get(k)!=truth[k] or public.get(k)!=truth[k]:return fail('stale task or challenge')
        if truth['mechanic_id']!=MECHANIC_ID:return fail('wrong mechanic')
        if public.get('world')!=truth.get('world') or public.get('control_condition')!=truth.get('control_condition'):return fail('contract mismatch')
        mode=(truth.get('control_condition') or {}).get('interaction','full')
        source={'full':'freehand','simplified':'vertices'}[mode]
        events=payload.get('events')
        if not isinstance(events,list) or len(events)>10000:return fail('invalid transcript')
        sim=Simulation(truth['world']);last=None
        for e in events:
            if not isinstance(e,dict) or type(e.get('tick')) is not int:raise ValueError('invalid event')
            sim.advance(e['tick'])
            if sim.done or sim.lost:raise ValueError('input after terminal state')
            if e.get('source')!=source:raise ValueError('wrong interaction surface')
            kind=e.get('type')
            if kind=='end':
                if last is None:raise ValueError('no stroke to end')
                last=None;continue
            a=e.get('point')
            if not isinstance(a,list) or len(a)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in a) or not(0<=a[0]<=900 and 70<=a[1]<=435):raise ValueError('invalid drawing point')
            if kind=='begin':
                if last is not None:raise ValueError('stroke already active')
                last=a
            elif kind=='point':
                if last is None:raise ValueError('unanchored segment')
                if math.dist(last,a)<.5:raise ValueError('segment below input threshold')
                sim.add(last,a);last=a
            else:raise ValueError('unknown input')
        tick=payload.get('tick')
        if type(tick) is not int:raise ValueError('missing final tick')
        sim.advance(tick)
        ink=float(payload.get('ink',-1))
        if not math.isfinite(ink) or payload.get('tallies')!=sim.tallies or payload.get('waste')!=sim.waste or abs(ink-sim.ink)>.02:raise ValueError('reported outcome differs from simulation')
        passed=sim.done and payload.get('completed') is True and sim.ink<=sim.w['ink_budget']
        return dict(graded=True,passed=passed,feedback=f"Jars {sim.tallies}; waste {sim.waste}; ink {sim.ink:.1f}/{sim.w['ink_budget']}")
    except (ValueError,TypeError,KeyError,OverflowError) as exc:return fail(str(exc))

def cheat(public_state,ground_truth):return {'canonical_routes':ground_truth['canonical_routes'],'answers':[]}
