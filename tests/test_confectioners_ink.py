from __future__ import annotations
import copy
import importlib.util
import json
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]/'weird_captcha_gym'
ENV=ROOT/'environments/confectioners_ink_env'
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
GEN=load(ROOT/'shared_scripts/incubator_generators/confectioners_ink.py','ink_gen')
GRADE=load(ROOT/'shared_runtime/server/incubator_graders/confectioners_ink.py','ink_grade')
CONTROLS=json.loads((ENV/'controls.json').read_text())
BASE=json.loads((ENV/'tasks/confectioners_ink_seed_0001/task.json').read_text())

def generate(d,mode,seed='test'):
    t=copy.deepcopy(BASE);t['_control_condition']={'difficulty':d,'interaction':mode,'real_time':'live','difficulty_parameters':CONTROLS['difficulty'][str(d)]['parameters']}
    return GEN.generate(t,seed)

def solution(public,truth):
    sim=GRADE.Simulation(public['world']);events=[]
    source='freehand' if (truth.get('control_condition') or {}).get('interaction','full')=='full' else 'vertices'
    for stage,route in enumerate(truth['canonical_routes']):
        sim.advance(stage*sim.w['batch_ticks']+5)
        events.append(dict(type='begin',point=route[0],tick=sim.tick,source=source))
        for a,b in zip(route,route[1:]):
            sim.add(a,b);events.append(dict(type='point',point=b,tick=sim.tick,source=source))
        events.append(dict(type='end',tick=sim.tick,source=source))
    while not(sim.done or sim.lost):sim.step()
    return {**{k:public[k] for k in ['mechanic_id','task_id','challenge_id']},'events':events,'tick':sim.tick,'ink':sim.ink,'waste':sim.waste,'tallies':sim.tallies,'completed':sim.done}

@pytest.mark.parametrize('difficulty',range(1,6))
def test_seeded_world_and_mode_parity(difficulty):
    worlds=[]
    for seed in range(12):
        p,h=generate(difficulty,'full',str(seed));p2,h2=generate(difficulty,'simplified',str(seed))
        assert p['world']==p2['world']==h['world']==h2['world']
        assert (p,h)==generate(difficulty,'full',str(seed))
        assert 'canonical_routes' not in p
        worlds.append(json.dumps(p['world'],sort_keys=True))
    assert len(set(worlds))>=10

def test_baseline_is_exact_profile():
    p,h=GEN.generate(BASE,'baseline');p2,h2=generate(4,'full','baseline')
    assert p['world']==p2['world'] and h['canonical_routes']==h2['canonical_routes']

@pytest.mark.parametrize('difficulty',range(1,6))
@pytest.mark.parametrize('seed',['test','fresh-a','fresh-b'])
def test_reachable_physics_and_replay(difficulty,seed):
    p,h=generate(difficulty,'full',seed);r=solution(p,h)
    assert r['completed'],r
    assert GRADE.grade(r,h,p)['passed']
    for mutation in [dict(challenge_id='stale'),dict(tallies=[{'rose':999}]),dict(events=[]),dict(tick=-1),dict(ink=float('nan'))]:
        bad={**r,**mutation};assert not GRADE.grade(bad,h,p)['passed']
    p2,h2=generate(difficulty,'simplified',seed)
    bad={**r,'challenge_id':p2['challenge_id']}
    assert not GRADE.grade(bad,h2,p2)['passed']
    for e in bad['events']:e['source']='vertices'
    assert GRADE.grade(bad,h2,p2)['passed']

def test_capsule_symmetry_gate_and_paint():
    for a,b in [([0,10],[20,10]),([20,10],[0,10])]:
        g=dict(x=10.,y=7.,vx=0.,vy=2.,colour='rose');GRADE.contact(g,a,b,2)
        assert g['y']==6 and g['vy']==0
        g=dict(x=10.,y=13.,vx=0.,vy=-2.,colour='rose');GRADE.contact(g,a,b,2)
        assert g['y']==14 and g['vy']==0
    g=dict(x=10.,y=7.,vx=0.,vy=2.,colour='rose');GRADE.contact(g,[0,10],[20,10],2,gate='rose');assert g['vy']==2
    GRADE.contact(g,[0,10],[20,10],2,gate='mint',paint='lemon');assert g['vy']==0 and g['colour']=='lemon'

