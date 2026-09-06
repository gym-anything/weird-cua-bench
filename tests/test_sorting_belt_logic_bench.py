import copy
import importlib.util
import json
from pathlib import Path
import pytest
B=Path(__file__).resolve().parents[1]/'weird_captcha_gym';M='sorting_belt_logic_bench';E=B/'environments'/f'{M}_env'
def load(path):
    spec=importlib.util.spec_from_file_location(path.stem,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
G=load(B/'shared_scripts/incubator_generators'/f'{M}.py');R=load(B/'shared_runtime/server/incubator_graders'/f'{M}.py');C=json.loads((E/'controls.json').read_text());BASE=json.loads((E/'tasks'/f'{M}_seed_0001/task.json').read_text())
def generated(level=4,mode='full',seed='test'):
    task=copy.deepcopy(BASE);task['_control_condition']={'difficulty':level,'interaction':mode,'difficulty_parameters':C['difficulty'][str(level)]['parameters']};return G.generate(task,seed)
def solution(public,truth):
    events=[]
    def add(action,**v):events.append({'seq':len(events)+1,'type':action,**v})
    source='drag' if (truth.get('control_condition') or {}).get('interaction','full')=='full' else 'click_pair'
    gates={};wires={}
    for g in truth['solution']['gates']:
        add('place',id=g['id'],slot=g['slot'],kind=g['kind'],input_source=source);gates[g['id']]={'slot':g['slot'],'kind':g['kind']}
    for g in truth['solution']['gates']:
        for i,s in enumerate(g['sources']):
            dst=f'{g["id"]}:{i}';add('wire',**{'from':s,'to':dst,'input_source':source});wires[dst]=s
    add('wire',**{'from':truth['solution']['output'],'to':'eject','input_source':source});wires['eject']=truth['solution']['output']
    actual=R.outputs(gates,wires,truth['world']);add('run',outputs=actual,routed=[{'row':i,'eject':actual[i]} for i in truth['world']['batch_order']],elapsed_ms=len(actual)*truth['world']['token_ms']);add('certify')
    return {**{k:truth[k] for k in ['task_id','challenge_id','mechanic_id']},'events':events}
@pytest.mark.parametrize('level',range(1,6))
@pytest.mark.parametrize('mode',['full','simplified'])
def test_seeded_matrix(level,mode):
    worlds=set()
    for seed in range(20):
        p,t=generated(level,mode,str(seed));assert (p,t)==generated(level,mode,str(seed));q,_=generated(level,'simplified' if mode=='full' else 'full',str(seed));assert p['world']==q['world']
        payload=solution(p,t);assert R.grade(payload,t,p)['passed'];worlds.add(json.dumps(p['world']['rows']))
        payload['events'][0]['input_source']='click_pair' if mode=='full' else 'drag';assert not R.grade(payload,t,p)['passed']
    assert len(worlds)>1

def test_baseline_and_adversarial():
    p,t=generated();raw,truth=G.generate(BASE,'test');assert raw['world']==p['world'];assert truth['solution']==t['solution']
    good=solution(p,t)
    for key in ['task_id','challenge_id','mechanic_id']:
        bad=copy.deepcopy(good);bad[key]='stale';assert not R.grade(bad,t,p)['passed']
    for edit in ['short','false_output','no_run','feedback','bad_slot','wrong_pin','extra_event','nan']:
        bad=copy.deepcopy(good)
        if edit=='short':bad['events'][-2]['elapsed_ms']=1
        elif edit=='false_output':bad['events'][-2]['outputs'][0]^=1
        elif edit=='no_run':bad['events']=[{'seq':1,'type':'certify'}]
        elif edit=='feedback':next(e for e in bad['events'] if e['type']=='wire')['from']='g0'
        elif edit=='bad_slot':bad['events'][0]['slot']=-1
        elif edit=='wrong_pin':next(e for e in bad['events'] if e['type']=='wire')['to']='g0:8'
        elif edit=='extra_event':bad['events'].append({'seq':len(bad['events'])+1,'type':'certify'})
        else:bad['events'][-2]['elapsed_ms']=float('nan')
        assert not R.grade(bad,t,p)['passed'],edit
    changed=copy.deepcopy(p);changed['world']['gate_budget']+=1;assert not R.grade(good,t,changed)['passed']

def test_equivalent_circuit_and_repair():
    p,t=generated(1);good=solution(p,t)
    # Commuting inputs is a distinct correct topology; grading is functional.
    wires=[e for e in good['events'] if e['type']=='wire' and e['to']!='eject'];wires[0]['from'],wires[1]['from']=wires[1]['from'],wires[0]['from']
    assert R.grade(good,t,p)['passed']
    assert not R.grade({},t,p)['passed']

def test_materialized_verifier_resolves_installed_benchmark(tmp_path):
    import shutil
    task_dir=E/'tasks'/f'{M}_seed_0001'
    # Exercise the copied file, rather than the original task verifier.
    copied=tmp_path/'conditions'/'tasks'/'condition'
    copied.mkdir(parents=True);shutil.copyfile(task_dir/'verifier.py',copied/'verifier.py')
    verifier=load(copied/'verifier.py');p,t=generated(5,'simplified');payload=solution(p,t)
    exported={'public_state':p,'ground_truth':t,'result':payload}
    def copy_from_env(source,dest):
        assert source=='/tmp/task_result.json'
        Path(dest).write_text(json.dumps(exported))
    assert verifier.verify_task(env_info={'copy_from_env':copy_from_env})['passed']

@pytest.mark.parametrize('level,gate_count',[(4,5),(5,7)])
@pytest.mark.parametrize('mode',['full','simplified'])
def test_smaller_functionally_equivalent_network(level,gate_count,mode):
    # XOR can use OR + NAND + AND instead of four NAND gates. The grader
    # must accept a different topology and reward its smaller component count.
    for seed in range(10):
        public,truth=generated(level,mode,f'alternative-{seed}')
        alternate=copy.deepcopy(truth)
        gates=alternate['solution']['gates']
        remove=set()
        for offset in ([0] if level==4 else [0,4]):
            first,second,third,last=gates[offset:offset+4]
            second.update(kind='OR',sources=first['sources'].copy())
            last.update(kind='AND',sources=[first['id'],second['id']])
            remove.add(third['id'])
        alternate['solution']['gates']=[g for g in gates if g['id'] not in remove]
        payload=solution(public,alternate)
        decision=R.grade(payload,truth,public)
        assert decision['passed'] and decision['gate_count']==gate_count
        assert decision['elegance']>R.grade(solution(public,truth),truth,public)['elegance']

def test_new_sorter_is_outside_immutable_historical_sample():
    from weird_captcha_gym.tools.run_agent_sample import corpus_snapshot, corpus_snapshot_for_tasks
    current,_=corpus_snapshot()
    historical,_=corpus_snapshot_for_tasks([{'environment_path':'benchmarks/weird_captcha_gym/environments/historical_env'}])
    assert any(row['task_spec_id']==BASE['id'] for row in current)
    assert not any(row['task_spec_id']==BASE['id'] for row in historical)
    # Historical-sample membership must not alter a generated task's contract.
    legacy=copy.deepcopy(BASE);legacy['metadata'].pop('legacy_agent_sample_population',None)
    for seed in range(10):
        assert G.generate(BASE,str(seed))==G.generate(legacy,str(seed))

@pytest.mark.parametrize('mode',['full','simplified'])
def test_normal_ui_does_not_grade_or_explain_a_trial(mode):
    """Native construction with a virtual test clock, separate from clock evidence."""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright, expect
    solver=load(B/'tools/incubator_solvers'/f'{M}.py')
    public,truth=generated(4,mode,'normal-surface')
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        try:
            context=browser.new_context(viewport={'width':1280,'height':720})
            page=context.new_page();page.clock.install()
            page.set_content('<main id="app"></main>')
            page.add_script_tag(path=str(B/'shared_runtime/app/mechanics'/f'{M}.js'))
            page.evaluate('''state => {
                const app=document.querySelector('#app');
                const h={app,setReadout(text,status){
                    const node=app.querySelector('.readout');
                    node.textContent=text;node.dataset.status=status;
                }};
                window.WeirdCaptchaMechanics.sorting_belt_logic_bench.render(state,h);
            }''',public)
            assert page.locator('.sb-gate-key,.sb-class.wrong').count()==0
            page.locator('#sb-run').click()
            expect(page.locator('.readout')).to_have_text('FAIL')
            assert 'Unconnected' not in page.locator('#app').inner_text()
            solver.build(page,truth)
            solver.connect(page,'s0','eject',mode)
            page.locator('#sb-run').click();page.clock.run_for(12000)
            expect(page.locator('.readout')).to_have_text('BATCH COMPLETE')
            wrong_poster=page.locator('.sb-poster').inner_html()
            solver.connect(page,truth['solution']['output'],'eject',mode)
            page.locator('#sb-run').click();page.clock.run_for(12000)
            expect(page.locator('.readout')).to_have_text('BATCH COMPLETE')
            assert page.locator('.sb-poster').inner_html()==wrong_poster
            visible=page.locator('#app').inner_text()
            for prohibited in ['✓','✕','MISROUTES','ZERO ERRORS','READY TO','GATE KEY','both inputs','Right-click','Select a class','REPAIR']:
                assert prohibited not in visible
            expect(page.locator('#sb-certify')).to_be_enabled()
            context.close()
        finally:
            browser.close()
