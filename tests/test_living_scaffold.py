import copy
import importlib.util
import json
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]/'weird_captcha_gym'

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

g=load(ROOT/'shared_scripts/incubator_generators/living_scaffold.py','ls_gen')
r=g.physics

def task(level=2,mode='full'):
    return {'id':f'ls-d{level}-{mode}','_control_condition':{'difficulty':level,'interaction':mode,'real_time':'live','difficulty_parameters':g.PROFILES[level]}}

def payload(pub,truth):
    mode=(truth.get('control_condition')or{}).get('interaction','full')
    return {**{k:pub.get(k) for k in ('mechanic_id','task_id','challenge_id','control_condition')},'actions':[dict(type='move',creature=i,direction=d,input_source='keyboard' if mode=='full' else 'buttons') for i,d in truth['solution_path']]}

@pytest.mark.parametrize('level',range(1,6))
@pytest.mark.parametrize('seed',['orchid','fern','clover'])
def test_certified_pairs(level,seed):
    full,truth=g.generate(task(level),seed)
    simple,s_truth=g.generate(task(level,'simplified'),seed)
    assert full['board']==simple['board']
    assert full==g.generate(task(level),seed)[0]
    state=r.initial(full['board'])
    assert state==r.settle(full['board'],state[0],state[1])
    for i,d in truth['solution_path']:
        state=r.step(full['board'],state,i,d)
        assert not state[2]
        points=[p for s in state[0] for p in s]
        assert len(points)==len(set(points))
        assert not set(points)&set(map(tuple,full['board']['rocks']))
        assert all(abs(a[0]-b[0])+abs(a[1]-b[1])==1 for s in state[0] for a,b in zip(s,s[1:]))
    assert r.solved(state)
    for p,t in ((full,truth),(simple,s_truth)):
        result=payload(p,t)
        assert r.grade(result,t,p)['passed']
        bad=copy.deepcopy(result);bad['actions'][0]['input_source']='forged';assert not r.grade(bad,t,p)['passed']
        bad=copy.deepcopy(result);bad['challenge_id']='stale';assert not r.grade(bad,t,p)['passed']
        bad=copy.deepcopy(result);bad['actions']=[];bad['completed']=True;assert not r.grade(bad,t,p)['passed']
        bad=copy.deepcopy(result);bad['actions'][0]['creature']=-1;assert not r.grade(bad,t,p)['passed']
        bad=copy.deepcopy(result);bad['actions'][0]['direction']='Q';assert not r.grade(bad,t,p)['passed']
        bad=copy.deepcopy(result);bad['control_condition']=None;assert not r.grade(bad,t,p)['passed']
        assert r.grade({**result,'actions':[{'type':'move','creature':0,'direction':'S','input_source':result['actions'][0]['input_source']},{'type':'reset'}]+result['actions']},t,p)['passed']

def test_support_and_unrecovered_fall():
    b=dict(width=7,height=7,rocks=[[1,5]],creatures=[[[2,4],[1,4]],[[2,3],[1,3]]],food=[[6,0]],exits=[[6,1],[6,2]])
    s=r.initial(b);assert r.settle(b,s[0],s[1])==s
    unsupported=r.settle({**b,'rocks':[]},s[0],s[1]);assert unsupported[2]
    # A ring of mutually supporting bodies is not an anchor to the terrain.
    bodies=(((2,2),(1,2),(1,3)),((2,3),(3,3),(3,2)))
    assert r.settle({**b,'rocks':[]},bodies,s[1])[2]
    # When the lower body exits, its former passenger falls.
    b['food']=[];b['exits'][0]=[2,4]
    assert r.settle(b,r.initial(b)[0],())[0][1]==((2,4),(1,4))

def test_growth_tail_collision_and_undo():
    b=dict(width=7,height=7,rocks=[[x,5] for x in range(7)],creatures=[[[2,3],[2,4],[1,4],[1,3]]],food=[[3,3]],exits=[[6,4]])
    s=r.initial(b)
    assert r.step(b,s,0,'S')==s # neck collision
    nxt=r.step(b,s,0,'W');assert len(nxt[0][0])==4 # may enter vacating tail
    nxt=r.step(b,s,0,'E');assert len(nxt[0][0])==5 and not nxt[1]

def test_baseline_and_variation():
    pub,_=g.generate({'id':'base'},'baseline')
    controlled,_=g.generate(task(2),'baseline')
    assert pub['board']==controlled['board']
    worlds=[g.generate(task(2),str(i))[0]['board'] for i in range(12)]
    assert len({json.dumps(b,sort_keys=True) for b in worlds})>=10
    assert len({json.dumps(b['rocks']) for b in worlds})>=3

def test_materialization_and_external_verifier(tmp_path):
    from weird_captcha_gym.tools.materialize_controlled_tasks import materialize_environment
    paths=materialize_environment(ROOT/'environments/living_scaffold_env',tmp_path)
    assert len(paths)==10
    for directory in paths:
        task_json=json.loads((directory/'task.json').read_text())
        selected={**task_json,'_control_condition':task_json['metadata']['control_condition']}
        pub,truth=g.generate(selected,'materialized-verifier')
        export={'public_state':pub,'ground_truth':truth,'result':payload(pub,truth)}
        exported=tmp_path/'export.json';exported.write_text(json.dumps(export))
        verifier=load(directory/'verifier.py','ls_external_verifier')
        import shutil
        result=verifier.verify_task(env_info={'copy_from_env':lambda src,dst:shutil.copyfile(exported,dst)})
        assert result['passed'],result


@pytest.mark.parametrize('direction', [[], {}, None, True, 1, ['N']])
def test_malformed_direction_rejected_by_grader_and_verifier(tmp_path, direction):
    pub, truth = g.generate(task(), 'malformed-direction')
    result = payload(pub, truth)
    result['actions'][0]['direction'] = direction
    direct = r.grade(result, truth, pub)
    assert direct['graded'] and not direct['passed'] and direct['score'] == 0
    exported = tmp_path / 'export.json'
    exported.write_text(json.dumps({'result': result, 'ground_truth': truth, 'public_state': pub}))
    verifier = load(ROOT / 'environments/living_scaffold_env/tasks/living_scaffold_seed_0001/verifier.py', 'ls_malformed_verifier')
    import shutil
    decision = verifier.verify_task(env_info={'copy_from_env': lambda src, dst: shutil.copyfile(exported, dst)})
    assert not decision['passed'] and decision['score'] == 0
