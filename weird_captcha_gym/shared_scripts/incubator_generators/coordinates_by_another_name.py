"""Seeded irregular chart; hidden fleet is revealed only by console shots."""
from __future__ import annotations
import copy
import hashlib
import itertools
import json
import random

MECHANIC_ID = 'coordinates_by_another_name'
BASELINE = dict(rows=5, columns=8, irregular=True, reverse_counts=False,
                orientation_feedback=True, touching=False, holes=0,
                fleet_lengths=[3, 3, 2], sweeps=2)


def generate(task, seed):
    condition = task.get('_control_condition')
    p = BASELINE | dict((condition or {}).get('difficulty_parameters') or {})
    rows, columns = p['rows'], p['columns']
    if not 3 <= rows <= 6 or not 5 <= columns <= 9 or not 0 <= p['holes'] <= 8:
        raise ValueError('unsupported chart size')
    if not 0 <= p['sweeps'] <= 2 or not all(2 <= n <= 4 for n in p['fleet_lengths']):
        raise ValueError('unsupported fleet or sweep count')
    rng = random.Random(int(hashlib.sha256(f'{MECHANIC_ID}|{seed}'.encode()).hexdigest(), 16))
    holes = set(rng.sample([(r,c) for r in range(rows) for c in range(columns)], p['holes']))
    cells, runs = [], []
    bands = rng.sample(range(1, 10), rows)
    for r in range(rows):
        # Three contiguous block spans, with different widths in each band.
        cuts = sorted(rng.sample(range(1,columns),2)) if p['irregular'] else [2,4]
        labels = rng.sample(list('ABC'),3) if p['irregular'] else list('ABC')
        for j,(start,end) in enumerate(zip([0]+cuts,cuts+[columns])):
            reverse = bool(p['reverse_counts'] and rng.randrange(2))
            run = dict(band=bands[r], block=labels[j], row=r, start=start,
                       width=end-start, reverse=reverse)
            runs.append(run)
            for c in range(start,end):
                if (r,c) in holes: continue
                cells.append(dict(id=f'{r}:{c}', row=r, column=c, band=bands[r],
                                  block=labels[j], count=end-c if reverse else c-start+1))
    valid = {(c['row'],c['column']) for c in cells}
    candidates = {}
    for length in set(p['fleet_lengths']):
        candidates[length] = [[(r+dr*k,c+dc*k) for k in range(length)]
            for r,c in sorted(valid) for dr,dc in [(0,1),(1,0)]
            if all((r+dr*k,c+dc*k) in valid for k in range(length))]
    def effective_runs(target_ids):
        return [run for run in runs if any(
            c['id'] in target_ids and c['band'] == run['band'] and c['block'] == run['block']
            and c['column'] - run['start'] + 1 != run['start'] + run['width'] - c['column']
            for c in cells)]

    fleet = None
    for _ in range(1000):
        ships, occupied = [], set()
        for length in p['fleet_lengths']:
            options = [x for x in candidates[length] if not occupied.intersection(x)
                and (p['touching'] or all((r+dr,c+dc) not in occupied
                    for r,c in x for dr in [-1,0,1] for dc in [-1,0,1]))]
            if not options: break
            chosen = rng.choice(options)
            ships.append({'cells':[f'{r}:{c}' for r,c in chosen],
                          'orientation':'H' if chosen[0][0]==chosen[-1][0] else 'V'})
            occupied.update(chosen)
        if len(ships)==len(p['fleet_lengths']):
            # A reversed width-one run (or just its middle cell) changes no
            # address. Require an occupied cell whose designation can change.
            if p['reverse_counts'] and not effective_runs({c for ship in ships for c in ship['cells']}):
                continue
            fleet=ships;break
    if fleet is None: raise ValueError('could not place a separated reachable fleet')
    # Exact omniscient lower bound, NOT an information-theoretic search minimum.
    target = {c for ship in fleet for c in ship['cells']}
    if p['reverse_counts']:
        eligible = effective_runs(target)
        reversed_run = next((run for run in eligible if run['reverse']), None)
        if reversed_run is None:
            reversed_run = rng.choice(eligible)
            reversed_run['reverse'] = True
        # Preserve a real mixture, so direction must be read locally rather
        # than adopting one global convention for the whole chart.
        forward_options = [run for run in effective_runs({c['id'] for c in cells}) if run is not reversed_run]
        if not any(not run['reverse'] for run in forward_options):
            rng.choice(forward_options)['reverse'] = False
        for run in runs:
            for cell in cells:
                if cell['band'] == run['band'] and cell['block'] == run['block']:
                    cell['count'] = (run['start'] + run['width'] - cell['column'] if run['reverse']
                                     else cell['column'] - run['start'] + 1)
    cover = [{c['id'] for c in cells if c['band']==run['band'] and c['block']==run['block']} & target for run in runs]
    minimum = len(target)
    for k in range(1,p['sweeps']+1):
        for chosen in itertools.combinations(cover,k):
            minimum=min(minimum,k+len(target-set.union(*chosen)))
    task_id=task['id']
    digest=hashlib.sha256(json.dumps([seed,task_id,p,condition],sort_keys=True).encode()).hexdigest()[:16]
    world=dict(rows=rows,columns=columns,cells=cells,runs=runs,bands=bands,
               fleet_lengths=p['fleet_lengths'],sweeps=p['sweeps'],
               orientation_feedback=p['orientation_feedback'],touching=p['touching'])
    public=dict(benchmark='weird_captcha_gym',mechanic_id=MECHANIC_ID,
                task_id=task_id,challenge_id=digest,world=copy.deepcopy(world),
                prompt='Find the fleet. Speak its coordinates.',
                # Required for local synchronous feedback in the existing plugin seam.
                # Not placed in DOM before a hit; inspectable browser exploration.
                runtime_fleet=copy.deepcopy(fleet),
                asset_manifest=f'shared_runtime/assets/provenance/{MECHANIC_ID}_v0.json',
                generator={'name':'irregular_designations_v1'})
    truth=dict(mechanic_id=MECHANIC_ID,task_id=task_id,challenge_id=digest,seed=seed,
               world=copy.deepcopy(world),fleet=fleet,omniscient_min_shots=minimum)
    if condition:
        public['control_condition']=copy.deepcopy(condition)
        truth['control_condition']=copy.deepcopy(condition)
    return public,truth
