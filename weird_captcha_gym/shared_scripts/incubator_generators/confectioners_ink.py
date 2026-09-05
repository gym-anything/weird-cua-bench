"""Seeded cabinet geometry. No solution coordinates are sent to the browser."""
from __future__ import annotations
import copy
import hashlib
import random

MECHANIC_ID = 'confectioners_ink'
DEFAULTS = dict(jar_count=3, jar_width=80, peg_count=1, hot_plate=True, ink_budget=1750, batch_grains=80)


def generate(task, seed):
    condition = copy.deepcopy(task.get('_control_condition'))
    p = {**DEFAULTS, **(condition or {}).get('difficulty_parameters', {})}
    if p['jar_count'] not in (1, 2, 3) or p['peg_count'] not in (0, 1, 2) or not 50 <= p['jar_width'] <= 120:
        raise ValueError('unsupported cabinet geometry')
    rng = random.Random(hashlib.sha256(f'{MECHANIC_ID}|{seed}'.encode()).hexdigest())
    mirror = rng.choice([False, True])
    shift = rng.randint(-18, 18)
    def point(x, y):
        x += shift
        return [900-x if mirror else x, y]
    colours = ['rose', 'mint', 'lemon']; rng.shuffle(colours)
    xs = [410+rng.randint(-12,12), 160+rng.randint(-18,18), 760+rng.randint(-12,12)]
    jars = [dict(x=point(x,0)[0], y=455, width=p['jar_width'], colour=colours[i], required=16) for i,x in enumerate(xs[:p['jar_count']])]
    # The hottest plate ends directly over the last jar. Its sloped surface is
    # the actual collider and colour-changing contact surface.
    plate = None
    if p['hot_plate']:
        plate = dict(a=point(xs[2]-116,350), b=point(xs[2]-28,402), colour=colours[2], radius=5)
    pegs = [dict(x=point(300,0)[0],y=365,radius=20),dict(x=point(465,0)[0],y=300,radius=18)][:p['peg_count']]
    world = dict(width=900,height=530,hopper=point(510,60),jars=jars,plate=plate,pegs=pegs,
                 colours=colours[:p['jar_count']],batch_grains=p['batch_grains'],emit_every=6,batch_ticks=p['batch_grains']*6,
                 ink_budget=p['ink_budget'],max_waste=p['batch_grains']*p['jar_count']-16*p['jar_count'],tick_ms=20,
                 max_ticks=p['batch_grains']*6*p['jar_count']+650)
    routes=[]
    routes.append([point(540,240),point(xs[0]+30,390),point(xs[0]+4,435)])
    if p['jar_count']>=2: routes.append([point(540,170),point(xs[1]+35,410),point(xs[1]+18,433)])
    if p['jar_count']==3:
        routes.append([point(480,95),point(600,150),point(xs[2]-121,325)] if plate else [point(480,110),point(xs[2]-20,415)])
    tid=task.get('id',MECHANIC_ID+'_seed_0001@0.1')
    identity=dict(mechanic_id=MECHANIC_ID,task_id=tid,challenge_id=hashlib.sha256(f'{seed}|{tid}|{condition}'.encode()).hexdigest()[:18])
    public={**identity,'benchmark':'weird_captcha_gym','prompt':task.get('natural_language','Fill every jar with matching sugar.'),'submit_label':'SEAL THE JARS','world':world,'parameters':p,'generator':{'name':'confectioners_ink_v1','variant_count':37*25*(37 if p['jar_count']>=2 else 1)*(25 if p['jar_count']==3 else 1)*(3 if p['jar_count']==1 else 6)*2,'variant_count_kind':'cabinet positions, distinct visible colour assignments and reflection'},'asset_manifest':'shared_runtime/assets/provenance/confectioners_ink_v0.json'}
    truth={**identity,'world':copy.deepcopy(world),'parameters':copy.deepcopy(p),'canonical_routes':routes}
    if condition is not None:public['control_condition']=copy.deepcopy(condition);truth['control_condition']=condition
    return public,truth
