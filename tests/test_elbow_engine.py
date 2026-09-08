import copy
import importlib.util
import json
import math
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]/'weird_captcha_gym'

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
G=load('shared_scripts/incubator_generators/elbow_engine.py','elbow_gen_test')
R=load('shared_runtime/server/incubator_graders/elbow_engine.py','elbow_grade_test')
S=load('tools/incubator_solvers/elbow_engine.py','elbow_solver_test')
E=ROOT/'environments/elbow_engine_env'
BASE=json.loads((E/'tasks/elbow_engine_seed_0001/task.json').read_text())
C=json.loads((E/'controls.json').read_text())

def task(level,mode):
    t=copy.deepcopy(BASE);t['metadata']['control_condition']={'difficulty':level,'interaction':mode,'real_time':'live','difficulty_parameters':C['difficulty'][str(level)]['parameters']};return t

def solution(pub):
    p=pub['physics'];s=pub['initial'];u=0;events=[{'seq':1,'type':'start','tick':0}]
    for tick in range(p['max_ticks']):
        if tick%12==0:
            new=S.choose_torque(s,p,tick)
            if new!=u:
                u=new;events.append({'seq':len(events)+1,'type':'torque','tick':tick,'value':u,'input_source':'held_torque' if (pub.get('control_condition') or {}).get('interaction','full')=='full' else 'latched_torque'})
        s=R.step(s,u*p['torque'],p)
        if R.height(s,p)>p['target_height']:break
    events.append({'seq':len(events)+1,'type':'finish','tick':tick+1,'state':s})
    return {**{k:pub[k] for k in ('mechanic_id','task_id','challenge_id')},'control_condition':pub.get('control_condition'),'events':events,'completed':True}

@pytest.mark.parametrize('level',range(1,6))
@pytest.mark.parametrize('mode',['full','simplified'])
def test_profiles_replay_and_adversarial(level,mode):
    for seed in ['elbow-test-a','elbow-test-b','elbow-test-c']:
        pub,truth=G.generate(task(level,mode),seed)
        assert (pub,truth)==G.generate(task(level,mode),seed)
        pair,_=G.generate(task(level,'simplified' if mode=='full' else 'full'),seed)
        assert pub['physics']==pair['physics'] and pub['initial']==pair['initial']
        payload=solution(pub)
        assert R.grade(payload,truth,pub)['passed']
        for mutation in ['stale','surface','pose','nan','time','unknown','empty','completed','after_terminal']:
            bad=copy.deepcopy(payload)
            if mutation=='stale':bad['challenge_id']='stale'
            if mutation=='surface':bad['events'][1]['input_source']='latched_torque' if mode=='full' else 'held_torque'
            if mutation=='pose':bad['events'][-1]['state'][0]+=.01
            if mutation=='nan':bad['events'][-1]['state'][0]=math.nan
            if mutation=='time':bad['events'][-1]['tick']=-1
            if mutation=='unknown':bad['events'][1]['type']='teleport'
            if mutation=='empty':bad['events']=[]
            if mutation=='completed':bad['events']=bad['events'][:1]
            if mutation=='after_terminal':bad['events'].append({'seq':len(bad['events'])+1,'type':'torque','tick':bad['events'][-1]['tick'],'value':0})
            assert not R.grade(bad,truth,pub)['passed'],mutation


def test_baseline_preserved_and_physical_energy():
    pub,_=G.generate(BASE,'baseline')
    controlled,_=G.generate(task(4,'full'),'baseline')
    assert pub['initial']==controlled['initial'] and pub['physics']==controlled['physics']
    p=pub['physics'];p={**p,'damping':0};s=[.7,-.9,.4,-.3];initial=R.energy(s,p)
    for _ in range(3000):s=R.step(s,0,p)
    assert abs(R.energy(s,p)-initial)<1e-5
    a=R.derivative([0,0,0,0],1,p)
    assert a[2]<0<a[3] # shoulder reaction arises from passive coupling.
    s=[.7,-.9,.4,-.3];initial=R.energy(s,p);p['damping']=.1
    for _ in range(1000):s=R.step(s,0,p)
    assert R.energy(s,p)<initial


def test_exported_verifier_rejects_wrong_surface(tmp_path):
    import shutil
    verifier=load('environments/elbow_engine_env/tasks/elbow_engine_seed_0001/verifier.py','elbow_export_test')
    pub,truth=G.generate(task(4,'simplified'),'export-boundary')
    export={'public_state':pub,'ground_truth':truth,'result':solution(pub)}
    path=tmp_path/'export.json'
    def copy_from_env(source,destination):
        assert source=='/tmp/task_result.json'
        shutil.copyfile(path,destination)
    path.write_text(json.dumps(export))
    assert verifier.verify_task(env_info={'copy_from_env':copy_from_env})['score']==100
    export['result']['events'][1]['input_source']='held_torque'
    path.write_text(json.dumps(export))
    assert verifier.verify_task(env_info={'copy_from_env':copy_from_env})['score']==0


@pytest.mark.parametrize('field', ['result', 'ground_truth', 'public_state'])
@pytest.mark.parametrize('malformed', [[1], 'invalid', 17, True])
def test_exported_verifier_rejects_non_object_contract(tmp_path, field, malformed):
    import shutil
    verifier=load('environments/elbow_engine_env/tasks/elbow_engine_seed_0001/verifier.py','elbow_malformed_export_test')
    pub,truth=G.generate(task(4,'full'),'malformed-export')
    export={'public_state':pub,'ground_truth':truth,'result':solution(pub)}
    export[field]=malformed
    path=tmp_path/'export.json';path.write_text(json.dumps(export))
    def copy_from_env(source,destination):
        shutil.copyfile(path,destination)
    decision=verifier.verify_task(env_info={'copy_from_env':copy_from_env})
    assert decision['passed'] is False and decision['score']==0
    assert 'JSON objects' in decision['feedback']
