"""Reachable paint targets on one shared polygonal surface; no recipe sent to UI."""
import copy
import hashlib
import math
import random

MECHANIC_ID = 'maskmakers_dispatch'
PALETTE = [('#e66a54','Coral'),('#efbd48','Saffron'),('#269e99','Lagoon'),('#525aaa','Iris'),('#b95183','Rose'),('#80a657','Fern')]

def generate(task, seed):
    condition = task.get('_control_condition') or task.get('metadata', {}).get('control_condition')
    n = int((condition or {}).get('difficulty_parameters', {}).get('cover_count', 2))
    if not 1 <= n <= 5:
        raise ValueError('cover_count outside 1..5')
    rng = random.Random(hashlib.sha256(f'{MECHANIC_ID}|{seed}'.encode()).digest())
    rotation = rng.randrange(12)
    direction = rng.choice([-1, 1])
    regions = []
    for ring in range(2):
        for sector in range(12):
            start = (sector * 30 - 90) * math.pi / 180
            end = start + math.pi / 6
            inner, outer = (0, 61) if ring == 0 else (61, 116)
            points = []
            for k in range(7):
                a = start + (end-start)*k/6
                points.append([round(outer*math.cos(a),4),round(outer*math.sin(a),4)])
            for k in range(6,-1,-1):
                a = start + (end-start)*k/6
                points.append([round(inner*math.cos(a),4),round(inner*math.sin(a),4)])
            regions.append(points)
    covers = []
    for i in range(n):
        # An exclusive outer petal plus overlapping neighbour and inner crescent.
        sectors = [(rotation+direction*(2*i+k))%12 for k in (0,1,2)]
        protected = [12+sectors[0],12+sectors[1]] + sectors
        protected += [(rotation+direction*(2*i+5+k))%12 for k in (0,1)]
        covers.append({'name':['Crown','Wing','Ribbon','Crescent','Fan'][i], 'regions':sorted(set(protected))})
    palette = rng.sample(PALETTE, n+1)
    palette = [{'colour':c,'name':name} for c,name in palette]
    order = rng.sample(range(n),n)
    paint_order = rng.sample(range(n+1), n+1)
    target = [-1]*24
    active = set()
    recipe = []
    # Every mask has exclusive outer paint; all n+1 colours survive.
    for step, colour in enumerate(paint_order):
        if step:
            cover = order[step-1]; active.add(cover);recipe.append({'kind':'cover','index':cover})
        protected = {r for i in active for r in covers[i]['regions']}
        target = [old if r in protected else colour for r,old in enumerate(target)]
        recipe.append({'kind':'paint','index':colour})
    recipe += [{'kind':'cover','index':i} for i in reversed(order)]
    assert set(target) == set(range(n+1))
    task_id = task.get('id',MECHANIC_ID+'_seed_0001@0.1')
    cid = hashlib.sha256(f'{seed}|{task_id}|{condition}'.encode()).hexdigest()[:16]
    public = {'benchmark':'weird_captcha_gym','mechanic_id':MECHANIC_ID,'task_id':task_id,'challenge_id':cid,'prompt':task.get('natural_language','Match the pictured order.'),'submit_label':'SHIP ORNAMENT','regions':regions,'covers':covers,'palette':palette,'target':target,'generator':{'name':MECHANIC_ID+'_v0','variant_count':24 * math.factorial(6) // math.factorial(5-n) * math.factorial(n) * math.factorial(n+1)},'asset_manifest':f'shared_runtime/assets/provenance/{MECHANIC_ID}_v0.json'}
    if condition:public['control_condition']=copy.deepcopy(condition)
    truth=copy.deepcopy(public);truth.update(seed=seed,solution=recipe)
    return public,truth
