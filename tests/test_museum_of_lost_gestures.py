from __future__ import annotations
import copy
import importlib.util
import json
from pathlib import Path
import pytest
B=Path(__file__).resolve().parents[1]/'weird_captcha_gym'
M='museum_of_lost_gestures'
def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
gen=load(B/'shared_scripts/incubator_generators'/f'{M}.py','museum_generator')
grader=load(B/'shared_runtime/server/incubator_graders'/f'{M}.py','museum_grader')
task=json.loads((B/'environments'/f'{M}_env'/'tasks'/f'{M}_seed_0001'/'task.json').read_text())
def generated(seed='test',level=1,mode='full'):
 t=copy.deepcopy(task);t['_control_condition']={'difficulty':level,'interaction':mode,'real_time':'live','difficulty_parameters':gen.PROFILES[level]};return gen.generate(t,seed)
def transcript(p,t):
 mode=t['control_condition']['interaction'];events=[];time=0;w=t['world'];point=[w['plinth'][0]+60,w['plinth'][1]+40]
 def e(kind,**kw):
  nonlocal time
  time+=700
  events.append(dict(seq=len(events)+1,t=time,type=kind,source=mode,**kw))
 def gesture(g):
  nonlocal time
  if mode=='simplified':
   e('proxy',gesture=g)
   if g in ('hold','dwell'):time+=5000;e('tick')
   return
  if g in ('double','right','drag','hold','modifier'):
   if g=='modifier':e('key_down',key='Shift')
   e('down',point=point,button=2 if g=='right' else 0)
   if g=='hold':time+=2200;e('tick')
   if g=='drag':e('move',point=[point[0]+150,point[1]])
   e('up',point=[point[0]+150,point[1]] if g=='drag' else point,button=2 if g=='right' else 0)
   if g=='double':time-=600;e('down',point=point,button=0);time-=600;e('up',point=point,button=0)
   if g=='modifier':e('key_up',key='Shift')
  elif g=='dwell':e('enter',point=point);time+=5200;e('tick')
  elif g=='return':e('enter',point=point);e('leave');e('enter',point=point)
  elif g=='scroll':e('scroll',value=0);e('scroll',value=w['scroll_max'])
  elif g=='resize':e('resize',value=380);e('resize',value=580)
  elif g=='chord':e('key_down',key='a');e('key_down',key='s');e('key_up',key='s');e('key_up',key='a')
 cases={c['id']:c for c in w['cases']}
 for id in t['solution_order']:
  for g in cases[id]['recipe']:gesture(g)
 return {k:t[k] for k in ('mechanic_id','task_id','challenge_id','control_condition')}|{'events':events,'opened':sorted(cases)}

@pytest.mark.parametrize('level',range(1,6))
def test_seeded_world_equivalence_reachability(level):
 worlds=set()
 for seed in range(30):
  a,ta=generated(str(seed),level,'full');b,tb=generated(str(seed),level,'simplified')
  assert a['world']==b['world']
  assert gen.generate(task,str(seed))[0]['world']==generated(str(seed),1)[0]['world']
  assert generated(str(seed),level)[0]==a
  worlds.add(json.dumps(a['world'],sort_keys=True))
  for p,t in [(a,ta),(b,tb)]:
   result=grader.grade(transcript(p,t),t,p)
   assert result['passed'],result
 assert len(worlds)==30

@pytest.mark.parametrize('mode',['full','simplified'])
def test_reject_forgery_stale_surface_and_malformed(mode):
 p,t=generated(mode=mode);valid=transcript(p,t)
 for field,value in [('opened',[]),('challenge_id','stale'),('task_id','foreign'),('control_condition',None),('events',[])]:
  bad=copy.deepcopy(valid);bad[field]=value;assert not grader.grade(bad,t,p)['passed']
 for change in [dict(source='simplified' if mode=='full' else 'full'),dict(t=float('nan')),dict(type='completed'),dict(seq=0)]:
  bad=copy.deepcopy(valid);bad['events'][0].update(change);assert not grader.grade(bad,t,p)['passed']


