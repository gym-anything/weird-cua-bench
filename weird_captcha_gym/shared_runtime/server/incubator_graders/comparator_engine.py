"""Independent replay of primitive lever actions; never trust a final permutation."""
from __future__ import annotations
import math
MECHANIC_ID = 'comparator_engine'


def grade(payload, truth, public):
    def fail(message, outcome='invalid_transcript'):
        return {'graded': True, 'passed': False, 'score': 0, 'feedback': message, 'outcome': outcome}
    if any(not isinstance(x, dict) for x in (payload, truth, public)):
        return fail('malformed result')
    for key in ('mechanic_id', 'task_id', 'challenge_id'):
        if not truth.get(key) or any(x.get(key) != truth[key] for x in (payload, public)):
            return fail('stale task or challenge')
    if truth['mechanic_id'] != MECHANIC_ID:
        return fail('wrong mechanic')
    condition = truth.get('control_condition')
    if condition != public.get('control_condition') or payload.get('control_condition') != condition:
        return fail('wrong control condition')
    manual = truth.get('manual_readings', False)
    if type(manual) is not bool or public.get('manual_readings', False) is not manual or bool((condition or {}).get('difficulty_parameters', {}).get('manual_readings')) != manual:
        return fail('wrong comparison mode')
    mode = (condition or {}).get('interaction', 'simplified')
    source = {'simplified': 'button', 'full': 'lever_drag'}.get(mode)
    if source is None:
        return fail('unsupported interaction')
    try:
        if public['slides'] != truth['slides'] or public['runtime_weights'] != truth['weights'] or public['limits'] != truth['limits']:
            return fail('public/private contract mismatch')
        row = [s['id'] for s in truth['slides']]
        weights = truth['weights']
        limits = truth['limits']
        if not 4 <= len(row) <= 13 or len(set(row)) != len(row) or set(row) != set(weights):
            return fail('invalid slide bank')
        if any(type(v) is not int for v in weights.values()) or len(set(weights.values())) != len(row):
            return fail('invalid weights')
        if any(type(limits[k]) is not int or limits[k] < 1 for k in ('readings', 'levers')):
            return fail('invalid limits')
        if condition and condition.get('difficulty_parameters') != truth['parameters']:
            return fail('difficulty contract mismatch')
    except (KeyError, TypeError, ValueError):
        return fail('malformed comparator contract')
    events = payload.get('events')
    if not isinstance(events, list) or not 1 <= len(events) <= (2000 if manual else 400):
        return fail('missing or excessive actions')
    cursor = advances = exchanges = 0
    readings = 0 if manual else 1
    terminal = None
    for seq, event in enumerate(events, 1):
        if terminal is not None or not isinstance(event, dict) or type(event.get('seq')) is not int or event['seq'] != seq:
            return fail('invalid event sequence')
        if event.get('input_source') != source:
            return fail('wrong interaction input')
        if mode == 'full':
            gesture = event.get('gesture')
            if not isinstance(gesture, dict):
                return fail('missing lever geometry')
            try:
                x0,y0,x1,y1 = (gesture[k] for k in ('x0','y0','x1','y1'))
                if any(type(v) not in (int,float) or not math.isfinite(v) for v in (x0,y0,x1,y1)):
                    return fail('invalid lever geometry')
                if not (0.25 <= x0 <= .75 and 0 <= y0 <= .4 and .1 <= x1 <= .9 and .72 <= y1 <= 1):
                    return fail('lever did not reach the lower detent')
            except (KeyError, TypeError):
                return fail('invalid lever geometry')
        if type(event.get('cursor')) is not int or event['cursor'] != cursor or event.get('pair') != row[cursor:cursor+2]:
            return fail('stale carriage or slide identities')
        action = event.get('type')
        if action == 'seal':
            terminal = 'sorted' if all(weights[a] < weights[b] for a,b in zip(row,row[1:])) else 'unsorted_seal'
        elif action == 'weigh' and manual:
            if readings >= limits['readings']:
                terminal = 'comparison_exhausted'
            else:
                readings += 1
        elif action in ('advance', 'exchange'):
            if advances + exchanges >= limits['levers']:
                terminal = 'lever_exhausted'
            elif action == 'advance' and not manual and readings >= limits['readings']:
                terminal = 'comparison_exhausted'
            elif action == 'advance':
                cursor = (cursor + 1) % (len(row)-1)
                advances += 1
                readings += 0 if manual else 1
            else:
                row[cursor], row[cursor+1] = row[cursor+1], row[cursor]
                exchanges += 1
        else:
            return fail('unknown lever action')
    if terminal is None:
        return fail('frame has not been sealed')
    counts = payload.get('counts')
    if not isinstance(counts, dict) or set(counts) != {'advances', 'exchanges', 'readings'} or any(type(v) is not int for v in counts.values()):
        return fail('invalid action counts')
    if payload.get('final_order') != row or payload.get('counts') != {'advances': advances, 'exchanges': exchanges, 'readings': readings}:
        return fail('reported state disagrees with replay')
    passed = terminal == 'sorted'
    if payload.get('completed') is not passed:
        return fail('false completion claim')
    inversions = sum(weights[a] > weights[b] for i,a in enumerate(row) for b in row[i+1:])
    return {'graded': True, 'passed': passed, 'score': 100 if passed else 0, 'outcome': terminal,
            'feedback': 'Exact specimen order accepted' if passed else {
                'unsorted_seal': 'FAIL · Frame sealed out of order', 'lever_exhausted': 'FAIL · Lever reserve exhausted',
                'comparison_exhausted': 'FAIL · Comparison reserve exhausted'}[terminal],
            'metrics': {'advances': advances, 'exchanges': exchanges, 'readings': readings,
                        'lever_pulls': advances+exchanges, 'inversions': inversions}}
