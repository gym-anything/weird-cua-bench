"""Original, seeded threshold-network construction with bounded graph repair."""
from __future__ import annotations
import copy
import bisect
import hashlib
import itertools
import json
import math
import random

MECHANIC_ID = 'threshold_grapevine'
DEFAULTS = dict(node_count=10, quarantine_count=3, threshold_profile='mixed', edit_limit=4, fixed_fraction=.45, stages=2)


def portrait_angles(count, phase):
    """Keep long chords clear of finite-radius portraits on the dense ellipse.

    Uniform angular spacing crowds portraits near the ellipse's flatter ends.
    Weight by inverse square root of tangent length to equalize chord clearance.
    L1–L4 retain their original layout and random stream.
    """
    steps = 4096
    angles = [-math.pi/2 + 2*math.pi*i/steps for i in range(steps+1)]
    cumulative = [0.0]
    for angle in angles[1:]:
        cumulative.append(cumulative[-1] + 1/math.sqrt(math.hypot(335*math.sin(angle), 183*math.cos(angle))))
    result = []
    for i in range(count):
        target = ((i/count + phase/(2*math.pi)) % 1)*cumulative[-1]
        index = max(1, bisect.bisect_left(cumulative, target))
        fraction = (target-cumulative[index-1])/(cumulative[index]-cumulative[index-1])
        result.append(angles[index-1] + fraction*(angles[index]-angles[index-1]))
    return result


def cascade(n, edges, seeds, thresholds):
    adjacent = [0]*n
    for a,b in edges:
        adjacent[a] |= 1<<b
        adjacent[b] |= 1<<a
    active = sum(1<<v for v in seeds)
    rounds = [[i for i in range(n) if active>>i&1]]
    while True:
        following = active
        for i,mask in enumerate(adjacent):
            num,den = thresholds[i]
            if mask and (mask&active).bit_count()*den >= mask.bit_count()*num:
                following |= 1<<i
        if following == active:
            return rounds
        active = following
        rounds.append([i for i in range(n) if active>>i&1])


def find_repair(n, initial, fixed, seeds, thresholds, target, limit):
    """Deterministic beam search provides a reachability witness, not an answer key."""
    choices = [e for e in itertools.combinations(range(n),2) if e not in fixed]
    target = set(target)
    def score(edges):
        adopted = set(cascade(n,edges,seeds,thresholds)[-1])
        return len(target-adopted) + 3*len(adopted-target)
    frontier = [(score(initial), ())]
    seen = {()}
    for depth in range(1,limit+1):
        candidates=[]
        for _,toggles in frontier:
            for edge in choices:
                if edge in toggles: continue
                change=tuple(sorted((*toggles,edge)))
                if change in seen: continue
                seen.add(change)
                loss=score(initial.symmetric_difference(change))
                if loss==0:return [list(e) for e in change]
                candidates.append((loss,change))
        frontier=sorted(candidates)[:18]
        if not frontier:break
    return None


def generate(task, seed):
    condition=copy.deepcopy(task.get('_control_condition') or task.get('metadata',{}).get('control_condition'))
    parameters=copy.deepcopy((condition or {}).get('difficulty_parameters') or DEFAULTS)
    if set(parameters)!=set(DEFAULTS):raise ValueError('invalid threshold parameters')
    n=parameters['node_count']; q=parameters['quarantine_count']; limit=parameters['edit_limit']
    if not 5<=n<=12 or not 0<=q<n-2 or not 1<=limit<=5 or parameters['stages'] not in (1,2):raise ValueError('unsupported graph profile')
    rng=random.Random(hashlib.sha256((str(seed)+'|'+json.dumps(parameters,sort_keys=True)).encode()).digest())
    pairs=list(itertools.combinations(range(n),2))
    protected=list(range(n-q,n)) if parameters['stages']==2 else []
    targets=[list(range(n))]+([list(range(n-q))] if parameters['stages']==2 else [])
    for attempt in range(1000):
        seeds=sorted(rng.sample(range(n-q),2))
        profiles={'half':[(1,2)],'mixed':[(1,2),(2,3)],'varied':[(1,2),(2,3),(3,4)]}
        thresholds=[list(rng.choice(profiles[parameters['threshold_profile']])) for _ in range(n)]
        if q==2:
            for i in protected:thresholds[i]=[2,3]
        initial={e for e in pairs if rng.random()<.24}
        if protected:
            initial.update(itertools.combinations(protected,2))
        # Fixed cross-group friendships make simple isolation unavailable.
        fixed=set(rng.sample(sorted(initial),min(len(initial),round(len(initial)*parameters['fixed_fraction']))))
        if protected and not any(a<n-q<=b for a,b in fixed):continue
        adopted=set(cascade(n,initial,seeds,thresholds)[-1])
        if any(adopted==set(t) for t in targets):continue
        repairs=[find_repair(n,initial,fixed,seeds,thresholds,t,limit) for t in targets]
        if any(r is None for r in repairs):continue
        if limit>=3 and any(len(r)<2 for r in repairs):continue
        break
    else:raise ValueError('no reachable graph found within generation bound')
    # Convexity alone does not protect finite-radius portraits from chords.
    phase=rng.uniform(-.09,.09)
    dense_angles = portrait_angles(n, phase) if n >= 11 else None
    nodes=[]
    for i in range(n):
        angle=-math.pi/2+2*math.pi*i/n+phase+rng.uniform(-.025,.025)
        if dense_angles is not None:
            angle = dense_angles[i]
        nodes.append(dict(id=i,x=round(430+335*math.cos(angle),3),y=round(235+183*math.sin(angle),3),
                          threshold=thresholds[i],portrait=rng.randrange(6)))
    task_id=task['id']; challenge=hashlib.sha256(f'{seed}|{task_id}|{json.dumps(parameters,sort_keys=True)}'.encode()).hexdigest()[:20]
    world=dict(nodes=nodes,edges=[list(e) for e in sorted(initial)],fixed_edges=[list(e) for e in sorted(fixed)],
               seeds=seeds,quarantine=protected,targets=targets,edit_limit=limit,round_ms=600)
    public=dict(benchmark='weird_captcha_gym',mechanic_id=MECHANIC_ID,task_id=task_id,challenge_id=challenge,
                prompt=task.get('natural_language','Spread the idea, then protect the quarantine.'),world=world,
                generator={'name':'threshold_grapevine_v0','seeded':True},
                asset_manifest='shared_runtime/assets/provenance/threshold_grapevine_v0.json')
    truth=dict(mechanic_id=MECHANIC_ID,task_id=task_id,challenge_id=challenge,seed=seed,world=copy.deepcopy(world),
               parameters=parameters,repairs=repairs,generation_attempt=attempt)
    if condition:
        public['control_condition']=copy.deepcopy(condition);truth['control_condition']=copy.deepcopy(condition)
    return public,truth