def test_hold_drag_dwell_and_chord_boundaries():
 p,t=generated();w=t['world'];r=grader.Replay(w,'full');x,y,_,_=w['plinth'];point=[x+30,y+30]
 r.event({'type':'enter','t':0,'point':point})
 r.event({'type':'down','t':0,'point':point,'button':0})
 r.event({'type':'tick','t':1999});assert 'hold' not in r.recognized
 r.event({'type':'move','t':2000,'point':[x+50,y+30]})
 r.event({'type':'tick','t':3000});assert 'hold' not in r.recognized
 r.event({'type':'up','t':3100,'point':point,'button':0})
 r.event({'type':'down','t':3200,'point':point,'button':0})
 r.event({'type':'tick','t':5200});assert r.recognized[-1]=='hold'
 r.event({'type':'up','t':5300,'point':point,'button':0})
 r.event({'type':'tick','t':10299});assert 'dwell' not in r.recognized
 r.event({'type':'tick','t':10300});assert r.recognized[-1]=='dwell'
 r.event({'type':'key_down','t':10400,'key':'a'});r.event({'type':'key_up','t':10500,'key':'a'})
 r.event({'type':'key_down','t':10600,'key':'s'});assert 'chord' not in r.recognized


def test_composition_cannot_be_replaced_with_repeated_final_gesture():
 p,t=generated(level=5,mode='simplified');r=grader.Replay(t['world'],'simplified')
 cases={c['id']:c for c in t['world']['cases']}
 for id in t['solution_order']:r.emit(cases[id]['gesture'])
 assert len(r.opened)<10
 assert any(len(c['recipe'])==5 for c in cases.values())

@pytest.mark.parametrize('value',[None,[],42,'invalid'])
def test_non_object_submission_rejected(value):
 p,t=generated()
 assert grader.grade(value,t,p)=={'graded':True,'passed':False,'score':0,'feedback':'invalid submission envelope'}

def test_cancelled_press_does_not_complete_and_can_be_retried():
 p,t=generated();w=t['world'];r=grader.Replay(w,'full');x,y,_,_=w['plinth'];point=[x+30,y+30]
 r.event({'type':'down','t':0,'point':point,'button':0})
 r.event({'type':'cancel','t':1000})
 r.event({'type':'tick','t':2500})
 assert 'hold' not in r.recognized and r.down is None
 r.event({'type':'down','t':2600,'point':point,'button':0})
 r.event({'type':'tick','t':4600})
 r.event({'type':'up','t':4700,'point':point,'button':0})
 assert r.recognized==['hold']

@pytest.mark.parametrize('source,target',[('full','simplified'),('simplified','full')])
def test_cross_mode_transcript_rejected_even_after_identity_rebinding(source,target):
 p,t=generated(seed='paired',level=5,mode=source)
 other,truth=generated(seed='paired',level=5,mode=target)
 assert p['world']==other['world']
 payload=transcript(p,t)
 for key in ('mechanic_id','task_id','challenge_id','control_condition'):payload[key]=truth[key]
 for event in payload['events']:event['source']=target
 assert not grader.grade(payload,truth,other)['passed']

@pytest.mark.parametrize('level',range(1,6))
def test_fixed_vocabulary_sweeps_only_solve_original_profile(level):
 for seed in range(100):
  p,t=generated(str(seed),level,'simplified');r=grader.Replay(t['world'],'simplified')
  for _ in range(4):
   for gesture in gen.GESTURES:r.emit(gesture)
  assert (len(r.opened)==10)==(level==1)

@pytest.mark.parametrize('level',range(2,6))
def test_longest_recipe_requires_each_prefix_in_order(level):
 p,t=generated('prefix-boundary',level,'simplified');w=t['world']
 case=next(c for c in w['cases'] if len(c['recipe'])==level)
 # Reach the prerequisite state, then isolate recognition of this exhibit.
 for recipe in [case['recipe'][1:],case['recipe']]:
  r=grader.Replay(w,'simplified');r.opened.update(case['requires'])
  for gesture in recipe:r.emit(gesture)
  assert (case['id'] in r.opened)==(recipe==case['recipe'])
