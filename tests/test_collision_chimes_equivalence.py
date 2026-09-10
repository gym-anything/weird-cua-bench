"""Regression coverage for audit 2's two legal-input grading failures."""
import copy
import runpy
from pathlib import Path

H = runpy.run_path(str(Path(__file__).with_name('test_collision_chimes.py')))


def configuration(surface):
    task = H['_task'](4, surface)
    public, truth = H['GENERATOR'].generate(task, 'audit-order-1')
    return task, public, truth


def test_physical_placement_order_and_simultaneous_event_order_are_irrelevant():
    for surface in ('full', 'simplified'):
        task, public, truth = configuration(surface)
        reverse = copy.deepcopy(truth)
        reverse['solution_cells'] = [dict(cell, id=f'c{i}') for i, cell in enumerate(reversed(truth['solution_cells']))]
        payload = H['_solution_payload'](task, public, reverse)
        assert payload['wall_events'] != truth['contract']['target_events']
        assert H['GRADER'].grade(payload, truth, public)['passed']
        payload['wall_events'].reverse()
        assert H['GRADER'].grade(payload, truth, public)['passed']


def test_redundant_rotations_preserve_acceptance_and_integrity_checks():
    for surface in ('full', 'simplified'):
        task, public, truth = configuration(surface)
        payload = H['_solution_payload'](task, public, truth)
        cell = payload['cells'][0]
        direction = cell['direction']
        for _ in range(16):
            after = (direction + 1) % 4
            payload['edit_events'].append(dict(sequence=len(payload['edit_events']) + 1,
                type='cycle', id=cell['id'], row=cell['row'], col=cell['col'],
                before_direction=direction, after_direction=after,
                input_source='cell_click' if surface == 'full' else 'cycle_button'))
            direction = after
        assert len(payload['edit_events']) == 31
        assert H['GRADER'].grade(payload, truth, public)['passed']
        for key, value in [('before_direction', (direction + 2) % 4), ('input_source', 'wrong'), ('sequence', 999)]:
            bad = copy.deepcopy(payload)
            bad['edit_events'][-1][key] = value
            assert not H['GRADER'].grade(bad, truth, public)['passed']


def test_missing_extra_and_changed_events_still_fail():
    task, public, truth = configuration('full')
    original = H['_solution_payload'](task, public, truth)
    for change in ('missing', 'extra', 'beat', 'slot', 'side', 'malformed'):
        payload = copy.deepcopy(original)
        if change == 'missing':
            payload['wall_events'].pop()
        elif change == 'extra':
            payload['wall_events'].append(copy.deepcopy(payload['wall_events'][0]))
        elif change == 'malformed':
            payload['wall_events'][0]['beat'] = '1'
        else:
            payload['wall_events'][0][change] = {'beat': 40, 'slot': 99, 'side': 'left'}[change]
        assert not H['GRADER'].grade(payload, truth, public)['passed']
    # Target multiplicity also matters; normalizing must not collapse duplicates.
    public, truth = copy.deepcopy(public), copy.deepcopy(truth)
    for state in (public, truth):
        state['contract']['target_events'].append(copy.deepcopy(state['contract']['target_events'][0]))
    assert not H['GRADER'].grade(original, truth, public)['passed']
