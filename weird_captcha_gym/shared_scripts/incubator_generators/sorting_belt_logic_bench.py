"""Original combinational sorter; RNG never depends on the input surface."""
from __future__ import annotations
import copy
import hashlib
import itertools
import random

MECHANIC_ID = 'sorting_belt_logic_bench'
DEFAULT_PARAMETERS = {'attribute_count': 4, 'rule_family': 'xor_filter', 'gate_budget': 8}
PROFILES = [(2,'pair',2),(3,'nested',4),(3,'mux',6),(4,'xor_filter',8),(4,'dual_xor',10)]


def generate(task, seed):
    condition = copy.deepcopy(task.get('_control_condition'))
    params = dict(condition['difficulty_parameters']) if condition else dict(DEFAULT_PARAMETERS)
    n, family, budget = (params[k] for k in ('attribute_count','rule_family','gate_budget'))
    if (n,family,budget) not in PROFILES or set(params) != set(DEFAULT_PARAMETERS):
        raise ValueError('unsupported sorting profile')
    if condition and (condition.get('interaction') not in ('full','simplified') or PROFILES[condition['difficulty']-1] != (n,family,budget)):
        raise ValueError('invalid control condition')
    rng = random.Random(int(hashlib.sha256(f'{MECHANIC_ID}|{seed}'.encode()).hexdigest(),16))
    inputs = [f's{i}' for i in range(n)]
    rng.shuffle(inputs)
    gates = []
    def gate(kind,*sources):
        key=f'g{len(gates)}';gates.append({'id':key,'kind':kind,'sources':list(sources),'slot':len(gates)});return key
    def xor(a,b):
        c=gate('NAND',a,b);return gate('NAND',gate('NAND',a,c),gate('NAND',b,c))
    a,b=inputs[:2]
    if family=='pair': out=gate(rng.choice(['AND','OR','NAND']),a,b)
    elif family=='nested':out=gate('AND',a,gate('OR',b,inputs[2])) if rng.randrange(2) else gate('OR',a,gate('AND',b,inputs[2]))
    elif family=='mux':
        c=inputs[2]; inv=gate('NOT',c);out=gate('OR',gate('AND',c,a),gate('AND',inv,b))
    elif family=='xor_filter':out=gate('AND',xor(a,b),gate(rng.choice(['AND','OR']),*inputs[2:]))
    else:out=gate('AND',xor(a,b),xor(*inputs[2:]))
    rows=[]
    for bits in itertools.product([0,1],repeat=n):
        values=dict(zip([f's{i}' for i in range(n)],bits))
        for g in gates:
            v=[values[s] for s in g['sources']]
            values[g['id']]=int((not v[0]) if g['kind']=='NOT' else (all(v) if g['kind']=='AND' else any(v) if g['kind']=='OR' else not all(v)))
        rows.append({'bits':list(bits),'eject':values[out]})
    rng.shuffle(rows)
    task_id=task['id'];challenge=hashlib.sha256(f'{seed}|{task_id}|{params}'.encode()).hexdigest()[:16]
    world={'attribute_count':n,'gate_budget':budget,'rows':rows,'batch_order':rng.sample(list(range(len(rows))),len(rows)), 'token_ms':700,'gate_types':['AND','OR','NOT','NAND'],'sensors':['AMBER','SQUARE','TWO NOTCHES','MARKED'][:n]}
    public={'benchmark':'weird_captcha_gym','mechanic_id':MECHANIC_ID,'task_id':task_id,'challenge_id':challenge,'prompt':'Sorting Belt Logic Bench','world':world,'generator':{'name':'boolean_sorter_v0'},'asset_manifest':f'shared_runtime/assets/provenance/{MECHANIC_ID}_v0.json'}
    truth={k:copy.deepcopy(public[k]) for k in ('mechanic_id','task_id','challenge_id','world')}
    truth.update(seed=seed,solution={'gates':gates,'output':out})
    if condition:public['control_condition']=condition;truth['control_condition']=copy.deepcopy(condition)
    return public,truth
