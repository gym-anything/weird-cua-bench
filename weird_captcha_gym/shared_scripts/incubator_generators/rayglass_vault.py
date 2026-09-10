"""Seeded opaque optical cabinets; no answer coordinates in public state."""
from __future__ import annotations
import hashlib
import importlib.util
import math
import random
from pathlib import Path

MECHANIC_ID = 'rayglass_vault'
PROFILES = {1: (4, 1), 2: (4, 2), 3: (5, 3), 4: (6, 4), 5: (7, 5)}
BASELINE = {'size': 6, 'bead_count': 4}


def _physics():
    path = Path(__file__).resolve().parents[2] / 'shared_runtime/server/incubator_graders/rayglass_vault.py'
    spec = importlib.util.spec_from_file_location('rayglass_physics', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def generate(task, seed):
    condition = task.get('_control_condition') or (task.get('metadata') or {}).get('control_condition')
    parameters = BASELINE
    if condition is not None:
        if not isinstance(condition, dict) or condition.get('interaction') not in ('full', 'simplified'):
            raise ValueError('invalid rayglass interaction')
        level = condition.get('difficulty')
        if type(level) is not int or level not in PROFILES:
            raise ValueError('invalid rayglass difficulty')
        n, count = PROFILES[level]
        parameters = {'size': n, 'bead_count': count}
        if condition.get('difficulty_parameters') != parameters:
            raise ValueError('rayglass profile does not match its level')
    n, count = parameters['size'], parameters['bead_count']
    digest = hashlib.sha256(f'{MECHANIC_ID}|{seed}|{n}|{count}'.encode()).hexdigest()
    rng = random.Random(int(digest, 16))
    beads = sorted(rng.sample(range(n*n), count))
    physics = _physics()
    shared = {'mechanic_id': MECHANIC_ID, 'task_id': task.get('id', 'rayglass_vault_seed_0001@0.1'),
              'challenge_id': digest[:16], 'size': n, 'bead_count': count}
    if condition is not None:
        shared['control_condition'] = dict(condition)
    public = {**shared, 'benchmark': 'weird_captcha_gym', 'prompt': task.get('natural_language', ''),
              'asset_manifest': 'shared_runtime/assets/provenance/rayglass_vault_v0.json',
              'generator': {'name': 'rayglass_vault_v0', 'variant_count': math.comb(n*n, count)},
              'geometry': physics.geometry(n), 'sensor_responses': physics.signature(n, beads),
              'case_number': digest[:4].upper()}
    truth = {**shared, 'seed': seed, 'beads': beads, 'variant_count': math.comb(n*n, count)}
    return public, truth
