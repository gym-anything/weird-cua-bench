"""Original procedural demolition scene; random draws never depend on input mode."""
import copy
import hashlib
import random

MECHANIC_ID='load_bearing_idol'
DEFAULT={'layers':3,'ballast_width':42,'post_width':50,'cradle_width':150,'offset':12}

def generate(task,seed):
    condition=task.get('_control_condition')
    p={**DEFAULT,**((condition or {}).get('difficulty_parameters') or {})}
    rng=random.Random(int(hashlib.sha256(str(seed).encode()).hexdigest()[:16],16))
    shift=rng.randint(-30,30);cx=430+shift;n=int(p['layers']);top=455-30*n
    bodies=[]
    def add(id,kind,x,y,w,h,fixed=False):bodies.append(dict(id=id,kind=kind,x=round(x,4),y=round(y,4),w=w,h=h,fixed=fixed))
    add('floor','floor',430,525,860,30,True)
    add('cradle','cradle',cx,475,p['cradle_width'],40,True)
    for j in range(n):
        offset=min(p['offset'],20) if j==n-1 else p['offset']
        add(f'piece{j}', 'plank' if j==1 else 'chalk',cx+rng.randint(-offset,offset),440-j*30,180,30)
    add('idol','idol',cx+rng.randint(-10,10),top-25,46,50)
    for i,sgn in enumerate([-1,1]):
        post=cx+sgn*160
        add(f'post{i}','iron',post,top+10,p['post_width'],20,True)
        add(f'timber{i}','timber',cx+sgn*230,top-50,38,40)
        add(f'ledge{i}','iron',cx+sgn*145,top-15,170,30)
        add(f'glass{i}','glass',post,top-48,22,36)
        if p['ballast_width'] and i < p.get('ballast_count', 2):
            add(f'weight{i}','chalk',cx+sgn*(82+rng.randint(-3,3)),top-30-p['ballast_width']/2,p['ballast_width'],p['ballast_width'])
    cid=hashlib.sha256(f'{seed}|{task["id"]}|{condition}'.encode()).hexdigest()[:16]
    public=dict(benchmark='weird_captcha_gym',mechanic_id=MECHANIC_ID,task_id=task['id'],challenge_id=cid,prompt='Lower the idol into its cradle. Keep both ampoules on their ledges.',bodies=bodies,quota=n,stage={'width':860,'height':550},generator={'name':'load_bearing_idol_v0','variant_count':1000000},asset_manifest='shared_runtime/assets/provenance/load_bearing_idol_v0.json')
    truth=copy.deepcopy(public);truth['seed']=seed
    if condition:
        public['control_condition']=copy.deepcopy(condition);truth['control_condition']=copy.deepcopy(condition)
    return public,truth
