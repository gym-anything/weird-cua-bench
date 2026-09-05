import copy
import json
from pathlib import Path
import pytest
from weird_captcha_gym.shared_scripts.setup_task import generate_incubator_candidate
from weird_captcha_gym.shared_runtime.server.incubator_graders.punchcutters_bench import grade,spacing_reference,deviation,flatten
from weird_captcha_gym.tools.materialize_controlled_tasks import controlled_task,materialize_environment
B=Path(__file__).resolve().parents[1]/'weird_captcha_gym';M='punchcutters_bench';E=B/'environments'/f'{M}_env'
BASE=json.loads((E/'tasks'/f'{M}_seed_0001/task.json').read_text());C=json.loads((E/'controls.json').read_text())
def world(level=4,mode='full',seed='test'):
 t=controlled_task(BASE,mechanic_id=M,level=level,interaction=mode,profile=C['difficulty'][str(level)],task_dir_name=f'{M}_d{level}_{mode}_seed_0001')
 return generate_incubator_candidate(t,seed)
def solution(public):
 b=public['bench'];mode=public.get('control_condition',{}).get('interaction','full');es=[]
 def event(kind,**kw):es.append(dict(sequence=len(es)+1,kind=kind,**kw))
 for x,y,dx,dy in b['master']:event('node',anchor=[x,y],tip=[x+dx,y+dy],input_source='pen_drag' if mode=='full' else 'pen_clicks')
 event('close',input_source='close_button');event('proof',input_source='proof_button')
 for i,x in enumerate(spacing_reference(b,b['master'])[1:-1],1):event('letter',index=i,start=b['initial_positions'][i],end=x,input_source='letter_drag' if mode=='full' else 'letter_place')
 event('certify',input_source='certify_button')
 return dict(events=es,**{k:public[k] for k in ['mechanic_id','task_id','challenge_id']})
@pytest.mark.parametrize('level',range(1,6))
def test_generation_and_pairs(level):
 for seed in ['one','two','three']:
  p,t=world(level,'full',seed);q,u=world(level,'simplified',seed)
  assert (p,t)==world(level,'full',seed)
  assert p['bench']==q['bench'] and p['challenge_id']==q['challenge_id']
  assert t['bench']==p['bench']
  for g in p['bench']['master']:
   assert 0<=g[0]<=800 and 0<=g[1]<=410
  refs=spacing_reference(p['bench'],p['bench']['master'])
  assert all(20<x<720 for x in refs)
  assert all(refs[i+1]-refs[i]>p['bench']['glyphs'][i]['width'] for i in range(len(refs)-1))
@pytest.mark.parametrize('level',range(1,6))
@pytest.mark.parametrize('mode',['full','simplified'])
def test_replay_and_wrong_mode(level,mode):
 p,t=world(level,mode);s=solution(p);assert grade(s,t,p)['passed']
 wrong=copy.deepcopy(s);wrong['events'][0]['input_source']='pen_clicks' if mode=='full' else 'pen_drag';assert not grade(wrong,t,p)['passed']
 wrong=copy.deepcopy(s);next(e for e in wrong['events'] if e['kind']=='letter')['input_source']='letter_place' if mode=='full' else 'letter_drag';assert not grade(wrong,t,p)['passed']

def test_baseline_materialization(tmp_path):
 p,t=generate_incubator_candidate(BASE,'same');q,u=world(4,'full','same');assert p['bench']==q['bench']
 files=materialize_environment(E,tmp_path);assert len(files)==10
 before={str(p):(p/'task.json').read_bytes() for p in files};assert before=={str(p):(p/'task.json').read_bytes() for p in materialize_environment(E,tmp_path)}

def test_adversarial_replay():
 p,t=world(1);s=solution(p)
 for key in ['challenge_id','task_id','mechanic_id']:
  wrong=copy.deepcopy(s);wrong[key]='stale';assert not grade(wrong,t,p)['passed']
 for events in [[],[{'sequence':1,'kind':'certify','input_source':'certify_button'}],s['events'][:-1]]:
  assert not grade(dict(s,events=events),t,p)['passed']
 for tip in [[float('nan'),1],[True,1],[900,2]]:
  wrong=copy.deepcopy(s);wrong['events'][0]['tip']=tip;assert not grade(wrong,t,p)['passed']
 wrong=copy.deepcopy(s);wrong['events'][0]['anchor'][0]+=80;assert not grade(wrong,t,p)['passed']
 wrong=copy.deepcopy(s);next(e for e in wrong['events'] if e['kind']=='letter')['index']=0;assert not grade(wrong,t,p)['passed']
 wrong=copy.deepcopy(s);next(e for e in wrong['events'] if e['kind']=='letter')['end']+=70;assert not grade(wrong,t,p)['passed']

def test_reverse_path_and_node_budget():
 p,t=world(1);nodes=p['bench']['master'];reverse=[[x,y,-dx,-dy] for x,y,dx,dy in reversed(nodes)]
 assert deviation(reverse,nodes)<1e-8
 s=solution(p);s['events'].insert(1,dict(s['events'][0]))
 for i,e in enumerate(s['events'],1):e['sequence']=i
 assert not grade(s,t,p)['passed']

def test_optical_reference_depends_on_curves():
 p,t=world(4);b=p['bench'];ns=copy.deepcopy(b['master']);ns[4][2]+=30
 assert spacing_reference(b,ns)!=spacing_reference(b,b['master'])
 assert b['initial_positions']!=spacing_reference(b,b['master'])


def test_fractional_position_key_nudges_roundtrip():
 p,t=world(4);s=solution(p);cert=s['events'].pop()
 last=next(e for e in reversed(s['events']) if e['kind']=='letter');last['end']=round(last['end'],2)
 position=last['end']
 for delta in [1,-1,10,-10]:
  end=round(position+delta,2)
  s['events'].append(dict(sequence=len(s['events'])+1,kind='letter',index=last['index'],start=position,end=end,input_source='letter_key'))
  position=end
 cert['sequence']=len(s['events'])+1;s['events'].append(cert)
 assert grade(s,t,p)['passed']
 wrong=copy.deepcopy(s);wrong['events'][-2]['end']+=.1
 assert not grade(wrong,t,p)['passed']


def test_materialized_verifiers_execute_export_copy(tmp_path):
 import importlib.util
 for path in materialize_environment(E,tmp_path):
  task=json.loads((path/'task.json').read_text())
  public,truth=generate_incubator_candidate(task,'detached-verifier')
  exported={'public_state':public,'ground_truth':truth,'result':solution(public)}
  copied=[]
  def copy_from_env(source,destination):
   copied.append(source);Path(destination).write_text(json.dumps(exported))
  spec=importlib.util.spec_from_file_location('detached_punch_verifier',path/'verifier.py')
  module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  assert module.verify_task(env_info={'copy_from_env':copy_from_env})['passed']
  assert copied==['/tmp/task_result.json']
  exported['result']['challenge_id']='wrong'
  assert not module.verify_task(env_info={'copy_from_env':copy_from_env})['passed']


def test_seeded_initial_ink_separation():
 from weird_captcha_gym.shared_runtime.server.incubator_graders.punchcutters_bench import glyph_polygons
 for level in range(1,6):
  for seed in range(100):
   p,_=world(level,seed=f'independent-generation-{seed}');b=p['bench']
   polygons=glyph_polygons(b,b['master']);pos=b['initial_positions']
   for i in range(len(pos)-1):
    assert pos[i]+max(x for x,y in polygons[i]) < pos[i+1]+min(x for x,y in polygons[i+1])
