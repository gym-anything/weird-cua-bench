import copy
import importlib.util
import itertools
import json
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]/'weird_captcha_gym'
ENV=ROOT/'environments/rayglass_vault_env'

def load(path):
    s=importlib.util.spec_from_file_location(path.stem+'_test',path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

g=load(ROOT/'shared_runtime/server/incubator_graders/rayglass_vault.py')
gen=load(ROOT/'shared_scripts/incubator_generators/rayglass_vault.py')
setup=load(ROOT/'shared_scripts/setup_task.py')

def task(d=4,mode='full'):
    from weird_captcha_gym.tools.materialize_controlled_tasks import controlled_task
    base=json.loads((ENV/'tasks/rayglass_vault_seed_0001/task.json').read_text())
    controls=json.loads((ENV/'controls.json').read_text())
    return controlled_task(base,mechanic_id='rayglass_vault',level=d,interaction=mode,
                           profile=controls['difficulty'][str(d)],
                           task_dir_name=f'rayglass_vault_d{d}_{mode}_seed_0001')

def payload(p,t,beads=None,probes=None):
    mode=(t.get('control_condition') or {}).get('interaction','full');events=[]
    for kind,indices in [('probe',probes or []),('mark',t['beads'] if beads is None else beads)]:
        for i in indices:
            e={'seq':len(events)+1,'type':kind,'index':i,'input_surface':'cabinet_click' if mode=='full' else 'console_button'}
            if mode=='full':
                obj=p['geometry']['ports' if kind=='probe' else 'cells'][i];e['point']=[obj['x'],obj['y']]
            if kind=='probe':e['response']=p['sensor_responses'][i]
            events.append(e)
    marks=set()
    for e in events:
        if e['type']=='mark':
            if e['index'] in marks:marks.remove(e['index'])
            else:marks.add(e['index'])
    return {**{k:t[k] for k in ('mechanic_id','task_id','challenge_id')},'control_condition':copy.deepcopy(t.get('control_condition')),'interaction_mode':mode,'events':events,'marks':sorted(marks)}

def test_manual_example_and_priority():
    # Published 8×8 worked example, independently transcribed from the manual.
    b=[2,4,46,61];sig=g.signature(8,b)
    assert sig[0]==23 and sig[30]==22 and sig[27]==9 and sig[25]=='H'
    assert sig[1:4]==['R','H','R']
    assert g.ray(4,[0,1],0)=='H'  # direct hit wins over entry reflection
    assert g.ray(4,[1],0)=='R'
    assert g.ray(4,[5],0)==15  # one diagonal deflects leftwards
    assert g.ray(4,[4,6],1)=='R'  # two diagonals reverse
    assert g.signature(4,[])==[11,10,9,8,15,14,13,12,3,2,1,0,7,6,5,4]


def test_reciprocity_exhaustive_small_worlds():
    for b in itertools.combinations(range(16),3):
        sig=g.signature(4,b)
        assert all(type(q)!=int or sig[q]==p for p,q in enumerate(sig))


@pytest.mark.parametrize('d',range(1,6))
def test_generation_pairs_and_replay(d):
    for seed in range(30):
        pairs=[setup.generate_task_state(task(d,m),f'rayglass-test-{seed}') for m in ('full','simplified')]
        p,t=pairs[0];q,u=pairs[1]
        assert pairs[0]==setup.generate_task_state(task(d),f'rayglass-test-{seed}')
        assert t['beads']==u['beads'] and p['sensor_responses']==q['sensor_responses']
        assert p['geometry']==q['geometry'] and len(set(t['beads']))==t['bead_count']
        for pp,tt in pairs:
            r=payload(pp,tt,probes=list(range(4*pp['size'])))
            assert g.grade(r,tt,pp)['passed']
            wrong=copy.deepcopy(r);wrong['interaction_mode']='full' if r['interaction_mode']=='simplified' else 'simplified'
            assert not g.grade(wrong,tt,pp)['passed']
        r=payload(p,t);r['task_id']=u['task_id'];r['control_condition']=u['control_condition'];r['interaction_mode']='simplified'
        assert not g.grade(r,u,q)['passed']


def test_original_reproduced_by_baseline():
    original=json.loads((ENV/'tasks/rayglass_vault_seed_0001/task.json').read_text())
    p,t=setup.generate_task_state(original,'reference')
    q,u=setup.generate_task_state(task(),'reference')
    for a,b in [(p,q),(t,u)]:
        for k in ('task_id','control_condition'):a.pop(k,None);b.pop(k,None)
        assert a==b


def test_equivalent_layouts_are_accepted():
    # Four enclosing beads make the fifth's location observationally ambiguous.
    n=8;b=[18,21,42,45,27];other=[18,21,42,45,28]
    assert b!=other and g.signature(n,b)==g.signature(n,other)
    p,t=gen.generate({},'equivalence')
    t.update(size=n,bead_count=5,beads=b);p.update(size=n,bead_count=5,geometry=g.geometry(n),sensor_responses=g.signature(n,b))
    r=payload(p,t,beads=other,probes=[0,7,10])
    result=g.grade(r,t,p)
    assert result['passed'] and result['metrics']['equivalent_layout']


@pytest.mark.parametrize('mutation',['stale','surface','point','response','marks','count','sequence','unknown','nan','bool','empty','condition'])
def test_adversarial(mutation):
    p,t=setup.generate_task_state(task(),'adversary');r=payload(p,t,probes=[0])
    if mutation=='stale':r['challenge_id']='old'
    elif mutation=='surface':r['events'][0]['input_surface']='console_button'
    elif mutation=='point':r['events'][0]['point']=[999,999]
    elif mutation=='response':r['events'][0]['response']='impossible'
    elif mutation=='marks':r['marks']=[]
    elif mutation=='count':r=payload(p,t,beads=t['beads'][:-1])
    elif mutation=='sequence':r['events'][0]['seq']=2
    elif mutation=='unknown':r['events'][0]['type']='win'
    elif mutation=='nan':r['events'][0]['point']=[float('nan'),0]
    elif mutation=='bool':r['events'][0]['index']=False
    elif mutation=='empty':r['events']=[]
    elif mutation=='condition':r['control_condition']['difficulty']=1
    assert not g.grade(r,t,p)['passed']


def test_erase_reprobe_and_efficiency():
    p,t=setup.generate_task_state(task(),'undo');b=t['beads'];r=payload(p,t,beads=[b[0],b[0],*b],probes=[0,0,1])
    result=g.grade(r,t,p);assert result['passed']
    assert result['metrics']['beam_queries']==3 and result['metrics']['unique_queries']==2


def test_rejects_invalid_profiles():
    for level,params in [(0,{}),(4,{'size':7,'bead_count':4})]:
        with pytest.raises(ValueError):gen.generate({'_control_condition':{'difficulty':level,'interaction':'full','difficulty_parameters':params}},'bad')


def test_exported_verifier_rejects_stale_and_accepts_replayed_solution(tmp_path):
    import shutil
    v=load(ENV/'tasks/rayglass_vault_seed_0001/verifier.py')
    p,t=setup.generate_task_state(task(),'export')
    export={'public_state':p,'ground_truth':t,'result':payload(p,t,probes=[0,3])}
    path=tmp_path/'export.json'
    def copy(src,dst):
        assert src=='/tmp/task_result.json';shutil.copyfile(path,dst)
    path.write_text(json.dumps(export))
    assert v.verify_task(env_info={'copy_from_env':copy})['score']==100
    export['result']['challenge_id']='stale';path.write_text(json.dumps(export))
    assert v.verify_task(env_info={'copy_from_env':copy})['passed'] is False


def test_controlled_materialization_deterministic(tmp_path):
    m=load(ROOT/'tools/materialize_controlled_tasks.py')
    first=m.materialize_environment(ENV,tmp_path/'one')
    second=m.materialize_environment(ENV,tmp_path/'two')
    assert len(first)==len(second)==10
    for a,b in zip(first,second):
        assert (a/'task.json').read_bytes()==(b/'task.json').read_bytes()
        assert (a/'setup_task.sh').stat().st_mode & 0o111


def test_native_dropdown_typeahead_handles_numeric_prefixes():
    from playwright.sync_api import sync_playwright
    from weird_captcha_gym.tools.incubator_solvers.rayglass_vault import choose
    # Standalone fixture, isolated headless process and fresh browser context;
    # the task solver itself never installs HTML or sets an option value.
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content('<select id="pick">'+''.join(f'<option value="{i}">{i+1}</option>' for i in range(28))+'</select><button>Next control</button>')
            for index in (27,0,9,1,18,2,11,0,19,20,1,7,26,0,21,10,21,*range(27,-1,-1)):
                choose(page,'#pick',index)
                assert page.locator('#pick').input_value() == str(index)
        finally:
            browser.close()
