"""Seeded workshop geometry, independent of the interaction surface."""
import copy
import hashlib
import random
MECHANIC_ID = 'clockwork_courier_works'

def generate(task, seed):
    condition=task.get('_control_condition') or task.get('metadata',{}).get('control_condition')
    params=(condition or {}).get('difficulty_parameters', {'rise':44,'gap':55,'ceiling':0})
    rng=random.Random(hashlib.sha256((str(seed)+MECHANIC_ID).encode()).digest())
    if params.get('course') == 'compound':
        return compound(task, seed, condition, params, rng)
    rise=int(params['rise']); gap=int(params['gap']); ceiling=int(params['ceiling'])
    if not 0<=rise<=60 or not 0<=gap<=100 or ceiling not in (0,250): raise ValueError('unsupported track')
    ramp=rng.randint(380,410); plateau=ramp+105; cut=plateau+75
    segments=[[0,410,ramp,410],[ramp,410,plateau,410-rise],[plateau,410-rise,cut,410-rise],[cut+gap,410-rise,790,410-rise],[790,410-rise,920,410-rise]]
    if ceiling: segments.append([ramp+30,ceiling,780,ceiling])
    state={'mechanic_id':MECHANIC_ID,'task_id':task['id'],'challenge_id':hashlib.sha256((str(seed)+task['id']).encode()).hexdigest()[:16], 'prompt':task.get('natural_language','Deliver the parcel.'),'stage':{'width':920,'height':480},'parcel':[rng.randint(175,205),310,18],'build_box':[45,160,330,390],'segments':segments,'receiver':[805,285-rise,910,410-rise],'max_wheels':6,'max_rods':14,'max_ticks':1200,'tick_ms':1000/60,'wheel_radii':[24,36,48], 'asset_manifest':'shared_runtime/assets/provenance/clockwork_courier_works_v0.json'}
    if condition:state['control_condition']=copy.deepcopy(condition)
    return state,copy.deepcopy(state)


def compound(task, seed, condition, params, rng):
    """Independent passage, incline and receiving-clearance constraints.

    Only static segment geometry changes. All bodies, contact rules, part
    choices, editor controls, and outcome grading remain the original model.
    """
    route = rng.choice(params['routes'])
    values = {key: rng.randint(*route[key])
              for key in ('headroom', 'rise', 'gap', 'exit_headroom') if key in route}
    ramp = rng.randint(530, 550)
    plateau, cut = ramp + 105, ramp + 160
    height = 410 - values['rise']
    segments = [[0,410,ramp,410], [ramp,410,plateau,height],
                [plateau,height,cut,height], [cut+values['gap'],height,920,height]]
    overhead = []
    if values['headroom']:
        overhead.append(len(segments))
        segments.append([rng.randint(340,360),410-values['headroom'],
                         rng.randint(485,505),410-values['headroom']])
    if values.get('exit_headroom'):
        overhead.append(len(segments))
        segments.append([cut-10,height-values['exit_headroom'],910,
                         height-values['exit_headroom']])
    state = {'mechanic_id':MECHANIC_ID, 'task_id':task['id'],
             'challenge_id':hashlib.sha256((str(seed)+task['id']).encode()).hexdigest()[:16],
             'prompt':task.get('natural_language','Deliver the parcel.'),
             'stage':{'width':920,'height':480}, 'parcel':[rng.randint(175,205),310,18],
             'build_box':[45,160,330,390], 'segments':segments,
             'overhead_segments':overhead, 'receiver':[805,height-125,910,height],
             'max_wheels':6, 'max_rods':14, 'max_ticks':1200,
             'tick_ms':1000/60, 'wheel_radii':[24,36,48],
             'asset_manifest':'shared_runtime/assets/provenance/clockwork_courier_works_v0.json',
             'control_condition':copy.deepcopy(condition)}
    return state, copy.deepcopy(state)
