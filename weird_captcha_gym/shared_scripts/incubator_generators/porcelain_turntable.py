"""Original contact-manipulation puzzle grounded in survey XAGT-345."""
import copy,hashlib,math,random
MECHANIC_ID='porcelain_turntable'
BASELINE={'tolerance_degrees':12,'hinge_damping':.25,'settle_speed':.09}
def generate(task,seed):
    condition=copy.deepcopy(task.get('_control_condition') or task.get('metadata',{}).get('control_condition'))
    params=dict(condition['difficulty_parameters'] if condition else BASELINE)
    if set(params)!=set(BASELINE) or not 5<=params['tolerance_degrees']<=40 or not .1<=params['hinge_damping']<=2 or not .04<=params['settle_speed']<=.25:raise ValueError('Unsupported porcelain profile')
    rng=random.Random(int(hashlib.sha256(f'{seed}|{MECHANIC_ID}'.encode()).hexdigest(),16))
    theta=round(rng.uniform(-math.pi,math.pi),6)
    target=theta+rng.choice([-1,1])*rng.uniform(.9,2.7)
    p={'l1':1.2,'l2':1.1,'base_distance':2.15,'radius':.78,'finger_radius':.085,'petal_radius':.14,'spinner_inertia':.32,'torque':1.6,'joint_damping':1.8,'tick_ms':10,'max_ticks':30000,'settle_ticks':80,'target':round(target,6),'tolerance':params['tolerance_degrees']*math.pi/180,'hinge_damping':params['hinge_damping'],'settle_speed':params['settle_speed']}
    # Folded away from the spinner: all generated states are collision free.
    initial=[round(rng.uniform(-1.3,-1.1),6),round(rng.uniform(-.2,.2),6),theta,0,0,0]
    identity={'mechanic_id':MECHANIC_ID,'task_id':task['id'],'challenge_id':hashlib.sha256(f'{seed}|{task["id"]}|{params}'.encode()).hexdigest()[:20]}
    shared={**identity,'physics':p,'initial':initial}
    if condition:shared['control_condition']=condition
    public={**copy.deepcopy(shared),'benchmark':'weird_captcha_gym','prompt':'Settle the painted petal inside the mint sector.','generator':{'name':'porcelain_turntable_v0','variant_count':10**12},'asset_manifest':'shared_runtime/assets/provenance/porcelain_turntable_v0.json'}
    return public,{**copy.deepcopy(shared),'seed':seed}
