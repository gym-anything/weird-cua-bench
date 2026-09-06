"""Comparator contract, adversarial replay and controllability tests."""
import copy
import json
from pathlib import Path
import pytest
from weird_captcha_gym.shared_scripts.setup_task import generate_incubator_candidate
from weird_captcha_gym.shared_runtime.server.incubator_graders.comparator_engine import grade
from weird_captcha_gym.tools.materialize_controlled_tasks import controlled_task
ROOT = Path(__file__).resolve().parents[1]/'weird_captcha_gym'
ENV = ROOT/'environments/comparator_engine_env'
BASE = json.loads((ENV/'tasks/comparator_engine_seed_0001/task.json').read_text())
CONTROLS = json.loads((ENV/'controls.json').read_text())


def task(level,mode):
    return controlled_task(BASE,mechanic_id='comparator_engine',level=level,interaction=mode,
        profile=CONTROLS['difficulty'][str(level)],task_dir_name=f'comparator_engine_d{level}_{mode}_seed_0001')


def transcript(public, truth, actions=None):
    row=[s['id'] for s in public['slides']];target=sorted(row,key=truth['weights'].get)
    manual=truth.get('manual_readings',False)
    cursor=advances=exchanges=0;readings=0 if manual else 1;events=[]
    source='lever_drag' if public.get('control_condition',{}).get('interaction')=='full' else 'button'
    def event(action):
        nonlocal cursor,advances,exchanges,readings
        events.append({'seq':len(events)+1,'type':action,'cursor':cursor,'pair':row[cursor:cursor+2],'input_source':source,
            **({'gesture':{'x0':.5,'y0':.18,'x1':.5,'y1':.87}} if source=='lever_drag' else {})})
        if action=='advance' and advances+exchanges < truth['limits']['levers'] and (manual or readings < truth['limits']['readings']):
            cursor=(cursor+1)%(len(row)-1);advances+=1;readings+=0 if manual else 1
        elif action=='weigh' and manual and readings < truth['limits']['readings']:
            readings+=1
        elif action=='exchange' and advances+exchanges < truth['limits']['levers']:
            row[cursor],row[cursor+1]=row[cursor+1],row[cursor];exchanges+=1
    if actions is None and manual:
        actions=truth['memory_plan']+['seal']
    if actions is None:
        while row!=target:
            if truth['weights'][row[cursor]]>truth['weights'][row[cursor+1]]:event('exchange')
            if row!=target:event('advance')
            assert len(events)<400
        event('seal')
    else:
        for a in actions:event(a)
    return {k:public.get(k) for k in ['mechanic_id','task_id','challenge_id','control_condition']} | {
        'events':events,'final_order':row,'counts':{'advances':advances,'exchanges':exchanges,'readings':readings},
        'completed':row==target and events[-1]['type']=='seal'}


@pytest.mark.parametrize('level',range(1,6))
def test_generated_worlds_and_reachable_profiles(level):
    worlds=set()
    for i in range(40):
        seed=f'comparator-property-{i}'
        pairs=[generate_incubator_candidate(task(level,mode),seed) for mode in ['simplified','full']]
        p,t=pairs[0]; q,u=pairs[1]
        assert (p,t)==generate_incubator_candidate(task(level,'simplified'),seed)
        for key in ['slides','limits','runtime_weights']:assert p[key]==q[key]
        assert p['limits']['readings']<len(p['slides'])*(len(p['slides'])-1)//2
        if t.get('manual_readings'):
            assert t['witness_cost']['readings'] <= p['limits']['readings'] < t['reactive_oracle_readings']
            if t['parameters']['planned_comparisons']:
                assert p['limits']['readings'] < t['pair_cache_oracle_readings']
        else:
            assert t['witness_cost']['advances']+1<=p['limits']['readings']
        for a,b in pairs:assert grade(transcript(a,b),b,a)['passed']
        worlds.add(json.dumps(p['slides'],sort_keys=True))
    assert len(worlds)==40


def test_baseline_preserves_world():
    p,t=generate_incubator_candidate(BASE,'baseline')
    q,u=generate_incubator_candidate(task(1,'simplified'),'baseline')
    for key in ['slides','limits','runtime_weights']:assert p[key]==q[key]
    assert t['weights']==u['weights']


@pytest.mark.parametrize('mode',['simplified','full'])
@pytest.mark.parametrize('level',[1,2,5])
def test_rejects_forged_transcripts(mode,level):
    p,t=generate_incubator_candidate(task(level,mode),'adversarial')
    good=transcript(p,t)
    assert grade(good,t,p)['passed']
    mutations=[lambda x:x.update(challenge_id='stale'),lambda x:x.update(task_id='wrong'),
        lambda x:x.update(events=[]),lambda x:x.update(final_order=list(reversed(x['final_order']))),
        lambda x:x['events'][0].update(input_source='button' if mode=='full' else 'lever_drag'),
        lambda x:x['events'][0].update(seq=True),lambda x:x['events'][0].update(pair=['wrong','ids']),
        lambda x:x['events'].append(x['events'][-1]),lambda x:x['counts'].update(readings=0),
        lambda x:x.update(completed=False),lambda x:x.update(control_condition={})]
    if mode=='full':mutations += [lambda x:x['events'][0]['gesture'].update(y1=.2),lambda x:x['events'][0]['gesture'].update(y1=float('nan'))]
    for change in mutations:
        bad=copy.deepcopy(good);change(bad)
        assert grade(bad,t,p)['passed'] is False
    altered=copy.deepcopy(p);altered['runtime_weights'][next(iter(altered['runtime_weights']))]+=1000
    assert not grade(good,t,altered)['passed']
    assert grade(transcript(p,t,['seal']),t,p)['outcome']=='unsorted_seal'
    assert grade(transcript(p,t,['weigh' if t.get('manual_readings') else 'advance']*(p['limits']['readings']+(1 if t.get('manual_readings') else 0))),t,p)['outcome']=='comparison_exhausted'
    # Odd number of toggles ensures an exhausted attempt does not claim a seal.
    payload=transcript(p,t,['exchange']*(p['limits']['levers']+1));payload['completed']=False
    assert grade(payload,t,p)['outcome']=='lever_exhausted'


