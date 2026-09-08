import copy
import json
from pathlib import Path
import pytest
from weird_captcha_gym.shared_scripts.incubator_generators.concertina_courier import generate
from weird_captcha_gym.shared_runtime.server.incubator_graders.concertina_courier import advance,bounds,clear,grade

CONTROLS=json.loads(Path('weird_captcha_gym/environments/concertina_courier_env/controls.json').read_text())

def world(seed,level,mode):
    return generate({'id':'test','_control_condition':dict(difficulty=level,interaction=mode,real_time='live',difficulty_parameters=CONTROLS['difficulty'][str(level)]['parameters'])},seed)

@pytest.mark.parametrize('level',range(1,6))
def test_generation_and_geometry(level):
    worlds=[]
    for seed in range(30):
        a,g=world(str(seed),level,'full');b,_=world(str(seed),level,'simplified')
        assert a==world(str(seed),level,'full')[0]
        for k in ['solids','seals','initial_state','parameters']:assert a[k]==b[k]
        assert clear(a['initial_state'],a)
        worlds.append(a['solids'])
        s=copy.deepcopy(a['initial_state'])
        for i in range(120):
            advance(s,[1,1 if i<60 else -1],a)
            box=bounds(s,a)
            assert box[2]*box[3]==pytest.approx(a['area'])
            assert clear(s,a)
    assert len({json.dumps(v) for v in worlds})>20


def test_reject_claims_and_stale():
    a,g=world('negative',3,'full')
    p=dict(mechanic_id=a['mechanic_id'],task_id=a['task_id'],challenge_id=a['challenge_id'],interaction_mode='full',events=[],terminal_tick=0,final_state=a['initial_state'],completed=True)
    assert not grade(p,g,a)['passed']
    for k,v in [('challenge_id','stale'),('interaction_mode','simplified'),('terminal_tick',float('nan'))]:
        assert not grade(dict(p,**{k:v}),g,a)['passed']


def test_support_loss_and_morph_collision():
    a,_=world('physics',2,'full');s=copy.deepcopy(a['initial_state'])
    # A tall parcel inside the gap falls; a wide parcel spans it.
    left=a['solids'][0][2];right=a['solids'][1][0]
    s.update(x=(left+right)/2,h=200.)
    for _ in range(40):advance(s,[0,0],a)
    assert s['status']=='fell'
    s=copy.deepcopy(a['initial_state']);s.update(x=(left+right)/2,h=32.)
    for _ in range(40):advance(s,[0,0],a)
    assert s['bottom']==420
    shelf=a['solids'][2];s.update(x=shelf[0]+shelf[2]/2,h=32.)
    for _ in range(100):advance(s,[0,1],a)
    assert s['h']<=a['parameters']['clearance'] and clear(s,a)

@pytest.mark.parametrize('level',range(1,6))
def test_reference_replay_and_wrong_surface(level):
    for seed in range(6):
        a,g=world(f'route-{seed}',level,'full');s=copy.deepcopy(a['initial_state']);events=[];control=[0,0]
        def command(c):
            nonlocal control
            if c!=control:
                if c != [0,0] and control != [0,0]:
                    events.append(dict(tick=s['tick'],control=[0,0],input_source='body_hold'))
                events.append(dict(tick=s['tick'],control=c,input_source='body_hold'));control=c
        def act(target,shape=False,precision=16):
            for _ in range(700):
                if s['status']!='active':return
                error=target-s['h' if shape else 'x']
                if shape:
                    if abs(error)<3:command([0,0]);return
                    c=[0,1 if error>0 else -1]
                else:
                    if abs(error)<precision and abs(s['vx'])<.15:command([0,0]);return
                    if precision<16:
                        from weird_captcha_gym.tools.incubator_solvers.concertina_courier import settle_plan
                        for c,n in settle_plan(s,a,target):
                            if not n:continue
                            command(c)
                            for _ in range(n):advance(s,control,a)
                        continue
                    lead=s['vx']*a['parameters']['drag']**.25/(4*(1-a['parameters']['drag']**.25))
                    c=[1 if error-lead>10 else -1 if error-lead<-10 else 0,0]
                command(c);advance(s,control,a)
            raise AssertionError(s)
        if a['parameters'].get('layout')=='island':
            act(200,True);act(a['seals'][0][0],precision=8);act(32,True)
            act(a['seals'][3][0],precision=3);act(200,True)
        else:
            shelf=a['solids'][2] if a['parameters']['gap'] else a['solids'][1];end=shelf[0]+shelf[2]
            for target,shape in [(a['parameters']['clearance']-8,True),(end+125,False),(200,True),(a['seals'][2][0],False),(end+125,False),(32,True),(847.5 if a['parameters']['alcove'] else a['seals'][3][0],False),(200,True)]:act(target,shape)
        p=dict(mechanic_id=a['mechanic_id'],task_id=a['task_id'],challenge_id=a['challenge_id'],interaction_mode='full',events=events,terminal_tick=s['tick'],final_state=s,completed=True)
        assert grade(p,g,a)['passed'],(level,seed,s)
        bad=copy.deepcopy(p);bad['events'][0]['input_source']='console_latch'
        assert not grade(bad,g,a)['passed']


