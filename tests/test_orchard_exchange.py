"""Economy invariants and seeded oracle feasibility for Orchard Exchange."""
import copy
import importlib.util
from pathlib import Path
import pytest
R=Path(__file__).resolve().parents[1]/'weird_captcha_gym'
def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
gen=load(R/'shared_scripts/incubator_generators/orchard_exchange.py','oxgen')
grade=load(R/'shared_runtime/server/incubator_graders/orchard_exchange.py','oxgrade')
solver=load(R/'tools/incubator_solvers/orchard_exchange.py','oxsolver')

def instance(level,seed,mode='full'):
 return gen.generate({'id':f'orchard-{level}-{mode}','_control_condition':{'difficulty':level,'interaction':mode,'difficulty_parameters':gen.PROFILES[level]}},str(seed))

def oracle(p,g):
 w=g['world'];s=grade.initial(w);events=[];mode=g['control_condition']['interaction']
 def action(k,v=None):
  source=('keyboard' if mode=='full' else 'direction_buttons') if k in grade.DELTAS else 'offer_buttons'
  events.append(dict(tick=s['tick'],kind=k,value=v,source=source));grade.act(w,s,k,v)
 def wait(n):grade.advance(w,s,s['tick']+n)
 def eat():
  if s['hunger']<100:
   if s['inventory'][0]:action('eat',0)
   elif s['inventory'][1]:action('eat',1)
 def move(target):
  for k in solver.route(w,s['pos'],target):eat();action(k);wait(2)
 def gather(n):
  tree=min([t['pos'] for t in w['trees'] if t['fruit']==0],key=lambda x:len(solver.route(w,s['pos'],x)))
  move(tree)
  for _ in range(150):
   eat()
   if s['inventory'][0]>=min(n,w['capacity']-s['inventory'][1]):return
   wait(5)
  raise AssertionError(s)
 gather(8)
 for _ in range(150):
  eat();assert not s['failed'],s
  if s['inventory'][1]>=w['demand'][1]:
   if s['inventory'][0]<w['demand'][0]:gather(w['demand'][0]);continue
   move(w['stall']);eat()
   if any(x<y for x,y in zip(s['inventory'],w['demand'])):continue
   action('deliver');break
  b=s['bots'][0];ask=grade.terms(w,b)[0]
  if s['inventory'][0]<max(ask,2):gather(8);continue
  move(b['pos']);ask=grade.terms(w,b)[0]
  if s['inventory'][0]<ask:continue
  for k,i,target in [('give',0,ask),('take',1,b['give'])]:
   while s['offer'][i]!=target:action(k,1 if target>s['offer'][i] else -1)
  before=len(s['trades']);action('post')
  for _ in range(40):
   wait(5);eat()
   if len(s['trades'])>before or s['offer']!=grade.terms(w,b) or s['inventory'][0]<s['offer'][0]:break
  action('cancel')
 assert s['delivered'],s
 return {**{k:g[k] for k in ('mechanic_id','task_id','challenge_id')},'events':events,'end_tick':s['tick'],'final':s}

@pytest.mark.parametrize('level',range(1,6))
def test_seeded_feasibility_and_mode_binding(level):
 for seed in range(20):
  p,g=instance(level,seed);p2,g2=instance(level,seed,'simplified')
  assert p['world']==p2['world']
  assert instance(level,seed)==(p,g)
  payload=oracle(p,g);assert grade.grade(payload,g,p)['passed']
  assert not grade.grade({**payload,'challenge_id':'stale'},g,p)['passed']
  for e in payload['events']:
   if e['kind'] in grade.DELTAS:e['source']='direction_buttons';break
  assert not grade.grade(payload,g,p)['passed']

def test_trade_is_reciprocal_spatial_and_stock_backed():
 p,g=instance(3,31);w=g['world'];s=grade.initial(w);b=s['bots'][0]
 s['inventory']=[5,0];s['offer']=grade.terms(w,b);s['posted']=True
 grade.step(w,s);assert not s['trades'] # Out of radius.
 s['pos']=b['pos'][:];s['offer']=[4,4];grade.step(w,s);assert not s['trades']
 s['offer']=grade.terms(w,b);b['inventory'][1]=0;b['progress']=0
 grade.step(w,s);assert not s['trades']
 b['inventory'][1]=2;before=[s['inventory'][i]+b['inventory'][i] for i in (0,1)]
 grade.step(w,s);assert len(s['trades'])==1 and not s['posted']
 assert before==[s['inventory'][i]+b['inventory'][i] for i in (0,1)]

def test_posted_offer_can_lose_stock_before_settlement():
 p,g=instance(3,7);w=g['world'];s=grade.initial(w);b=s['bots'][0]
 s['pos']=b['pos'][:];s['inventory']=[4,0];b['inventory']=[0,1];b['hunger']=1;b['progress']=0
 s['offer']=grade.terms(w,b);s['posted']=True;grade.step(w,s)
 assert b['inventory'][1]==0 and not s['trades'] and s['posted']

def test_food_harvest_capacity_terminal_and_forgery():
 p,g=instance(5,4);w=g['world'];s=grade.initial(w)
 s['pos']=w['trees'][0]['pos'][:];grade.advance(w,s,w['apple_ticks']);assert s['inventory']==[2,0]
 before=s['hunger'];grade.act(w,s,'eat',0);assert s['inventory']==[1,0] and s['hunger']>before
 s['inventory']=[w['capacity'],0];grade.advance(w,s,s['tick']+w['apple_ticks']);assert sum(s['inventory'])==w['capacity']
 s['hunger']=1;grade.step(w,s);assert s['failed']
 payload=oracle(p,g);payload['final']['inventory'][1]+=1;assert not grade.grade(payload,g,p)['passed']
 for bad in (None,[],[{}],[{'tick':True,'kind':'deliver'}]):
  assert not grade.grade({**payload,'events':bad},g,p)['passed']

def test_assigned_baseline_world_is_preserved():
 base,_=gen.generate({'id':'base'},'baseline-constant')
 controlled,_=instance(3,'baseline-constant')
 assert base['world']==controlled['world']
 assert base['generator']['variant_count']==controlled['generator']['variant_count']
