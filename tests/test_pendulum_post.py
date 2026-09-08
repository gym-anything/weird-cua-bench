import copy
import importlib.util
import json
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]/'weird_captcha_gym'
def load(path,name):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
G=load(ROOT/'shared_scripts/setup_task.py','pendulum_setup');P=load(ROOT/'shared_runtime/server/incubator_graders/pendulum_post.py','pendulum_grade')
def make(level,mode,seed):
 from weird_captcha_gym.tools.materialize_controlled_tasks import controlled_task
 env=ROOT/'environments/pendulum_post_env'
 base=json.loads((env/'tasks/pendulum_post_seed_0001/task.json').read_text())
 controls=json.loads((env/'controls.json').read_text())
 t=controlled_task(base,mechanic_id='pendulum_post',level=level,interaction=mode,
                   profile=controls['difficulty'][str(level)],
                   task_dir_name=f'pendulum_post_d{level}_{mode}_seed_0001')
 return G.generate_task_state(t,seed)
def solution(pub,truth):
 w=truth['world'];s=P.initial(w);events=[];mode=truth['control_condition']['interaction']
 for e in truth['reference_schedule']:
  while s['tick']<e['tick']:P.advance(s,w)
  i=e['rope'];r=w['ropes'][i];pts=P.rope_points(r,s);a,b=pts[:2];dx,dy=b[0]-a[0],b[1]-a[1];d=(dx*dx+dy*dy)**.5;x,y=a[0]+.4*dx,a[1]+.4*dy
  events.append(dict(e,input_source='rope_swipe' if mode=='full' else 'rope_button',a=[x-dy/d*20,y+dx/d*20],b=[x+dy/d*20,y-dx/d*20]));s['active'][i]=False
 while s['status']=='active':P.advance(s,w)
 return dict(mechanic_id='pendulum_post',task_id=truth['task_id'],challenge_id=truth['challenge_id'],interaction_mode=mode,events=events,terminal_tick=s['tick'],completed=True)
@pytest.mark.parametrize('level',range(1,6))
def test_world_pair_deterministic_and_reachable(level):
 for seed in map(str,range(12)):
  p,t=make(level,'full',seed);q,u=make(level,'simplified',seed)
  assert p['world']==q['world']
  assert (p,t)==make(level,'full',seed)
  for pub,truth in [(p,t),(q,u)]:
   result=solution(pub,truth);assert P.grade(result,truth,pub)['passed']
   result['interaction_mode']='simplified' if result['interaction_mode']=='full' else 'full';assert not P.grade(result,truth,pub)['passed']

def test_negative_replay_and_swipe_geometry():
 p,t=make(4,'full','adversarial');payload=solution(p,t)
 for change in [dict(events=[]),dict(completed=False),dict(challenge_id='stale'),dict(task_id='other'),dict(terminal_tick=0)]:
  bad=dict(payload,**change);assert not P.grade(bad,t,p)['passed']
 bad=copy.deepcopy(payload);bad['events'][1]['input_source']='rope_button';assert not P.grade(bad,t,p)['passed']
 bad=copy.deepcopy(payload);bad['events'][0].update(a=[0,0],b=[0,40]);assert not P.grade(bad,t,p)['passed']
 bad=copy.deepcopy(payload);bad['events'][0]['tick']=True;assert not P.grade(bad,t,p)['passed']
 bad=copy.deepcopy(p);bad['world']['basket']['width']=900;assert not P.grade(payload,t,bad)['passed']

def test_cut_preserves_momentum_and_ropes_bound_distance():
 p,t=make(4,'full','physics');w=t['world'];s=P.initial(w);s['active'][t['reference_schedule'][0]['rope']]=False
 for _ in range(350):
  P.advance(s,w)
  for i,r in enumerate(w['ropes']):
   if s['active'][i]:assert ((s['x']-r['x'])**2+(s['y']-r['y'])**2)**.5<=r['length']+.001
 velocity=[s['vx'],s['vy']];s['active'][t['reference_schedule'][1]['rope']]=False;assert [s['vx'],s['vy']]==velocity
 assert abs(s['vx'])>1

def test_no_pre_run_release_shortcut():
 for level in range(1,6):
  for seed in map(str,range(12)):
   p,t=make(level,'full',seed);s=P.initial(t['world']);s['active']=[False]*len(s['active'])
   while s['status']=='active':P.advance(s,t['world'])
   assert s['status']!='delivered'


def test_every_certified_cut_removes_a_loaded_rope():
 for level in range(1,6):
  for seed in map(str,range(6)):
   _,t=make(level,'full',seed);w=t['world'];s=P.initial(w)
   for e in t['reference_schedule']:
    while s['tick']<e['tick']:P.advance(s,w)
    r=w['ropes'][e['rope']]
    assert abs(((s['x']-r['x'])**2+(s['y']-r['y'])**2)**.5-r['length'])<.2
    s['active'][e['rope']]=False

def test_baseline_world_preserved_and_seeds_vary():
 task=json.loads((ROOT/'environments/pendulum_post_env/tasks/pendulum_post_seed_0001/task.json').read_text())
 worlds=[]
 for seed in ('baseline-a','baseline-b','baseline-c'):
  p,t=G.generate_task_state(task,seed);q,u=make(4,'full',seed)
  assert p['asset_manifest']==q['asset_manifest']==task['metadata']['asset_manifest']
  assert (ROOT/p['asset_manifest']).is_file()
  assert p['world']==q['world'] and t['reference_schedule']==u['reference_schedule']
  worlds.append(json.dumps(p['world'],sort_keys=True))
 assert len(set(worlds))==3


def test_malformed_contracts_and_events_fail_without_exception():
 p,t=make(4,'full','malformed');result=solution(p,t)
 for bad in (None, [], 'parcel', 1):
  assert not P.grade(bad,t,p)['passed']
  assert not P.grade(result,bad,p)['passed']
  assert not P.grade(result,t,bad)['passed']
  altered=copy.deepcopy(result);altered['events'][0]=bad
  assert not P.grade(altered,t,p)['passed']
 altered=copy.deepcopy(result);wrong_truth=copy.deepcopy(t);wrong_public=copy.deepcopy(p)
 for value in (altered,wrong_truth,wrong_public):value['mechanic_id']='unrelated'
 assert not P.grade(altered,wrong_truth,wrong_public)['passed']


def test_split_lists_both_schedules_and_materialization_is_reproducible(tmp_path):
 from weird_captcha_gym.tools.materialize_controlled_tasks import materialize_environment
 split=json.loads((ROOT/'splits/pendulum_post_split.json').read_text())
 written=materialize_environment(ROOT/'environments/pendulum_post_env',tmp_path)
 assert len(written)==10
 assert len(split['variations_tasks'])==20
 assert set(split['variations_tasks'])=={p.name+suffix for p in written for suffix in ('','_tpaused')}
 assert all(json.loads((p/'task.json').read_text())['metadata']['control_condition']['real_time']=='live' for p in written)
 assert json.loads((ROOT/'real_time.json').read_text())['environments']['pendulum_post']['observation_window_ms']==240
