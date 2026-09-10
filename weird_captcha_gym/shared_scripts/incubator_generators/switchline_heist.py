"""Original circuit-stealth building; no source-game code or assets."""
import copy
import hashlib
import random

MECHANIC_ID = 'switchline_heist'
PROFILES = {
 1: dict(gates=1, permissions=False, interlock=False, repair_ticks=420, alarm=False, sight=65),
 2: dict(gates=1, permissions=False, interlock=False, repair_ticks=240, alarm=False, sight=105),
 3: dict(gates=2, permissions=True, interlock=False, repair_ticks=240, alarm=False, sight=105),
 4: dict(gates=3, permissions=True, interlock=True, repair_ticks=240, alarm=False, sight=105),
 5: dict(gates=3, permissions=True, interlock=True, repair_ticks=180, alarm=True, sight=125),
}

def generate(task, seed):
    condition = copy.deepcopy(task.get('_control_condition') or task.get('metadata', {}).get('control_condition'))
    p = copy.deepcopy((condition or {}).get('difficulty_parameters') or PROFILES[3])
    if p not in PROFILES.values():
        raise ValueError('unsupported switchline difficulty profile')
    rng = random.Random(hashlib.sha256((MECHANIC_ID + str(seed)).encode()).hexdigest())
    n = p['gates']
    colors = rng.sample(['amber', 'cyan', 'violet'], n)
    gates = []
    switches = []
    for i in range(n):
        x = (700 if n == 1 else round(260 + i * 440 / (n - 1))) + rng.randrange(-12,13,4)
        color = colors[i] if p['permissions'] else colors[0]
        gates.append(dict(id=f'gate{i}', x=x, color=color))
        for side, dx in [('L',-64),('R',64)]:
            switches.append(dict(id=f's{i}{side}', x=x+dx, color=color, kind='switch', label=f'{i+1}{side}'))
    last = gates[-1]
    switches.append(dict(id='service', x=948, color=last['color'], kind='attendant', label='SERVICE'))
    outputs = [dict(g,kind='gate',label=f'GATE {i+1}') for i,g in enumerate(gates)]
    outputs.append(dict(id='lamp', x=850, color=last['color'], kind='lamp',label='ARCHIVE LIGHT'))
    wires = {s['id']: ('lamp' if s['color']==last['color'] else None) for s in switches}
    wires['service'] = last['id']
    chips = [dict(x=gates[i-1]['x']+92, color=colors[i]) for i in range(1,n)] if p['permissions'] else []
    world = dict(parameters=p, gates=gates, switches=switches, outputs=outputs, wires=wires,
                 chips=chips, initial_permissions=[colors[0]], booths=[last['x']+64,884],
                 start=64, item=884, guard_x=rng.randrange(820,941,4), guard_dir=rng.choice([-1,1]),
                 guard_speed=rng.choice([1.0,1.25,1.5]), tick_ms=50, player_speed=4,
                 archive_start=last['x']+12)
    task_id=task['id']
    cid=hashlib.sha256((str(seed)+task_id+repr(p)).encode()).hexdigest()[:24]
    public=dict(mechanic_id=MECHANIC_ID, task_id=task_id, challenge_id=cid, benchmark='weird_captcha_gym',
                asset_manifest='shared_runtime/assets/provenance/switchline_heist_v0.json',
                generator=dict(name='switchline_heist_v1', variant_count=(3 if n==1 else 6)*7**n*31*2*3,
                               variant_count_kind='circuit colors, gate positions, patrol phase, direction and speed'),
                prompt='Switchline Heist', submit_label='EXTRACT', world=world,
                control_condition=condition, generator_version=1)
    truth=copy.deepcopy(public)
    truth['seed']=str(seed)
    return public, truth
