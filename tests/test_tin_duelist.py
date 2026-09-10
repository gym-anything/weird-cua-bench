import copy
import importlib.util
import json
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]/'weird_captcha_gym'
def load(path):
 s=importlib.util.spec_from_file_location(path.stem,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
G=load(ROOT/'shared_scripts/incubator_generators/tin_duelist.py')
R=load(ROOT/'shared_runtime/server/incubator_graders/tin_duelist.py')
S=load(ROOT/'tools/incubator_solvers/tin_duelist.py')
C=json.loads((ROOT/'environments/tin_duelist_env/controls.json').read_text())
T=json.loads((ROOT/'environments/tin_duelist_env/tasks/tin_duelist_seed_0001/task.json').read_text())
def generate(level,mode,seed='probe'):
 t=copy.deepcopy(T);t['_control_condition']=dict(difficulty=level,interaction=mode,real_time='live',difficulty_parameters=C['difficulty'][str(level)]['parameters']);return G.generate(t,seed)
def run(public):
 w=public['world'];s=R.initial(w);events=[];d=0;guard=False;mode=public['control_condition']['interaction']
 while s['status']=='active':
  if s['tick']%4==0:
   direction,g,attack=S.choose(s,w)
   for name,v,needed in [('direction',direction,d!=direction),('guard',g,guard!=g),(attack,None,attack is not None)]:
    if needed:
     events.append(dict(seq=len(events)+1,tick=s['tick'],action=name,value=v,input_source='keyboard' if mode=='full' else 'button'));R.command(s,name,v)
   d,guard=direction,g
  R.step(s,w)
 return dict(mechanic_id='tin_duelist',task_id=public['task_id'],challenge_id=public['challenge_id'],interaction_mode=mode,events=events,terminal_tick=s['tick'],final_state=s,completed=s['status']=='won')
@pytest.mark.parametrize('level',range(1,6))
@pytest.mark.parametrize('seed',['alpha','beta','gamma','delta','epsilon'])
def test_duel_matrix(level,seed):
 a,truth=generate(level,'full',seed);b,_=generate(level,'simplified',seed)
 assert a['world']==b['world'];assert G.generate({**T,'_control_condition':a['control_condition']},seed)==(a,truth)
 for mode in ['full','simplified']:
  public,truth=generate(level,mode,seed);out=run(public);assert R.grade(out,truth,public)['passed'],out['final_state']
  for key,val in [('challenge_id','stale'),('completed',False),('interaction_mode','full' if mode=='simplified' else 'simplified')]:
   bad=copy.deepcopy(out);bad[key]=val;assert not R.grade(bad,truth,public)['passed']
  bad=copy.deepcopy(out);bad['final_state']['enemy']['hp']=99;assert not R.grade(bad,truth,public)['passed']
  bad=copy.deepcopy(out);bad['events'][0]['input_source']='forged';assert not R.grade(bad,truth,public)['passed']
def test_baseline_and_collision_rules():
 base,_=G.generate(T,'baseline');a,_=generate(4,'full','baseline');assert base['world']==a['world']
 w=a['world'];s=R.initial(w);s['player']['x']=400;s['enemy']['x']=400+48+96
 R.attack(s['player'],'jab')
 for _ in range(12):
  s['enemy']['stun']=100;R.step(s,w)
 assert s['enemy']['hp']==100 # one unit beyond the drawn jab
 s=R.initial(w);s['player']['x']=400;s['enemy']['x']=400+48+90;R.attack(s['player'],'jab');s['player']['age']=7
 # enemy guard reacts to winding; contact is blocked
 R.step(s,w);assert s['contacts'][-1]['blocked'] and s['enemy']['hp']==100
 s=R.initial(w);s['player']['x']=400;s['enemy']['x']=500;s['guard']=True
 R.attack(s['enemy'],'hammer');s['enemy']['age']=21+w['parameters']['startup_bonus'];R.step(s,w)
 assert s['player']['hp']==72
