import copy
import json
from pathlib import Path
import pytest
from weird_captcha_gym.shared_scripts.incubator_generators.long_way_home import generate,PROFILES
from weird_captcha_gym.shared_runtime.server.incubator_graders.long_way_home import grade,inspect


def instance(level,mode,seed):
    w,h,o=PROFILES[level]
    return generate({'id':f'lwh-d{level}-{mode}','_control_condition':{'difficulty':level,'interaction':mode,'difficulty_parameters':{'width':w,'height':h,'openings':o}}},seed)


def solution(p,t):
    mode=t['control_condition']['interaction']
    return dict(mechanic_id='long_way_home',task_id=t['task_id'],challenge_id=t['challenge_id'],interaction=mode,board=t['solution_board'],events=[dict(kind='edit',cell=i,value=v,input_source='brush' if mode=='full' else 'tile_controls') for i,v in enumerate(t['solution_board']) if v!=t['garden']['initial'][i]])


@pytest.mark.parametrize('level',range(1,6))
def test_generation_and_replay(level):
    layouts=set()
    for seed in map(str,range(30)):
        p,t=instance(level,'full',seed);q,u=instance(level,'simplified',seed)
        assert (p,t)==instance(level,'full',seed)
        assert p['garden']==q['garden'] and t['solution_board']==u['solution_board']
        layouts.add(tuple(p['garden']['initial']))
        assert inspect(p['garden']['initial'],p['garden'])['distance']<p['garden']['target']
        for pub,truth in [(p,t),(q,u)]:
            payload=solution(pub,truth);assert grade(payload,truth,pub)['passed']
            bad=copy.deepcopy(payload);bad['challenge_id']='stale';assert not grade(bad,truth,pub)['passed']
            bad=copy.deepcopy(payload);bad['events'][0]['input_source']='tile_controls' if truth==t else 'brush';assert not grade(bad,truth,pub)['passed']
            bad=copy.deepcopy(payload);bad['events']=[];assert not grade(bad,truth,pub)['passed']
            bad=copy.deepcopy(payload);bad['events'][0]['cell']=True;assert not grade(bad,truth,pub)['passed']
            bad=copy.deepcopy(payload);bad['events'].append({'kind':'test','report':{'components':1,'distance':0,'path':[]}});assert not grade(bad,truth,pub)['passed']
    assert len(layouts)>20


def test_bfs_and_disconnected_floor():
    g=dict(width=3,height=3,entrance=0,exit=2)
    r=inspect([0,0,0,1,1,1,0,1,1],g)
    assert r=={'components':2,'distance':2,'path':[0,1,2]}
    assert inspect([0,1,0,1,1,1,1,1,1],g)['distance'] is None


def test_baseline_parameters():
    root=Path(__file__).resolve().parents[1]/'weird_captcha_gym/environments/long_way_home_env'
    c=json.loads((root/'controls.json').read_text());t=json.loads((root/'tasks/long_way_home_seed_0001/task.json').read_text())
    p,g=generate(t,'baseline');w,h,o=PROFILES[3]
    t['_control_condition']={'difficulty':3,'interaction':'full','difficulty_parameters':c['difficulty']['3']['parameters']}
    q,u=generate(t,'baseline');assert p['garden']==q['garden'] and g['solution_board']==u['solution_board']


def test_alternate_geometry_is_accepted():
    # The verifier judges route properties, never equality with the private witness.
    for seed in map(str,range(50)):
        p,t=instance(3,'full',seed);g=t['garden'];original=t['solution_board']
        for i,v in enumerate(original):
            if i in g['locked']+[g['entrance'],g['exit']]:continue
            alternate=original[:];alternate[i]=1-v
            report=inspect(alternate,g)
            if report['components']==1 and report['distance']==g['target']:
                payload=solution(p,t);payload['board']=alternate
                payload['events'].append(dict(kind='edit',cell=i,value=1-v,input_source='brush'))
                assert grade(payload,t,p)['passed'];return
    raise AssertionError('No alternate geometry found in 50 seeds')


def test_full_grader_rejects_disconnected_pocket_and_protected_edits():
    p,t=instance(3,'full','adversarial');g=t['garden'];payload=solution(p,t)
    bad=copy.deepcopy(payload);bad['events'].append(dict(kind='edit',cell=g['entrance'],value=1,input_source='brush'))
    assert not grade(bad,t,p)['passed']
    for i,v in enumerate(t['solution_board']):
        if i in g['locked']+[g['entrance'],g['exit']]:continue
        altered=t['solution_board'][:];altered[i]=1-v
        if inspect(altered,g)['components']>1:
            bad=copy.deepcopy(payload);bad['board']=altered;bad['events'].append(dict(kind='edit',cell=i,value=1-v,input_source='brush'))
            assert not grade(bad,t,p)['passed'];return
    raise AssertionError('Missing disconnected negative case')


