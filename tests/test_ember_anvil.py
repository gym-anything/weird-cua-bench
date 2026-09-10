"""Ember Anvil conservation, reachable generation and adversarial replay."""
import copy
import importlib.util
import json
from pathlib import Path
import pytest
B=Path(__file__).resolve().parents[1]/'weird_captcha_gym'
E=B/'environments/ember_anvil_env'

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
G=load(B/'shared_scripts/incubator_generators/ember_anvil.py','ember_gen')
R=load(B/'shared_runtime/server/incubator_graders/ember_anvil.py','ember_grade')
BASE=json.loads((E/'tasks/ember_anvil_seed_0001/task.json').read_text())
CONTROLS=json.loads((E/'controls.json').read_text())

def task(level,mode):
    t=copy.deepcopy(BASE);t['_control_condition']={'difficulty':level,'interaction':mode,'real_time':'live','difficulty_parameters':CONTROLS['difficulty'][str(level)]['parameters']};return t

def payload(public,truth):
    h=truth['world']['initial'][:];events=[];discarded=0
    def event(typ,source='tool_control',**kw):events.append(dict(seq=len(events)+1,t=len(events)*30,type=typ,input_source=source,**kw))
    for a in truth['solution']:
        event('mode',mode=a['mode']);event('direction',direction=a['direction'])
        h=G.move(h,a['cell'],a['mode'],a['direction'],truth['world']['max_height'])
        discarded+=a['mode']=='split'
        event('strike',source='direct_drag' if truth.get('control_condition',{}).get('interaction')=='full' else 'proxy_click',**a,outcome='split' if a['mode']=='split' else 'moved',heights=h[:])
    event('stamp')
    return {k:public[k] for k in ('mechanic_id','task_id','challenge_id')}|dict(events=events,heights=h,discarded=discarded,reheats=0)

@pytest.mark.parametrize('level',range(1,6))
def test_determinism_pairing_reachability_and_volume(level):
    worlds=set()
    for seed in range(30):
        p,t=G.generate(task(level,'simplified'),str(seed));p2,t2=G.generate(task(level,'full'),str(seed))
        assert p['world']==p2['world'] and t['solution']==t2['solution']
        assert (p,t)==G.generate(task(level,'simplified'),str(seed))
        assert G.connected(p['world']['initial'])
        worlds.add(tuple(p['world']['initial']))
        for public,truth in ((p,t),(p2,t2)):
            result=payload(public,truth)
            assert R.grade(result,truth,public)['passed']
            assert sum(result['heights'])+result['discarded']==sum(public['world']['initial'])
    assert len(worlds)>=25

def test_baseline_preserves_world_and_solution():
    p,t=G.generate(BASE,'baseline');p2,t2=G.generate(task(3,'simplified'),'baseline')
    assert p['world']==p2['world'] and t['solution']==t2['solution']

@pytest.mark.parametrize('attack',['stale','mode','input','heat','volume','discard','reheat','time','nan','post_stamp','silhouette','empty','malformed'])
def test_forgery_rejected(attack):
    p,t=G.generate(task(3,'full'),'adversarial');v=payload(p,t)
    strike=next(e for e in v['events'] if e['type']=='strike')
    if attack=='stale':v['challenge_id']='old'
    elif attack=='mode':strike['mode']='split'
    elif attack=='input':strike['input_source']='proxy_click'
    elif attack=='heat':
        for e in v['events']:e['t']+=100000
    elif attack=='volume':strike['heights'][0]+=1
    elif attack=='discard':v['discarded']+=1
    elif attack=='reheat':v['reheats']+=1
    elif attack=='time':strike['t']=-1
    elif attack=='nan':strike['t']=float('nan')
    elif attack=='post_stamp':v['events'].append(dict(seq=len(v['events'])+1,type='stamp',t=10000,input_source='tool_control'))
    elif attack=='silhouette':v['heights']=[int(bool(x)) for x in v['heights']]
    elif attack=='empty':v['events']=[]
    elif attack=='malformed':v['events']=[None]
    assert not R.grade(v,t,p)['passed']

def test_wrong_mode_transcript_rebound_to_other_challenge_rejected():
    p,t=G.generate(task(3,'full'),'same');p2,t2=G.generate(task(3,'simplified'),'same');v=payload(p,t)
    v.update({k:p2[k] for k in ('task_id','challenge_id')})
    assert not R.grade(v,t2,p2)['passed']

def test_temperature_block_and_reheat_preserve_shape():
    p,t=G.generate(task(3,'simplified'),'heat');v=payload(p,t)
    # Add a legal cold no-op and a full reheat before the untouched solution.
    a=t['solution'][0]
    start=[dict(type='strike',cell=a['cell'],mode='draw',direction=0,outcome='cold',heights=t['world']['initial'],input_source='proxy_click',t=60000),dict(type='transfer',to='forge',input_source='proxy_click',t=60000),dict(type='transfer',to='anvil',input_source='proxy_click',t=62400)]
    for e in v['events']:e['t']+=62400
    v['events']=start+v['events'];v['reheats']=1
    for i,e in enumerate(v['events'],1):e['seq']=i
    assert R.grade(v,t,p)['passed']

def test_legal_wrong_thickness_with_correct_silhouette_fails():
    p,t=G.generate(task(3,'simplified'),'thickness');v=payload(p,t);h=v['heights']
    options=[]
    for i in range(49):
        for d in range(4):
            after=G.move(h,i,'draw',d,t['world']['max_height'])
            if after and after!=h and [bool(x) for x in after]==[bool(x) for x in h]:options.append((i,d,after))
    assert options
    i,d,after=options[0];v['events'].pop()
    def add(typ,source='tool_control',**kw):v['events'].append(dict(seq=len(v['events'])+1,t=len(v['events'])*30,type=typ,input_source=source,**kw))
    add('mode',mode='draw');add('direction',direction=d);add('strike','proxy_click',cell=i,mode='draw',direction=d,outcome='moved',heights=after);add('stamp');v['heights']=after
    decision=R.grade(v,t,p)
    assert not decision['passed'] and 'solid differs' in decision['feedback']
