"""Original event-recognition gallery; no imported art or remote runtime."""
from __future__ import annotations
import copy
import hashlib
import random

MECHANIC_ID = 'museum_of_lost_gestures'
GESTURES = ['double', 'right', 'drag', 'hold', 'scroll', 'resize', 'return', 'dwell', 'modifier', 'chord']
TITLES = ['Second Tap', 'Other Hand', 'Long Journey', 'Lingering Touch', 'Deepest Floor', 'Growing Room', 'The Withdrawal', 'Perfect Stillness', 'Held Companion', 'Together Apart']
LABELS = ['Double tap', 'Right click', 'Long drag', 'Hold 2 seconds', 'Scroll to bottom', 'Resize room', 'Leave and return', 'Dwell 5 seconds', 'Shift + click', 'A + S chord']
# L1 is the exact original uncontrolled configuration, including its sweep solution.
PROFILES = {
 level: {'clues': 'titles', 'gated': True, 'composition': level}
 for level in range(1, 6)
}


def generate(task, seed):
    condition = copy.deepcopy(task.get('_control_condition'))
    params = dict((condition or {}).get('difficulty_parameters') or PROFILES[1])
    if params not in PROFILES.values():
        raise ValueError('unsupported gallery profile')
    rng = random.Random(int.from_bytes(hashlib.sha256(f'{seed}|{MECHANIC_ID}'.encode()).digest()[:8], 'big'))
    order = list(range(10)); rng.shuffle(order)
    cases = []
    for rank, index in enumerate(order):
        # Later compositions refer to gestures already learned from open exhibits.
        earlier = [i for i in order[:rank] if GESTURES[i] in {"double", "right", "drag", "hold", "modifier", "chord"}]
        prefix = rng.sample(earlier, min(len(earlier), params['composition'] - 1))
        cases.append({'id': f'case-{index}', 'title': TITLES[index], 'gesture': GESTURES[index],
                      'recipe': [GESTURES[p] for p in prefix] + [GESTURES[index]],
                      'requires': [f'case-{p}' for p in sorted(set(prefix + ([order[rank-3]] if params['gated'] and rank >= 3 else [])))],
                      'number': index + 3})
    # Wall positions do not reveal the topological solving order.
    rng.shuffle(cases)
    world = {'cases': cases, 'parameters': params, 'plinth': [150 + rng.randrange(-20,21), 112, 120, 92],
             'room_width': 490, 'room_height': 310, 'scroll_max': 310,
             'hold_ms': 2000, 'dwell_ms': 5000, 'double_ms': 550,
             'resize_px': 80, 'still_px': 6, 'budget': 120,
             'vocabulary': [dict(id=g, label=l) for g,l in zip(GESTURES, LABELS)]}
    task_id = task.get('id', MECHANIC_ID + '_seed_0001@0.1')
    challenge = hashlib.sha256(f'{seed}|{task_id}|{condition}'.encode()).hexdigest()[:16]
    common = {'mechanic_id': MECHANIC_ID, 'task_id': task_id, 'challenge_id': challenge, 'world': world}
    public = dict(copy.deepcopy(common), benchmark='weird_captcha_gym', prompt='Recover the ten lost gestures.',
                  submit_label='Close the exhibition', asset_manifest='shared_runtime/assets/provenance/museum_of_lost_gestures_v0.json',
                  generator={'name': 'museum_of_lost_gestures_v0', 'version': 1})
    truth = dict(copy.deepcopy(common), seed=seed, solution_order=[f'case-{i}' for i in order])
    if condition:
        public['control_condition'] = copy.deepcopy(condition)
        truth['control_condition'] = copy.deepcopy(condition)
    return public, truth
