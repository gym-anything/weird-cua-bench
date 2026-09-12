"""Planar articulated rigid-body dynamics with unilateral capsule contacts.

Two uniform links use a coupled mass matrix and Coriolis forces. An unpowered
three-petal spinner receives only contact impulses and dissipative bearing drag.
Fixed 10 ms ticks contain five semi-implicit 2 ms substeps. Contact stabilization
uses separating velocity; there is no angle assignment or motor on the spinner.
"""
import math
MECHANIC_ID = 'porcelain_turntable'

def dot(a,b): return a[0]*b[0]+a[1]*b[1]
def sub(a,b): return [a[0]-b[0],a[1]-b[1]]
def cross(a,b): return a[0]*b[1]-a[1]*b[0]
def point(a,b,t): return [a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t]
def closest(a,b,c,d):
    ab=sub(b,a); cd=sub(d,c); den=cross(ab,cd)
    if abs(den)>1e-12:
        ac=sub(c,a); t=cross(ac,cd)/den; u=cross(ac,ab)/den
        if 0<=t<=1 and 0<=u<=1: return point(a,b,t),point(c,d,u),t
    candidates=[]
    for v,t in ((a,0),(b,1)):
        u=max(0,min(1,dot(sub(v,c),cd)/max(dot(cd,cd),1e-12)))
        w=point(c,d,u); candidates.append((dot(sub(v,w),sub(v,w)),v,w,t))
    for w in (c,d):
        t=max(0,min(1,dot(sub(w,a),ab)/max(dot(ab,ab),1e-12)))
        v=point(a,b,t); candidates.append((dot(sub(v,w),sub(v,w)),v,w,t))
    z=min(candidates,key=lambda z:z[0]); return z[1],z[2],z[3]

def geometry(s,p):
    a,b=s[:2]; base=[-p['base_distance'],0]
    elbow=[base[0]+p['l1']*math.cos(a),p['l1']*math.sin(a)]
    tip=[elbow[0]+p['l2']*math.cos(a+b),elbow[1]+p['l2']*math.sin(a+b)]
    petals=[[p['radius']*math.cos(s[2]+i*2*math.pi/3),p['radius']*math.sin(s[2]+i*2*math.pi/3)] for i in range(3)]
    return base,elbow,tip,petals

def step(s,u,p):
    s=list(s); contacts=0; dt=.002
    for _ in range(5):
        a,b,theta,va,vb,w=s; l1=p['l1']; l2=p['l2']; m1=1.;m2=.7
        h=m2*l1*l2/2; d22=m2*l2*l2/3
        d12=d22+h*math.cos(b);d11=m1*l1*l1/3+m2*l1*l1+d22+2*h*math.cos(b)
        det=d11*d22-d12*d12; inv00=d22/det;inv01=-d12/det;inv11=d11/det
        r1=u[0]*p['torque']-p['joint_damping']*va+h*math.sin(b)*(2*va*vb+vb*vb)
        r2=u[1]*p['torque']-p['joint_damping']*vb-h*math.sin(b)*va*va
        va+=dt*(inv00*r1+inv01*r2);vb+=dt*(inv01*r1+inv11*r2)
        w*=math.exp(-p['hinge_damping']*dt/p['spinner_inertia'])
        base,elbow,tip,petals=geometry(s,p)
        for index,(aa,bb) in enumerate(((base,elbow),(elbow,tip))):
            for end in petals:
                v,z,t=closest(aa,bb,[0,0],end); delta=sub(v,z);dist=math.hypot(*delta);depth=p['finger_radius']+p['petal_radius']-dist
                if depth<=0:continue
                n=[delta[0]/max(dist,1e-12),delta[1]/max(dist,1e-12)]
                if dist<1e-9:n=[0,1]
                j0=cross(sub(v,base),n); j1=cross(sub(v,elbow),n) if index else 0; js=-cross(z,n)
                effective=j0*(inv00*j0+inv01*j1)+j1*(inv01*j0+inv11*j1)+js*js/p['spinner_inertia']
                rel=j0*va+j1*vb+js*w
                impulse=max(0,(.16*max(0,depth-.0005)/dt-rel)/max(effective,1e-12))
                va+=(inv00*j0+inv01*j1)*impulse;vb+=(inv01*j0+inv11*j1)*impulse;w+=js*impulse/p['spinner_inertia']
                if impulse>1e-8:contacts+=1
        s=[a+dt*va,b+dt*vb,theta+dt*w,va,vb,w]
    return s,contacts

def error(s,p): return abs(math.atan2(math.sin(s[2]-p['target']),math.cos(s[2]-p['target'])))
def settled(s,u,p): return u==[0,0] and error(s,p)<=p['tolerance'] and abs(s[5])<=p['settle_speed']

def grade(payload,truth,public):
    def result(ok,msg):return {'graded':True,'passed':ok,'score':100 if ok else 0,'feedback':msg}
    try:
        if not all(isinstance(x,dict) for x in (payload,truth,public)):return result(False,'Malformed contract')
        for k in ('mechanic_id','task_id','challenge_id'):
            if not truth.get(k) or payload.get(k)!=truth[k] or public.get(k)!=truth[k]:return result(False,'Stale task or challenge')
        if truth['mechanic_id']!=MECHANIC_ID:return result(False,'Wrong mechanic')
        for k in ('physics','initial','control_condition'):
            if truth.get(k)!=public.get(k):return result(False,'Generated contract differs')
        if payload.get('control_condition')!=truth.get('control_condition'):return result(False,'Wrong condition')
        mode=(truth.get('control_condition') or {}).get('interaction','full')
        source={'full':'held_keys','simplified':'latched_buttons'}[mode]
        p=truth['physics'];s=truth['initial'];u=[0,0];tick=0;hold=0;done=False
        events=payload.get('events')
        if not isinstance(events,list) or not 2<=len(events)<=20000:return result(False,'Malformed input transcript')
        for seq,e in enumerate(events,1):
            if not isinstance(e,dict) or e.get('seq')!=seq or type(e.get('seq')) is not int or done:return result(False,'Invalid event order')
            t=e.get('tick')
            if type(t) is not int or not tick<=t<=p['max_ticks']:return result(False,'Invalid time')
            if seq==1 and (e.get('type')!='start' or t!=0):return result(False,'Missing start')
            while tick<t:
                s,_=step(s,u,p);tick+=1;hold=hold+1 if settled(s,u,p) else 0
            kind=e.get('type')
            if kind=='start':
                if seq!=1:return result(False,'Duplicate start')
            elif kind=='torque':
                v=e.get('value')
                if not isinstance(v,list) or len(v)!=2 or any(type(x) is not int or x not in (-1,0,1) for x in v) or v==u or e.get('input_source')!=source:return result(False,'Invalid control surface')
                u=v
                if u!=[0,0]:hold=0
            elif kind=='finish':
                if seq!=len(events):return result(False,'Invalid finish')
                done=True;reported=e.get('state')
                if not isinstance(reported,list) or len(reported)!=6 or any(type(x) not in (int,float) or not math.isfinite(x) or abs(x-y)>1e-6 for x,y in zip(reported,s)):return result(False,'Displayed physics differs from replay')
            else:return result(False,'Unknown action')
        ok=done and hold>=p['settle_ticks'] and settled(s,u,p)
        return result(ok,'Petal settled in the sector' if ok else 'Release both joints and settle the painted petal inside the sector')
    except (KeyError,ValueError,TypeError,OverflowError):return result(False,'Malformed physical transcript')
