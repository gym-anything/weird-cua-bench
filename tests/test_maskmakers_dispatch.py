import copy
import importlib.util
import json
from pathlib import Path
import pytest
R=Path(__file__).resolve().parents[1]/'weird_captcha_gym';M='maskmakers_dispatch'
def load(path):
 s=importlib.util.spec_from_file_location(path.stem,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
G=load(R/'shared_scripts/incubator_generators'/f'{M}.py');V=load(R/'shared_runtime/server/incubator_graders'/f'{M}.py')
T=json.loads((R/'environments'/f'{M}_env/tasks/{M}_seed_0001/task.json').read_text())
def task(level,mode):
 t=copy.deepcopy(T);t['_control_condition']={'difficulty':level,'interaction':mode,'real_time':'live','difficulty_parameters':{'cover_count':level}};return t

def payload(p,g):
 colours=[-1]*24;active=set();events=[]
 for op in g['solution']:
  kind,i=op['kind'],op['index']
  if kind=='cover':active.symmetric_difference_update({i})
  else:
   protected={r for c in active for r in g['covers'][c]['regions']}
   colours=[old if r in protected else i for r,old in enumerate(colours)]
  events.append(dict(op,sequence=len(events)+1,input_source='tool_click' if p.get('control_condition',{}).get('interaction')=='simplified' else 'ornament_drag',colours=colours[:],active=sorted(active)))
 return {**{k:p[k] for k in ['mechanic_id','task_id','challenge_id']},'events':events,'colours':colours,'active':sorted(active)}

@pytest.mark.parametrize('level',range(1,6))
def test_generation_and_replay(level):
 targets=set()
 for seed in range(30):
  p,g=G.generate(task(level,'full'),str(seed));assert (p,g)==G.generate(task(level,'full'),str(seed))
  q,h=G.generate(task(level,'simplified'),str(seed))
  for key in ['regions','covers','palette','target']:assert p[key]==q[key]
  assert len(set(p['target']))==level+1
  targets.add(tuple(p['target']))
  for pub,truth in [(p,g),(q,h)]:
   result=payload(pub,truth);assert V.grade(result,truth,pub)['passed']
   wrong=copy.deepcopy(result);wrong['challenge_id']='stale';assert not V.grade(wrong,truth,pub)['passed']
   wrong=copy.deepcopy(result);wrong['events'][0]['input_source']='tool_click' if pub is p else 'ornament_drag';assert not V.grade(wrong,truth,pub)['passed']
   wrong=copy.deepcopy(result);wrong['colours'][0]=-1;assert not V.grade(wrong,truth,pub)['passed']
   wrong=copy.deepcopy(result);wrong['events'][0]['index']=True;assert not V.grade(wrong,truth,pub)['passed']
   assert not V.grade({**result,'events':[]},truth,pub)['passed']
 assert len(targets)>15

def test_baseline_world_and_protection():
 p,g=G.generate(T,'baseline');q,h=G.generate(task(2,'full'),'baseline')
 for k in ('regions','covers','palette','target'):assert p[k]==q[k]
 result=payload(p,g);assert V.grade(result,g,p)['passed']
 # A finished painted surface still under a cover must fail shipping.
 result['events']=result['events'][:-1];result['active']=result['events'][-1]['active'];assert not V.grade(result,g,p)['passed']
 # No cover bypass: direct all-over dips cannot construct a multicolour order.
 result=payload(p,g);result['events']=[e for e in result['events'] if e['kind']=='paint'];assert not V.grade(result,g,p)['passed']


def test_public_target_planner():
 solver=load(R/'tools/incubator_solvers'/f'{M}.py')
 for level in range(1,6):
  for seed in range(40):
   p,g=G.generate(task(level,'full'),f'planner-{seed}')
   assert 'solution' not in p
   alternate=copy.deepcopy(g);alternate['solution']=solver.plan(p)
   result=payload(p,alternate)
   assert V.grade(result,g,p)['passed']


@pytest.mark.parametrize('level', range(1, 6))
@pytest.mark.parametrize('mode', ['full', 'simplified'])
@pytest.mark.parametrize('length', [499, 500, 501, 899, 1001])
def test_long_history_recovery_preserves_exact_replay(level, mode, length):
 p,g=G.generate(task(level,mode),'long-recovery')
 result=payload(p,g)
 source='tool_click' if mode=='simplified' else 'ornament_drag'
 # Wrong paint and a worn cover are both cleared by reset. All old events
 # remain auditable, including at and beyond the former hidden ceiling.
 prefix=[
  dict(kind='paint',index=0,input_source=source,colours=[0]*24,active=[]),
  dict(kind='cover',index=0,input_source=source,colours=[0]*24,active=[0]),
 ]
 prefix.extend(dict(kind='reset',index=None,input_source='reset_button',colours=[-1]*24,active=[])
               for _ in range(length-len(result['events'])-len(prefix)))
 result['events']=prefix+result['events']
 for sequence,event in enumerate(result['events'],1):event['sequence']=sequence
 assert len(result['events'])==length
 assert V.grade(result,g,p)['passed']
 # Reset must not erase evidence of a forged earlier state or wrong surface.
 wrong=copy.deepcopy(result);wrong['events'][0]['colours'][0]=-1
 assert not V.grade(wrong,g,p)['passed']
 wrong=copy.deepcopy(result);wrong['events'][0]['input_source']='forged'
 assert not V.grade(wrong,g,p)['passed']
 wrong=copy.deepcopy(result);wrong['events'][-1]['colours'][0]=-1
 assert not V.grade(wrong,g,p)['passed']
