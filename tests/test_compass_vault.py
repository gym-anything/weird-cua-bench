import copy
import importlib.util
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]/'weird_captcha_gym'
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,ROOT/path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
gen=load('shared_scripts/incubator_generators/compass_vault.py','cv_gen')
grader=load('shared_runtime/server/incubator_graders/compass_vault.py','cv_grade')
solver=load('tools/incubator_solvers/compass_vault.py','cv_solver')
def instance(level,mode,seed):
    return gen.generate({'id':'cv_test','_control_condition':{'difficulty':level,'interaction':mode,'difficulty_parameters':{}}},str(seed))
def payload(pub,ops):return {**{k:pub[k] for k in ('mechanic_id','task_id','challenge_id','control_condition')},'operations':ops}
@pytest.mark.parametrize('level',range(1,6))
@pytest.mark.parametrize('mode',['full','simplified'])
def test_profiles_and_perturbation(level,mode):
    for seed in range(12):
        p,t=instance(level,mode,seed);assert (p,t)==instance(level,mode,seed)
        other,_=instance(level,'full' if mode=='simplified' else 'simplified',seed);assert other['world']==p['world']
        ops=solver.plan(p['world'],mode);data=payload(p,ops)
        assert grader.grade(data,t,p)['passed']
        assert not grader.grade(payload(p,[]),t,p)['passed']
        stale=copy.deepcopy(data);stale['challenge_id']='stale';assert not grader.grade(stale,t,p)['passed']
        wrong=copy.deepcopy(data)
        for op in wrong['operations']:
            if op['kind']!='point':op['input_source']='canvas_clicks' if mode=='full' else 'canvas_drag'
        assert not grader.grade(wrong,t,p)['passed']
        invented=copy.deepcopy(data);invented['operations'][0]['a']='x999_1000_0';assert not grader.grade(invented,t,p)['passed']
        shortened=copy.deepcopy(data);shortened['operations']=shortened['operations'][:-1];assert not grader.grade(shortened,t,p)['passed']
def test_intersection_geometry():
    a={'kind':'circle','p':(0,0),'r':5};b={'kind':'circle','p':(6,0),'r':5}
    assert grader.intersections(a,b)==[(3,4),(3,-4)]
    line={'kind':'line','p':(-10,0),'q':(10,0)}
    assert grader.intersections(line,a)==[(-5,0),(5,0)]
    assert grader.intersections(a,dict(a))==[]
def test_reject_wrong_geometric_goal():
    p,t=instance(3,'full',6);ops=solver.plan(p['world']);ops[-1]['a']='g0'
    assert not grader.grade(payload(p,ops),t,p)['passed']

def test_malformed_records_are_failures_not_exceptions():
    p,t=instance(3,'full',0)
    for ops in [[None],[7],['line'],[{'kind':'line','a':[]}]]:
        assert not grader.grade(payload(p,ops),t,p)['passed']

def test_accidental_equilateral_solution_fails_perturbations():
    import math
    p,t=instance(3,'full',2)
    world=copy.deepcopy(p['world']);world['givens']=[[300.,350.],[540.,350.],[420.,350.-120*math.sqrt(3)]]
    p['world']=world;t['world']=copy.deepcopy(world)
    model=grader.Construction(world);ops=[]
    def add(kind,a,b=None):
        op={'kind':kind,'a':a,'input_source':'point_click' if kind=='point' else 'canvas_drag'}
        if b is not None:op['b']=b
        i=len(model.objects);model.apply(op);ops.append(op);return i
    def midpoint(a,b,base):
        i=add('circle',a,b);j=add('circle',b,a);line=add('line',f'x{i}_{j}_0',f'x{i}_{j}_1')
        return f'x{base}_{line}_0'
    ab=midpoint('g0','g1',0);median1=add('line','g2',ab)
    bc=midpoint('g1','g2',1);median2=add('line','g0',bc)
    add('point',f'x{median1}_{median2}_0')
    assert grader.satisfied(world,model), 'centroid must coincide with circumcenter only in this equilateral world'
    assert not grader.grade(payload(p,ops),t,p)['passed']

def test_valid_extra_stroke_reduces_efficiency_without_changing_success():
    p,t=instance(3,'full',1);ops=solver.plan(p['world'])
    ops.append({'kind':'line','a':'g0','b':'g1','input_source':'canvas_drag'})
    grade=grader.grade(payload(p,ops),t,p)
    assert grade['passed'] and grade['moves']==7
    assert grade['score']==pytest.approx(100*6/7,abs=1e-4)

def test_replacing_correct_marker_with_wrong_point_fails():
    p,t=instance(3,'full',1);ops=solver.plan(p['world'])
    ops.append({'kind':'point','a':'g0','input_source':'point_click'})
    assert not grader.grade(payload(p,ops),t,p)['passed']
    ops.append(solver.plan(p['world'])[-1])
    assert grader.grade(payload(p,ops),t,p)['passed']

@pytest.mark.parametrize('level',range(1,6))
def test_completed_construction_survives_visible_given_drag(level):
    p,t=instance(level,'full',1);data=payload(p,solver.plan(p['world']))
    data['displayed_givens']=copy.deepcopy(p['world']['givens'])
    data['displayed_givens'][0][0]+=12
    data['displayed_givens'][0][1]-=8
    result=grader.grade(data,t,p)
    assert result['passed']
    assert '10 geometry checks' in result['feedback']

@pytest.mark.parametrize('level',range(1,6))
@pytest.mark.parametrize('mode',['full','simplified'])
def test_materialized_verifier_from_unrelated_directory(tmp_path,level,mode):
    import json
    import subprocess
    import sys
    from weird_captcha_gym.tools.materialize_controlled_tasks import materialize_environment
    paths=materialize_environment(ROOT/'environments/compass_vault_env',tmp_path/'materialized')
    task_dir=next(p for p in paths if p.name==f'compass_vault_d{level}_{mode}_seed_0001')
    task=json.loads((task_dir/'task.json').read_text())
    public,truth=gen.generate(task,'materialized-verifier-regression')
    exported={'public_state':public,'ground_truth':truth,'result':payload(public,solver.plan(public['world'],mode))}
    export_path=tmp_path/'export.json';export_path.write_text(json.dumps(exported))
    # -I excludes the current directory and PYTHONPATH. Resolve dependencies
    # through the installed benchmark, not the copied task's ancestor folders.
    script='''
import importlib.util,json,shutil,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location("copied_verifier",sys.argv[1])
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
p=Path(sys.argv[2])
def copy_from_env(source,destination):
    assert source=="/tmp/task_result.json"
    shutil.copyfile(p,destination)
valid=v.verify_task(env_info={"copy_from_env":copy_from_env})
data=json.loads(p.read_text());data["result"]["operations"]=[]
data["result"]["server_grade"]={"passed":True,"score":100}
p.write_text(json.dumps(data))
invalid=v.verify_task(env_info={"copy_from_env":copy_from_env})
missing=v.verify_task(env_info={})
print(json.dumps({"valid":valid,"invalid":invalid,"missing":missing}))
'''
    result=subprocess.run([sys.executable,'-I','-c',script,str(task_dir/'verifier.py'),str(export_path)],cwd=tmp_path,capture_output=True,text=True,check=True)
    verdicts=json.loads(result.stdout)
    assert verdicts['valid']['passed'],verdicts
    assert verdicts['valid']['score']==100
    assert not verdicts['invalid']['passed']
    assert not verdicts['missing']['passed']
