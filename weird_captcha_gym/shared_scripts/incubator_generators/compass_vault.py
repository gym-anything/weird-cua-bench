"""Original seeded compass-and-straightedge construction challenges."""
from __future__ import annotations
import copy
import hashlib
import math
import random
MECHANIC_ID='compass_vault'
PROFILES={1:('midpoint',5,1),2:('bisector',8,3),3:('circumcenter',14,6),4:('orthocenter',20,8),5:('incircle',28,13)}
PROMPTS={'midpoint':'Mark the midpoint of the highlighted segment.','bisector':'Construct the perpendicular bisector of the highlighted segment.','circumcenter':'Mark the point equally distant from all three givens.','orthocenter':'Mark where the three triangle altitudes meet.','incircle':'Construct the circle tangent to all three triangle sides, inside the triangle.'}
def generate(task,seed):
    condition=copy.deepcopy(task.get('_control_condition') or task.get('metadata',{}).get('control_condition'))
    level=int((condition or {}).get('difficulty',3)); params=(condition or {}).get('difficulty_parameters',{})
    goal,budget,reference=PROFILES[level]
    goal=params.get('goal',goal); budget=int(params.get('move_budget',budget))
    if goal not in PROMPTS: raise ValueError('unknown construction goal')
    rng=random.Random(int.from_bytes(hashlib.sha256(f'{MECHANIC_ID}|{seed}'.encode()).digest()[:8],'big'))
    def triangle():
        # Acute, scalene triangles keep all target centers and useful crossings on the board.
        theta=rng.uniform(-.30,.30); scale=rng.uniform(.88,1.06)
        base=[(-130+rng.uniform(-14,14),75+rng.uniform(-8,8)),(132+rng.uniform(-14,14),72+rng.uniform(-8,8)),(rng.uniform(-38,38),-130+rng.uniform(-12,12))]
        return [[round(420+scale*(x*math.cos(theta)-y*math.sin(theta)),6),round(270+scale*(x*math.sin(theta)+y*math.cos(theta)),6)] for x,y in base]
    world={'givens':triangle(),'goal':goal,'move_budget':budget,'reference_moves':reference,'initial_objects':[{'kind':'line','a':'g0','b':'g1'}]}
    if level>=3: world['initial_objects'] += [{'kind':'line','a':'g1','b':'g2'},{'kind':'line','a':'g2','b':'g0'}]
    if goal=='midpoint': world['initial_objects'] += [{'kind':'circle','a':'g0','b':'g1'},{'kind':'circle','a':'g1','b':'g0'}]
    task_id=task.get('id','compass_vault_seed_0001@0.1'); challenge=hashlib.sha256(f'{seed}|{task_id}|{condition}'.encode()).hexdigest()[:16]
    public={'benchmark':'weird_captcha_gym','mechanic_id':MECHANIC_ID,'task_id':task_id,'challenge_id':challenge,'control_condition':condition,'prompt':PROMPTS[goal],'world':world,'submit_label':'TEST CONSTRUCTION','asset_manifest':'shared_runtime/assets/provenance/compass_vault_v0.json','generator':{'name':'compass_vault_v0'}}
    truth=copy.deepcopy(public); truth['seed']=seed; truth['perturbations']=[triangle() for _ in range(8)]
    return public,truth
