import copy
import json
from pathlib import Path
import pytest
from weird_captcha_gym.shared_scripts.incubator_generators import valence_caravan as gen
from weird_captcha_gym.shared_runtime.server.incubator_graders import valence_caravan as grader
ROOT=Path(__file__).resolve().parents[1]/'weird_captcha_gym'

def fixture(level,mode,seed='audit'):
    condition={'difficulty':level,'interaction':mode,'real_time':'live','difficulty_parameters':gen.PROFILES[level]}
    return gen.generate({'id':f'test-{level}-{mode}','_control_condition':condition},seed)

def payload(public,truth):
    state=grader.initial(truth['world']);actions=[]
    for cmd in truth['solution_path']:
        state=grader.advance(truth['world'],state,cmd)
        actions.append({'seq':len(actions)+1,'command':cmd,'source':'keyboard' if truth['control_condition']['interaction']=='full' else 'buttons','state':copy.deepcopy(state)})
    return {k:public[k] for k in ('mechanic_id','task_id','challenge_id')}|{'actions':actions,'final_state':state}

@pytest.mark.parametrize('level',range(1,6))
def test_profiles(level):
    layouts=set()
    for seed in ('alpha','beta','gamma','delta','epsilon'):
        a,b=fixture(level,'full',seed);c,d=fixture(level,'simplified',seed)
        assert a['world']==c['world'] and b['solution_path']==d['solution_path']
        assert gen.generate({'id':a['task_id'],'_control_condition':a['control_condition']},seed)==(a,b)
        layouts.add(json.dumps(a['world'],sort_keys=True))
        state=(tuple(map(tuple,a['world']['positions'])),())
        replay=grader.initial(a['world'])
        for cmd in b['solution_path']:
            state=gen.transition(a['world'],state,cmd);replay=grader.advance(a['world'],replay,cmd)
            assert replay=={'positions':list(map(list,state[0])),'bonds':list(map(list,state[1]))}
        assert gen.solved(a['world'],state)
        if level>=3:assert gen.solve_world({**a['world'],'turntables':[]})[0] is None
        for public,truth in ((a,b),(c,d)):
            p=payload(public,truth);assert grader.grade(p,truth,public)['passed']
            for mutate in ('mode','identity','state','empty','unknown','sequence'):
                q=copy.deepcopy(p)
                if mutate=='mode':q['actions'][0]['source']='buttons' if q['actions'][0]['source']=='keyboard' else 'keyboard'
                if mutate=='identity':q['challenge_id']='stale'
                if mutate=='state':q['actions'][-1]['state']['positions'][0][0]+=1
                if mutate=='empty':q['actions']=[]
                if mutate=='unknown':q['actions'][0]['command']='teleport'
                if mutate=='sequence':q['actions'][0]['seq']=True
                assert not grader.grade(q,truth,public)['passed'],mutate
    assert len(layouts)==5

def test_collision_rigid_body_and_capacity():
    w={'floor':[[x,y] for x in range(4) for y in range(4)],'positions':[[0,0],[1,0],[3,0]],'valences':[1,2,1],'turntables':[[0,0]]}
    s={'positions':[[0,0],[1,0],[3,0]],'bonds':[[0,1]]}
    assert grader.advance(w,s,'N')==s
    assert grader.advance(w,s,'W')==s
    n=grader.advance(w,s,'E');assert n['positions']==[[1,0],[2,0],[3,0]] and grader.complete(w,n)
    assert grader.advance(w,n,'E')==n
    assert grader.advance(w,s,'CW')['positions']==[[0,0],[0,1],[3,0]]

def test_reset_undo_replay():
    a,b=fixture(4,'full');p=payload(a,b);first=copy.deepcopy(p['actions'][0]);reset={'seq':2,'command':'reset','source':'toolbar','state':grader.initial(a['world'])}
    p['actions']=[first,reset]+p['actions']
    for i,e in enumerate(p['actions']):e['seq']=i+1
    assert grader.grade(p,b,a)['passed']

def test_visible_surface_has_terse_prompt_without_progress_or_rules_panel():
    mechanic=(ROOT/'shared_runtime/app/mechanics/valence_caravan.js').read_text()
    styles=(ROOT/'shared_runtime/app/mechanics/valence_caravan.css').read_text()
    assert '<h2>Assemble one body.</h2>' in mechanic
    assert '<p>Complete the chamber.</p>' in mechanic
    for forbidden in ('vc-stat','vc-rule','vc-pad-note','atoms joined','empty slots',
                      'Bonded atoms move together','Touching atoms bond','One bond per pair',
                      'A must be on a turntable','Blocked — the whole body needs room',
                      'Bond formed — your body has changed','Fresh chamber ready',
                      'Assembly incomplete','All slots filled','Find a route'):
        assert forbidden not in mechanic
    assert '.vc-submit.ready' not in styles

def test_baseline_world_and_no_hidden_operation_quota():
    from weird_captcha_gym.tools.materialize_controlled_tasks import controlled_task
    task=json.loads((ROOT/'environments/valence_caravan_env/tasks/valence_caravan_seed_0001/task.json').read_text())
    controls=json.loads((ROOT/'environments/valence_caravan_env/controls.json').read_text())
    for seed in ('alpha','beta','gamma'):
        public,truth=gen.generate(task,seed)
        variant=controlled_task(task,mechanic_id='valence_caravan',level=4,interaction='full',
                                profile=controls['difficulty']['4'],
                                task_dir_name='valence_caravan_d4_full_seed_0001')
        controlled,ct=gen.generate(variant,seed)
        assert public['world']==controlled['world'] and truth['solution_path']==ct['solution_path']
    a,b=fixture(1,'full');p=payload(a,b)
    resets=[{'seq':i+1,'command':'reset','source':'toolbar','state':grader.initial(a['world'])} for i in range(2100)]
    p['actions']=resets+p['actions']
    for i,e in enumerate(p['actions']):e['seq']=i+1
    assert grader.grade(p,b,a)['passed']
