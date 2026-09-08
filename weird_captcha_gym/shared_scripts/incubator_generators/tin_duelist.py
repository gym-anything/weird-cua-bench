"""Original fixed-tick, side-view duel. No source game code or assets reused."""
from __future__ import annotations
import copy
import hashlib
import json
import random

MECHANIC_ID = 'tin_duelist'
BASELINE_PARAMETERS = dict(tick_ms=50, max_ticks=1800, enemy_moves=['jab','lunge','hammer'], enemy_guard=True, adaptive=True, startup_bonus=4, recovery_bonus=8, enemy_speed=4, decision_ticks=12)

def generate(task, seed):
    condition = copy.deepcopy(task.get('_control_condition'))
    p = copy.deepcopy(condition['difficulty_parameters'] if condition else BASELINE_PARAMETERS)
    if set(p) != set(BASELINE_PARAMETERS): raise ValueError('invalid duel parameters')
    for k in ('tick_ms','max_ticks','startup_bonus','recovery_bonus','enemy_speed','decision_ticks'):
        if type(p[k]) is not int: raise ValueError(k)
    if p['tick_ms'] != 50 or not 600 <= p['max_ticks'] <= 2400 or not 0 <= p['startup_bonus'] <= 20 or not 0 <= p['recovery_bonus'] <= 30 or not 2 <= p['enemy_speed'] <= 6 or not 6 <= p['decision_ticks'] <= 30: raise ValueError('parameters outside duel limits')
    if type(p['enemy_guard']) is not bool or type(p['adaptive']) is not bool or not p['enemy_moves'] or not set(p['enemy_moves']) <= {'jab','lunge','hammer'}: raise ValueError('invalid opponent')
    rng = random.Random(hashlib.sha256(str(seed).encode()).hexdigest())
    world = dict(parameters=p, player_x=rng.randrange(170,271), enemy_x=rng.randrange(650,791), policy_seed=rng.randrange(1,65536), approach_gap=rng.randrange(65,96), palette=rng.randrange(4))
    identity = hashlib.sha256((str(seed)+json.dumps(world,sort_keys=True)).encode()).hexdigest()[:16]
    public = dict(benchmark='weird_captcha_gym',mechanic_id=MECHANIC_ID,task_id=task['id'],challenge_id=identity,prompt=task.get('natural_language','Win the duel.'),generator={'name':'tin_duelist_v0','variant_count':10000000},asset_manifest='shared_runtime/assets/provenance/tin_duelist_v0.json',world=world)
    truth = copy.deepcopy(public)
    truth['seed'] = str(seed)
    if condition:
        public['control_condition']=copy.deepcopy(condition)
        truth['control_condition']=copy.deepcopy(condition)
    return public,truth
