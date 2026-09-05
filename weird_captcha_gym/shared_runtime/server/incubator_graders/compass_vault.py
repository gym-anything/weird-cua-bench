"""Analytic construction replay; intersections retain their parent object identities."""
from __future__ import annotations
import math

MECHANIC_ID = 'compass_vault'
EPS = 1e-7

def sub(a,b): return (a[0]-b[0],a[1]-b[1])
def add(a,b): return (a[0]+b[0],a[1]+b[1])
def mul(a,s): return (a[0]*s,a[1]*s)
def dot(a,b): return a[0]*b[0]+a[1]*b[1]
def cross(a,b): return a[0]*b[1]-a[1]*b[0]
def dist(a,b): return math.hypot(*sub(a,b))

def intersections(a,b):
    if a['kind']=='circle' and b['kind']=='line': return intersections(b,a)
    p,q=a['p'],b['p']
    if a['kind']==b['kind']=='line':
        u,v=sub(a['q'],p),sub(b['q'],q); den=cross(u,v)
        return [] if abs(den)<EPS else [add(p,mul(u,cross(sub(q,p),v)/den))]
    if a['kind']=='line':
        u=sub(a['q'],p); v=sub(p,q); aa=dot(u,u); bb=2*dot(u,v); cc=dot(v,v)-b['r']**2
        dd=bb*bb-4*aa*cc
        if dd < -EPS: return []
        roots=[(-bb-math.sqrt(max(0,dd)))/(2*aa),(-bb+math.sqrt(max(0,dd)))/(2*aa)]
        return [add(p,mul(u,t)) for t in roots[:1 if abs(dd)<EPS else 2]]
    d=dist(p,q)
    if d<EPS or d>a['r']+b['r']+EPS or d<abs(a['r']-b['r'])-EPS: return []
    x=(a['r']**2-b['r']**2+d*d)/(2*d); h=math.sqrt(max(0,a['r']**2-x*x)); u=mul(sub(q,p),1/d); base=add(p,mul(u,x)); v=(-u[1],u[0])
    return [add(base,mul(v,h)),add(base,mul(v,-h))][:1 if h<EPS else 2]

class Construction:
    def __init__(self, world, givens=None):
        self.points={f'g{i}':tuple(p) for i,p in enumerate(givens or world['givens'])}
        self.objects=[]; self.marked=[]
        for op in world['initial_objects']: self.apply(op)
    def apply(self, op):
        kind=op['kind']; p=self.points[op['a']]
        if kind=='point':
            # The point tool replaces the previous marker on the canvas.
            self.marked[:] = [op['a']]; return
        if kind not in ('line','circle'): raise ValueError('unknown tool')
        q=self.points[op['b']]
        if dist(p,q)<EPS: raise ValueError('coincident endpoints')
        obj={'kind':kind,'p':p,'q':q,'r':dist(p,q)}
        j=len(self.objects)
        for i,other in enumerate(self.objects):
            for k,pt in enumerate(intersections(other,obj)):
                if all(math.isfinite(x) and abs(x)<1e7 for x in pt): self.points[f'x{i}_{j}_{k}']=pt
        self.objects.append(obj)

def goal_geometry(world, givens=None):
    a,b,c=(givens or world['givens']); goal=world['goal']; mid=mul(add(a,b),.5)
    if goal in ('midpoint','bisector'): return {'p':mid,'q':add(mid,(-(b[1]-a[1]),b[0]-a[0]))}
    ab,ac=sub(b,a),sub(c,a); den=2*cross(ab,ac)
    u=((dot(ab,ab)*ac[1]-dot(ac,ac)*ab[1])/den,(ab[0]*dot(ac,ac)-ac[0]*dot(ab,ab))/den)
    circum=add(a,u)
    if goal=='circumcenter': return {'p':circum}
    if goal=='orthocenter': return {'p':sub(add(add(a,b),c),mul(circum,2))}
    lengths=[dist(b,c),dist(a,c),dist(a,b)]; perimeter=sum(lengths)
    center=mul(add(add(mul(a,lengths[0]),mul(b,lengths[1])),mul(c,lengths[2])),1/perimeter)
    return {'p':center,'r':abs(cross(ab,sub(center,a)))/dist(a,b)}

def satisfied(world, model, givens=None):
    target=goal_geometry(world,givens); p=target['p']; tol=1e-5
    if world['goal']=='bisector':
        v=sub(target['q'],p)
        return any(o['kind']=='line' and abs(cross(sub(o['q'],o['p']),sub(p,o['p'])))/o['r']<tol and abs(cross(sub(o['q'],o['p']),v))/(o['r']*math.hypot(*v))<tol for o in model.objects[len(world['initial_objects']):])
    if world['goal']=='incircle':
        return any(o['kind']=='circle' and dist(o['p'],p)<tol and abs(o['r']-target['r'])<tol for o in model.objects[len(world['initial_objects']):])
    return any(dist(model.points[ref],p)<tol for ref in model.marked)

def grade(payload, ground_truth, public_state):
    def fail(msg): return {'graded':True,'passed':False,'score':0,'feedback':msg}
    try:
        for key in ('mechanic_id','task_id','challenge_id','control_condition'):
            if payload.get(key)!=ground_truth.get(key) or public_state.get(key)!=ground_truth.get(key): return fail(f'{key} mismatch')
        if payload.get('mechanic_id')!=MECHANIC_ID or public_state.get('world')!=ground_truth['world']: return fail('world mismatch')
        ops=payload.get('operations'); world=ground_truth['world']; mode=(ground_truth.get('control_condition') or {}).get('interaction','full')
        source={'full':'canvas_drag','simplified':'canvas_clicks'}[mode]
        if not isinstance(ops,list) or not 1<=len(ops)<=world['move_budget']+1: return fail('construction budget exceeded or empty')
        if any(not isinstance(op,dict) for op in ops): return fail('invalid operation record')
        if sum(op.get('kind')!='point' for op in ops)>world['move_budget']: return fail('move budget exceeded')
        if any(op.get('input_source')!=('point_click' if op.get('kind')=='point' else source) for op in ops): return fail('wrong interaction surface')
        displayed=payload.get('displayed_givens',world['givens'])
        if not isinstance(displayed,list) or len(displayed)!=3: return fail('invalid displayed givens')
        for p,base in zip(displayed,world['givens']):
            if not isinstance(p,(list,tuple)) or len(p)!=2 or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or abs(x-y)>28.00001 for x,y in zip(p,base)): return fail('displayed givens outside legal drag region')
        for givens in [displayed,world['givens']]+ground_truth['perturbations']:
            model=Construction(world,givens)
            for op in ops:
                if not isinstance(op,dict) or set(op)-{'kind','a','b','input_source'}: return fail('invalid operation')
                model.apply(op)
            if not satisfied(world,model,givens): return fail('FAIL · construction does not survive the base-point checks')
        moves=sum(op['kind']!='point' for op in ops)
        efficiency=min(1,world['reference_moves']/max(1,moves))
        checks = 2 + len(ground_truth['perturbations'])
        return {'graded':True,'passed':True,'score':round(100*efficiency,4),'moves':moves,'efficiency':round(efficiency,4),'feedback':f'PASS · invariant holds in {checks} geometry checks; {moves} strokes'}
    except (KeyError,ValueError,TypeError,ZeroDivisionError,OverflowError): return fail('invalid or degenerate construction')
