"""Seeded, construction-tested original glass merge worlds. No borrowed assets."""
import copy
import hashlib
import importlib.util
import random
from pathlib import Path
MECHANIC_ID='prismfall_kiln'
DEFAULT={'target':4,'width':300,'height':390,'initial_count':5,'offer_types':3}
def engine():
    path=Path(__file__).resolve().parents[2]/'shared_runtime/server/incubator_graders/prismfall_kiln.py'
    spec=importlib.util.spec_from_file_location('kiln_physics',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def generate(task,seed):
    c=task.get('_control_condition');p={**DEFAULT,**((c or {}).get('difficulty_parameters') or {})}
    rng=random.Random(int(hashlib.sha256(str(seed).encode()).hexdigest()[:16],16));sim=engine()
    world={'width':p['width'],'height':p['height'],'overflow':82}
    for attempt in range(40):
        initial=[];initial_failed=False
        for i in range(p['initial_count']):
            t=rng.randrange(p['offer_types']);r=sim.RADII[t]
            initial,_,bad=sim.drop(initial,world,t,rng.uniform(r+2,p['width']-r-2));initial_failed=initial_failed or bad
        if initial_failed or any(b['t']>=p['target'] for b in initial):continue
        offers=[rng.randrange(p['offer_types']) for _ in range(48)]
        bs=copy.deepcopy(initial);route=[]
        for t in offers:
            x,bs,n,over=sim.choose(bs,world,t,p['target']);route.append(x)
            if over:break
            if any(b['t']>=p['target'] for b in bs):break
        if not over and len(route)>=2 and any(b['t']>=p['target'] for b in bs):break
    else:raise ValueError('no reachable kiln generated within construction budget')
    cid=hashlib.sha256(f'{seed}|{task["id"]}|{c}'.encode()).hexdigest()[:20]
    pub=dict(benchmark='weird_captcha_gym',mechanic_id=MECHANIC_ID,task_id=task['id'],challenge_id=cid,prompt='Prismfall Kiln',world=world,initial=initial,offers=offers,target=p['target'],stage={'width':900,'height':520},generator={'name':'prismfall_kiln_v0','variant_count':1000000},asset_manifest='shared_runtime/assets/provenance/prismfall_kiln_v0.json')
    if c:pub['control_condition']=copy.deepcopy(c)
    truth=copy.deepcopy(pub);truth['solution_x']=route;truth['seed']=str(seed)
    return pub,truth
