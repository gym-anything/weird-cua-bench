from copy import deepcopy
import json
from pathlib import Path
import pytest
from weird_captcha_gym.shared_scripts.incubator_generators.clockbeat_catacomb import generate,PROFILES
from weird_captcha_gym.shared_runtime.server.incubator_graders.clockbeat_catacomb import initial,act,advance,grade
from weird_captcha_gym.tools.incubator_solvers.clockbeat_catacomb import plan

def task(level,mode):return {'id':f'clockbeat-d{level}-{mode}','_control_condition':{'difficulty':level,'interaction':mode,'real_time':'live','difficulty_parameters':PROFILES[level]}}
def solved(p,g):
 b=p['board'];s=initial(b);events=[]
 for key in plan(b):
  ms=s['beat']*b['beat_ms']+100
  events.append(dict(sequence=len(events)+1,key=key,ms=ms,input_source='keyboard' if p['control_condition']['interaction']=='full' else 'direction_buttons',outcome=act(b,s,key)))
  if not s['won']:advance(b,s)
 return dict(mechanic_id=p['mechanic_id'],task_id=p['task_id'],challenge_id=p['challenge_id'],actions=events,final_ms=ms,final_state=s)

@pytest.mark.parametrize('level',range(1,6))
def test_profile_pair_and_replay(level):
 p,g=generate(task(level,'full'),'contract-seed');p2,g2=generate(task(level,'simplified'),'contract-seed')
 assert p['board']==p2['board']
 assert (p,g)==generate(task(level,'full'),'contract-seed')
 for public,truth in ((p,g),(p2,g2)):
  payload=solved(public,truth);assert grade(payload,truth,public)['passed']
  bad=deepcopy(payload);bad['actions'][0]['input_source']='forged';assert not grade(bad,truth,public)['passed']
  bad=deepcopy(payload);bad['challenge_id']='stale';assert not grade(bad,truth,public)['passed']
  bad=deepcopy(payload);bad['final_state']['hp']=999;assert not grade(bad,truth,public)['passed']
  bad=deepcopy(payload);bad['actions'][0]['ms']=float('nan');assert not grade(bad,truth,public)['passed']
  assert not grade({**payload,'actions':[]},truth,public)['passed']

def test_shield_strike_order_and_collision():
 b={'start':[1,1],'exit':[3,3],'health':3,'walls':[[0,1]],'enemies':[{'id':1,'pos':[2,1],'kind':'hopper','hp':2,'offset':1}]}
 s=initial(b);assert act(b,s,'RIGHT')=='shield';assert s['enemies'][0]['hp']==2
 advance(b,s);assert s['hp']==2
 assert act(b,s,'RIGHT')=='hit';assert s['enemies'][0]['hp']==1
 assert act(b,s,'LEFT')=='unavailable'
 advance(b,s);assert act(b,s,'LEFT')=='wall';assert s['player']==[1,1]

def test_offbeat_replay_and_invalid_time():
 p,g=generate(task(1,'full'),'negative');payload=solved(p,g)
 bad=deepcopy(payload);bad['actions'][0]['ms']=p['board']['open_ms'];assert not grade(bad,g,p)['passed']
 for end in (True,-1,float('inf'),None):assert not grade({**payload,'final_ms':end},g,p)['passed']

def test_baseline():
 root=Path('weird_captcha_gym/environments/clockbeat_catacomb_env');base=json.loads((root/'tasks/clockbeat_catacomb_seed_0001/task.json').read_text())
 p,g=generate(base,'baseline');q,h=generate(task(4,'full'),'baseline');assert p['board']==q['board']


def test_malformed_keys_and_exact_cutoff_are_rejected():
 p,g=generate(task(1,'full'),'negative');payload=solved(p,g)
 for key in ([],{},None,True,42):
  bad=deepcopy(payload);bad['actions'][0]['key']=key
  assert not grade(bad,g,p)['passed']
 assert not grade([],g,p)['passed']
 # A valid route reaching the stair exactly at the expired boundary must fail,
 # even if the replayed board otherwise agrees. The browser rejects this input.
 b=deepcopy(p['board']);b['max_beats']=1;b['enemies']=[];b['start']=[1,1];b['exit']=[2,1]
 b['walls']=[q for q in b['walls'] if q not in ([1,1],[2,1])]
 public={**p,'board':b};truth={**g,'board':deepcopy(b)}
 s=initial(b);advance(b,s);out=act(b,s,'RIGHT')
 late={**payload,'actions':[dict(sequence=1,key='RIGHT',ms=b['beat_ms'],input_source='keyboard',outcome=out)],'final_ms':b['beat_ms'],'final_state':s}
 assert s['won'] and not grade(late,truth,public)['passed']

