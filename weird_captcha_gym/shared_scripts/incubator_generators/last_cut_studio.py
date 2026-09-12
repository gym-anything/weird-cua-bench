"""Original procedural paper-theatre footage; frame ranges are half open."""
from __future__ import annotations
import copy
import hashlib
import random

MECHANIC_ID = 'last_cut_studio'
PROFILES = {
 1: dict(shots=2, decoys=0, margin=14, budget_slack=32, tolerance=16, double_action=False),
 2: dict(shots=3, decoys=0, margin=9, budget_slack=24, tolerance=10, double_action=False),
 3: dict(shots=3, decoys=1, margin=9, budget_slack=16, tolerance=5, double_action=False),
 4: dict(shots=3, decoys=2, margin=7, budget_slack=12, tolerance=3, double_action=False),
 5: dict(shots=4, decoys=2, margin=7, budget_slack=16, tolerance=2, double_action=True),
}
PALETTE = ['#f1b85b', '#72c6bb', '#e58b9d', '#b7a0e3']

def generate(task, seed):
    condition = copy.deepcopy(task.get('_control_condition') or task.get('metadata', {}).get('control_condition'))
    p = dict(condition['difficulty_parameters']) if condition else dict(PROFILES[4])
    rng = random.Random(int(hashlib.sha256(f'{seed}|{MECHANIC_ID}'.encode()).hexdigest(),16))
    kinds = ['leap','flight','bloom','roll']; rng.shuffle(kinds)
    clips=[]; brief=[]; required=[]
    for i in range(p['shots']):
        a=rng.randint(25,52); duration=rng.randint(32,49)
        b=a+duration*(2 if p['double_action'] else 1)
        c=dict(id=f'take-{i}', kind=kinds[i], color=PALETTE[i], direction=rng.choice([-1,1]),
               start=a, end=b, safe_start=a-p['margin'], safe_end=b+p['margin'],
               frames=b+p['margin']+rng.randint(20,36), cycles=2 if p['double_action'] else 1,
               backdrop=rng.randrange(3))
        clips.append(c);required.append(c['id'])
        brief.append({k:c[k] for k in ['kind','color','direction','cycles']})
    for i in range(p['decoys']):
        c=copy.deepcopy(clips[i]);c['id']=f'alternate-{i}';c['direction']*=-1
        c['start']+=rng.randint(4,12);c['end']+=12;c['safe_start']=c['start']-p['margin'];c['safe_end']=c['end']+p['margin'];c['frames']=c['safe_end']+24
        clips.append(c)
    rng.shuffle(clips)
    for i,c in enumerate(clips):c['label']=f'REEL {chr(65+i)}'
    minimum=sum(c['end']-c['start'] for c in clips if c['id'] in required)
    target=minimum+p['budget_slack']
    identity=dict(mechanic_id=MECHANIC_ID,task_id=task['id'],challenge_id=hashlib.sha256(f'{seed}|{task["id"]}|{p}'.encode()).hexdigest()[:16])
    public={**identity,'benchmark':'weird_captcha_gym','prompt':task.get('natural_language',''),
      'clips':clips,'brief':brief,'fps':20,'target_frames':target,'tolerance':p['tolerance'],
      'submit_label':'EXPORT MONTAGE','asset_manifest':'shared_runtime/assets/provenance/last_cut_studio_v0.json',
      'generator':{'name':'last_cut_studio_v1','variant_count':1000000}}
    truth={**identity,'clips':copy.deepcopy(clips),'required':required,'target_frames':target,'tolerance':p['tolerance'],'seed':seed}
    if condition:
        public['control_condition']=copy.deepcopy(condition);truth['control_condition']=copy.deepcopy(condition)
    return public,truth
