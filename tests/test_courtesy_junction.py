"""Courtesy Junction contracts and adversarial physical replay."""
import copy
import importlib.util
import json
from pathlib import Path
import pytest

R=Path(__file__).resolve().parents[1]/'weird_captcha_gym'
def load(path,name):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
G=load(R/'shared_scripts/incubator_generators/courtesy_junction.py','courtesy_gen')
S=load(R/'tools/incubator_solvers/courtesy_junction.py','courtesy_solver');P=S.physics
C=json.loads((R/'environments/courtesy_junction_env/controls.json').read_text())
BASE=json.loads((R/'environments/courtesy_junction_env/tasks/courtesy_junction_seed_0001/task.json').read_text())
def task(level,mode):
    t=copy.deepcopy(BASE);t['_control_condition']=dict(difficulty=level,interaction=mode,real_time='live',difficulty_parameters=copy.deepcopy(C['difficulty'][str(level)]['parameters']));return t

def transcript(public):
    w=public['world'];state=P.initial(w);points=S.route(w);events=[dict(seq=1,type='start')];control=[0,0]
    def record(kind,**extra):events.append(dict(seq=len(events)+1,type=kind,**extra))
    while state['status']=='driving' and state['tick']<2400:
        value=S.choose(state,w,points)
        if value!=control:
            control=value;record('control',tick=state['tick'],value=value,input_source='held_keys' if public['control_condition']['interaction']=='full' else 'panel_buttons')
        for i in range(20):
            if state['status']!='driving':break
            P.step(state,control,w);record('tick',state=P.snapshot(state))
    record('submit',tick=state['tick'])
    return {**{k:copy.deepcopy(public[k]) for k in ['mechanic_id','task_id','challenge_id','control_condition']},'events':events,'final':P.snapshot(state)}

@pytest.mark.parametrize('level',range(1,6))
def test_deterministic_world_pairs_and_initial_geometry(level):
    worlds=set()
    for i in range(30):
        t=task(level,'full');a,truth=G.generate(t,f'pair-{i}');b,_=G.generate(task(level,'simplified'),f'pair-{i}')
        assert a==G.generate(t,f'pair-{i}')[0]
        assert a['world']==b['world']==truth['world']
        worlds.add(json.dumps(a['world'],sort_keys=True))
        bodies=[P.corners(a['world']['start'])]+[P.corners(P.pose(c)) for c in a['world']['traffic']]
        assert all(not P.intersect(x,y) for n,x in enumerate(bodies) for y in bodies[n+1:])
    assert len(worlds)==30

def test_baseline_preserved():
    for seed in ['original-a','original-b','original-c']:
        assert G.generate(BASE,seed)==G.generate(task(4,'full'),seed)

@pytest.mark.parametrize('level',range(1,6))
@pytest.mark.parametrize('mode',['full','simplified'])
def test_all_profiles_replay_and_reject_tampering(level,mode):
    public,truth=G.generate(task(level,mode),'evidence-f');payload=transcript(public)
    assert P.grade(payload,truth,public)['passed'],payload['final']
    bad=copy.deepcopy(payload);bad['challenge_id']='stale';assert not P.grade(bad,truth,public)['passed']
    bad=copy.deepcopy(payload);bad['final']['ego']['x']+=10;assert not P.grade(bad,truth,public)['passed']
    bad=copy.deepcopy(payload);next(e for e in bad['events'] if e['type']=='tick')['state']['traffic'][0]['s']+=10;assert not P.grade(bad,truth,public)['passed']
    bad=copy.deepcopy(payload);next(e for e in bad['events'] if e['type']=='control')['input_source']='panel_buttons' if mode=='full' else 'held_keys';assert not P.grade(bad,truth,public)['passed']
    bad=copy.deepcopy(payload);bad['events']=[];assert not P.grade(bad,truth,public)['passed']
    other_public,other_truth=G.generate(task(level,'full' if mode=='simplified' else 'simplified'),'evidence-f')
    assert not P.grade(payload,other_truth,other_public)['passed']

def test_driver_reacts_to_ego_and_contact_is_symmetric():
    public,_=G.generate(BASE,'causal');w=public['world'];a=P.initial(w);b=copy.deepcopy(a)
    a['traffic']=a['traffic'][:1];b['traffic']=b['traffic'][:1]
    a['traffic'][0].update(s=350,v=45,cruise=50,horizon=2);b['traffic'][0].update(s=350,v=45,cruise=50,horizon=2)
    a['ego'].update(x=440,y=290,a=0,v=0);b['ego'].update(x=480,y=470,a=-1.57,v=0)
    P.step(a,[0,0],w);P.step(b,[0,0],w)
    assert a['traffic'][0]['braking'] and a['traffic'][0]['v']<b['traffic'][0]['v']
    car=dict(x=450,y=260,a=.6,v=0);other=dict(x=470,y=260,a=-.3,v=0)
    assert P.intersect(P.corners(car),P.corners(other))==P.intersect(P.corners(other),P.corners(car))==True
    other['x']=550;assert not P.intersect(P.corners(car),P.corners(other))

def test_collision_offroad_and_nonnumeric_forgery_fail():
    public,truth=G.generate(BASE,'failure');w=public['world'];s=P.initial(w);s['ego']=P.pose(s['traffic'][0]);P.step(s,[0,0],w);assert s['status']=='collision'
    s=P.initial(w);s['ego'].update(x=200,y=100);P.step(s,[0,0],w);assert s['status']=='offroad'
    assert not P.grade({'completed':True},truth,public)['passed']
    assert not P.close(float('nan'),0)
