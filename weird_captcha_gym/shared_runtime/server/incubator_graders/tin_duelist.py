"""Independent integer combat replay; never trusts client health or winner."""
from __future__ import annotations
import copy
MECHANIC_ID='tin_duelist'
MOVES={'jab':dict(start=8,active=4,recovery=16,reach=95,damage=12), 'lunge':dict(start=16,active=4,recovery=26,reach=170,damage=22), 'hammer':dict(start=22,active=4,recovery=30,reach=105,damage=28)}

def initial(world):
    def fighter(x): return dict(x=x,hp=100,move='',age=0,stun=0,guard=False,hit=False)
    return dict(tick=0,player=fighter(world['player_x']),enemy=fighter(world['enemy_x']),direction=0,guard=False,rng=world['policy_seed'],next_decision=12,last_exchange='none',status='active',contacts=[])

def move_data(name, enemy, p):
    m=copy.deepcopy(MOVES[name])
    if enemy:
        m['start']+=p['startup_bonus'];m['recovery']+=p['recovery_bonus']
    return m

def attack(f,name):
    if not f['move'] and not f['stun']:
        f.update(move=name,age=0,hit=False,guard=False)
        return True
    return False

def command(s, name, value):
    if name=='direction':s['direction']=value
    elif name=='guard':s['guard']=value
    else:attack(s['player'],name)

def step(s,w):
    if s['status']!='active':return
    p=w['parameters'];s['tick']+=1
    a,b=s['player'],s['enemy']
    for enemy,f in ((False,a),(True,b)):
        if f['stun']: f['stun']-=1
        if f['move']:
            f['age']+=1;m=move_data(f['move'],enemy,p)
            if f['age']>=m['start']+m['active']+m['recovery']:f.update(move='',age=0)
    a['guard']=bool(s['guard'] and not a['move'] and not a['stun'])
    if not a['move'] and not a['stun'] and not a['guard']:
        a['x']=max(40,min(b['x']-48,a['x']+s['direction']*5))
    b['guard']=False
    gap=b['x']-a['x']-48
    if not b['move'] and not b['stun']:
        # Guard reacts to a visible winding attack, never a future input.
        if p['enemy_guard'] and a['move'] and a['age']<MOVES[a['move']]['start']+MOVES[a['move']]['active'] and gap<=175 and a['move']!='hammer':
            b['guard']=True
        elif s['tick']>=s['next_decision']:
            s['rng']=(s['rng']*25173+13849)%65536
            s['next_decision']=s['tick']+p['decision_ticks']+s['rng']%5
            if gap<=max(MOVES[n]['reach'] for n in p['enemy_moves']):
                choices=[n for n in p['enemy_moves'] if MOVES[n]['reach']>=gap] or ['lunge']
                name=choices[s['rng']%len(choices)]
                if p['adaptive'] and a['guard'] and 'hammer' in choices:name='hammer'
                elif p['adaptive'] and s['last_exchange']=='enemy_miss' and 'jab' in choices and gap<=90:name='jab'
                attack(b,name)
        if not b['move'] and not b['guard']:
            b['x']=max(a['x']+48,min(960,b['x']-p['enemy_speed'] if gap>w['approach_gap']-10 else b['x']))
    # Evaluate both hitboxes before applying damage: trades are symmetric.
    hits=[]
    for enemy,f,target in ((False,a,b),(True,b,a)):
        if not f['move']:continue
        m=move_data(f['move'],enemy,p)
        if m['start']<=f['age']<m['start']+m['active'] and not f['hit']:
            if b['x']-a['x']-48<=m['reach']:
                blocked=target['guard'] and f['move']!='hammer'
                hits.append((enemy,blocked,m['damage'],f['move']))
                f['hit']=True
        if f['age']==m['start']+m['active'] and not f['hit']:
            s['last_exchange']='enemy_miss' if enemy else 'player_miss'
    for enemy,blocked,damage,name in hits:
        target=a if enemy else b
        if not blocked:
            target['hp']=max(0,target['hp']-damage)
            target.update(stun=10,move='',age=0,guard=False)
        target['x']=max(40,min(960,target['x']+(-1 if enemy else 1)*(12 if blocked else 24)))
        s['last_exchange']=('enemy_' if enemy else 'player_')+('block' if blocked else 'hit')
        s['contacts'].append(dict(tick=s['tick'],attacker='enemy' if enemy else 'player',move=name,blocked=blocked,damage=0 if blocked else damage))
    if a['hp']==0 or b['hp']==0 or s['tick']>=p['max_ticks']:
        s['status']='won' if a['hp']>b['hp'] else 'lost'

def grade(payload,truth,public):
    def fail(msg):return dict(graded=True,passed=False,feedback=msg)
    if any(x.get('mechanic_id')!=MECHANIC_ID for x in (payload,truth,public)):return fail('mechanic mismatch')
    for k in ('task_id','challenge_id'):
        if not truth.get(k) or any(x.get(k)!=truth[k] for x in (payload,public)):return fail('stale task or challenge')
    if public.get('world')!=truth.get('world') or public.get('control_condition')!=truth.get('control_condition'):return fail('contract mismatch')
    mode=(truth.get('control_condition') or {}).get('interaction','full')
    source='keyboard' if mode=='full' else 'button'
    if payload.get('interaction_mode')!=mode:return fail('wrong interaction mode')
    events=payload.get('events');end=payload.get('terminal_tick')
    if not isinstance(events,list) or len(events)>12000 or type(end) is not int or not 0<=end<=truth['world']['parameters']['max_ticks']:return fail('malformed transcript')
    s=initial(truth['world'])
    try:
        for n,e in enumerate(events):
            if not isinstance(e,dict) or e.get('seq')!=n+1 or type(e.get('tick')) is not int or not s['tick']<=e['tick']<=end or e.get('input_source')!=source:return fail('invalid event or input surface')
            while s['tick']<e['tick'] and s['status']=='active':step(s,truth['world'])
            if s['status']!='active':return fail('input after terminal state')
            action=e.get('action');v=e.get('value')
            if action=='direction':
                if type(v) is not int or v not in (-1,0,1):return fail('invalid direction')
            elif action=='guard':
                if type(v) is not bool:return fail('invalid guard')
            elif action not in MOVES or v is not None:return fail('invalid move')
            command(s,action,v)
        while s['tick']<end and s['status']=='active':step(s,truth['world'])
    except (KeyError,TypeError,ValueError):return fail('malformed combat data')
    if s!=payload.get('final_state'):return fail('combat replay differs from visible result')
    passed=s['status']=='won' and payload.get('completed') is True
    return dict(graded=True,passed=passed,feedback=f"{'Win' if passed else 'No win'}: health {s['player']['hp']}–{s['enemy']['hp']}; {len(s['contacts'])} contacts replayed")
