"""Seeded adjacent-comparison engine. No browser secrets or solver routes shipped."""
from __future__ import annotations
import copy
import hashlib
import math
import random

MECHANIC_ID = 'comparator_engine'
# Baseline: nine specimens, three coarse weight bands, bounded leftward displacement.
DEFAULTS = dict(slide_count=9, band_size=3, displacement=3, lever_slack=12)


def sorting_cost(order):
    """Cyclic adjacent-exchange witness; no automatic early-success UI signal."""
    row = list(order)
    cursor = advances = exchanges = 0
    while row != sorted(row):
        if row[cursor] > row[cursor + 1]:
            row[cursor], row[cursor + 1] = row[cursor + 1], row[cursor]
            exchanges += 1
        if row == sorted(row):
            break
        cursor = (cursor + 1) % (len(row) - 1)
        advances += 1
    return advances, exchanges


def comparison_plan(order, band_size, *, remember=True, deduce=True, oracle_stop=False):
    """Visible-information witness; truth is consulted only for a requested weigh.

    The no-memory counterfactual gets an oracle early-stop, making its reading
    count a stronger lower bound than waiting for a full unchanged pass.
    """
    row = list(order)
    relations = {(a,b) for a in row for b in row if a//band_size < b//band_size}
    def known(a,b):
        if not deduce:
            return (a,b) in relations
        pending, seen = [a], set()
        while pending:
            v = pending.pop()
            if v == b:
                return True
            if v not in seen:
                seen.add(v)
                pending.extend(y for x,y in relations if x == v)
        return False
    cursor = advances = exchanges = readings = 0
    actions = []
    for _ in range(400):
        if (all(known(a,b) for a,b in zip(row,row[1:])) if remember and not oracle_stop else row == sorted(row)):
            return {'advances': advances, 'exchanges': exchanges, 'readings': readings, 'actions': actions}
        a,b = row[cursor:cursor+2]
        if not known(a,b) and not known(b,a):
            actions.append('weigh');readings += 1
            if remember:
                relations.add((min(a,b),max(a,b)))
        if a > b:
            actions.append('exchange');exchanges += 1
            row[cursor],row[cursor+1] = b,a
        if (all(known(a,b) for a,b in zip(row,row[1:])) if remember and not oracle_stop else row == sorted(row)):
            return {'advances': advances, 'exchanges': exchanges, 'readings': readings, 'actions': actions}
        actions.append('advance');advances += 1
        cursor = (cursor+1)%(len(row)-1)
    raise ValueError('comparison witness failed to terminate')


def insertion_plan(order):
    """Binary insertion with a movable specimen; every comparison is adjacent.

    The other prefix specimens remain in their learned relative order while
    the pivot is moved to the next chosen comparison. No specimen is lifted.
    """
    row = list(order)
    cursor = advances = exchanges = readings = 0
    actions = []
    def go(index):
        nonlocal cursor, advances
        while cursor != index:
            actions.append('advance');advances += 1
            cursor = (cursor+1)%(len(row)-1)
    def swap(index):
        nonlocal exchanges
        go(index);actions.append('exchange');exchanges += 1
        row[index],row[index+1] = row[index+1],row[index]
    for k in range(1,len(row)):
        pivot = row[k]
        prefix = row[:k]
        lo,hi = 0,k
        while lo < hi:
            mid = (lo+hi)//2
            anchor = prefix[mid]
            while abs(row.index(pivot)-row.index(anchor)) > 1:
                p,q = row.index(pivot),row.index(anchor)
                swap(p-1 if p > q else p)
            go(min(row.index(pivot),row.index(anchor)))
            actions.append('weigh');readings += 1
            if pivot < anchor:
                hi = mid
            else:
                lo = mid+1
        while row.index(pivot) != lo:
            p = row.index(pivot)
            swap(p-1 if p > lo else p)
    assert row == sorted(order)
    return {'advances':advances,'exchanges':exchanges,'readings':readings,'actions':actions}


def generate(task, seed):
    condition = copy.deepcopy(task.get('_control_condition') or task.get('metadata', {}).get('control_condition'))
    parameters = dict((condition or {}).get('difficulty_parameters') or DEFAULTS)
    manual = parameters.get('manual_readings', 0)
    extra = {'manual_readings', 'reading_slack', 'planned_comparisons'} if manual else set()
    if set(parameters) != set(DEFAULTS) | extra:
        raise ValueError('comparator parameters must specify count, band size, displacement and slack')
    # Canonicalize field order while retaining the baseline's original seed bytes.
    parameters = {key: parameters[key] for key in [*DEFAULTS, *sorted(extra)]}
    if any(type(v) is not int for v in parameters.values()):
        raise ValueError('integer comparator parameters required')
    n, band, displacement, slack = (parameters[k] for k in DEFAULTS)
    if not (4 <= n <= 13 and 2 <= band <= n and 1 <= displacement <= (n-1 if manual else 5) and 2 <= slack <= 30):
        raise ValueError('unsupported comparator parameters')
    if manual and (manual != 1 or not 0 <= parameters['reading_slack'] <= 3 or parameters['planned_comparisons'] not in (0,1)):
        raise ValueError('invalid metered comparison settings')
    rng = random.Random(int.from_bytes(hashlib.sha256(f'{seed}|{MECHANIC_ID}|{parameters}'.encode()).digest()[:8], 'big'))
    # Bound disorder structurally: each item can travel at most d slots left.
    # Rejection additionally proves a complete solve before the lamp budget.
    comparison_limit = n * (n - 1) // 2 - 1
    for _ in range(10000):
        ranks = list(range(n))
        rng.shuffle(ranks)
        if max(i-r for i, r in enumerate(ranks)) > displacement:
            continue
        advances, swaps = sorting_cost(ranks)
        if swaps < 2 or (not manual and advances + 1 > comparison_limit):
            continue
        if manual:
            direct_plan = comparison_plan(ranks, band, deduce=False)
            insertion = insertion_plan(ranks)
            plan = insertion if parameters['planned_comparisons'] else direct_plan
            reactive = comparison_plan(ranks, band, remember=False)
            pair_cache = comparison_plan(ranks, band, deduce=False, oracle_stop=True)
            allowance = (insertion['readings'] if parameters['planned_comparisons'] else max(direct_plan['readings'],insertion['readings'])) + parameters['reading_slack']
            if not (1 <= allowance <= comparison_limit and allowance < reactive['readings']):
                continue
            if parameters['planned_comparisons'] and allowance >= pair_cache['readings']:
                continue
        break
    else:
        raise ValueError('could not generate a reachable comparator frame')
    identities = rng.sample(list('ABCDEFGHJKLMNPQRSTUVWXYZ'), n)
    rng.shuffle(identities)
    weights = {identities[r]: 100 + 20*r + rng.randrange(9) for r in range(n)}
    slides = []
    for rank in ranks:
        slides.append({'id': identities[rank], 'size_band': rank // band,
                       'engraving': rng.randrange(6), 'spots': rng.randrange(1, 4)})
    task_id = task['id']
    challenge_id = hashlib.sha256(f'{seed}|{task_id}|{parameters}|{condition}'.encode()).hexdigest()[:16]
    limits = {'readings': comparison_limit, 'levers': comparison_limit - 1 + n*(n-1)//2 + slack}
    if manual:
        limits = {'readings': allowance, 'levers': n*n*(n-1) + slack}
        assert max(plan['advances'] + plan['exchanges'],insertion['advances']+insertion['exchanges']) <= limits['levers']
    public = {'benchmark': 'weird_captcha_gym', 'mechanic_id': MECHANIC_ID, 'task_id': task_id,
              'challenge_id': challenge_id, 'prompt': task.get('natural_language', 'Seal the specimens from lightest to heaviest.'),
              'slides': slides, 'limits': limits,
              # The local static renderer needs weights to operate the comparator.
              # They are never text, DOM labels, or an observation-side answer.
              'runtime_weights': weights,
              'generator': {'name': 'comparator_engine_v0', 'variant_count': math.factorial(n)},
              'asset_manifest': 'shared_runtime/assets/provenance/comparator_engine_v0.json'}
    truth = {'mechanic_id': MECHANIC_ID, 'task_id': task_id, 'challenge_id': challenge_id, 'seed': seed,
             'slides': copy.deepcopy(slides), 'weights': weights.copy(), 'limits': limits.copy(),
             'parameters': parameters, 'witness_cost': {'advances': advances, 'exchanges': swaps}}
    if manual:
        public['manual_readings'] = True
        truth['manual_readings'] = True
        truth['witness_cost'] = {k:plan[k] for k in ('advances','exchanges','readings')}
        truth['memory_plan'] = plan['actions']
        truth['reactive_oracle_readings'] = reactive['readings']
        truth['pair_cache_oracle_readings'] = pair_cache['readings']
        truth['insertion_cost'] = {k:insertion[k] for k in ('advances','exchanges','readings')}
        truth['insertion_plan'] = insertion['actions']
    if condition:
        public['control_condition'] = copy.deepcopy(condition)
        truth['control_condition'] = copy.deepcopy(condition)
    return public, truth
