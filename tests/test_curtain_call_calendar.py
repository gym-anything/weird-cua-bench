import copy
import importlib.util
import json
from pathlib import Path
import pytest
B=Path(__file__).resolve().parents[1]/'weird_captcha_gym'
M='curtain_call_calendar'
def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
G=load(B/f'shared_scripts/incubator_generators/{M}.py','ccgen')
R=load(B/f'shared_runtime/server/incubator_graders/{M}.py','ccgrade')
S=load(B/f'tools/incubator_solvers/{M}.py','ccsolve')
C=json.loads((B/f'environments/{M}_env/controls.json').read_text())
def task(level,mode):return {'id':f'cc-{level}-{mode}','_control_condition':{'difficulty':level,'interaction':mode,'real_time':'live','difficulty_parameters':C['difficulty'][str(level)]['parameters']}}
def payload(p,solution):
 mode=p['control_condition']['interaction'];events=[]
 for r in p['world']['bookings']:
  if r['fixed']:continue
  events.append({'type':'open','id':r['id']})
  for f,v in enumerate(solution[r['id']]):
   if mode=='simplified':events.append({'type':'set','field':f,'value':v,'input_source':'direct_fields'})
   else:
    day=(v-1)//16 if f==1 and v>0 and v%16==0 else v//16
    slot=16 if f==1 and v>0 and v%16==0 else v%16
    for part,value in [('time',1),('day',day),('time',slot)]:events.append({'type':'pick','field':f,'part':part,'value':value,'input_source':'datetime_picker'})
  events.append({'type':'save','before':r['initial'],'after':solution[r['id']]})
 return {k:p[k] for k in ['mechanic_id','task_id','challenge_id']}|{'interaction_mode':mode,'events':events,'intervals':solution}
@pytest.mark.parametrize('level',range(1,6))
def test_feasible_deterministic_and_mode_equivalent(level):
 for seed in range(20):
  worlds=[]
  for mode in ['simplified','full']:
   t=task(level,mode);p,g=G.generate(t,str(seed));assert (p,g)==G.generate(t,str(seed));worlds.append(p['world'])
   assert not R.violations(g['world'],g['solution'])
   answer=S.plan(p['world']);assert not R.violations(p['world'],answer)
   q=payload(p,answer);assert R.grade(q,g,p)['passed']
   q['interaction_mode']='full' if mode=='simplified' else 'simplified';assert not R.grade(q,g,p)['passed']
  assert worlds[0]==worlds[1]
@pytest.mark.parametrize('mode',['full','simplified'])
def test_adversarial(mode):
 p,g=G.generate(task(4,mode),'adversarial');q=payload(p,S.plan(p['world']))
 for key,value in [('challenge_id','stale'),('task_id','stale'),('events',[]),('intervals',{})]:
  bad=copy.deepcopy(q);bad[key]=value;assert not R.grade(bad,g,p)['passed']
 bad=copy.deepcopy(q);bad['events'][1]['value']=True;assert not R.grade(bad,g,p)['passed']
 bad=copy.deepcopy(q);bad['events'][1]['input_source']='wrong';assert not R.grade(bad,g,p)['passed']
 for r in p['world']['bookings']:
  intervals=copy.deepcopy(q['intervals']);intervals[r['id']][1]+=1;assert R.violations(p['world'],intervals)
 fixed=next(r for r in p['world']['bookings'] if r['fixed']);bad=copy.deepcopy(q);bad['events'].insert(0,{'type':'open','id':fixed['id']});bad['events'].insert(1,{'type':'save','before':fixed['initial'],'after':fixed['initial']});assert not R.grade(bad,g,p)['passed']

@pytest.mark.parametrize('bad',[None,[],False,3,'bad'])
def test_non_mapping_envelope(bad):
 p,g=G.generate(task(3,'full'),'bad-envelope')
 assert not R.grade(bad,g,p)['passed']

@pytest.mark.parametrize('field,value',[(0,16),(1,0)])
def test_full_picker_rejects_ambiguous_closing_start_or_opening_end(field,value):
 p,g=G.generate(task(3,'full'),'day-boundary');q=payload(p,S.plan(p['world']))
 q['events'].insert(1,{'type':'pick','field':field,'part':'time','value':value,'input_source':'datetime_picker'})
 assert not R.grade(q,g,p)['passed']

def test_provenance_and_baseline_registration():
 p,g=G.generate({'id':'baseline'},'manifest')
 assert (B/p['asset_manifest']).is_file()
 assert p['world']==G.generate(task(3,'full'),'manifest')[0]['world']
