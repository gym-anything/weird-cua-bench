import copy
import importlib.util
import json
from pathlib import Path
import pytest
B=Path(__file__).resolve().parents[1]/'weird_captcha_gym'
E=B/'environments/switchline_heist_env'
def load(p,n):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
gen=load(B/'shared_scripts/incubator_generators/switchline_heist.py','shgen')
gr=load(B/'shared_runtime/server/incubator_graders/switchline_heist.py','shgrader')
def task(level=3,mode='full'):
 from weird_captcha_gym.tools.materialize_controlled_tasks import controlled_task
 base=json.loads((E/'tasks/switchline_heist_seed_0001/task.json').read_text())
 controls=json.loads((E/'controls.json').read_text())
 return controlled_task(base,mechanic_id='switchline_heist',level=level,interaction=mode,
                        profile=controls['difficulty'][str(level)],
                        task_dir_name=f'switchline_heist_d{level}_{mode}_seed_0001')
@pytest.mark.parametrize('level',range(1,6))
def test_generation_and_mode_worlds(level):
 worlds=[]
 for seed in range(30):
  a,t=gen.generate(task(level,'full'),str(seed));b,_=gen.generate(task(level,'simplified'),str(seed))
  assert a['world']==b['world'];assert gen.generate(task(level),str(seed))==(a,t)
  assert 'seed' not in a and a['asset_manifest'].endswith('switchline_heist_v0.json')
  w=a['world'];worlds.append(json.dumps(w,sort_keys=True))
  assert all(y['x']-x['x']>=180 for x,y in zip(w['gates'],w['gates'][1:]))
 assert len(set(worlds))>=25

def test_baseline():
 base=json.loads((E/'tasks/switchline_heist_seed_0001/task.json').read_text())
 assert gen.generate(base,'base')[0]['world']==gen.generate(task(),'base')[0]['world']

def test_physical_traversal_circuits_and_attendant():
 public,truth=gen.generate(task(4),'physics');w=public['world'];s=gr.initial(w)
 with pytest.raises(ValueError):gr.action(w,s,dict(type='use',source='s2L'))
 s['overlay']=True
 with pytest.raises(ValueError):gr.action(w,s,dict(type='wire',source='s2L',target='gate2'))
 with pytest.raises(ValueError):gr.action(w,s,dict(type='wire',source='service',target='lamp'))
 g=w['gates'][0];s['x']=g['x']-20;s['move']=1;s['overlay']=False
 for _ in range(10):gr.tick(w,s)
 assert s['x']==g['x']-20
 gr.output(w,s,g['id']);gr.tick(w,s);assert s['x']>g['x']-20
 s=gr.initial(w);gr.output(w,s,'gate0');gr.output(w,s,'gate1');assert s['gates']==dict(gate0=False,gate1=True,gate2=False)
 gr.output(w,s,'lamp');s['gx']=948
 for _ in range(w['parameters']['repair_ticks']):gr.tick(w,s)
 assert s['service_count']==1 and s['light'] and s['gates']['gate2']

def test_hidden_cover_alarm_and_capture():
 p,t=gen.generate(task(5),'guard');w=p['world'];s=gr.initial(w);s.update(x=884,gx=900,gd=-1)
 gr.detect(w,s);assert s['caught']
 s=gr.initial(w);s.update(x=884,gx=900,gd=-1,light=False)
 gr.action(w,s,dict(type='hide'));gr.action(w,s,dict(type='pickup'))
 assert s['item'] and s['light'] and s['hidden'] and not s['caught']

def test_reject_false_outcomes_malformed_and_stale():
 p,t=gen.generate(task(),'negative')
 payload=dict(mechanic_id='switchline_heist',task_id=t['task_id'],challenge_id=t['challenge_id'],completed=True,
 events=[dict(seq=1,type='extract',tick=0,input_source='direct')])
 assert not gr.grade(payload,t,p)['passed']
 for mutation in [dict(challenge_id='stale'),dict(events=None),dict(events=[None]),dict(events=[dict(seq=1,type='extract',tick=float('nan'),input_source='direct')])]:
  assert not gr.grade({**payload,**mutation},t,p)['passed']

def test_recorded_browser_exports_if_present():
 paths=list((E/'evidence_docs').glob('*/export.json'))
 for path in paths:
  x=json.loads(path.read_text());assert gr.grade(x['result'],x['ground_truth'],x['public_state'])['passed']
  bad=copy.deepcopy(x['result']);bad['events'][0]['input_source']='wrong'
  assert not gr.grade(bad,x['ground_truth'],x['public_state'])['passed']
  bad=copy.deepcopy(x['result']);bad['events']=[e for e in bad['events'] if e['type']!='pickup']
  for i,e in enumerate(bad['events']):e['seq']=i+1
  assert not gr.grade(bad,x['ground_truth'],x['public_state'])['passed']

