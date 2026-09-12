"""Original seeded bilateral market grounded in XAGT-216."""
from __future__ import annotations
import copy
import hashlib
import random

MECHANIC_ID='orchard_exchange'
PROFILES={
 1:dict(capacity=20,initial_hunger=600,max_hunger=900,water_cost=0,changing_terms=False,farmers=1,demand_b=3,ratio=1),
 2:dict(capacity=16,initial_hunger=300,max_hunger=700,water_cost=0,changing_terms=False,farmers=2,demand_b=3,ratio=2),
 3:dict(capacity=12,initial_hunger=160,max_hunger=500,water_cost=15,changing_terms=True,farmers=2,demand_b=4,ratio=2),
 4:dict(capacity=10,initial_hunger=130,max_hunger=400,water_cost=25,changing_terms=True,farmers=3,demand_b=5,ratio=2),
 5:dict(capacity=8,initial_hunger=110,max_hunger=350,water_cost=40,changing_terms=True,farmers=3,demand_b=5,ratio=3),
}

def generate(task,seed):
    c=copy.deepcopy(task.get('_control_condition') or task.get('metadata',{}).get('control_condition'))
    level=int((c or {}).get('difficulty',3))
    p={**PROFILES[level],**(c or {}).get('difficulty_parameters',{})}
    rng=random.Random(int(hashlib.sha256((str(seed)+'|'+MECHANIC_ID).encode()).hexdigest(),16))
    rows=rng.sample([1,3,5],3); mirror=rng.choice([False,True])
    def pos(x,y):return [9-x if mirror else x,y]
    bridge=rng.choice([0,2,4,6])
    trees=[dict(pos=pos(1,rows[0]),fruit=0),dict(pos=pos(2,rows[1]),fruit=0),dict(pos=pos(8,rows[2]),fruit=1)]
    bots=[]
    for i in range(p['farmers']):
        bots.append(dict(name=['Pip','Mallow','Fern'][i],pos=pos(6+i%2,rows[i]),inventory=[0,rng.randint(1,3)],
             hunger=rng.randint(35,95),progress=rng.randrange(25),harvest_ticks=35+i*10,meal_ticks=150+i*35,
             capacity=7,ask=p['ratio'] if level==2 or i>0 else 1,give=1 if i!=1 else 2))
    trees.extend(dict(pos=b['pos'][:],fruit=1) for b in bots)
    w=dict(width=10,height=7,start=pos(1,6),stall=pos(1,6),trees=trees,bots=bots,
           water=[pos(4,y) for y in range(7) if y!=bridge] if p['water_cost'] else [],walls=[],bridge=bridge,
           demand=[3 if level==5 else 2,p['demand_b']],capacity=p['capacity'],initial_hunger=p['initial_hunger'],
           max_hunger=p['max_hunger'],water_cost=p['water_cost'],changing_terms=p['changing_terms'],
           radius=1.5,apple_ticks=18,banana_ticks=900,food=[170,340],tick_ms=100,limit_ticks=1800)
    task_id=task.get('id','orchard_exchange_seed_0001@0.1')
    identity=dict(mechanic_id=MECHANIC_ID,task_id=task_id,challenge_id=hashlib.sha256(f'{seed}|{task_id}|{level}'.encode()).hexdigest()[:16])
    variants=12*(3*61*25)**p['farmers']*(4 if p['water_cost'] else 1)
    public={**identity,'benchmark':'weird_captcha_gym','prompt':'Keep yourself fed. Barter for the delivery basket.',
            'world':w,'generator':{'name':'orchard_exchange_v0','variant_count':variants},
            'asset_manifest':'shared_runtime/assets/provenance/orchard_exchange_v0.json'}
    truth={**identity,'seed':str(seed),'world':copy.deepcopy(w),'variant_count':variants}
    if c:public['control_condition']=copy.deepcopy(c);truth['control_condition']=copy.deepcopy(c)
    return public,truth
