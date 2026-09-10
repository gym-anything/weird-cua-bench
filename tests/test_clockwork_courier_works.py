import copy
import importlib.util
import json
from pathlib import Path
import pytest
R=Path(__file__).resolve().parents[1]/'weird_captcha_gym'; M='clockwork_courier_works'; E=R/'environments'/f'{M}_env'
def load(path):
    spec=importlib.util.spec_from_file_location('cc_module',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
G=load(R/'shared_scripts/incubator_generators'/f'{M}.py');P=load(R/'shared_runtime/server/incubator_graders'/f'{M}.py'); C=json.loads((E/'controls.json').read_text());T=json.loads((E/'tasks'/f'{M}_seed_0001/task.json').read_text())
def state(level,mode,seed):
    t=copy.deepcopy(T);t['_control_condition']={'difficulty':level,'interaction':mode,'real_time':'live','difficulty_parameters':C['difficulty'][str(level)]['parameters']};return G.generate(t,seed)[0]
def solution(s):
    S=load(R/'tools/incubator_solvers'/f'{M}.py');w,rods=S.choose_design(s);sim=P.simulate(s,w,rods)
    src='drag' if s.get('control_condition',{}).get('interaction','full')=='full' else 'click'
    events=[{'kind':'place','wheel':p,'input_source':src} for p in w]+[{'kind':'rod','ends':p,'input_source':src} for p in rods]+[{'kind':'run'},{'kind':'finish','ticks':sim['tick']}]
    return {**{k:s[k] for k in ('mechanic_id','task_id','challenge_id')},'events':events},sim
@pytest.mark.parametrize('level',range(1,6))
@pytest.mark.parametrize('seed',['trial','second','third'])
def test_deterministic_reachable_pair(level,seed):
    a=state(level,'full',seed);b=state(level,'simplified',seed);assert a==state(level,'full',seed)
    assert {k:v for k,v in a.items() if k!='control_condition'}=={k:v for k,v in b.items() if k!='control_condition'}
    for s in [a,b]:
        payload,sim=solution(s);assert sim['delivered'];assert P.grade(payload,s,s)['passed']
        bad=copy.deepcopy(payload);bad['events'][0]['input_source']='click' if s is a else 'drag';assert not P.grade(bad,s,s)['passed']
        bad=copy.deepcopy(payload);bad['challenge_id']='stale';assert not P.grade(bad,s,s)['passed']
        bad=copy.deepcopy(payload);bad['events'][-1]['ticks']=1;bad['completed']=True;assert not P.grade(bad,s,s)['passed']
def test_baseline_world_preserved():
    a=G.generate(T,'same')[0];b=state(2,'full','same');assert {k:v for k,v in b.items() if k!='control_condition'}==a

def test_outcome_depends_on_physics_and_design():
    s=state(2,'full','trial');x=s['parcel'][0]
    assert not P.simulate(s,[[x-75,345,36,-1],[x+75,345,36,-1]],[(0,1),(0,2),(1,2)])['delivered']
    assert not P.simulate(s,[[x-75,345,36,1],[x+75,345,36,1]],[])['delivered']
    assert not P.simulate(s,[[x-90,360,24,1],[x+90,360,24,1]],[(0,1),(0,2),(1,2)])['delivered']

def test_invalid_construction_and_alternative_geometry():
    s=state(2,'full','trial');payload,_=solution(s)
    for value in [float('nan'),float('inf'),-1000]:
        bad=copy.deepcopy(payload);bad['events'][0]['wheel'][0]=value;assert not P.grade(bad,s,s)['passed']
    bad=copy.deepcopy(payload);bad['events'][2]['ends']=[0,999];assert not P.grade(bad,s,s)['passed']
    x=s['parcel'][0];assert P.simulate(s,[[x-75,325,48,1],[x+75,325,48,1]],[(0,1),(0,2),(1,2)])['delivered']