def test_ink_exhaustion_and_unreachable_claim():
    p,h=generate(4,'full');sim=GRADE.Simulation(p['world'])
    assert sim.add([0,80],[900,80]);assert not sim.add([900,80],[0,80]);assert sim.lost
    assert not GRADE.grade({'completed':True},h,p)['passed']


@pytest.mark.parametrize('velocity', [(0., 2.), (0., 0.), (1., -2.)])
def test_exact_center_contact_remains_solid_and_endpoint_order_independent(velocity):
    outcomes=[]
    for a,b in [([0,10],[20,10]),([20,10],[0,10])]:
        g=dict(x=10.,y=10.,vx=velocity[0],vy=velocity[1],colour='rose')
        GRADE.contact(g,a,b,2,paint='mint');outcomes.append(g)
        assert g['colour']=='mint'
        assert (g['x']-10)**2+(g['y']-10)**2 == pytest.approx(16)
    assert outcomes[0]==outcomes[1]


def test_replay_rejects_segments_the_visible_input_cannot_deliver():
    p,h=generate(1,'full')
    events=[dict(type='begin',point=[100,100],tick=0,source='freehand'),
            dict(type='point',point=[100.1,100.1],tick=0,source='freehand')]
    result=GRADE.grade({**{k:p[k] for k in ['mechanic_id','task_id','challenge_id']},'events':events},h,p)
    assert not result['passed']
    assert result['feedback']=='segment below input threshold'


@pytest.mark.parametrize('difficulty', range(1, 6))
@pytest.mark.parametrize('mode', ['full', 'simplified'])
def test_materialized_verifier_uses_installed_runtime_in_isolated_process(tmp_path, difficulty, mode):
    import subprocess
    import sys
    from weird_captcha_gym.tools.materialize_controlled_tasks import materialize_environment

    materialize_environment(ENV, tmp_path / 'separate-output')
    copied = tmp_path / 'separate-output' / ENV.name / 'tasks' / f'confectioners_ink_d{difficulty}_{mode}_seed_0001' / 'verifier.py'
    canonical = ENV / 'tasks/confectioners_ink_seed_0001/verifier.py'
    public, truth = generate(difficulty, mode, 'portable-verifier')
    exported = {'public_state': public, 'ground_truth': truth, 'result': solution(public, truth)}
    artifact = tmp_path / 'export.json'
    artifact.write_text(json.dumps(exported))
    # -I ignores cwd/PYTHONPATH: this must use the installed benchmark package.
    script = r"""
import copy, importlib.util, json, pathlib, shutil, sys
exported = json.loads(pathlib.Path(sys.argv[3]).read_text())
results = []
for verifier_path in sys.argv[1:3]:
    spec = importlib.util.spec_from_file_location('portable_ink', verifier_path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    def verify(payload):
        def copy_from_env(source, destination):
            assert source == '/tmp/task_result.json'
            pathlib.Path(destination).write_text(json.dumps(payload))
        return module.verify_task(env_info={'copy_from_env': copy_from_env})
    accepted = verify(exported)
    forged = copy.deepcopy(exported)
    forged['result']['events'] = []
    forged['result']['server_grade'] = {'passed': True}
    rejected = verify(forged)
    wrong_mode = copy.deepcopy(exported)
    for event in wrong_mode['result']['events']:
        event['source'] = 'vertices' if event['source'] == 'freehand' else 'freehand'
    results.append({'accepted': accepted, 'forged': rejected, 'wrong_mode': verify(wrong_mode), 'missing_callback': module.verify_task()})
print(json.dumps(results))
"""
    run = subprocess.run([sys.executable, '-B', '-I', '-c', script, str(copied), str(canonical), str(artifact)], cwd=tmp_path, capture_output=True, text=True, check=True, timeout=90)
    for result in json.loads(run.stdout):
        assert result['accepted']['passed'] and result['accepted']['score'] == 100
        assert not result['forged']['passed']
        assert not result['wrong_mode']['passed']
        assert result['wrong_mode']['feedback'].endswith('wrong interaction surface')
        assert not result['missing_callback']['passed']
        assert result['missing_callback']['feedback'] == 'copy_from_env unavailable'
