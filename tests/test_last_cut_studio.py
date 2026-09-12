import copy
import importlib.util
import json
from pathlib import Path
import pytest
B=Path(__file__).resolve().parents[1]/'weird_captcha_gym'
def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
gen=load(B/'shared_scripts/incubator_generators/last_cut_studio.py','lc_gen')
grade=load(B/'shared_runtime/server/incubator_graders/last_cut_studio.py','lc_grade').grade
oracle=load(B/'tools/incubator_solvers/last_cut_studio.py','lc_solver').oracle

def fixture(level,mode,seed='check'):
 task=json.loads((B/f'environments/last_cut_studio_env/tasks/last_cut_studio_d{level}_{mode}_seed_0001/task.json').read_text())
 public,truth=gen.generate(task,seed)
 montage=oracle(truth);events=[]
 for i,e in enumerate(montage):
  events.extend([dict(type='add',clip=e['clip']),dict(type='trim',index=i,in_frame=e['in_frame'],out_frame=e['out_frame'])])
 for i,e in enumerate(events):e.update(seq=i+1,input_source='direct' if mode=='full' else 'proxy')
 payload={k:truth[k] for k in ['mechanic_id','task_id','challenge_id','control_condition']};payload.update(events=events,montage=montage)
 return public,truth,payload

@pytest.mark.parametrize('level',range(1,6))
def test_seeded_oracles_and_mode_worlds(level):
 worlds=set()
 for seed in range(50):
  a,t,p=fixture(level,'full',str(seed));b,u,q=fixture(level,'simplified',str(seed))
  assert grade(p,t,a)['passed'] and grade(q,u,b)['passed']
  assert a['clips']==b['clips'] and a['brief']==b['brief']
  assert a['target_frames']==b['target_frames']
  assert fixture(level,'full',str(seed))==(a,t,p)
  worlds.add(json.dumps(a['clips']))
  swapped=copy.deepcopy(p);swapped.update({k:q[k] for k in ['task_id','challenge_id','control_condition']})
  assert not grade(swapped,u,b)['passed']
 assert len(worlds)==50

@pytest.mark.parametrize('level',range(1,6))
@pytest.mark.parametrize('mode',['full','simplified'])
def test_adversarial_outcome_and_alternate_edit(level,mode):
 a,t,p=fixture(level,mode)
 for mutation in ['stale','truncated','slate','duration','order','forged','nan','float','wrong_surface','unknown']:
  q=copy.deepcopy(p)
  if mutation=='stale':q['challenge_id']='old'
  elif mutation=='truncated':
   q['events'][1]['in_frame']=t['clips'][next(i for i,c in enumerate(t['clips']) if c['id']==t['required'][0])]['start']+1;q['montage'][0]['in_frame']=q['events'][1]['in_frame']
  elif mutation=='slate':q['events'][1]['in_frame']=0;q['montage'][0]['in_frame']=0
  elif mutation=='duration':
   for i,e in enumerate(q['montage']):
    c=next(c for c in t['clips'] if c['id']==e['clip']);e.update(in_frame=c['safe_start'],out_frame=c['safe_end']);q['events'][2*i+1].update(in_frame=e['in_frame'],out_frame=e['out_frame'])
   # L1's broad duration allowance intentionally accepts some padded edits.
   if level==1:continue
  elif mutation=='order':q['montage'].reverse()
  elif mutation=='forged':q['events']=[]
  elif mutation=='nan':q['events'][1]['in_frame']=float('nan')
  elif mutation=='float':q['events'][1]['in_frame']=1.5
  elif mutation=='wrong_surface':q['events'][0]['input_source']='proxy' if mode=='full' else 'direct'
  else:q['events'][0]['type']='complete'
  assert not grade(q,t,a)['passed'],mutation
 # An equal-duration cut with different handles is a valid alternative.
 q=copy.deepcopy(p);q['events'][1]['in_frame']-=1;q['events'][1]['out_frame']-=1;q['montage'][0]['in_frame']-=1;q['montage'][0]['out_frame']-=1
 assert grade(q,t,a)['passed']

def test_baseline_matches_profile_four():
 task=json.loads((B/'environments/last_cut_studio_env/tasks/last_cut_studio_seed_0001/task.json').read_text());a,t=gen.generate(task,'baseline');b,u,_=fixture(4,'full','baseline')
 for key in ['clips','brief','target_frames','tolerance']:assert a[key]==b[key]
