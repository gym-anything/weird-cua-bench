"""Original seeded postal cabinets, constructively certified by owned physics."""
import copy
import hashlib
import importlib.util
import json
import math
import random
from pathlib import Path

MECHANIC_ID='pendulum_post'
BASELINE_PARAMETERS=dict(rope_count=3,seal_count=3,basket_width=116,seal_radius=14,hazard_count=2,gravity=28)

def physics():
    path=Path(__file__).resolve().parents[2]/'shared_runtime/server/incubator_graders/pendulum_post.py'
    spec=importlib.util.spec_from_file_location('pendulum_physics',path); m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def generate(task,seed):
    m=physics(); condition=copy.deepcopy(task.get('_control_condition'))
    p=copy.deepcopy(condition['difficulty_parameters'] if condition else BASELINE_PARAMETERS)
    rng=random.Random(int(hashlib.sha256((str(seed)+'pendulum-post-v1').encode()).hexdigest(),16))
    for attempt in range(1000):
        n=p['rope_count']; x=rng.uniform(230,290); y=rng.uniform(155,195)
        anchors=[(x-130,rng.uniform(35,65)),(x+170,rng.uniform(35,65))]
        for i in range(n-2):anchors.append((x+70-i*65,rng.uniform(25,45)))
        ropes=[dict(x=ax,y=ay,length=math.hypot(x-ax,y-ay)+(0 if i<2 else 35+25*(i-2))) for i,(ax,ay) in enumerate(anchors)]
        w=dict(start=[x,y],ropes=ropes,gravity=p['gravity'],radius=16,seal_radius=p['seal_radius'],seals=[],hazards=[],basket=dict(x=450,y=425,width=p['basket_width']))
        schedule=[]; t=rng.randint(30,65)
        cut_order=list(range(1,n));rng.shuffle(cut_order);cut_order=[0]+cut_order
        for i in cut_order:
            schedule.append(dict(tick=round(t*math.sqrt(90/p['gravity'])),rope=i));t+=rng.randint(130,240)
        s=m.initial(w); path=[]; states={}
        for tick in range(1800):
            for e in schedule:
                if e['tick']==s['tick']:
                    states[e['rope']]=copy.deepcopy(s);s['active'][e['rope']]=False
            before=s['y'];m.advance(s,w);path.append([s['x'],s['y']])
            if s['y']+16>=425 and before+16<425:
                if s['tick']<=schedule[-1]['tick']:break
                if not 100<s['x']<800:break
                w['basket']['x']=s['x'];break
            if s['status']!='active':break
        else:continue
        if s['tick']<=schedule[-1]['tick'] or not 100<s['x']<800 or s['y']<408:continue
        if any(math.hypot(states[i]['x']-ropes[i]['x'],states[i]['y']-ropes[i]['y'])<ropes[i]['length']-.2 for i in range(1,n)):continue
        # One or more separated seals on the evolving arc, never at the start.
        candidate_indices=list(range(schedule[0]['tick']+60,len(path)-25,10))
        rng.shuffle(candidate_indices)
        for idx in candidate_indices:
            point=path[min(idx,len(path)-1)]
            if math.dist(point,w['start'])<65 or point[1]>370:continue
            if all(math.dist(point,a)>max(48,2*p['seal_radius']+18) for a in w['seals']):w['seals'].append(point)
            if len(w['seals'])==p['seal_count']:break
        if len(w['seals'])!=p['seal_count']:continue
        # Visible ink spills occupy real disk hazards, clear of the certified path.
        for _ in range(100):
            h=[rng.uniform(150,750),rng.uniform(250,385),rng.uniform(19,28)]
            if min(math.dist(h[:2],a) for a in path)>h[2]+48 and all(math.dist(h[:2],a[:2])>85 for a in w['hazards']):w['hazards'].append(h)
            if len(w['hazards'])==p['hazard_count']:break
        if p['hazard_count']==0:w['hazards']=[]
        if len(w['hazards'])!=p['hazard_count']:continue
        if rng.choice([True,False]):
            w['start'][0]=900-w['start'][0]
            for r in w['ropes']:r['x']=900-r['x']
            for a in w['seals']+w['hazards']:a[0]=900-a[0]
            w['basket']['x']=900-w['basket']['x']
        order=list(range(n));rng.shuffle(order)
        w['ropes']=[w['ropes'][i] for i in order]
        schedule=[dict(e,rope=order.index(e['rope'])) for e in schedule]
        s=m.initial(w)
        for tick in range(1800):
            for e in schedule:
                if e['tick']==s['tick']:s['active'][e['rope']]=False
            m.advance(s,w)
            if s['status']!='active':break
        if s['status']!='delivered':continue
        break
    else:raise ValueError('No reachable cabinet found')
    cid=hashlib.sha256((str(seed)+json.dumps(w,sort_keys=True)).encode()).hexdigest()[:16]
    common=dict(mechanic_id=MECHANIC_ID,task_id=task['id'],challenge_id=cid,world=w)
    if condition:common['control_condition']=condition
    public=dict(copy.deepcopy(common),benchmark='weird_captcha_gym',asset_manifest='shared_runtime/assets/provenance/pendulum_post_v0.json',prompt='Collect every seal. Cut the ropes. Deliver intact.',generator=dict(name='pendulum_post_v1',variant_count=1000000000))
    truth=dict(copy.deepcopy(common),seed=seed,reference_schedule=schedule,reference_terminal_tick=s['tick'])
    return public,truth
