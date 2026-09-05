import copy
import json
import math
import importlib.util
import shutil
from pathlib import Path
import pytest
from weird_captcha_gym.shared_scripts.incubator_generators import coordinates_by_another_name as gen
from weird_captcha_gym.shared_runtime.server.incubator_graders import coordinates_by_another_name as grader

ROOT=Path(__file__).resolve().parents[1]/'weird_captcha_gym'
ENV=ROOT/'environments/coordinates_by_another_name_env'
BASE=json.loads((ENV/'tasks/coordinates_by_another_name_seed_0001/task.json').read_text())
CONTROLS=json.loads((ENV/'controls.json').read_text())


def task(level,mode):
    x=copy.deepcopy(BASE)
    x['_control_condition']={'difficulty':level,'interaction':mode,'real_time':'live','difficulty_parameters':CONTROLS['difficulty'][str(level)]['parameters']}
    return x


def tape(public,truth):
    world=truth['world'];opts=grader.options(world);events=[];seen=set();sunk=[]
    mode=truth.get('control_condition',{}).get('interaction','full')
    for ship in truth['fleet']:
        for id_ in ship['cells']:
            c=next(c for c in world['cells'] if c['id']==id_)
            address=[c['band'],c['block'],c['count']]
            for axis,value in enumerate(address):
                index=opts[axis].index(value)
                e={'sequence':len(events)+1,'action':'select','axis':axis,'index':index,'input_source':'rotary_drag' if mode=='full' else 'value_button'}
                if mode=='full':
                    angle=math.radians(max(-209.8,min(29.8,-210+240*index/(len(opts[axis])-1))))
                    e['release']=[84+56*math.cos(angle),84+56*math.sin(angle)]
                    e['start']=[84,84]
                events.append(e)
            seen.add(id_);new=[i for i,s in enumerate(truth['fleet']) if i not in sunk and set(s['cells'])<=seen];sunk+=new
            events.append({'sequence':len(events)+1,'action':'fire','input_source':'fire_button','designation':address,'outcome':'shot','hits':[id_],'sunk':new})
    return {k:truth[k] for k in ['mechanic_id','task_id','challenge_id']}|{'events':events,'final':{'shots':len(seen),'seen':sorted(seen),'sweeps':world['sweeps'],'sunk':sorted(sunk)}}


@pytest.mark.parametrize('level',range(1,6))
def test_generation_pair_geometry_and_replay(level):
    worlds=set()
    for seed in range(30):
        p,g=gen.generate(task(level,'full'),str(seed));q,h=gen.generate(task(level,'simplified'),str(seed))
        assert (p,g)==gen.generate(task(level,'full'),str(seed))
        assert p['world']==q['world'] and g['fleet']==h['fleet']
        cells=p['world']['cells'];assert len({(c['band'],c['block'],c['count']) for c in cells})==len(cells)
        all_ship_cells=[c for s in g['fleet'] for c in s['cells']]
        assert len(all_ship_cells)==len(set(all_ship_cells))
        for ship in g['fleet']:
            coords=[tuple(map(int,c.split(':'))) for c in ship['cells']]
            assert all(abs(a[0]-b[0])+abs(a[1]-b[1])==1 for a,b in zip(coords,coords[1:]))
            assert all(any(c['id']==id_ for c in cells) for id_ in ship['cells'])
        for public,truth in [(p,g),(q,h)]:
            payload=tape(public,truth);assert grader.grade(payload,truth,public)['passed']
            wrong=copy.deepcopy(payload);wrong['events'][0]['input_source']='rotary_drag' if truth is h else 'value_button'
            assert not grader.grade(wrong,truth,public)['passed']
        worlds.add(json.dumps(g['fleet']))
    assert len(worlds)>25


def test_baseline_preservation():
    p,g=gen.generate(BASE,'baseline');q,h=gen.generate(task(2,'full'),'baseline')
    assert p['world']==q['world'] and g['fleet']==h['fleet'] and g['omniscient_min_shots']==h['omniscient_min_shots']


