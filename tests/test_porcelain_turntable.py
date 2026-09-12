"""Physical invariants and independent replay for the porcelain environment."""
import copy,importlib.util,json,math,shutil
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]/'weird_captcha_gym';E=ROOT/'environments/porcelain_turntable_env'
def load(p,n):
 s=importlib.util.spec_from_file_location(n,ROOT/p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
G=load('shared_scripts/incubator_generators/porcelain_turntable.py','pt_g');R=load('shared_runtime/server/incubator_graders/porcelain_turntable.py','pt_r');S=load('tools/incubator_solvers/porcelain_turntable.py','pt_s')
BASE=json.loads((E/'tasks/porcelain_turntable_seed_0001/task.json').read_text());C=json.loads((E/'controls.json').read_text())
def task(level,mode):
 t=copy.deepcopy(BASE);t['metadata']['control_condition']={'difficulty':level,'interaction':mode,'real_time':'live','difficulty_parameters':C['difficulty'][str(level)]['parameters']};return t

def payload(pub):
 plan=S.plan(pub['initial'],pub['physics']);s=pub['initial'];u=[0,0];tick=0;events=[{'seq':1,'tick':0,'type':'start'}]
 for a in plan['path']:
  if a['u']!=u:
   u=a['u'];events.append({'seq':len(events)+1,'tick':tick,'type':'torque','value':u,'input_source':'held_keys' if (pub.get('control_condition') or {}).get('interaction','full')=='full' else 'latched_buttons'})
  for _ in range(a['ticks']):s,_=R.step(s,u,pub['physics']);tick+=1
 events.append({'seq':len(events)+1,'type':'finish','tick':tick,'state':s})
 return {**{k:pub[k] for k in ['task_id','mechanic_id','challenge_id']},'control_condition':pub.get('control_condition'),'events':events}

@pytest.mark.parametrize('level',range(1,6))
@pytest.mark.parametrize('mode',['full','simplified'])
def test_all_profiles_reachable_replay_and_surface(level,mode):
 pub,truth=G.generate(task(level,mode),'porcelain-test-a')
 assert (pub,truth)==G.generate(task(level,mode),'porcelain-test-a')
 other,_=G.generate(task(level,'simplified' if mode=='full' else 'full'),'porcelain-test-a')
 assert pub['physics']==other['physics'] and pub['initial']==other['initial']
 out=payload(pub);assert R.grade(out,truth,pub)['passed']
 for mutation in ['stale','surface','angle','nan','negative_time','teleport','empty','held','condition']:
  bad=copy.deepcopy(out)
  if mutation=='stale':bad['challenge_id']='old'
  if mutation=='surface':bad['events'][1]['input_source']='latched_buttons' if mode=='full' else 'held_keys'
  if mutation=='angle':bad['events'][-1]['state'][2]=pub['physics']['target']
  if mutation=='nan':bad['events'][-1]['state'][0]=math.nan
  if mutation=='negative_time':bad['events'][-1]['tick']=-1
  if mutation=='teleport':bad['events'][1]['type']='set_spinner_angle'
  if mutation=='empty':bad['events']=[]
  if mutation=='held':bad['events'][-2]['value']=[1,0]
  if mutation=='condition':bad['control_condition']['interaction']='invalid'
  assert not R.grade(bad,truth,pub)['passed'],mutation

def test_generation_baseline_and_collision_free_diversity():
 worlds=[]
 for seed in range(60):
  pub,_=G.generate(BASE,seed);controlled,_=G.generate(task(4,'full'),seed)
  assert pub['physics']==controlled['physics'] and pub['initial']==controlled['initial']
  p=pub['physics'];s=pub['initial'];base,elbow,tip,petals=R.geometry(s,p)
  assert R.error(s,p)>p['tolerance']
  for a,b in [(base,elbow),(elbow,tip)]:
   for end in petals:
    v,z,_=R.closest(a,b,[0,0],end);assert math.dist(v,z)>p['finger_radius']+p['petal_radius']
  worlds.append((tuple(s),p['target']))
 assert len(set(worlds))==60

def test_no_contact_means_no_spinner_motor_and_reflection_symmetry():
 pub,_=G.generate(BASE,10);p=pub['physics'];s=pub['initial'];original=s[2]
 for _ in range(40):s,c=R.step(s,[-1,0],p);assert c==0
 assert s[2]==original and s[5]==0
 a=pub['initial'];b=[-x for x in a]
 for _ in range(700):
  a,_=R.step(a,[1,1],p);b,_=R.step(b,[-1,-1],p)
  assert all(abs(x+y)<1e-8 for x,y in zip(a,b))
 assert abs(a[2]-original)>.1

def test_capsule_contact_from_both_sides():
 for sign in [-1,1]:
  pub,_=G.generate(BASE,10);p=pub['physics'];s=[-.6*sign,0,0,0,0,0];count=0
  for _ in range(150):s,c=R.step(s,[sign,0],p);count+=c
  assert count>0 and abs(s[5])>.01

def test_exported_verifier(tmp_path):
 V=load('environments/porcelain_turntable_env/tasks/porcelain_turntable_seed_0001/verifier.py','pt_v')
 pub,truth=G.generate(task(4,'simplified'),'pt-export');out=payload(pub);path=tmp_path/'result.json'
 def copy_from_env(source,destination):assert source=='/tmp/task_result.json';shutil.copyfile(path,destination)
 export={'public_state':pub,'ground_truth':truth,'result':out};path.write_text(json.dumps(export));assert V.verify_task(env_info={'copy_from_env':copy_from_env})['score']==100
 out['events'][1]['input_source']='held_keys';path.write_text(json.dumps(export));assert V.verify_task(env_info={'copy_from_env':copy_from_env})['score']==0