def test_default_matches_island_l3_profile():
    original,_=generate({'id':'test'},'baseline')
    controlled,_=world('baseline',3,'full')
    for key in ['solids','seals','initial_state','parameters','area','min_height','max_height']:
        assert original[key]==controlled[key]


def test_unavailable_controls_and_malformed_envelopes():
    a,g=world('input-integrity',3,'full')
    base=dict(mechanic_id=a['mechanic_id'],task_id=a['task_id'],challenge_id=a['challenge_id'],interaction_mode='full',events=[],terminal_tick=0,final_state=a['initial_state'],completed=True)
    for value in [None, [], 'completed', 1]:
        assert not grade(value,g,a)['passed']
        assert not grade(dict(base,final_state=value),g,a)['passed']
    diagonal=dict(base,events=[dict(tick=0,control=[1,1],input_source='body_hold')])
    assert 'diagonal' in grade(diagonal,g,a)['feedback']
    switch=dict(base,events=[dict(tick=0,control=[1,0],input_source='body_hold'),dict(tick=0,control=[0,1],input_source='body_hold')])
    assert 'released' in grade(switch,g,a)['feedback']
    changed=copy.deepcopy(a);changed['solids'][0][1]-=20
    assert 'rendered world' in grade(base,g,changed)['feedback']


def test_l1_admits_prepared_single_slide():
    # The framework's pre-run exclusion applies despite visible inertia.
    for seed in range(20):
        a,_=world(f'pre-run-{seed}',1,'full')
        s=copy.deepcopy(a['initial_state'])
        for _ in range(7):advance(s,[0,1],a)
        for _ in range(400):advance(s,[1,0],a)
        assert s['status']=='solved'


def test_materialized_verifier_replays_outside_checkout(tmp_path):
    import importlib.util
    import shutil
    a,g=world('portable',1,'full');s=copy.deepcopy(a['initial_state'])
    for _ in range(7):advance(s,[0,1],a)
    while s['status']=='active':advance(s,[1,0],a)
    events=[dict(tick=0,control=[0,1],input_source='body_hold'),dict(tick=7,control=[0,0],input_source='body_hold'),dict(tick=7,control=[1,0],input_source='body_hold')]
    p=dict(mechanic_id=a['mechanic_id'],task_id=a['task_id'],challenge_id=a['challenge_id'],interaction_mode='full',events=events,terminal_tick=s['tick'],final_state=s,completed=True)
    export=tmp_path/'result.json';export.write_text(json.dumps(dict(public_state=a,ground_truth=g,result=p)))
    source=Path('weird_captcha_gym/environments/concertina_courier_env/tasks/concertina_courier_seed_0001/verifier.py')
    outside=tmp_path/'materialized'/'tasks'/'courier'/'verifier.py';outside.parent.mkdir(parents=True);shutil.copyfile(source,outside)
    spec=importlib.util.spec_from_file_location('concertina_portable_verifier',outside);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    def copy_from_env(source,destination):shutil.copyfile(export,destination)
    assert module.verify_task(env_info={'copy_from_env':copy_from_env})['passed']


def test_original_configuration_frozen_before_revision():
    import hashlib
    original=world('0',2,'full')
    for value in original:value.pop('control_condition')
    digest=hashlib.sha256(json.dumps(original,sort_keys=True).encode()).hexdigest()
    assert digest=='e26924caa25e8f85157f8f2761de8ed14cf2ec73791c8410149420e254c9964d'


@pytest.mark.parametrize('level',[3,4,5])
def test_island_has_distinct_support_choices_and_reachable_well(level):
    directions=set()
    for seed in range(30):
        a,_=world(f'island-{seed}',level,'simplified')
        p=a['parameters'];platform=a['solids'][1];other=a['solids'][0]
        # The far-side floor cannot be bridged even at maximum width.
        unsupported=max(platform[0],other[0])-min(platform[0]+platform[2],other[0]+other[2])
        assert unsupported>a['area']/a['min_height']
        assert p['opening_range'][0]>a['area']/p['well_clearance']
        assert p['gap_range'][1]<a['area']/a['min_height']
        assert p['opening_range'][1]<a['area']/p['clearance'] or level==3
        directions.add(a['seals'][-1][0]>a['initial_state']['x'])
    assert directions=={False,True}
