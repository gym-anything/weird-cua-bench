"""Threshold Grapevine contract checks; automation is not human calibration."""
import copy
import json
import hashlib
import importlib.util
import itertools
import math
import shutil
from pathlib import Path
import pytest
from weird_captcha_gym.shared_scripts.incubator_generators import threshold_grapevine as generator
from weird_captcha_gym.shared_runtime.server.incubator_graders import threshold_grapevine as grader
from weird_captcha_gym.tools.incubator_solvers.threshold_grapevine import scratch_path

ENV=Path(__file__).resolve().parents[1]/'weird_captcha_gym/environments/threshold_grapevine_env'
BASE=json.loads((ENV/'tasks/threshold_grapevine_seed_0001/task.json').read_text())
CONTROLS=json.loads((ENV/'controls.json').read_text())


def task(level,mode):
    t=copy.deepcopy(BASE)
    t['_control_condition']={'difficulty':level,'interaction':mode,'real_time':'live','difficulty_parameters':CONTROLS['difficulty'][str(level)]['parameters']}
    return t


def witness(public,truth):
    w=truth['world'];events=[];time=0;full=(truth.get('control_condition') or {}).get('interaction','full')=='full'
    for stage,repair in enumerate(truth['repairs']):
        edges={tuple(e) for e in w['edges']}
        def log(kind,**extra):events.append(dict(seq=len(events)+1,type=kind,stage=stage,t=time,**extra))
        for edge in repair:
            adding=tuple(edge) not in edges
            path=[[w['nodes'][i]['x'],w['nodes'][i]['y']] for i in edge] if adding else scratch_path(w,edges,edge)
            log('edit',edge=edge,operation='add' if adding else 'cut',input_source='graph_gesture' if full else 'pair_buttons',**({'path':path} if full else {}))
            edges.symmetric_difference_update({tuple(edge)})
        rounds=grader.cascade(w,edges);log('run');time+=len(rounds)*w['round_ms'];log('accept',rounds=rounds)
    return {**{k:public[k] for k in ('mechanic_id','task_id','challenge_id')},'control_condition':public.get('control_condition'),'events':events,'completed':True}


@pytest.mark.parametrize('level',range(1,6))
@pytest.mark.parametrize('seed',['a','b','c','d'])
def test_world_pair_determinism_reachability_and_replay(level,seed):
    p,t=generator.generate(task(level,'full'),seed)
    assert (p,t)==generator.generate(task(level,'full'),seed)
    sp,st=generator.generate(task(level,'simplified'),seed)
    assert sp['world']==p['world'] and st['repairs']==t['repairs']
    for public,truth in [(p,t),(sp,st)]:
        result=witness(public,truth)
        assert grader.grade(result,truth,public)['passed']
        for stage,repair in enumerate(truth['repairs']):
            edges={tuple(e) for e in truth['world']['edges']}^{tuple(e) for e in repair}
            w=truth['world']
            assert generator.cascade(len(w['nodes']),edges,w['seeds'],[n['threshold'] for n in w['nodes']])==grader.cascade(w,edges)
    forged=witness(p,t);forged['control_condition']=sp['control_condition']
    assert not grader.grade(forged,t,p)['passed']
    forged=witness(p,t);forged['events'][0]['input_source']='pair_buttons'
    assert not grader.grade(forged,t,p)['passed']


def test_baseline_preserves_world():
    p,t=generator.generate(BASE,'baseline')
    cp,ct=generator.generate(task(4,'full'),'baseline')
    assert p['world']==cp['world'] and t['repairs']==ct['repairs']


def test_original_baseline_geometry_and_graph_are_frozen():
    public, _ = generator.generate(BASE, 'baseline-preservation')
    digest = hashlib.sha256(json.dumps(public['world'], sort_keys=True).encode()).hexdigest()
    assert digest == '9c80c851acee079e108724a6f883fdfb1ae2498e15383ff118f7b9f3c15315d9'


def point_segment_distance(point, first, second):
    dx, dy = second[0]-first[0], second[1]-first[1]
    t = max(0, min(1, ((point[0]-first[0])*dx+(point[1]-first[1])*dy)/(dx*dx+dy*dy)))
    return math.hypot(point[0]-first[0]-t*dx, point[1]-first[1]-t*dy)


@pytest.mark.parametrize('phase', [-.09, -.06, -.03, 0, .03, .06, .09])
def test_dense_layout_keeps_every_possible_friendship_clear_of_other_faces(phase):
    points = [(430+335*math.cos(a), 235+183*math.sin(a)) for a in generator.portrait_angles(12, phase)]
    for a, b in itertools.combinations(range(12), 2):
        for i, p in enumerate(points):
            if i not in (a, b):
                # 25-unit portrait radius plus 3-unit half-width of fixed lines.
                assert point_segment_distance(p, points[a], points[b]) > 30


def test_materialized_verifiers_load_the_installed_runtime_and_verify_all_ten(tmp_path):
    from weird_captcha_gym.tools.materialize_controlled_tasks import materialize_environment
    paths = materialize_environment(ENV, tmp_path/'controlled')
    assert len(paths) == 10
    for index, path in enumerate(paths):
        controlled = json.loads((path/'task.json').read_text())
        public, truth = generator.generate(controlled, 'materialized-verifier')
        exported = { 'public_state': public, 'ground_truth': truth, 'result': witness(public, truth) }
        result_file = tmp_path/'result.json'
        result_file.write_text(json.dumps(exported))
        spec = importlib.util.spec_from_file_location(f'threshold_materialized_{index}', path/'verifier.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        result = module.verify_task(env_info={'copy_from_env': lambda source, destination: shutil.copyfile(result_file, destination)})
        assert result['passed'] and result['score'] == 100


def test_dilution_can_stop_a_cascade():
    w={'nodes':[{'id':i,'threshold':[2,3]} for i in range(4)],'seeds':[0]}
    assert grader.cascade(w,{(0,1)})[-1]==[0,1]
    assert grader.cascade(w,{(0,1),(1,2)})[-1]==[0]
    assert grader.cascade(w,set())[-1]==[0]  # Isolated people do not auto-adopt.


@pytest.mark.parametrize('tamper',['stale','empty','false_rounds','early','no_run','wrong_gesture','after_terminal','wrong_world','false_stage'])
def test_reject_invalid_claims(tamper):
    p,t=generator.generate(task(4,'full'),'adversarial');r=witness(p,t)
    if tamper=='stale':r['challenge_id']='old'
    elif tamper=='empty':r['events']=[]
    elif tamper=='false_rounds':next(e for e in r['events'] if e['type']=='accept')['rounds']=[[0]]
    elif tamper=='early':next(e for e in r['events'] if e['type']=='accept')['t']=0
    elif tamper=='no_run':next(e for e in r['events'] if e['type']=='run')['type']='reset'
    elif tamper=='wrong_gesture':r['events'][0]['path']=[[0,0],[1,1]]
    elif tamper=='after_terminal':r['events'].append(dict(seq=len(r['events'])+1,type='reset',stage=2,t=99999))
    elif tamper=='wrong_world':p['world']['edit_limit']=99
    elif tamper=='false_stage':r['events'][0]['stage']=1
    assert not grader.grade(r,t,p)['passed']
