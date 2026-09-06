import copy
import importlib.util
import json
import math
import subprocess
import sys
from pathlib import Path
import pytest
B=Path(__file__).resolve().parents[1]/'weird_captcha_gym'
E=B/'environments/waggle_dispatch_env'
def load(path):
    spec=importlib.util.spec_from_file_location(path.stem,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
G=load(B/'shared_scripts/incubator_generators/waggle_dispatch.py')
R=load(B/'shared_runtime/server/incubator_graders/waggle_dispatch.py')
C=json.loads((E/'controls.json').read_text())
T=json.loads((E/'tasks/waggle_dispatch_seed_0001/task.json').read_text())
def task(level,mode):
    t=copy.deepcopy(T);t['_control_condition']={'difficulty':level,'interaction':mode,'real_time':'live','difficulty_parameters':C['difficulty'][str(level)]['parameters']};return t

def solution(p):
    w=p['world'];site=w['sites'][w['target']];duration=math.hypot(site['x'],site['y'])/36*1000;t=0;ev=[]
    for _ in range(6):
        start=t;t+=duration;a=math.atan2(site['x'],-site['y'])-math.radians(R.sun(w,t));ev.append(dict(seq=len(ev),type='dance',start=start,t=t,x=110*math.sin(a),y=-110*math.cos(a),source='comb_drag_hold' if p.get('control_condition',{}).get('interaction','full')=='full' else 'comb_toggle'));t+=w['flight_ms']
    ev.append(dict(seq=len(ev),type='certify',t=t))
    return {**{k:p[k] for k in ('mechanic_id','task_id','challenge_id')},'interaction_mode':p.get('control_condition',{}).get('interaction','full'),'events':ev}

@pytest.mark.parametrize('level',range(1,6))
@pytest.mark.parametrize('mode',['full','simplified'])
def test_profiles(level,mode):
    for seed in range(30):
        p,t=G.generate(task(level,mode),str(seed));assert (p,t)==G.generate(task(level,mode),str(seed))
        assert p['world']==G.generate(task(level,'full'),str(seed))[0]['world']
        w=p['world'];assert all(math.hypot(a['x']-b['x'],a['y']-b['y'])>a['radius']+b['radius']+12 for a in w['sites'] for b in w['sites'] if a!=b)
        payload=solution(p);assert R.grade(payload,t,p)['passed']
        payload['interaction_mode']='full' if mode=='simplified' else 'simplified';assert not R.grade(payload,t,p)['passed']
        payload=solution(p);payload['events'][0]['source']='wrong';assert not R.grade(payload,t,p)['passed']
        payload=solution(p);payload['challenge_id']='stale';assert not R.grade(payload,t,p)['passed']

def test_baseline_and_rejection():
    p,t=G.generate(T,'baseline');assert p['world']==G.generate(task(4,'full'),'baseline')[0]['world']
    good=solution(p)
    for field,value in [('t',float('nan')),('start',-1),('x',True),('y',float('inf'))]:
        bad=copy.deepcopy(good);bad['events'][0][field]=value;assert not R.grade(bad,t,p)['passed']
    bad=copy.deepcopy(good);bad['events']=[dict(seq=0,type='certify',t=0)];assert not R.grade(bad,t,p)['passed']
    bad=copy.deepcopy(good);bad['events'][1]['start']=0;assert not R.grade(bad,t,p)['passed']
    bad=copy.deepcopy(good);bad['events'].append(dict(seq=7,type='recall',t=100000));assert not R.grade(bad,t,p)['passed']

def test_recall_changes_outcome_and_boundary():
    p,t=G.generate(T,'recall');good=solution(p);last=good['events'].pop()['t'];good['events'].extend([dict(seq=6,type='recall',t=last),dict(seq=7,type='certify',t=last)])
    assert not R.grade(good,t,p)['passed']
    w=p['world'];site=w['sites'][w['target']];d=math.hypot(site['x'],site['y']);a=math.atan2(site['x'],-site['y'])
    for offset,hit in [(site['radius']-.01,True),(site['radius']+.01,False)]:
        end=(d+offset)/36*1000;angle=a-math.radians(R.sun(w,end));assert (R.landing(w,0,end,110*math.sin(angle),-110*math.cos(angle))[0]==w['target'])==hit


def test_malformed_containers_are_rejected():
    p,t=G.generate(T,'malformed')
    assert not R.grade(None,t,p)['passed']
    for item in (None,True,3,[],"dance"):
        bad=solution(p);bad['events'][0]=item;assert not R.grade(bad,t,p)['passed']


def test_materialized_verifiers_outside_source_layout(tmp_path):
    from weird_captcha_gym.tools.materialize_controlled_tasks import materialize_environment
    from weird_captcha_gym.shared_scripts.setup_task import generate_task_state

    tasks = materialize_environment(E, tmp_path / 'separate-output')
    assert len(tasks) == 10
    for directory in tasks:
        config = json.loads((directory / 'task.json').read_text())
        public, truth = generate_task_state(config, 'portable-verifier')
        export = {'result': solution(public), 'public_state': public, 'ground_truth': truth}
        assert R.grade(export['result'], truth, public)['passed']
        data_path = tmp_path / 'export.json'
        data_path.write_text(json.dumps(export))
        # Import the copied verifier, not the original source task's verifier.
        # -I excludes cwd/PYTHONPATH: dependencies must be installable imports.
        code = '''
import importlib.util, json, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location('copied', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
export = json.loads(Path(sys.argv[2]).read_text())
def copy_from_env(source, destination):
    assert source == '/tmp/task_result.json'
    Path(destination).write_text(json.dumps(export))
info = {'copy_from_env': copy_from_env}
assert module.verify_task(env_info=info)['passed']
export['result']['challenge_id'] = 'stale'
assert not module.verify_task(env_info=info)['passed']
assert not module.verify_task(env_info={})['passed']
'''
        subprocess.run(
            [sys.executable, '-I', '-B', '-c', code, str(directory / 'verifier.py'), str(data_path)],
            cwd=tmp_path, check=True, capture_output=True, text=True,
        )
