"""Contact physics, controlled generation and independent replay regression checks."""
import copy
import importlib.util
import json
from pathlib import Path
import pytest

B=Path(__file__).resolve().parents[1]/'weird_captcha_gym'
def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
G=load(B/'shared_scripts/incubator_generators/load_bearing_idol.py','idol_generator_test')
P=load(B/'shared_runtime/server/incubator_graders/load_bearing_idol.py','idol_grader_test')
E=B/'environments/load_bearing_idol_env'
TASK=json.loads((E/'tasks/load_bearing_idol_seed_0001/task.json').read_text())
CONTROLS=json.loads((E/'controls.json').read_text())

def task(level,mode):
 t=copy.deepcopy(TASK);t['_control_condition']={'difficulty':level,'interaction':mode,'real_time':'live','difficulty_parameters':CONTROLS['difficulty'][str(level)]['parameters']};return t

@pytest.mark.parametrize('level',range(1,6))
def test_world_is_deterministic_and_interaction_independent(level):
 for seed in ['test','alpha','bravo']:
  a,truth=G.generate(task(level,'full'),seed);b,_=G.generate(task(level,'simplified'),seed)
  assert a==G.generate(task(level,'full'),seed)[0]
  assert a['bodies']==b['bodies'] and a['quota']==b['quota']
  assert truth['bodies']==a['bodies']
  # Interior overlaps are forbidden in the initial physical scene.
  bs=[P.body(b) for b in a['bodies']]
  for i,x in enumerate(bs):
   for y in bs[i+1:]:
    c=P.contact(x,y)
    assert c is None or c[0]<.001,(x['id'],y['id'],c)

def test_baseline_preservation():
 assert G.generate(TASK,'reference')[0]['bodies']==G.generate(task(3,'full'),'reference')[0]['bodies']

def test_resting_body_does_not_drift_and_contact_is_symmetric():
 a=P.body(dict(id='a',kind='glass',x=100.,y=82.,w=22,h=36));b=P.body(dict(id='floor',kind='floor',x=100.,y=110.,w=200,h=20,fixed=True))
 for _ in range(180):P.step([a,b])
 assert abs(a['x']-100)<.01 and abs(a['angle'])<.01
 assert P.contact(a,b,.1) is not None and P.contact(b,a,.1) is not None

def test_real_cut_creates_mass_bearing_fragments_and_wrong_input_rejected():
 b=P.body(dict(id='beam',kind='timber',x=100.,y=100.,w=80,h=30));bs=[b]
 e=dict(body='beam',source='full',start=[100,60],end=[100,140])
 with pytest.raises(ValueError,match='wrong interaction'):P.action(bs,e,'simplified')
 P.action(bs,e,'full');assert [b['id'] for b in bs]==['beama','beamb']
 assert sum(b['w'] for b in bs)==79 and all(b['im']>0 for b in bs)
 for _ in range(20):P.tick(bs)
 assert all(b['y']>100 for b in bs)

@pytest.mark.parametrize('level',range(1,6))
def test_replayed_solution_and_adversarial_transcripts(level):
 public,truth=G.generate(task(level,'full'),'test');bs=[P.body(b) for b in public['bodies']];events=[];now=0
 order=[b['id'] for b in bs if b['id'].startswith('weight')]+[b['id'] for b in sorted(bs,key=lambda b:b['y']) if b['id'].startswith('piece')]
 for name in order:
  b=next(b for b in bs if b['id']==name);x,y=b['x'],b['y']
  e=dict(body=name,source='full',start=[x,y],end=[x+b['w']+60 if b['kind']=='plank' else x,y],tick=now)
  P.action(bs,e,'full');events.append(e)
  for _ in range(180):P.tick(bs);now+=1
 payload={k:truth[k] for k in ['mechanic_id','task_id','challenge_id']};payload.update(events=events,ticks=now)
 assert P.grade(payload,truth,public)['passed']
 bad=copy.deepcopy(payload);bad['events'][0]['source']='simplified';assert not P.grade(bad,truth,public)['passed']
 bad=copy.deepcopy(payload);bad['challenge_id']='old';assert not P.grade(bad,truth,public)['passed']
 bad=copy.deepcopy(payload);bad['events']=[];bad['completed']=True;assert not P.grade(bad,truth,public)['passed']
 bad=copy.deepcopy(payload);bad['events'][0]['start']=[float('nan'),0];assert not P.grade(bad,truth,public)['passed']

def test_l5_unloading_order_changes_the_physical_outcome():
    public,truth=G.generate(task(5,'full'),'idol-b')
    outcomes=[]
    for first in [('weight0','weight1'),('weight1','weight0')]:
        bs=[P.body(b) for b in public['bodies']];floor=False
        order=[*first,'piece3','piece2','piece1','piece0']
        for name in order:
            b=next(b for b in bs if b['id']==name);x,y=b['x'],b['y']
            P.action(bs,dict(body=name,source='full',start=[x,y],end=[x+b['w']+60 if b['kind']=='plank' else x,y]),'full')
            for _ in range(216):floor|=any(set(pair)=={'idol','floor'} for pair in P.tick(bs))
        outcomes.append(P.outcome(bs,set(order),truth['quota'],floor))
    assert outcomes==[False,True]


def test_blocked_extraction_preserves_the_physical_support():
    plank=P.body(dict(id='plank',kind='plank',x=100.,y=100.,w=80,h=20))
    wall=P.body(dict(id='wall',kind='iron',x=160.,y=100.,w=40,h=2000,fixed=True))
    floor=P.body(dict(id='floor',kind='floor',x=100.,y=120.,w=1000,h=20,fixed=True))
    bs=[plank,wall,floor]
    P.action(bs,dict(body='plank',source='full',start=[100,100],end=[240,100]),'full')
    for _ in range(240):P.tick(bs)
    assert plank in bs
    assert plank['x']-plank['extract_origin']<plank['w']+60


def test_unobstructed_extraction_requires_actual_travel():
    plank=P.body(dict(id='plank',kind='plank',x=100.,y=100.,w=80,h=20))
    bs=[plank]
    P.action(bs,dict(body='plank',source='full',start=[100,100],end=[240,100]),'full')
    for _ in range(35):P.tick(bs)
    assert plank in bs  # damping means 35 ticks travel less than 140 pixels
    for _ in range(2):P.tick(bs)
    assert plank not in bs


def test_original_uncontrolled_geometry_is_frozen():
    import hashlib
    public,_=G.generate(TASK,'reference')
    assert hashlib.sha256(json.dumps(public['bodies'],sort_keys=True).encode()).hexdigest()=='029bb99a5d734276b02044c6aadbba45d071c3a3747046b58e364f9251dc3b18'
    assert public['quota']==3


def test_l2_load_changes_the_stack_only_outcome():
    outcomes=[]
    for level in [1,2]:
        public,truth=G.generate(task(level,'full'),'test')
        bs=[P.body(b) for b in public['bodies']];floor=False
        for name in ['piece1','piece0']:
            b=next(b for b in bs if b['id']==name);x,y=b['x'],b['y']
            P.action(bs,dict(body=name,source='full',start=[x,y],end=[x+b['w']+60 if b['kind']=='plank' else x,y]),'full')
            for _ in range(216):floor|=any(set(pair)=={'idol','floor'} for pair in P.tick(bs))
        outcomes.append(P.outcome(bs,{'piece1','piece0'},truth['quota'],floor))
    assert outcomes==[True,False]
