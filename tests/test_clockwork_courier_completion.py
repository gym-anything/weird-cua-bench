"""Regression coverage for editor/replay discrepancies found during completion."""
import copy
import pytest
import importlib.util
from pathlib import Path
_spec = importlib.util.spec_from_file_location("clockwork_test_fixtures", Path(__file__).with_name("test_clockwork_courier_works.py"))
_fixtures = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixtures)
P, state, solution = _fixtures.P, _fixtures.state, _fixtures.solution


def test_zero_tick_aborted_test_does_not_poison_later_delivery():
    s = state(2, 'full', 'completion')
    payload, _ = solution(s)
    payload['events'][:0] = [
        {'kind': 'run'}, {'kind': 'finish', 'ticks': 0}, {'kind': 'edit'},
    ]
    assert P.grade(payload, s, s)['passed']


@pytest.mark.parametrize('kind', ['place', 'move'])
def test_illegal_editor_prefix_cannot_be_hidden_by_repair(kind):
    s = state(2, 'full', 'completion')
    payload, _ = solution(s)
    position = payload['events'][0]['wheel'][:2]
    if kind == 'place':
        payload['events'][0]['wheel'][0] = -1000
    else:
        payload['events'].insert(1, {'kind': 'move', 'index': 1, 'point': [-1000, 345], 'input_source': 'drag'})
    payload['events'].insert(2 if kind == 'move' else 1,
                             {'kind': 'move', 'index': 1, 'point': position, 'input_source': 'drag'})
    assert not P.grade(payload, s, s)['passed']


@pytest.mark.parametrize('mode', ['full', 'simplified'])
def test_remove_and_reconnect_one_rod_preserves_delivery(mode):
    s = state(2, mode, 'completion')
    payload, _ = solution(s)
    source = 'drag' if mode == 'full' else 'click'
    payload['events'][5:5] = [
        {'kind': 'unrod', 'ends': [1, 2], 'input_source': source},
        {'kind': 'rod', 'ends': [1, 2], 'input_source': source},
    ]
    assert P.grade(payload, s, s)['passed']
    bad = copy.deepcopy(payload)
    bad['events'].insert(6, {'kind': 'unrod', 'ends': [1, 2], 'input_source': source})
    assert not P.grade(bad, s, s)['passed']


def test_zero_tick_finish_cannot_be_duplicated_or_turned_into_delivery():
    s = state(2, 'full', 'completion')
    payload, _ = solution(s)
    payload['events'][:0] = [
        {'kind': 'run'}, {'kind': 'finish', 'ticks': 0},
        {'kind': 'finish', 'ticks': 0}, {'kind': 'edit'},
    ]
    assert not P.grade(payload, s, s)['passed']
    payload['events'] = [{'kind': 'run'}, {'kind': 'finish', 'ticks': 0}]
    payload['completed'] = True
    assert not P.grade(payload, s, s)['passed']


def test_boolean_indices_and_non_mapping_payloads_fail_without_exception():
    s = state(2, 'full', 'completion')
    payload, _ = solution(s)
    payload['events'].insert(2, {'kind': 'reverse', 'index': True, 'input_source': 'drag'})
    assert not P.grade(payload, s, s)['passed']
    assert not P.grade([], s, s)['passed']
