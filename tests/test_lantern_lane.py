import copy
import json
from pathlib import Path
import pytest
from weird_captcha_gym.shared_scripts.incubator_generators import lantern_lane as gen
from weird_captcha_gym.shared_runtime.server.incubator_graders import lantern_lane as grader
from weird_captcha_gym.tools.incubator_solvers import lantern_lane as solver

ROOT=Path(__file__).resolve().parents[1]/'weird_captcha_gym/environments/lantern_lane_env'
BASE=json.loads((ROOT/'tasks/lantern_lane_seed_0001/task.json').read_text())
CONTROLS=json.loads((ROOT/'controls.json').read_text())

def task(level,mode):
    t=copy.deepcopy(BASE);t['_control_condition']=dict(difficulty=level,interaction=mode,real_time='live',difficulty_parameters=CONTROLS['difficulty'][str(level)]['parameters']);return t

def reference(public):
    w=public['world'];s=grader.initial(w);events=[]
    mode=(public.get('control_condition') or {}).get('interaction','full')
    while s['status']=='active':
        # One road edit per observation window during town operation.
        while s['tick']==0 or s['tick']%8==0:
            edit=solver.next_action(w,s)
            if edit is None:break
            kind,a,b=edit;source={'road':'road_drag','remove':'road_right_click'} if mode=='full' else {'road':'road_click_pair','remove':'remove_button'}
            e=dict(sequence=len(events)+1,type=kind,tick=s['tick'],a=a,b=b,input_source=source[kind])
            e['accepted']=grader.apply(w,s,e);assert e['accepted'],(len(s['roads']),s['tick'],a,b)
            events.append(e)
            if s['tick']>0:break
        grader.advance(w,s)
    return dict(mechanic_id=gen.MECHANIC_ID,task_id=public['task_id'],challenge_id=public['challenge_id'],interaction_mode=mode,events=events,terminal_tick=s['tick'],final_state=s,completed=s['status']=='delivered')

@pytest.mark.parametrize('level',range(1,6))
@pytest.mark.parametrize('mode',['full','simplified'])
def test_reachable_and_replayed(level,mode):
    for seed in range(8):
        p,t=gen.generate(task(level,mode),str(seed));result=reference(p)
        assert grader.grade(result,t,p)['passed'],(level,mode,seed,result['final_state'])
        forged=copy.deepcopy(result);forged['final_state']['sites'][0]['delivered']+=1
        assert not grader.grade(forged,t,p)['passed']
        forged=copy.deepcopy(result);forged['challenge_id']='stale'
        assert not grader.grade(forged,t,p)['passed']
        forged=copy.deepcopy(result);forged['events'][0]['input_source']='road_click_pair' if mode=='full' else 'road_drag'
        assert not grader.grade(forged,t,p)['passed']
        assert not grader.grade({},t,p)['passed']

@pytest.mark.parametrize('level',range(1,6))
def test_determinism_and_interaction_world(level):
    p,t=gen.generate(task(level,'full'),'paired');p2,t2=gen.generate(task(level,'simplified'),'paired')
    assert p['world']==p2['world'];assert (p,t)==gen.generate(task(level,'full'),'paired')
    if level==4:assert gen.generate(BASE,'paired')[0]['world']==p['world']


def test_occupied_road_deletion_and_entrance_effect():
    p,_=gen.generate(task(1,'full'),'edge');w=p['world'];s=grader.initial(w)
    while (edit:=solver.needed(w,s)) is not None:assert grader.apply(w,s,dict(type='road',a=edit[0],b=edit[1]))
    for _ in range(150):
        grader.advance(w,s)
        moving=next((c for c in s['carts'] if c['remaining']),None)
        if moving:break
    a,b=moving['node'],moving['to'];k=grader.edge(a,b)
    assert grader.apply(w,s,dict(type='remove',a=a,b=b));assert s['roads'][k] is True
    before=moving['remaining'];grader.advance(w,s);assert moving['remaining']==before-1
    for _ in range(w['parameters']['trip_ticks']):grader.advance(w,s)
    assert k not in s['roads']
    h=w['homes'][0]['node'];target=w['sites'][0]['node'];assert grader.apply(w,s,dict(type='orient',a=h,b=h-1))
    assert grader.route(w,s,h,target) is None


def test_idle_overflow_locked_site_and_invalid_input():
    p,_=gen.generate(BASE,'negative');w=p['world'];s=grader.initial(w)
    j=w['parameters']['colors'];n=w['sites'][j]['node'];b=grader.neighbors(w,n)[0]
    assert not grader.apply(w,s,dict(type='road',a=n,b=b))
    assert not grader.apply(w,s,dict(type='road',a=0,b=76))
    while s['status']=='active':grader.advance(w,s)
    assert s['status']=='overflow';assert s['peak_queue']==w['parameters']['queue_limit']+1