@pytest.mark.parametrize('mutation',['identity','wrong_address','false_hit','no_selectors','fake_geometry','false_final','nan_geometry','boolean_axis','missing_start','stationary_click','outside_start'])
def test_forged_transcripts_rejected(mutation):
    p,g=gen.generate(task(2,'full'),'adversarial');x=tape(p,g)
    if mutation=='identity':x['challenge_id']='stale'
    elif mutation=='wrong_address':x['events'][3]['designation'][0]=99
    elif mutation=='false_hit':x['events'][3]['hits']=[]
    elif mutation=='no_selectors':x['events']=[]
    elif mutation=='fake_geometry':x['events'][0]['release']=[84,84]
    elif mutation=='nan_geometry':x['events'][0]['release']=[float('nan'),84]
    elif mutation=='boolean_axis':x['events'][0]['axis']=False
    elif mutation=='missing_start':del x['events'][0]['start']
    elif mutation=='stationary_click':x['events'][0]['start']=x['events'][0]['release']
    elif mutation=='outside_start':x['events'][0]['start']=[0,0]
    elif mutation=='false_final':x['final']['shots']-=1
    assert not grader.grade(x,g,p)['passed']


def test_materialized_verifiers_replay_exports_outside_repository(tmp_path):
    from weird_captcha_gym.tools.materialize_controlled_tasks import materialize_environment
    from weird_captcha_gym.shared_scripts.setup_task import generate_task_state
    variants=materialize_environment(ENV,tmp_path/'tasks')
    assert len(variants)==10
    for variant in variants:
        configuration=json.loads((variant/'task.json').read_text())
        public,truth=generate_task_state(configuration,'portable-verifier')
        exported={'public_state':public,'ground_truth':truth,'result':tape(public,truth)}
        export_path=tmp_path/'export.json'
        spec=importlib.util.spec_from_file_location('coordinates_portable_verifier',variant/'verifier.py')
        verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
        def copy_from_env(source,destination):
            assert source=='/tmp/task_result.json'
            shutil.copyfile(export_path,destination)
        export_path.write_text(json.dumps(exported))
        result=verifier.verify_task(env_info={'copy_from_env':copy_from_env})
        assert result['passed']
        assert result['score']==grader.grade(exported['result'],truth,public)['score']
        exported['result']['events']=[None]
        export_path.write_text(json.dumps(exported))
        assert not verifier.verify_task(env_info={'copy_from_env':copy_from_env})['passed']


@pytest.mark.parametrize('level',range(1,6))
@pytest.mark.parametrize('mode',['full','simplified'])
def test_unnecessary_shot_lowers_reward_and_claimed_score_is_ignored(level,mode):
    public,truth=gen.generate(task(level,mode),'score-regression')
    efficient=tape(public,truth)
    target=set(efficient['final']['seen'])
    miss=next(c for c in truth['world']['cells'] if c['id'] not in target)
    # Use the normal selector/fire surfaces to add a real miss before solving.
    prefix=copy.deepcopy(efficient['events'][:3])
    address=[miss['band'],miss['block'],miss['count']]
    opts=grader.options(truth['world'])
    for axis,event in enumerate(prefix):
        event['index']=opts[axis].index(address[axis])
        if mode=='full':
            angle=math.radians(-210+240*event['index']/(len(opts[axis])-1))
            event['release']=[84+56*math.cos(angle),84+56*math.sin(angle)]
    prefix.append({'action':'fire','input_source':'fire_button','designation':address,'outcome':'shot','hits':[],'sunk':[]})
    wasteful=copy.deepcopy(efficient)
    wasteful['events']=prefix+wasteful['events']
    for index,event in enumerate(wasteful['events']):event['sequence']=index+1
    wasteful['final']['shots']+=1
    wasteful['final']['seen']=sorted(target|{miss['id']})
    wasteful['score']=100
    wasteful['server_grade']={'passed':True,'score':100}
    better=grader.grade(efficient,truth,public);worse=grader.grade(wasteful,truth,public)
    assert better['passed'] and worse['passed']
    assert 0<worse['score']<better['score']<=100
    assert worse['score']==worse['efficiency_percent']
