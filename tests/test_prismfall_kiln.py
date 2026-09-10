"""Prismfall contact, replay, generation and control-pair invariants."""
import copy
import json
from pathlib import Path
import pytest
from weird_captcha_gym.shared_scripts.incubator_generators.prismfall_kiln import generate,engine
ROOT=Path(__file__).resolve().parents[1]/'weird_captcha_gym'
ENV=ROOT/'environments/prismfall_kiln_env'
BASE=json.loads((ENV/'tasks/prismfall_kiln_seed_0001/task.json').read_text())
CONTROLS=json.loads((ENV/'controls.json').read_text())
SIM=engine()
def task(d,m):
 t=copy.deepcopy(BASE);t['_control_condition']={'difficulty':d,'interaction':m,'real_time':'live','difficulty_parameters':CONTROLS['difficulty'][str(d)]['parameters']};return t

def ledger(p,tr):
 bs=p['initial'];events=[]
 for i,x in enumerate(tr['solution_x']):
  bs,n,over=SIM.drop(bs,p['world'],p['offers'][i],x);assert not over
  events.append(dict(seq=i+1,input_source='rail_click',x=x,ticks=n,bodies=bs))
 return dict(mechanic_id='prismfall_kiln',task_id=p['task_id'],challenge_id=p['challenge_id'],events=events)

@pytest.mark.parametrize('d',range(1,6))
def test_pairs_reachable_deterministic_and_adversarial(d):
 p,tr=generate(task(d,'full'),'invariants-2');p2,tr2=generate(task(d,'full'),'invariants-2');assert (p,tr)==(p2,tr2)
 q,tq=generate(task(d,'simplified'),'invariants-2')
 for key in ('world','initial','offers','target'):assert p[key]==q[key]
 assert 'solution_x' not in p and len(tr['solution_x'])>=2
 payload=ledger(p,tr);assert SIM.grade(payload,tr,p)['passed']
 bad=copy.deepcopy(payload);bad['challenge_id']='stale';assert not SIM.grade(bad,tr,p)['passed']
 bad=copy.deepcopy(payload);bad['events'][0]['x']=float('nan');assert not SIM.grade(bad,tr,p)['passed']
 bad=copy.deepcopy(payload);bad['events'][0]['bodies'][0]['x']+=2;assert not SIM.grade(bad,tr,p)['passed']
 bad=copy.deepcopy(payload);bad['events'][0]['ticks']=0;assert not SIM.grade(bad,tr,p)['passed']
 bad=copy.deepcopy(payload);bad['challenge_id']=q['challenge_id'];assert not SIM.grade(bad,tq,q)['passed']
 for e in bad['events']:e['input_source']='position_button'
 assert SIM.grade(bad,tq,q)['passed']
 for b in p['initial']:
  r=SIM.RADII[b['t']];assert r-.02<=b['x']<=p['world']['width']-r+.02
 for i,a in enumerate(p['initial']):
  for b in p['initial'][i+1:]:assert ((a['x']-b['x'])**2+(a['y']-b['y'])**2)**.5>=SIM.RADII[a['t']]+SIM.RADII[b['t']]-.1

def test_contact_merge_and_displacement():
 w=dict(width=300,height=390,overflow=82)
 bs=[SIM.body(0,120,374),SIM.body(0,151,374),SIM.body(1,185,367)]
 mass=sum(2**b['t'] for b in bs);SIM.settle(bs,w)
 assert sum(2**b['t'] for b in bs)==mass and len(bs)<3
 assert all(b['y']+SIM.RADII[b['t']]<=390.01 for b in bs)

def test_empty_claim_rejected():
 p,tr=generate(task(1,'full'),'empty');assert not SIM.grade({'completed':True},tr,p)['passed']

def test_baseline_preserves_generated_world():
 p,tr=generate(copy.deepcopy(BASE),'baseline');q,tq=generate(task(3,'full'),'baseline')
 for key in ('world','initial','offers','target'):assert p[key]==q[key]
 assert tr['solution_x']==tq['solution_x']

def test_forged_completion_and_illegal_release_do_not_pass():
 p,tr=generate(task(1,'full'),'forgery');a=ledger(p,tr)
 for x in (-1,1e9,float('inf'),True,'150'):
  b=copy.deepcopy(a);b['events'][0]['x']=x;assert not SIM.grade(b,tr,p)['passed']
 b=copy.deepcopy(a);b['events']=[];b['completed']=True;assert not SIM.grade(b,tr,p)['passed']
 b=copy.deepcopy(a);b['events'].append(copy.deepcopy(b['events'][-1]));assert not SIM.grade(b,tr,p)['passed']

def test_malformed_json_returns_failure_instead_of_raising():
 p,tr=generate(task(1,'full'),'malformed');valid=ledger(p,tr)
 for payload in (None,[],True,'claim'):
  assert SIM.grade(payload,tr,p)==dict(graded=True,passed=False,feedback='malformed kiln ledger')
 for value in (None,[],True,12,'body'):
  bad=copy.deepcopy(valid);bad['events'][0]['bodies'][0]=value
  assert not SIM.grade(bad,tr,p)['passed']
 for key in ('seq','ticks'):
  bad=copy.deepcopy(valid);bad['events'][0][key]=float(bad['events'][0][key])
  assert not SIM.grade(bad,tr,p)['passed']
 bad=copy.deepcopy(valid);bad['events'][0]['bodies'][0]['t']=float(bad['events'][0]['bodies'][0]['t'])
 assert not SIM.grade(bad,tr,p)['passed']

def test_capability_annotation_is_recorded_on_public_task():
    capabilities = BASE['metadata']['capabilities']
    assert capabilities == ['visual understanding: 2D', 'reasoning and planning']