@pytest.mark.parametrize('level',range(1,6))
def test_reachable_physical_return_across_seeds(level):
 for seed in range(20):
  p,t=gen.generate(task(level),f'reach-{seed}');w=p['world'];s=gr.initial(w);events=[]
  def act(kind,**kw):
   e=dict(seq=len(events)+1,tick=s['tick'],type=kind,input_source='direct',**kw);gr.action(w,s,e);events.append(e)
  def advance_until(predicate):
   for _ in range(3000):
    if predicate():return
    gr.tick(w,s)
    assert not s['caught'],s
   raise AssertionError('unreachable continuation')
  def walk(x):
   direction=1 if x>s['x'] else -1
   act('move',direction=direction);advance_until(lambda:(x-s['x'])*direction<=0);act('move',direction=0)
  def wire(src,dst):act('overlay');act('wire',source=src,target=dst);act('overlay')
  for i,g in enumerate(w['gates']):
   walk(g['x']-64);wire(f's{i}L',g['id']);act('use',source=f's{i}L')
   if i<len(w['gates'])-1:walk(g['x']+100)
  i=len(w['gates'])-1;wire(f's{i}L','lamp');act('use',source=f's{i}L')
  advance_until(lambda:s['gx']>=936);walk(w['item']);act('hide');act('pickup')
  if w['parameters']['alarm']:advance_until(lambda:908<=s['gx']<=916 and s['gd']==1)
  act('hide')
  for i in reversed(range(len(w['gates']))):
   g=w['gates'][i];walk(g['x']+64)
   if not s['gates'][g['id']]:wire(f's{i}R',g['id']);act('use',source=f's{i}R')
   walk(g['x']-64)
  walk(64);act('extract')
  payload=dict(mechanic_id='switchline_heist',task_id=t['task_id'],challenge_id=t['challenge_id'],events=events)
  assert gr.grade(payload,t,p)['passed']
  # The same event types tagged with the other mode cannot pass this task.
  wrong=copy.deepcopy(payload)
  for e in wrong['events']:e['input_source']='proxy'
  assert not gr.grade(wrong,t,p)['passed']

def test_complete_registered_plugin_surface_and_materializer(tmp_path):
 setup=load(B/'shared_scripts/setup_task.py','shsetup')
 materializer=load(B/'tools/materialize_controlled_tasks.py','shmaterializer')
 controls=json.loads((E/'controls.json').read_text())
 materializer.validate_controls(controls,E)
 written=materializer.materialize_environment(E,tmp_path)
 assert len(written)==10
 for d in written:
  spec=json.loads((d/'task.json').read_text());a,t=setup.generate_incubator_candidate(spec,'integrated')
  assert 'seed' not in a and (B/a['asset_manifest']).is_file()
  assert a['control_condition']==t['control_condition']==spec['metadata']['control_condition']
  assert spec['metadata']['source_anchors']==['VGE-022']
  for hook in d.glob('*.sh'):assert hook.stat().st_mode & 0o111
 assert 'switchline_heist_env' in json.loads((B/'benchmark_manifest.json').read_text())['environments']
 assert json.loads((B/'real_time.json').read_text())['environments']['switchline_heist']==controls['real_time']

@pytest.mark.parametrize('slot',range(3))
@pytest.mark.parametrize('malformed',[None, [], ['invalid'], 'invalid', 7, True])
def test_malformed_export_objects_fail_closed(slot,malformed):
 p,t=gen.generate(task(),'malformed-export')
 payload=dict(mechanic_id='switchline_heist',task_id=t['task_id'],challenge_id=t['challenge_id'],
              events=[dict(seq=1,type='extract',tick=0,input_source='direct')])
 args=[payload,t,p];args[slot]=malformed
 assert gr.grade(*args)==dict(graded=True,passed=False,
     feedback='result, ground truth and public state must be objects')

@pytest.mark.parametrize('field',['result','ground_truth','public_state'])
def test_exported_verifier_rejects_malformed_objects(field):
 p,t=gen.generate(task(),'malformed-verifier')
 exported=dict(public_state=p,ground_truth=t,result=dict(
     mechanic_id='switchline_heist',task_id=t['task_id'],challenge_id=t['challenge_id']))
 exported[field]=['invalid']
 verifier=load(E/'tasks/switchline_heist_seed_0001/verifier.py','sh_malformed_verifier')
 def copy_from_env(source,destination):
  Path(destination).write_text(json.dumps(exported))
 result=verifier.verify_task(env_info={'copy_from_env':copy_from_env})
 assert result['passed'] is False and result['score']==0
 assert 'must be objects' in result['feedback']