def test_exported_verifier_binds_requested_task_and_handles_bad_export(tmp_path):
    import importlib.util
    import shutil
    path=Path(__file__).resolve().parents[1]/'weird_captcha_gym/environments/long_way_home_env/tasks/long_way_home_seed_0001/verifier.py'
    spec=importlib.util.spec_from_file_location('lwh_verifier',path)
    verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
    p,t=instance(3,'full','export-boundary')
    export=tmp_path/'export.json'
    export.write_text(json.dumps({'public_state':p,'ground_truth':t,'result':solution(p,t)}))
    info={'copy_from_env':lambda src,dst:shutil.copyfile(export,dst)}
    assert verifier.verify_task(env_info=info,task_info={'id':t['task_id']})['passed']
    assert not verifier.verify_task(env_info=info,task_info={'id':'another-task'})['passed']
    del p['garden'];del t['garden']
    export.write_text(json.dumps({'public_state':p,'ground_truth':t,'result':solution_board_payload(t)}))
    assert verifier.verify_task(env_info=info)['passed'] is False


def solution_board_payload(t):
    return dict(mechanic_id='long_way_home',task_id=t['task_id'],challenge_id=t['challenge_id'],interaction='full',events=[],board=[])


def test_materialized_condition_tasks_and_split(tmp_path):
    from weird_captcha_gym.tools.materialize_controlled_tasks import controlled_task, materialize_environment
    b=Path(__file__).resolve().parents[1]/'weird_captcha_gym'
    env=b/'environments/long_way_home_env'
    controls=json.loads((env/'controls.json').read_text())
    base=json.loads((env/'tasks/long_way_home_seed_0001/task.json').read_text())
    split=json.loads((b/'splits/long_way_home_split.json').read_text())
    written=materialize_environment(env,tmp_path)
    assert len(written)==10
    assert len(split['variations_tasks'])==20
    assert set(split['variations_tasks'])=={p.name+suffix for p in written for suffix in ('','_tpaused')}
    for folder in written:
        name=folder.name
        task=json.loads((folder/'task.json').read_text());condition=task['metadata']['control_condition']
        expected=controlled_task(base,mechanic_id='long_way_home',level=condition['difficulty'],interaction=condition['interaction'],profile=controls['difficulty'][str(condition['difficulty'])],task_dir_name=name)
        assert task==expected
        for hook in ['setup_task.sh','export_result.sh']:assert (folder/hook).stat().st_mode & 0o111
        assert (folder/'verifier.py').read_bytes()==(env/'tasks/long_way_home_seed_0001/verifier.py').read_bytes()


@pytest.mark.parametrize('mode', ['full', 'simplified'])
def test_browser_rejection_without_replacement_remains_editable(mode):
    """A graded failure without fresh state must not lock the visible editor."""
    playwright = pytest.importorskip('playwright.sync_api')
    from weird_captcha_gym.tools.incubator_solvers.long_way_home import paint
    root = Path(__file__).resolve().parents[1] / 'weird_captcha_gym'
    public, truth = instance(3, mode, 'no-replacement-regression')
    submitted = []
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            context = browser.new_context(viewport={'width': 1280, 'height': 720})
            page = context.new_page()
            page.route('http://127.0.0.1/**', lambda route: route.fulfill(
                content_type='text/html', body='<div id="app"></div>'))

            def certify(route):
                payload = route.request.post_data_json
                result = grade(payload, truth, public)
                submitted.append(payload)
                route.fulfill(json={'ok': True, 'passed': result['passed']})

            page.route('**/result', certify)
            page.goto('http://127.0.0.1/')
            page.add_style_tag(path=str(root / 'shared_runtime/app/mechanics/long_way_home.css'))
            page.add_script_tag(path=str(root / 'shared_runtime/app/mechanics/long_way_home.js'))
            page.evaluate("""state => {
                const app = document.querySelector('#app');
                WeirdCaptchaMechanics.long_way_home.render(state, {
                    app, text: String,
                    setReadout(text, status) {
                        const node = app.querySelector('.readout');
                        node.textContent = text; node.dataset.status = status;
                    }
                });
            }""", public)
            page.locator('#lwh-test').click()
            page.locator('#lwh-certify').click()
            playwright.expect(page.locator('.readout')).to_have_text('FAIL · REVISE & RETRY')
            playwright.expect(page.locator('#lwh-certify')).to_be_enabled()
            assert page.locator('.lwh').get_attribute('data-challenge-id') == public['challenge_id']
            assert submitted[0]['events'][0]['kind'] == 'test'
            for i, value in enumerate(truth['solution_board']):
                if value != truth['garden']['initial'][i]:
                    paint(page, i, value, mode)
            page.locator('#lwh-test').click()
            playwright.expect(page.locator('#lwh-report')).to_have_attribute('data-ok', 'true')
            page.locator('#lwh-certify').click()
            playwright.expect(page.locator('.readout')).to_have_text('PASS')
            # Recovery preserves the previous transcript and appends native edits.
            assert submitted[1]['events'][:len(submitted[0]['events'])] == submitted[0]['events']
            assert submitted[1]['board'] == truth['solution_board']
            context.close()
        finally:
            browser.close()
