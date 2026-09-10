"""Physical consequences of the revised courses, without topology quotas."""
import copy
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location('courier_fixtures', Path(__file__).with_name('test_clockwork_courier_works.py'))
F = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(F)


def test_original_course_is_the_exact_l2_reference():
    assert F.C['baseline']['difficulty'] == 2
    for seed in ['audit-fixed-0', 'audit-fixed-49', 'preserve-reference']:
        original = F.G.generate(F.T, seed)[0]
        controlled = F.state(2, 'full', seed)
        controlled.pop('control_condition')
        assert controlled == original
        assert original['build_box'] == [45, 160, 330, 390]
        assert original['wheel_radii'] == [24, 36, 48]
        assert original['segments'][2][1] == 366
        assert original['segments'][3][0] - original['segments'][2][2] == 55


def test_audit_carrier_remains_legal_but_meets_real_tunnel_contacts():
    wheels = [[105,325,48,1],[275,325,48,1]]
    rods = [(0,1),(0,2),(1,2)]
    assert F.P.simulate(F.state(2, 'full', 'revision-0'), wheels, rods)['delivered']
    for level in [4,5]:
        s = F.state(level, 'full', 'revision-0')
        assert not F.P.simulate(s, wheels, rods)['delivered']
        # No coordinate blacklist or new part limit caused that failure.
        assert all(45+r <= x <= 330-r and 160+r <= y <= 390-r for x,y,r,_ in wheels)
        assert s['wheel_radii'] == [24,36,48]
        assert s['max_wheels'] == 6 and s['max_rods'] == 14


def test_two_reachable_l5_worlds_need_different_tested_carriers():
    narrow = F.state(5, 'full', 'revision-2')
    wide = F.state(5, 'full', 'revision-0')
    results = []
    for s in [narrow, wide]:
        x = s['parcel'][0]
        small = [[x-75,295,24,1],[x+75,295,24,1]]
        medium = [[x-75,310,36,1],[x+75,310,36,1]]
        results.append([F.P.simulate(s, small, [(0,1),(0,2)])['delivered'],
                        F.P.simulate(s, medium, [(0,1),(0,2),(1,2)])['delivered']])
    assert results == [[True, False], [False, True]]


def test_flexible_two_rod_machine_is_accepted_without_failed_attempt():
    s = F.state(5, 'simplified', 'revision-2')
    x = s['parcel'][0]
    wheels = [[x-75,295,24,1],[x+75,295,24,1]]
    rods = [(0,1),(0,2)]
    sim = F.P.simulate(s, wheels, rods)
    events = [{'kind':'place','wheel':w,'input_source':'click'} for w in wheels]
    events += [{'kind':'rod','ends':r,'input_source':'click'} for r in rods]
    events += [{'kind':'run'},{'kind':'finish','ticks':sim['tick']}]
    payload = {**{k:s[k] for k in ['mechanic_id','task_id','challenge_id']},'events':events}
    assert F.P.grade(payload, s, s)['passed']


def test_receiving_roof_changes_the_same_physical_design_outcome():
    s = F.state(5, 'full', 'revision-0')
    x = s['parcel'][0]
    wheels = [[x-75,295,24,1],[x+75,310,36,1]]
    rods = [(0,1),(0,2),(1,2)]
    assert not F.P.simulate(s, wheels, rods)['delivered']
    without_roof = copy.deepcopy(s)
    without_roof['segments'].pop()
    assert F.P.simulate(without_roof, wheels, rods)['delivered']


def test_parameter_key_order_does_not_change_generated_world():
    import json
    for level in [3,4,5]:
        task = copy.deepcopy(F.T)
        task['_control_condition'] = {'difficulty':level,'interaction':'full','real_time':'live',
                                     'difficulty_parameters':F.C['difficulty'][str(level)]['parameters']}
        assert F.G.generate(task, 'ordering-proof') == F.G.generate(json.loads(json.dumps(task, sort_keys=True)), 'ordering-proof')
