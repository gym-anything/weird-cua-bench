"""Original cubic outlines. No imported font or third-party game assets."""
from __future__ import annotations
import copy
import hashlib
import json
import random

MECHANIC_ID = 'punchcutters_bench'
DEFAULT = dict(shape='shoulder', outline_tolerance=7, spacing_threshold=84, letter_count=5, skew=0)


def generate(task, seed):
    condition = task.get('_control_condition')
    p = dict(DEFAULT, **((condition or {}).get('difficulty_parameters') or {}))
    if p['shape'] not in ('bar', 'el', 'arch', 'shoulder') or not 3 <= p['letter_count'] <= 6 or not 3 <= p['outline_tolerance'] <= 18 or not 50 <= p['spacing_threshold'] <= 95 or not 0 <= p['skew'] <= .3:
        raise ValueError('unsupported punchcutter profile')
    rng = random.Random(int.from_bytes(hashlib.sha256(f'{seed}|{MECHANIC_ID}|v1'.encode()).digest()[:8], 'big'))
    w, h = rng.randint(200, 240), rng.randint(230, 260)
    ox, oy = rng.randint(235, 260), rng.randint(67, 84)
    if p['shape'] == 'bar':
        raw = [(0,0,0,0),(.35,0,0,0),(.35,1,0,0),(0,1,0,0)]
    elif p['shape'] == 'el':
        raw = [(0,0,0,0),(.24,0,0,0),(.24,.78,0,0),(1,.78,0,0),(1,1,0,0),(0,1,0,0)]
    else:
        # Clockwise n: tangent vectors point toward the next node.
        raw = [(0,1,0,0),(0,.40,0,-.23),(.5,0,.28,0),(1,.40,0,.23),(1,1,0,0),(.76,1,0,0),(.76,.46,0,-.14),(.5,.26,-.15,0),(.24,.46,0,.14),(.24,1,0,0)]
        if p['shape'] == 'shoulder':
            raw[:3] = [(0,1,0,0),(0,0,0,0),(.24,0,0,0),(.24,.14,0,0),(.57,0,.24,0)]
        # Change arch proportions, not just palette or challenge identity.
        bulge = rng.uniform(-.025,.025)
        raw = [(x + (bulge if 0 < x < 1 else 0), y, dx, dy) for x,y,dx,dy in raw]
    nodes = [[round(ox+w*(x+p['skew']*(1-y)),2), round(oy+h*y,2), round(w*(dx-p['skew']*dy),2), round(h*dy,2)] for x,y,dx,dy in raw]
    glyphs = []
    # Original polygonal display letters; all used by both renderer and spacing reference.
    shapes = {
        'V':[(0,0),(.23,0),(.5,.73),(.77,0),(1,0),(.64,1),(.36,1)],
        'T':[(0,0),(1,0),(1,.21),(.61,.21),(.61,1),(.39,1),(.39,.21),(0,.21)],
        'N':[(0,1),(0,0),(.23,0),(.76,.66),(.76,0),(1,0),(1,1),(.77,1),(.24,.34),(.24,1)],
        'I':[(.25,0),(.75,0),(.75,1),(.25,1)],
        'Y':[(0,0),(.25,0),(.5,.38),(.75,0),(1,0),(.62,.6),(.62,1),(.38,1),(.38,.6)],
        'L':[(0,0),(.24,0),(.24,.79),(1,.79),(1,1),(0,1)],
    }
    count = p['letter_count']; own = min(2,count//2)
    for i in range(count):
        name = {3:'LIT',4:'TILT' if p['shape']=='el' else 'TINT',5:'TINNY',6:'TINTIN'}[count][i]
        width = rng.randint(69,87)
        glyphs.append({'name': 'cut' if i == own else name, 'width':width,
                       'polygon':[] if i == own else [[round(x*width,2),round(y*140,2)] for x,y in shapes[name]]})
    # Endpoints fixed, interiors initially perturbed without overlap or clipping.
    positions = [round(74+i*(650-74)/(count-1),2) for i in range(count)]
    for i in range(1,count-1): positions[i] += rng.choice([-1,1])*rng.randint(8,12 if count==6 else 28)
    if p['skew']:
        # Cubics lie inside the convex hull of their control points. Include
        # the sheared cut's actual hull instead of assuming its nominal width.
        bounds = []
        for i, glyph in enumerate(glyphs):
            xs = ([(x + sign*dx - ox)/w*glyph['width']
                   for x,y,dx,dy in nodes for sign in (-1,0,1)]
                  if i == own else [point[0] for point in glyph['polygon']])
            bounds.append((min(xs), max(xs)))
        for i in range(1, count-1):
            minimum = positions[i-1] + bounds[i-1][1] - bounds[i][0] + 2
            if positions[i] < minimum:
                positions[i] = round(minimum + .005, 2)
        for i in range(count-2, 0, -1):
            maximum = positions[i+1] + bounds[i+1][0] - bounds[i][1] - 2
            if positions[i] > maximum:
                positions[i] = round(maximum - .005, 2)
    bench = dict(parameters=p, master=nodes, node_budget=len(nodes), stage={'width':800,'height':410},
                 glyphs=glyphs, cut_index=own, initial_positions=positions, glyph_origin=[ox,oy], glyph_scale=[w,h])
    cid=hashlib.sha256((str(seed)+json.dumps(bench,sort_keys=True)).encode()).hexdigest()[:16]
    public=dict(benchmark='weird_captcha_gym',mechanic_id=MECHANIC_ID,task_id=task['id'],challenge_id=cid,
                prompt=task.get('natural_language','Cut the master. Space the word.'),bench=bench,
                generator={'name':'punchcutter_v1','variant_count':10**12},asset_manifest='shared_runtime/assets/provenance/punchcutters_bench_v0.json')
    truth=dict(mechanic_id=MECHANIC_ID,task_id=task['id'],challenge_id=cid,seed=seed,bench=copy.deepcopy(bench))
    if condition is not None:
        public['control_condition']=copy.deepcopy(condition);truth['control_condition']=copy.deepcopy(condition)
    return public,truth