@pytest.mark.parametrize('level',range(1,6))
def test_cross_mode_replay_rejected_after_identity_rebinding(level):
    p,t=generate_incubator_candidate(task(level,'simplified'),'pair')
    q,u=generate_incubator_candidate(task(level,'full'),'pair')
    payload=transcript(p,t)
    for key in ['task_id','challenge_id','control_condition']:payload[key]=q[key]
    assert grade(payload,u,q)['feedback']=='wrong interaction input'


def test_serialized_materialization_preserves_baseline():
    p,t=generate_incubator_candidate(BASE,'serialized-world')
    materialized=json.loads(json.dumps(task(1,'simplified'),sort_keys=True))
    q,u=generate_incubator_candidate(materialized,'serialized-world')
    for key in ['slides','limits','runtime_weights']:assert p[key]==q[key]


def test_detached_materialized_verifier(tmp_path):
    import importlib.util, shutil
    from weird_captcha_gym.tools.materialize_controlled_tasks import materialize_environment
    paths=materialize_environment(ENV,tmp_path/'detached')
    for directory in paths:
        p,t=generate_incubator_candidate(json.loads((directory/'task.json').read_text()),'detached')
        result=transcript(p,t)
        exported=tmp_path/'result.json';exported.write_text(json.dumps({'public_state':p,'ground_truth':t,'result':result}))
        spec=importlib.util.spec_from_file_location('detached_comparator_verifier',directory/'verifier.py')
        verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
        def copy_from_env(source,destination):
            assert source=='/tmp/task_result.json';shutil.copyfile(exported,destination)
        assert verifier.verify_task(env_info={'copy_from_env':copy_from_env})['passed']


def test_replay_rejects_boolean_and_noninteger_counters():
    p,t=generate_incubator_candidate(task(1,'simplified'),'typed-counters')
    good=transcript(p,t)
    assert grade(good,t,p)['passed']
    for cursor in (False, 0.0):
        bad=copy.deepcopy(good)
        bad['events'][0]['cursor']=cursor
        assert not grade(bad,t,p)['passed']
    for name in ('advances','exchanges','readings'):
        bad=copy.deepcopy(good)
        bad['counts'][name]=float(bad['counts'][name])
        assert not grade(bad,t,p)['passed']
    bad=copy.deepcopy(good);bad['counts']['unreplayed']=0
    assert not grade(bad,t,p)['passed']


@pytest.mark.parametrize('level',[2,3,4,5])
def test_metered_readings_are_separate_from_travel_and_bind_to_contract(level):
    p,t=generate_incubator_candidate(task(level,'simplified'),'metered-reserves')
    result=transcript(p,t,['weigh']*p['limits']['readings']+['advance','advance','seal'])
    decision=grade(result,t,p)
    assert decision['outcome']=='unsorted_seal'
    assert decision['metrics']['readings']==p['limits']['readings']
    assert decision['metrics']['advances']==2
    altered=copy.deepcopy(p);altered.pop('manual_readings')
    assert not grade(result,t,altered)['passed']
    assert grade(result,t,altered)['outcome']=='invalid_transcript'


def test_uncontrolled_task_cannot_use_the_metered_control():
    p,t=generate_incubator_candidate(BASE,'automatic-original')
    assert grade(transcript(p,t,['weigh','seal']),t,p)['outcome']=='invalid_transcript'


def test_exact_original_uncontrolled_worlds_golden_digest():
    import hashlib
    from weird_captcha_gym.shared_scripts.incubator_generators.comparator_engine import generate
    worlds={str(i):generate(BASE,f'baseline-preservation-{i}') for i in range(100)}
    digest=hashlib.sha256(json.dumps(worlds,sort_keys=True).encode()).hexdigest()
    assert digest=='77dc1e03674ecaf1fe41ac7808b3d02e22e99419fc790b50928950a37690c791'


def test_introductory_metered_profile_has_no_fixed_rank_slot():
    """A tight reading filter must not collapse L2 to one predictable template."""
    orders=set()
    for i in range(200):
        public,truth=generate_incubator_candidate(task(2,'simplified'),f'l2-diversity-{i}')
        ranked=sorted(truth['weights'],key=truth['weights'].get)
        orders.add(tuple(ranked.index(s['id']) for s in public['slides']))
    assert len(orders)>=30
    n=len(next(iter(orders)))
    assert all({order[slot] for order in orders}==set(range(n)) for slot in range(n))
