import copy
import json
import math
from pathlib import Path
import pytest
from weird_captcha_gym.shared_scripts.incubator_generators.fluke_census import generate,separated
from weird_captcha_gym.shared_runtime.server.incubator_graders.fluke_census import grade,pose,hit,BODY

ROOT=Path(__file__).resolve().parents[1]/'weird_captcha_gym'
BASE=json.loads((ROOT/'environments/fluke_census_env/tasks/fluke_census_seed_0001/task.json').read_text())
CONTROLS=json.loads((ROOT/'environments/fluke_census_env/controls.json').read_text())

def task(level,mode):
 t=copy.deepcopy(BASE)
 t['_control_condition']={'difficulty':level,'interaction':mode,'real_time':'live','difficulty_parameters':CONTROLS['difficulty'][str(level)]['parameters']}
 return t

def transcript(pub,tr,ids=None):
 mode=(pub['control_condition'] or {}).get('interaction','full');events=[]
 for epoch,animal in enumerate(tr['required_ids'] if ids is None else ids):
  item=next(x for x in pub['layouts'][epoch] if x['id']==animal)
  x,y,_,_=pose(item,0)
  events.extend([{'seq':len(events)+1,'type':'aim','t':0,'source':'pointer' if mode=='full' else 'coordinates','x':x,'y':y},{'seq':len(events)+2,'type':'photo','t':0,'source':'space' if mode=='full' else 'photo_button','animal_id':animal,'epoch':epoch}])
 events.append({'seq':len(events)+1,'type':'submit','source':'census_button','t':0})
 return {k:pub[k] for k in ('mechanic_id','task_id','challenge_id','control_condition')}|{'interaction_mode':mode,'events':events}

@pytest.mark.parametrize('level',range(1,6))
def test_world_invariants(level):
 for seed in range(30):
  p,t=generate(task(level,'full'),str(seed));q,u=generate(task(level,'simplified'),str(seed))
  assert t['world']==u['world']
  assert (ROOT/p['asset_manifest']).is_file()
  assert generate(task(level,'full'),str(seed))==(p,t)
  assert grade(transcript(p,t),t,p)['passed']
  assert grade(transcript(q,u),u,q)['passed']
  assert not grade(transcript(p,t),u,q)['passed']
  assert len({(a['species'],tuple(a['notches'])) for a in p['animals']})==len(p['animals'])
  for layout in p['layouts']:
   assert separated(layout)
   for a in layout:
    for ms in (0,2500,10000,25000):
     x,y,_,_=pose(a,ms)
     assert hit(t['world'],p['layouts'].index(layout),ms,x,y)==a['id']
  for a,b in zip(p['layouts'],p['layouts'][1:]):assert all(x['id']!=y['id'] for x,y in zip(a,b))

def test_baseline_preserves_world():
 p,t=generate(BASE,'baseline');q,u=generate(task(4,'full'),'baseline');assert t['world']==u['world']

@pytest.mark.parametrize('mode',['simplified','full'])
def test_replay_rejects_bad_claims(mode):
 p,t=generate(task(4,mode),'negative');result=transcript(p,t);assert grade(result,t,p)['passed']
 for field,value in [('challenge_id','stale'),('task_id','other'),('events',[]),('interaction_mode','other')]:
  bad=copy.deepcopy(result);bad[field]=value;assert not grade(bad,t,p)['passed']
 for key,value in [('animal_id','forged'),('epoch',2),('t',float('nan')),('source','button')]:
  bad=copy.deepcopy(result);bad['events'][1][key]=value;assert not grade(bad,t,p)['passed']
 for coords in [(-1,0),(1000,0),(float('inf'),0),(True,50),(0,0)]:
  bad=copy.deepcopy(result);bad['events'][0].update(x=coords[0],y=coords[1]);assert not grade(bad,t,p)['passed']
 bad=transcript(p,t,[t['required_ids'][0]]*2);bad['events'].pop();decision=grade(bad,t,p);assert not decision['passed'] and decision['duplicates']==1
 decoy=next(a['id'] for a in p['animals'] if a['id'] not in t['required_ids']);bad=transcript(p,t,[decoy]);bad['events'].pop();assert grade(bad,t,p)['off_list']==1
 assert not grade(transcript(p,t,t['required_ids'][:-1]),t,p)['passed']
 bad=copy.deepcopy(p);bad['layouts'][0][0]['x']+=20;assert not grade(result,t,bad)['passed']


def test_individual_notch_changes_the_actual_shutter_region():
 # First upper notch: its tip lies at y=-22.1875. The same coordinate is
 # solid tail for a shallow notch and water for a deeper individual notch.
 animal={'id':'a','species':0,'notches':[10]*8}
 item={'id':'a','x':100,'y':100,'angle':0,'scale':1,'phase':0,'omega':0}
 world={'animals':[animal],'layouts':[[item]]}
 assert hit(world,0,0,56,89.8125)=='a'
 animal['notches'][0]=30
 assert hit(world,0,0,56,89.8125) is None
 assert hit(world,0,0,100,112)=='a'
